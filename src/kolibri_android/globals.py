import os
import sys
import traceback
from functools import partial
from logging.config import dictConfig
from pathlib import Path

from jnius import autoclass

from .android_utils import apply_android_workarounds
from .android_utils import get_log_root
from .android_utils import get_logging_config
from .android_utils import setup_analytics


SCRIPT_PATH = Path(__file__).absolute().parent.parent

FirebaseCrashlytics = autoclass("com.google.firebase.crashlytics.FirebaseCrashlytics")
PythonException = autoclass("org.learningequality.PythonException")
Arrays = autoclass("java.util.Arrays")


def initialize():
    # initialize logging before loading any third-party modules, as they may cause logging to get configured.
    log_root = get_log_root()
    os.makedirs(log_root, exist_ok=True)
    logging_config = get_logging_config(log_root, debug=True)
    dictConfig(logging_config)

    setup_analytics()
    apply_android_workarounds()

    sys.path.append(SCRIPT_PATH.as_posix())
    sys.path.append(SCRIPT_PATH.joinpath("kolibri", "dist").as_posix())
    sys.path.append(SCRIPT_PATH.joinpath("extra-packages").as_posix())

    sys.excepthook = partial(log_exception, default_excepthook=sys.excepthook)


def log_exception(type, value, tb, default_excepthook=None):
    if callable(default_excepthook):
        default_excepthook(type, value, tb)
    FirebaseCrashlytics.getInstance().recordException(
        PythonException(Arrays.toString(traceback.format_exception(type, value, tb)))
    )
