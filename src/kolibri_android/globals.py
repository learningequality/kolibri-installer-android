import logging
import sys
import traceback
from functools import partial
from pathlib import Path

from jnius import autoclass

from .android_utils import apply_android_workarounds


SCRIPT_PATH = Path(__file__).absolute().parent.parent

FirebaseCrashlytics = autoclass("com.google.firebase.crashlytics.FirebaseCrashlytics")
PythonException = autoclass("org.learningequality.PythonException")
Arrays = autoclass("java.util.Arrays")


def initialize():
    # initialize logging before loading any third-party modules, as they may cause logging to get configured.
    logging.basicConfig(level=logging.DEBUG)
    jnius_logger = logging.getLogger("jnius")
    jnius_logger.setLevel(logging.INFO)

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
