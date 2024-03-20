import logging
from datetime import datetime

from jnius import autoclass
from kolibri.core.tasks.hooks import StorageHook
from kolibri.core.tasks.job import Priority
from kolibri.plugins import KolibriPluginBase
from kolibri.plugins.hooks import register_hook

Locale = autoclass("java.util.Locale")
Task = autoclass("org.learningequality.Task")
TaskWorker = autoclass("org.learningequality.Kolibri.task.TaskWorkerImpl")
PROGRESS_LIMIT = 10000


logger = logging.getLogger(__name__)


class AndroidApp(KolibriPluginBase):
    pass


@register_hook
class StorageHook(StorageHook):
    def schedule(
        self,
        job,
        orm_job,
    ):
        if orm_job.id:

            delay = (
                max(0, (orm_job.scheduled_time - datetime.now()).total_seconds())
                if orm_job.scheduled_time
                else 0
            )

            high_priority = orm_job.priority <= Priority.HIGH

            # Android has no mechanism for scheduling a limited run of repeating tasks,
            # so we just schedule it as a one-off task, and then re-schedule it when the task
            # is completed.
            # We could use WorkManager's PeriodicWorkRequest, but this gives us more control
            # over execution, and also allows us to use the same mechanism for all tasks.
            # Similarly, retry_intervals are handled by the schedule mechanism, so we don't
            # leverage Android's retry mechanism either.
            logger.info(
                "Scheduling task {} for job {} with delay {} and high priority {}".format(
                    job.func, orm_job.id, delay, high_priority
                )
            )
            request_id = Task.enqueueOnce(
                orm_job.id,
                delay,
                high_priority,
                job.func,
                job.long_running,
            )
            job.update_worker_info(extra=request_id)

    def update(self, job, orm_job, state=None, **kwargs):
        currentLocale = Locale.getDefault().toLanguageTag()

        status = job.status(currentLocale)

        if status:
            if job.total_progress:
                progress = job.progress
                total_progress = job.total_progress
            else:
                progress = -1
                total_progress = -1

            # avoid passing integers that are too large
            # PROGRESS_LIMIT gives sufficient precision for a % progress calculation
            if total_progress > PROGRESS_LIMIT:
                progress = PROGRESS_LIMIT * progress // total_progress
                total_progress = PROGRESS_LIMIT

            TaskWorker.notifyLocalObservers(
                status.title,
                status.text,
                progress,
                total_progress,
            )

    def clear(self, job, orm_job):
        logger.info("Clearing task {} for job {}".format(job.func, orm_job.id))
        Task.clear(orm_job.id)
