#!/usr/bin/env python
# -*- coding: utf-8 -*-
import typing

from flask import redirect
from flask_security import current_user
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError

from api.controller import check_sources_by_id
from db import insert_or_ignore
from db.models.activities import Data, Source, SourceUser, Tag, TagUser, TagSet, TagSetUser, TagTagSet, Tagging, Time, Type
from db.models.brain import Prediction
from flask_modules.database import db
from . import defaults

_best_models_for_user_sql = text('''
SELECT id FROM (
SELECT DISTINCT ON (tagset_id, sources)
    model.id, model.score, model.trained_ts, model.tagset_id, jsonb_agg(DISTINCT src_mdl.source_id ORDER BY src_mdl.source_id) AS sources
FROM activity.model AS model
JOIN activity.source_model AS src_mdl ON src_mdl.model_id = model.id
JOIN activity.model_user AS model_user ON model_user.model_id = model.id
WHERE model_user.user_id = :user_id 
GROUP BY model.tagset_id, model.id, model.score, model.trained_ts
ORDER BY model.tagset_id, sources, score DESC, model.trained_ts DESC) AS best_models''')


def source_to_json(source: Source):
    return dict(
        id=source.id,
        type=source.type,
        uri=source.uri,
        slug=source.slug)


def tagset_to_json(tagset: TagSet):
    return dict(
        id=tagset.id,
        title=tagset.title,
        tags=[tag.tag for tag in tagset.tags])


def generic_parser(data: Data) -> dict:
    # todo for large amount of rows this is very inefficient
    return dict(
        text=data.text.text if data.text else "",
        source=dict(id=data.source.id,
                    type=data.source.type,
                    uri=data.source.uri,
                    slug=data.source.slug),
        tags=[tag.tag for tag in data.tags],
        created_time=data.time.time.isoformat() if data.time else '1970-01-01T00:00:00+00:00',
        language=data.language.language.name if data.language else 'un',
        prediction=dict(
            (prediction.model.tags.filter_by(id=k).one().tag, v)
            for prediction in data.predictions.filter(
                Prediction.model_id.in_(_best_models_for_user_sql.bindparams(user_id=current_user.id)))
            for k, v in prediction.prediction)
        if data.predictions else dict())


_parsers = {
    Type.facebook: lambda data: dict(
        id=data.data['id'],
        user=data.data.get('from'),
        **generic_parser(data)
    ),
    Type.twitter: lambda data: dict(
        id=data.data['id_str'],
        user=dict(id=data.data['user']['screen_name'], name=data.data['user']['name']),
        **generic_parser(data)
    ),
    Type.twitter_dm: lambda data: dict(
        id=data.data['id'],
        user=dict(id=data.data['message_create']['sender_id'], name=data.data['message_create']['sender_id']),
        **generic_parser(data)
    ),
    Type.crunchbase: lambda _: None,
    Type.generic: lambda data: dict(
        id=str(data.data['comment_id']),
        user=dict(id=str(data.data['user']['id']), name=data.data['user']['id']),
        **generic_parser(data)
    ),
}


def parser(data: Data) -> dict:
    return _parsers[Type(data.source.type)](data)


@defaults
def source_ids_get(source_ids: list = None,
                   count: int = None,
                   max_id: str = None,
                   random: bool = False,
                   since: str = None,
                   until: str = None,
                   tagset_ids: list = None) -> typing.Union[dict, tuple]:
    error = check_sources_by_id(set(source_ids))
    if error:
        return error

    # data_query = db.session.query(Data)
    # if random:
    #     data_query = data_query.filter(
    #         Data.id.in_(db.select([func.activity.random_rows(count, 0.6, '{de, en}', source_ids)])))
    # else:
    #     data_query = data_query.filter(Data.source_id.in_(source_ids)).order_by(Data.object_id)
    data_query = (db.session
                  .query(Data)
                  .filter(Data.source_id.in_(source_ids))
                  .join(Time, Time.data_id == Data.id))

    if max_id:
        data_query = data_query.filter(Data.object_id < max_id)

    if since or until:
        if since:
            data_query = data_query.filter(Time.time >= since)
        if until:
            data_query = data_query.filter(Time.time <= until)

    if tagset_ids:
        data_query = (data_query
                      .join(Tagging, Tagging.data_id == Data.id)
                      .join(TagTagSet, TagTagSet.tag_id == Tagging.tag_id)
                      .filter(TagTagSet.tagset_id.in_(tuple(tagset_ids))))

    if random:
        data_query = data_query.order_by(db.func.random())
    else:
        data_query = data_query.order_by(Time.time.desc())

    data_query = data_query.limit(count)

    data = [parser(data) for data in data_query]
    return dict(activities=list(data))


