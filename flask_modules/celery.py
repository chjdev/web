#!/usr/bin/env python
# -*- coding: utf-8 -*-

from celery import Celery
from config.db import Config

celery = object  # type: Celery


def setup_celery(app):
    worker_config = Config('worker')
    app.config['CELERY_ALWAYS_EAGER'] = False  # important so it doesn't get executed locally!
    app.config['CELERY_TASK_SERIALIZER'] = 'msgpack'
    app.config['CELERY_RESULT_SERIALIZER'] = 'msgpack'
    app.config['CELERY_ACCEPT_CONTENT'] = ['msgpack']
    app.config['CELERY_IGNORE_RESULT'] = False,
    app.config['CELERY_TRACK_STARTED'] = True,

    global celery
    celery = Celery(app.import_name, backend=worker_config['backend'], broker=worker_config['broker'])
    celery.conf.update(app.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask


class Brain(object):
    @staticmethod
    def train_model(*args, **kwargs) -> Celery.AsyncResult:
        return celery.send_task('worker.brain.' + Brain.train_model.__name__, args=args, kwargs=kwargs)

    @staticmethod
    def predict_text(*args, **kwargs) -> Celery.AsyncResult:
        return celery.send_task('worker.brain.' + Brain.predict_text.__name__, args=args, kwargs=kwargs)


class Scrape(object):
    @staticmethod
    def scrape_meta_for_url(*args, **kwargs) -> Celery.AsyncResult:
        return celery.send_task('worker.scrape.' + Scrape.scrape_meta_for_url.__name__, args=args, kwargs=kwargs)
