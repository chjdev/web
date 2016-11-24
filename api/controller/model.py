#!/usr/bin/env python
# -*- coding: utf-8 -*-
from flask import redirect
from flask_modules.celery import celery, Brain
from flask_modules.database import db
from flask_security import current_user
from flask_security.decorators import roles_required

from db.models.brain import Model, Job

from . import defaults, check_sources_by_id


def _model_to_result(model: Model):
    result = dict(id=model.id, trained_ts=model.trained_ts)
    if 'admin' in [role.name for role in current_user.roles]:
        result['score'] = model.score
        result['params'] = model.params
    return result


@defaults
def model_id_get(model_id: str) -> dict:
    model = current_user.models.filter_by(id=model_id).one_or_none()
    if not model:
        return dict(error='Model not associated to user'), 403
    return _model_to_result(model)


@defaults
def search_post(body: dict, internal=False) -> dict:
    tagset_id = body.get('tagsetId')
    sources = body.get('sources')
    if tagset_id is None and sources is None:
        return None if internal else (dict(error='No criterium specified'), 400)
    model_query = db.session.query(Model).filter_by(user_id=current_user.id)
    if tagset_id is not None:
        model_query = model_query.filter_by(tagset_id=tagset_id)
    # todo: add sources support
    #    if sources is not None:
    #        model_query = model_query.filter_by(sources=sources)
    model_query = model_query.order_by(Model.score.desc())
    model = model_query.first()
    if model is None:
        return None if internal else (dict(error='No model found for this query'), 404)
    return _model_to_result(model)


@roles_required('admin')
@defaults
def train_post(body: dict, fast=True) -> dict:
    jobs = current_user.jobs.all()
    if jobs:
        job_url = '/v3/model/jobs/' + str(jobs[0].id)
        return dict(job=str(jobs[0].id), url=job_url), 409

    tagset_id = body['tagset_id']
    tagset = current_user.tagsets.filter_by(id=tagset_id).one_or_none()
    if not tagset:
        return dict(error='Tagset not associated with user'), 403

    source_ids = set(body['source_ids'])
    error = check_sources_by_id(source_ids)
    if error:
        return error

    params = None
    # if fast:
    #     best_model = model__search_post(dict(tagset_id=tagset_id, sources=sources), internal=True)
    #     params = best_model and best_model['params']
    job = Brain.train_model(tagset_id, tuple(source_ids), n_estimators=1, params=params)
    current_user.jobs.append(Job(id=job.id, user_id=current_user.id))
    db.session.commit()
    job_url = '/v3/model/jobs/' + job.id
    return dict(job=job.id, url=job_url), 202


@defaults
def jobs_job_id_get(job_id) -> dict:
    job = current_user.jobs.filter_by(id=job_id).one_or_none()
    if not job:
        return dict(error='not associated to user ' + job_id), 403

    result = celery.AsyncResult(job_id)
    if result.ready():
        if result.successful():
            model_id = result.get(timeout=2)
            return redirect('/v3/model/%s' % model_id, code=201)
        elif result.failed():
            return dict(error='model could not be created'), 410
    else:  # still running
        if result.state == 'PENDING':  # most likely doesn't exist
            # todo strictly speaking not 404, the task could be simply not started yet
            return dict(error='no job with id ' + job_id), 404
        else:
            job_url = '/v3/jobs/' + job_id
            return dict(job=job_id, url=job_url), 304, {'Retry-After': 30, 'Location': job_url}


@defaults
def jobs_job_id_delete(job_id) -> dict:
    job = current_user.jobs.filter_by(id=job_id).one_or_none()
    if not job:
        return dict(error='not associated to user ' + job_id), 403

    result = celery.AsyncResult(job_id)
    result.revoke()  # todo: simply revokes the task, does not kill training by default
    current_user.jobs.filter_by(id=job_id).delete()
    db.session.commit()
    return dict(job=job_id)


@defaults
def suggestion_post(body: dict) -> dict:
    try:
        text = body['text']
        task = celery.send_task('worker.brain.predict', args=(text,),
                                kwargs=dict(model_id='32797cd2-4203-11e6-9215-f45c89bc662f'))
        suggestion = dict((k, v) for [v, k] in task.get())
        return dict(text=text, suggestion=suggestion)
    except KeyError:
        return dict(error='no text field in request'), 400
    except Exception as err:
        return dict(error=str(err.args)), 400