@defaults
def source_id_activity_id_get(source_id: int, activity_id: str, _internal=False) -> typing.Union[dict, tuple, Data]:
    data = current_user.data.filter_by(source_id=source_id, object_id=activity_id).one_or_none()
    if not data:
        return dict(error='No activity found for user and %d -> %s' % (source_id, activity_id)), 404
    if _internal:
        return data
    return parser(data)


@defaults
def source_id_activity_id_field_id_get(source_id: int, activity_id: str, field_id: str) -> typing.Union[dict, tuple]:
    activity = source_id_activity_id_get(source_id, activity_id)
    if isinstance(activity, tuple):  # error
        return activity
    return {'id': activity_id, field_id: activity.get(field_id, None)}


@defaults
def source_id_activity_id_tags_patch(source_id: int, activity_id: str, body: dict) -> typing.Union[dict, tuple]:
    remove = tuple(set(body.get('remove', [])))
    add = tuple(set(body.get('add', [])))

    if add or remove:
        sql = text("""
            BEGIN;
            
            INSERT INTO %(tagging_table)s (tag_id, data_id, tagging_ts)
            SELECT tag.id as tag_id, data.id as data_id, now() as tagging_ts
            FROM %(tag_table)s as tag
            INNER JOIN %(data_table)s as data ON data.object_id = :object_id   -- correct data id
            INNER JOIN %(source_user_table)s as source_user ON data.source_id = source_user.source_id AND source_user.user_id = :user_id  -- data belongs to user
            INNER JOIN %(tag_user_table)s as tag_user ON tag.id = tag_user.tag_id AND tag_user.user_id = :user_id  -- tag belongs to user
            WHERE tag.tag in :add
            ON CONFLICT DO NOTHING;
            
            DELETE FROM %(tagging_table)s as tagging
            USING %(tag_user_table)s as tag_user,
                  %(tag_table)s as tag, 
                  %(data_table)s as data,  
                  %(source_user_table)s as source_user
            WHERE tag.tag in :remove AND
                  tag.id = tag_user.tag_id AND tag_user.user_id = :user_id AND  -- tag belongs to user
                  data.object_id = :object_id AND  -- correct data id
                  data.source_id = source_user.source_id AND source_user.user_id = :user_id AND  -- data belongs to user
                  tagging.tag_id = tag.id AND 
                  tagging.data_id = data.id;
            
            COMMIT;
            """ % dict(tagging_table=Tagging.__table__.fullname,
                       tag_table=Tag.__table__.fullname,
                       tag_user_table=TagUser.__table__.fullname,
                       data_table=Data.__table__.fullname,
                       source_user_table=SourceUser.__table__.fullname))
        db.engine.execute(sql,
                          object_id=activity_id,
                          user_id=current_user.id,
                          add=add or tuple([None]),
                          remove=remove or tuple([None]))

    data = source_id_activity_id_get(source_id, activity_id, _internal=True)  # type: Data
    if isinstance(data, tuple):  # error
        return data
    return {'id': activity_id, 'tags': [tag.tag for tag in data.tags]}


@defaults
def source_id_activity_id_put(source_id: int,
                              activity_id: str,
                              activity_import: dict,
                              commit=True) -> typing.Union[dict, tuple]:
    if ('source_id' in activity_import and source_id != activity_import['source_id']) or (
                    'id' in activity_import and activity_id != activity_import['id']):
        db.session.rollback()
        return dict(error="source_id does not match activity"), 400

    err = check_sources_by_id({source_id})
    if err:
        db.session.rollback()
        return err

    insert_or_ignore(db.session,
                     Data(source_id=source_id,
                          object_id=activity_id,
                          data=activity_import['data']))
    # insert_or_update(db.session,
    #                  Data(source_id=source_id,
    #                       object_id=activity_id,
    #                       data=activity_import['data']),
    #                  'source_id, object_id')
    commit and db.session.commit()


@defaults
def source_id_activity_id_delete(source_id: int, activity_id: str, commit=True) -> typing.Union[dict, tuple]:
    # directly deleting from current_user relationship has a glitch :(
    err = check_sources_by_id({source_id})
    if err:
        return err
    db.session.query(Data).filter_by(source_id=source_id, object_id=activity_id).delete()
    commit and db.session.commit()


