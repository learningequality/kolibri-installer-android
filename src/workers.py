from kolibri_android.globals import initialize
from kolibri_android.kolibri_utils import init_kolibri

initialize()
init_kolibri()

from kolibri_android.workers_service import *  # noqa F403 F401
