import logging
import os
import re
from importlib.util import find_spec

from .android_utils import get_android_node_id
from .android_utils import get_endless_key_uris
from .android_utils import get_home_folder
from .android_utils import get_initial_content_pack_id
from .android_utils import get_logging_config
from .android_utils import get_signature_key_issuing_organization
from .android_utils import get_timezone_name
from .android_utils import get_version_name
from .android_whitenoise import AndroidDynamicWhiteNoise
from .globals import SCRIPT_PATH

logger = logging.getLogger(__name__)


# These Kolibri plugins conflict with the plugins listed in REQUIRED_PLUGINS
# or OPTIONAL_PLUGINS:
DISABLED_PLUGINS = [
    "kolibri.plugins.learn",
]

# These Kolibri plugins must be enabled for the application to function
# correctly:
REQUIRED_PLUGINS = [
    "kolibri.plugins.app",
]

# These Kolibri plugins will be dynamically enabled if they are available:
OPTIONAL_PLUGINS = [
    "kolibri_explore_plugin",
    "kolibri_zim_plugin",
]


def init_kolibri(**kwargs):
    logger.info("Initializing Kolibri and running any upgrade routines")

    _init_kolibri_env()
    _update_kolibri_content_fallback_dirs()
    _update_explore_plugin_options()

    _monkeypatch_kolibri_logging()
    _monkeypatch_whitenoise()

    for plugin_name in DISABLED_PLUGINS:
        _kolibri_disable_plugin(plugin_name)

    for plugin_name in REQUIRED_PLUGINS:
        _kolibri_enable_plugin(plugin_name)

    for plugin_name in OPTIONAL_PLUGINS:
        _kolibri_enable_plugin(plugin_name, optional=True)

    _kolibri_initialize(**kwargs)


def _init_kolibri_env():
    signing_org = get_signature_key_issuing_organization()
    if signing_org == "Learning Equality":
        runmode = "android-testing"
    elif signing_org == "Android":
        runmode = "android-debug"
    elif signing_org == "Google Inc.":
        runmode = ""  # Play Store!
    else:
        runmode = "android-" + re.sub(r"[^a-z ]", "", signing_org.lower()).replace(
            " ", "-"
        )
    os.environ["KOLIBRI_RUN_MODE"] = runmode
    os.environ["KOLIBRI_PROJECT"] = "endless-key-android"

    os.environ["TZ"] = get_timezone_name()
    os.environ["LC_ALL"] = "en_US.UTF-8"

    os.environ["KOLIBRI_HOME"] = get_home_folder()

    os.environ["KOLIBRI_APK_VERSION_NAME"] = get_version_name()
    os.environ["DJANGO_SETTINGS_MODULE"] = "kolibri_android.kolibri_extra.settings"

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

    node_id = get_android_node_id()

    # Don't set this if the retrieved id is falsy, too short, or a specific
    # id that is known to be hardcoded in many devices.
    if node_id and len(node_id) >= 16 and node_id != "9774d56d682e549c":
        os.environ["MORANGO_NODE_ID"] = node_id


def _update_explore_plugin_options():
    pack_id = get_initial_content_pack_id()
    if pack_id is not None:
        os.environ["KOLIBRI_INITIAL_CONTENT_PACK"] = pack_id
    else:
        os.environ["KOLIBRI_USE_EK_IGUANA_PAGE"] = "1"


def _update_kolibri_content_fallback_dirs():
    endless_key_uris = get_endless_key_uris()

    if endless_key_uris is None:
        return

    content_fallback_dirs = AndroidDynamicWhiteNoise.encode_root(
        endless_key_uris["content"]
    )

    logger.info("Setting KOLIBRI_CONTENT_FALLBACK_DIRS to %s", content_fallback_dirs)
    os.environ["KOLIBRI_CONTENT_FALLBACK_DIRS"] = content_fallback_dirs


def _monkeypatch_kolibri_logging():
    """Monkeypatch kolibri.utils.logger.get_default_logging_config

    Currently this is the only way to fully customize logging in
    kolibri. Custom Django LOG settings can be used, but that's only
    applied later when django is initialized.
    """
    import kolibri.utils.logger

    logger.info("Monkeypatching kolibri get_default_logging_config")
    kolibri.utils.logger.get_default_logging_config = get_logging_config


def _monkeypatch_whitenoise():
    from kolibri.utils import kolibri_whitenoise

    logger.info("Applying DynamicWhiteNoise workarounds")
    kolibri_whitenoise.DynamicWhiteNoise = AndroidDynamicWhiteNoise


def _kolibri_initialize(**kwargs):
    from kolibri.utils.main import initialize

    initialize(**kwargs)


def _kolibri_disable_plugin(plugin_name: str) -> bool:
    from kolibri.main import disable_plugin
    from kolibri.plugins import config as plugins_config

    if plugin_name in plugins_config.ACTIVE_PLUGINS:
        logger.info(f"Disabling plugin {plugin_name}")
        disable_plugin(plugin_name)

    return True


def _kolibri_enable_plugin(plugin_name: str, optional=False) -> bool:
    from kolibri.main import enable_plugin
    from kolibri.plugins import config as plugins_config

    if optional and not find_spec(plugin_name):
        return False

    if plugin_name not in plugins_config.ACTIVE_PLUGINS:
        logger.info(f"Enabling plugin {plugin_name}")
        enable_plugin(plugin_name)

    return True