@defaults
def root_post(import_activities: dict) -> typing.Union[dict, tuple]:
    ids = set()
    for activity in import_activities['activities']:
        if 'id' not in activity:
            activity['id'] = hash(activity['data'])
        if 'source_id' not in activity:
            return dict(error='no source_id found for ' + activity['id']), 400
        ids.add((activity['source_id'], activity['id']))
        err = source_id_activity_id_put(activity['source_id'], activity['id'], activity, False)
        if err:
            db.session.rollback()
            return err
    db.session.commit()
    return dict(activities=[dict(id=activity_id, source_id=source_id) for source_id, activity_id in ids]), 201


@defaults
def sources_get() -> dict:
    return dict(sources=[source_to_json(source) for source in current_user.sources.all()])


@defaults
def sources_post(source: dict) -> typing.Union[dict, tuple]:
    if 'id' in source:
        return dict(error='id not allowed, will be assigned'), 400

    source_entry = Source(type=source['type'],
                          uri=source['uri'],
                          slug=source['slug'])
    current_user.sources.append(source_entry)
    db.session.commit()
    return redirect('/sources/%d' % source_entry.id, code=201)


@defaults
def sources_source_id_get(source_id: int) -> typing.Union[dict, tuple]:
    source = current_user.sources.filter_by(id=source_id).one_or_none()
    return (dict(id=source.id,
                 type=source.type,
                 uri=source.uri,
                 slug=source.slug), 200) if source else \
        (dict(error="source does not exist"), 404)


@defaults
def sources_source_id_patch(source_id: int, source: dict) -> typing.Union[dict, tuple]:
    user_source = current_user.sources.filter_by(id=source_id).one_or_none()
    if user_source is None:
        return dict(error="source does not exist"), 404
    if 'id' in source:
        return dict(error="source id cannot be changed!"), 403
    if 'type' in source:
        return dict(error="type cannot be changed!"), 403
    if 'uri' in source:
        user_source.uri = source['uri']
    if 'slug' in source:
        user_source.uri = source['slug']
    db.session.commit()


@defaults
def sources_source_id_delete(source_id: int) -> dict:
    current_user.sources.filter_by(id=source_id).delete()
    db.session.commit()


@defaults
def tags_get(with_count: bool = False) -> dict:
    tags = dict(tags=[tag.tag for tag in current_user.tags])
    if with_count:
        tags['counts'] = dict((tag.tag, tag.data.count()) for tag in current_user.tags)
    return tags


@defaults
def source_ids_tags_get(source_ids: list, with_count: bool = True) -> typing.Union[dict, tuple]:
    error = check_sources_by_id(set(source_ids))
    if error:
        return error
    current_user.sources.filter(Source.id.in_(source_ids))
    tags = dict()
    tags['counts'] = dict((t, c) for t, c in
                          ((tag.tag, tag.data.filter(Data.source_id.in_(source_ids)).count()) for tag in
                           current_user.tags)
                          if c > 0)
    tags['tags'] = list(tags['counts'].keys())
    if not with_count:
        del (tags['counts'])
    return tags


@defaults
def tags_tag_get(tag: str, with_count: bool = False) -> typing.Union[dict, tuple]:
    the_tag = current_user.tags.filter_by(tag=tag).one_or_none()
    if the_tag is None:
        return dict(error="Tag not found"), 404

    result = dict(tag=the_tag.tag)
    if with_count:
        result['count'] = the_tag.data.count()
    return result


@defaults
def tags_tag_put(tag: str, commit=True) -> dict:
    tag = Tag(tag=tag, created_by_user_id=current_user.id)
    try:
        tag.user.append(current_user)
        db.session.add(tag)
        commit and db.session.commit()
    except IntegrityError as err:
        pass
    return dict(tag=tag.tag), 201


@defaults
def tags_tag_delete(tag: str) -> dict:
    # current_user.tags.filter_by(tag=tag).delete() << not working
    current_user.created_tags.filter_by(tag=tag).delete()
    db.session.commit()


@defaults
def source_ids_tags_tag_activities_get(source_ids: list, tag: str, count: int = 10, random=False) -> dict:
    data_query = (db.session.query(Data)
                  .join(Source,
                        (Data.source_id == Source.id) &
                        (Source.id.in_(source_ids)) &
                        (Source.id.in_(current_user.sources.with_entities(Source.id))))
                  .join(Tagging, Data.id == Tagging.data_id)
                  .join(Tag, Tag.user.any(id=current_user.id) & (Tag.tag == tag) & (Tag.id == Tagging.tag_id)))

    if random:  # todo: order_by random a bit inefficient
        data_query = data_query.from_self().order_by(func.random())

    data_query = data_query.limit(count)
    data = [parser(data) for data in data_query]
    return dict(activities=list(data))


@defaults
def tags_tag_activities_get(tag: str, count: int = 10, random=False) -> dict:
    return source_ids_tags_tag_activities_get(current_user.sources.with_entities(Source.id),
                                              tag=tag,
                                              count=count,
                                              random=random)


