import logging

from android.activity import register_activity_lifecycle_callbacks


class BaseActivity(object):
    def __init__(self):
        register_activity_lifecycle_callbacks(
            onActivityPostCreated=self.on_activity_post_created,
            onActivityStarted=self.on_activity_started,
            onActivityPaused=self.on_activity_paused,
            onActivityResumed=self.on_activity_resumed,
            onActivityStopped=self.on_activity_stopped,
            onActivityDestroyed=self.on_activity_destroyed,
            onActivitySaveInstanceState=self.on_activity_save_instance_state,
        )

    def run(self):
        raise NotImplementedError()

    def start_service(self, service_name, service_args=None):
        from .android_utils import start_service

        start_service(service_name, service_args)

    def on_activity_post_created(self, activity, state_bundle):
        # FIXME: With the current version of python-for-android, it is
        #        unlikely that this function will run, because the Python
        #        program is started asynchronously from PythonActivity's
        #        onCreate method.
        logging.info("onActivityPostCreated")

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

    def on_activity_save_instance_state(self, activity, out_state_bundle):
        logging.info("onActivitySaveInstanceState")


class BaseService(object):
    def run(self):
        raise NotImplementedError()
