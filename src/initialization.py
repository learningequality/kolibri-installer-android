import logging
import os
import re
import sys

from android_utils import apply_android_workarounds
from android_utils import get_activity
from android_utils import get_endless_key_uris
from android_utils import get_home_folder
from android_utils import get_signature_key_issuing_organization
from android_utils import get_timezone_name
from android_utils import get_version_name
from jnius import autoclass

# initialize logging before loading any third-party modules, as they may cause logging to get configured.
logging.basicConfig(level=logging.DEBUG)
jnius_logger = logging.getLogger("jnius")
jnius_logger.setLevel(logging.INFO)

apply_android_workarounds()

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)
sys.path.append(os.path.join(script_dir, "kolibri", "dist"))
sys.path.append(os.path.join(script_dir, "extra-packages"))

from android_whitenoise import DynamicWhiteNoise  # noqa: E402
from android_whitenoise import monkeypatch_whitenoise  # noqa: E402

monkeypatch_whitenoise()

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

endless_key_uris = get_endless_key_uris()
if endless_key_uris is not None:
    content_uri = DynamicWhiteNoise.encode_root(endless_key_uris["content"])
    logging.info("Setting KOLIBRI_CONTENT_FALLBACK_DIRS to %s", content_uri)
    os.environ["KOLIBRI_CONTENT_FALLBACK_DIRS"] = content_uri

os.environ["KOLIBRI_APK_VERSION_NAME"] = get_version_name()
os.environ["DJANGO_SETTINGS_MODULE"] = "kolibri_app_settings"

AUTOPROVISION_FILE = os.path.join(script_dir, "automatic_provision.json")
if os.path.exists(AUTOPROVISION_FILE):
    os.environ["KOLIBRI_AUTOMATIC_PROVISION_FILE"] = AUTOPROVISION_FILE

os.environ["KOLIBRI_CHERRYPY_THREAD_POOL"] = "2"

os.environ["KOLIBRI_APPS_BUNDLE_PATH"] = os.path.join(script_dir, "apps-bundle", "apps")

Secure = autoclass("android.provider.Settings$Secure")

node_id = Secure.getString(get_activity().getContentResolver(), Secure.ANDROID_ID)

# Don't set this if the retrieved id is falsy, too short, or a specific
# id that is known to be hardcoded in many devices.
if node_id and len(node_id) >= 16 and node_id != "9774d56d682e549c":
    os.environ["MORANGO_NODE_ID"] = node_id