@defaults
def source_ids_tagsets_tagset_id_activities_get(source_ids: list, tagset_id: int, count: int = 10,
                                                random=False) -> dict:
    tag_id_query = (db.session.query(TagTagSet.tag_id)
                    .join(TagSetUser, (TagSetUser.user_id == current_user.id) &
                          (TagSetUser.tagset_id == TagTagSet.tagset_id))
                    .filter(TagTagSet.tagset_id == tagset_id))
    data_query = (db.session.query(Data)
                  .distinct(Data.id)
                  .join(Source,
                        (Data.source_id == Source.id) &
                        (Source.id.in_(source_ids)) &
                        (Source.id.in_(current_user.sources.with_entities(Source.id))))
                  .join(Tagging, (Data.id == Tagging.data_id) & (Tagging.tag_id.in_(tag_id_query))))

    if random:  # todo: order_by random a bit inefficient
        data_query = data_query.from_self().order_by(func.random())

    data_query = data_query.limit(count)
    data = [parser(data) for data in data_query]
    return dict(activities=list(data))


@defaults
def tagsets_tagset_id_activities_get(tagset_id: int, count: int = 10, random=False) -> dict:
    return source_ids_tagsets_tagset_id_activities_get(current_user.sources.with_entities(Source.id),
                                                       tagset_id=tagset_id,
                                                       count=count,
                                                       random=random)


@defaults
def tagsets_get() -> dict:
    tagsets = [tagset_to_json(tagset) for tagset in current_user.tagsets]
    return dict(tagSets=tagsets)


@defaults
def tagsets_post(tagset: dict):
    tags = set(tagset['tags'])
    for tag in tags:  # make sure all tags are in DB
        tags_tag_put(tag, commit=False)
    tagset = TagSet(title=tagset['title'])
    tagset.tags.update(db.session.query(Tag).filter(Tag.user.any(id=current_user.id) & Tag.tag.in_(tags)))
    current_user.tagsets.append(tagset)
    db.session.commit()
    return redirect('/tagset/%d' % tagset.id, code=201)


@defaults
def tagsets_tagset_id_get(tagset_id: int) -> typing.Union[dict, tuple]:
    tagset = current_user.tagsets.filter_by(id=tagset_id).one_or_none()
    return dict(id=tagset.id,
                title=tagset.title,
                tags=[tag.tag for tag in tagset.tags]) if tagset else dict(error="tagset does not exist"), 404


@defaults
def tagsets_tagset_id_patch(tagset_id: int, tagset: dict) -> typing.Union[dict, tuple]:
    user_tagset = current_user.tagsets.filter_by(id=tagset_id).one_or_none()
    if user_tagset is None:
        return dict(error="tagset does not exist"), 404
    if 'id' in tagset:
        return dict(error="tagset id cannot be changed!"), 403
    if 'title' in tagset:
        user_tagset.title = tagset['title']
    if 'tags' in tagset:
        tags = set(tagset['tags'])
        for tag in tags:  # make sure all tags are in DB
            tags_tag_put(tag, commit=False)
        user_tagset.tags.update(
            db.session.query(Tag).filter(Tag.user.any(id=current_user.id)).filter(Tag.tag.in_(tags)))
    db.session.commit()
    if user_tagset:
        return dict(id=user_tagset.id,
                    title=user_tagset.title,
                    tags=[tag.tag for tag in user_tagset.tags]), 200
    else:
        return dict(error="tagset does not exist"), 404


@defaults
def tagsets_tagset_id_delete(tagset_id: int) -> dict:
    current_user.tagsets.filter_by(id=tagset_id).delete()
    db.session.commit()


@defaults
def tagsets_tagset_id_tag_delete(tagset_id: int, tag: str) -> typing.Union[dict, tuple]:
    tagset = current_user.tagsets.filter_by(id=tagset_id).one_or_none()
    if tagset is None:
        return dict(error="tagset does not exist"), 404
    tagset.tags.discard(db.session.query(Tag).filter(Tag.user.any(id=current_user.id) & (Tag.tag == tag)).one_or_none())
    db.session.commit()


@defaults
def tagsets_tagset_id_tag_put(tagset_id: int, tag: str) -> typing.Union[dict, tuple]:
    tagset = current_user.tagsets.filter_by(id=tagset_id).one_or_none()
    if tagset is None:
        return dict(error="tagset does not exist"), 404
    tags_tag_put(tag, commit=False)
    tagset.tags.update(db.session.query(Tag).filter(Tag.user.any(id=current_user.id) & (Tag.tag == tag)))
    db.session.commit()
