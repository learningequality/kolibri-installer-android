import logging

from kolibri.main import initialize

from .android_utils import make_service_foreground

logging.info("Starting Kolibri task workers")

# ensure the service stays running by "foregrounding" it with a persistent notification
make_service_foreground("Kolibri service", "Running tasks.")

initialize(debug=True, skip_update=True)

from kolibri.core.tasks.main import initialize_workers  # noqa: E402
from kolibri.core.analytics.tasks import schedule_ping  # noqa: E402
from kolibri.core.deviceadmin.tasks import schedule_vacuum  # noqa: E402

schedule_ping()

schedule_vacuum()

# Initialize the iceqube engine to handle queued tasks
worker = initialize_workers()
# Join the job checker thread to loop forever
worker.job_checker.join()
