import logging

from android.activity import register_activity_lifecycle_callbacks


class BaseActivity(object):
    def __init__(self):
        register_activity_lifecycle_callbacks(
            onActivityStarted=self.on_activity_started,
            onActivityPaused=self.on_activity_paused,
            onActivityResumed=self.on_activity_resumed,
            onActivityStopped=self.on_activity_stopped,
            onActivityDestroyed=self.on_activity_destroyed,
        )

    def run(self):
        raise NotImplementedError()

    def start_service(self, service_name, service_args=None):
        from .android_utils import start_service

        start_service(service_name, service_args)

    def on_activity_started(self, activity):
        logging.info("onActivityStarted")

    def on_activity_paused(self, activity):
        logging.info("onActivityPaused")

    def on_activity_resumed(self, activity):
        logging.info("onActivityResumed")

    def on_activity_stopped(self, activity):
        logging.info("onActivityStopped")

    def on_activity_destroyed(self, activity):
        logging.info("onActivityDestroyed")


class BaseService(object):
    def run(self):
        raise NotImplementedError()
