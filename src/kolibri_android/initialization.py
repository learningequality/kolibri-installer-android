import logging
import os
import re
import sys
from pathlib import Path

from jnius import autoclass

from .android_utils import apply_android_workarounds
from .android_utils import get_activity
from .android_utils import get_endless_key_uris
from .android_utils import get_home_folder
from .android_utils import get_signature_key_issuing_organization
from .android_utils import get_timezone_name
from .android_utils import get_version_name

SCRIPT_PATH = Path(__file__).absolute().parent.parent

# initialize logging before loading any third-party modules, as they may cause logging to get configured.
logging.basicConfig(level=logging.DEBUG)
jnius_logger = logging.getLogger("jnius")
jnius_logger.setLevel(logging.INFO)

apply_android_workarounds()

sys.path.append(SCRIPT_PATH.as_posix())
sys.path.append(SCRIPT_PATH.joinpath("kolibri", "dist").as_posix())
sys.path.append(SCRIPT_PATH.joinpath("extra-packages").as_posix())

from .android_whitenoise import DynamicWhiteNoise  # noqa: E402
from .android_whitenoise import monkeypatch_whitenoise  # noqa: E402

monkeypatch_whitenoise()


def set_content_fallback_dirs_env():
    endless_key_uris = get_endless_key_uris()
    if endless_key_uris is not None:
        content_uri = DynamicWhiteNoise.encode_root(endless_key_uris["content"])
        logging.info("Setting KOLIBRI_CONTENT_FALLBACK_DIRS to %s", content_uri)
        os.environ["KOLIBRI_CONTENT_FALLBACK_DIRS"] = content_uri


signing_org = get_signature_key_issuing_organization()
if signing_org == "Learning Equality":
    runmode = "android-testing"
elif signing_org == "Android":
    runmode = "android-debug"
elif signing_org == "Google Inc.":
    runmode = ""  # Play Store!
else:
    runmode = "android-" + re.sub(r"[^a-z ]", "", signing_org.lower()).replace(" ", "-")

os.environ["KOLIBRI_RUN_MODE"] = runmode
os.environ["KOLIBRI_PROJECT"] = "endless-key-android"

os.environ["TZ"] = get_timezone_name()
os.environ["LC_ALL"] = "en_US.UTF-8"

os.environ["KOLIBRI_HOME"] = get_home_folder()

set_content_fallback_dirs_env()

os.environ["KOLIBRI_APK_VERSION_NAME"] = get_version_name()
os.environ["DJANGO_SETTINGS_MODULE"] = "kolibri_app_settings"

AUTOPROVISION_PATH = SCRIPT_PATH.joinpath("automatic_provision.json")
if AUTOPROVISION_PATH.is_file():
    os.environ["KOLIBRI_AUTOMATIC_PROVISION_FILE"] = AUTOPROVISION_PATH.as_posix()

os.environ["KOLIBRI_CHERRYPY_THREAD_POOL"] = "2"

os.environ["KOLIBRI_APPS_BUNDLE_PATH"] = SCRIPT_PATH.joinpath(
    "apps-bundle", "apps"
).as_posix()
os.environ["KOLIBRI_CONTENT_COLLECTIONS_PATH"] = SCRIPT_PATH.joinpath(
    "collections"
).as_posix()

Secure = autoclass("android.provider.Settings$Secure")

node_id = Secure.getString(get_activity().getContentResolver(), Secure.ANDROID_ID)

# Don't set this if the retrieved id is falsy, too short, or a specific
# id that is known to be hardcoded in many devices.
if node_id and len(node_id) >= 16 and node_id != "9774d56d682e549c":
    os.environ["MORANGO_NODE_ID"] = node_id
