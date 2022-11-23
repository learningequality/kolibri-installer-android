import logging
import sys
from pathlib import Path

from .android_utils import apply_android_workarounds


SCRIPT_PATH = Path(__file__).absolute().parent.parent


def initialize():
    # initialize logging before loading any third-party modules, as they may cause logging to get configured.
    logging.basicConfig(level=logging.DEBUG)
    jnius_logger = logging.getLogger("jnius")
    jnius_logger.setLevel(logging.INFO)

    apply_android_workarounds()

    sys.path.append(SCRIPT_PATH.as_posix())
    sys.path.append(SCRIPT_PATH.joinpath("kolibri", "dist").as_posix())
    sys.path.append(SCRIPT_PATH.joinpath("extra-packages").as_posix())
