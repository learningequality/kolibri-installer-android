import logging

from ..android_utils import make_service_foreground
from ..application import BaseService
from ..kolibri_utils import init_kolibri


class WorkersService(BaseService):
    def run(self):
        logging.info("Starting Kolibri task workers")

        # ensure the service stays running by "foregrounding" it with a persistent notification
        make_service_foreground("Kolibri service", "Running tasks.")

        init_kolibri(debug=True, skip_update=True)
        self._run_kolibri_workers()

    def _run_kolibri_workers(self):
        from kolibri.core.tasks.main import initialize_workers
        from kolibri.core.analytics.tasks import schedule_ping
        from kolibri.core.deviceadmin.tasks import schedule_vacuum

        schedule_ping()

        schedule_vacuum()

        # Initialize the iceqube engine to handle queued tasks
        worker = initialize_workers()
        # Join the job checker thread to loop forever
        worker.job_checker.join()
