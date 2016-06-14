#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sqlalchemy.sql import text, func

from db import insert_or_ignore
from db.models.facebook import FacebookCommentEntry

from web.model.tags import UserToTagToComment
from web.modules.database import db
from web.modules.celery import celery


class TaggerController(object):
    _random_comment_sql = text("""
SELECT
  id,
  meta :: JSONB ->> 'page'                         AS page,
  data :: JSONB ->> 'message'                      AS message,
  data :: JSONB -> 'from'                          AS user,
  COALESCE(meta :: JSONB -> 'tags', '[]' :: JSONB) AS tags
FROM data.facebook_comments
WHERE meta :: JSONB ->> 'lang' = :lang AND
      meta :: JSONB -> 'fingerprint' IS NOT NULL AND
      (:ignore_source OR meta :: JSONB ->> 'page' IN :sources) AND
      id IN (
        SELECT id
        FROM data.facebook_comments
          TABLESAMPLE SYSTEM (:frac)
        WHERE CHAR_LENGTH(data :: JSONB ->> 'message') > 64)
LIMIT :limit""")

    _sources_sql = text("select distinct(meta::jsonb->>'page') as source from data.facebook_comments")

    @classmethod
    def get_sources(cls) -> list:
        query = db.session.execute(cls._sources_sql)
        return sorted([r[0] for r in query])

    @classmethod
    def get_random_comments(cls, user_id: int, count=1, with_entity=False, with_suggestion=False, sources=None):
        # todo: using frac of 1.0 might be pretty slow
        if sources is None:
            sources = [None]
            ignore_source = True
        else:
            ignore_source = False
        query = db.session.execute(cls._random_comment_sql,
                                   dict(frac=1.0, limit=count, lang='en', ignore_source=ignore_source,
                                        sources=tuple(sources)))

        if with_entity:
            results = [dict((k, v) for k, v in zip(query.keys(), r)) for r in query]
            for result in results:
                result['tags'] = cls.get_tags_for(result['id'], user_id)['tags']
        else:
            results = [{'id': r[0]} for r in query]

        if with_suggestion:
            for result in results:
                result['suggestion'] = cls.get_suggestions_for_id(result['id'])
            for result in results:
                # switch to better backend
                result['suggestion'] = cls.get_suggestions_for_id(result['id']).get(interval=0.0005)
        return results

    @classmethod
    def get_tag_counts_for_user_id(cls, user_id: int):
        return dict((k, v) for k, v in
                    db.session.query(UserToTagToComment.tag).filter_by(user_id=user_id).add_column(
                        func.count()).group_by(
                        UserToTagToComment.tag).all())

    @classmethod
    def get_tags_for(cls, comment_id: str, user_id: int) -> dict:
        tags = UserToTagToComment.query.filter_by(comment_id=comment_id, user_id=user_id).all()
        return dict(id=comment_id, tags=[tag.tag for tag in tags])

    @classmethod
    def patch_tags(cls, comment_id: str, user_id: int, add=set(), remove=set()) -> dict:
        for remove_tag in remove:
            UserToTagToComment.query.filter_by(user_id=user_id, tag=remove_tag, comment_id=comment_id).delete()
        for add_tag in add:
            insert_or_ignore(db.session, UserToTagToComment(user_id=user_id, tag=add_tag, comment_id=comment_id))
        db.session.commit()
        return cls.get_tags_for(comment_id, user_id)

    @classmethod
    def get_suggestions_for_text(cls, text: str) -> tuple:
        task = celery.send_task('worker.brain.predict_text', args=(text,), kwargs=dict(model_id='debug_tagger'))
        # switch to better backend
        return task.get(interval=0.0005)

    @classmethod
    def get_suggestions_for_id(cls, comment_id: str) -> tuple:
        # todo do some nice mapping
        comment = db.session.query(FacebookCommentEntry).get(comment_id)
        if not comment or 'fingerprint' not in comment.meta or 'tokens' not in comment.meta:
            raise ValueError
        else:
            return celery.send_task('worker.brain.predict', args=(
                dict(tokens=comment.meta['tokens'], fingerprint=comment.meta['fingerprint']),),
                                    kwargs=dict(model_id='debug_tagger'))
