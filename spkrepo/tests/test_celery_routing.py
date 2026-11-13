# -*- coding: utf-8 -*-
"""Regression tests for Celery task routing."""

from spkrepo.tests.common import BaseTestCase


class CeleryRoutingTestCase(BaseTestCase):
    def test_ops_tasks_route_to_ops_queue(self):
        celery_app = self.app.extensions["celery"]
        tasks = [
            task
            for task in celery_app.tasks.values()
            if task.name.startswith("spkrepo.views.tasks.")
        ]

        self.assertTrue(tasks)
        for task in tasks:
            route = celery_app.amqp.router.route(task._get_exec_options(), task.name)
            self.assertEqual(route["queue"].name, "ops", task.name)
