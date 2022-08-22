import importlib
import logging
import os
import time

import initialization  # noqa: F401 keep this first, to ensure we're set up for other imports
from android_utils import choose_endless_key_uris
from android_utils import get_endless_key_uris
from android_utils import PermissionsCancelledError
from android_utils import PermissionsWrongFolderError
from android_utils import provision_endless_key_database
from android_utils import set_endless_key_uris
from android_utils import start_service
from android_utils import StartupState
from android_utils import stat_file
from jnius import autoclass
from kolibri.plugins import config as plugins_config
from kolibri.plugins.app.utils import interface
from kolibri.plugins.registry import registered_plugins
from kolibri.plugins.utils import disable_plugin
from kolibri.plugins.utils import enable_plugin
from kolibri.utils.cli import initialize
from kolibri.utils.server import _read_pid_file
from kolibri.utils.server import PID_FILE
from kolibri.utils.server import STATUS_RUNNING
from kolibri.utils.server import wait_for_status
from runnable import Runnable

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


TO_RUN_IN_MAIN = None


def _disable_kolibri_plugin(plugin_name: str) -> bool:
    if plugin_name in plugins_config.ACTIVE_PLUGINS:
        logging.info(f"Disabling plugin {plugin_name}")
        disable_plugin(plugin_name)

    return True


def _enable_kolibri_plugin(plugin_name: str, optional=False) -> bool:
    if optional and not importlib.util.find_spec(plugin_name):
        return False

    if plugin_name not in plugins_config.ACTIVE_PLUGINS:
        logging.info(f"Enabling plugin {plugin_name}")
        registered_plugins.register_plugins([plugin_name])
        enable_plugin(plugin_name)

    return True


def load():
    global TO_RUN_IN_MAIN
    TO_RUN_IN_MAIN = start_kolibri


def load_with_usb():
    global TO_RUN_IN_MAIN
    # TODO: Show grant access view
    TO_RUN_IN_MAIN = start_kolibri_with_usb


def evaluate_javascript(js_code):
    PythonActivity.mWebView.evaluateJavascript(js_code, None)


evaluate_javascript = Runnable(evaluate_javascript)


def is_usb_connected():
    """
    Check if the KOLIBRI_HOME db file is reachable.

    This only works after the user has granted permissions correctly. In other
    case it always return False.
    """

    key_uris = get_endless_key_uris()
    if not key_uris:
        return False
    try:
        # Check if the USB is connected
        stat_file(key_uris.get("db"))
        evaluate_javascript("setHasUSB(true)")
        return True
    except FileNotFoundError:
        evaluate_javascript("setHasUSB(false)")
        return False


def wait_until_usb_is_connected():
    repeat = not is_usb_connected()
    return repeat


def on_loading_ready():
    global TO_RUN_IN_MAIN

    startup_state = StartupState.get_current_state()
    if startup_state == StartupState.FIRST_TIME:
        logging.info("First time")
        PythonActivity.mWebView.evaluateJavascript("show_welcome()", None)

    elif startup_state == StartupState.USB_USER:
        logging.info("Starting USB mode")
        # If it's USB we should have the permissions here so it's not needed to
        # ask again

        if not is_usb_connected():
            evaluate_javascript("show_endless_key_required()")
            TO_RUN_IN_MAIN = wait_until_usb_is_connected
        else:
            TO_RUN_IN_MAIN = start_kolibri_with_usb

    else:
        logging.info("Starting network mode")
        TO_RUN_IN_MAIN = start_kolibri


PythonActivity = autoclass("org.kivy.android.PythonActivity")

FullScreen = autoclass("org.learningequality.FullScreen")
configureWebview = Runnable(FullScreen.configureWebview)

configureWebview(
    PythonActivity.mActivity,
    Runnable(load),
    Runnable(load_with_usb),
    Runnable(on_loading_ready),
)

loadUrl = Runnable(PythonActivity.mWebView.loadUrl)

logging.info("Initializing Kolibri and running any upgrade routines")

loadUrl("file:///android_asset/_load.html")

for plugin_name in DISABLED_PLUGINS:
    _disable_kolibri_plugin(plugin_name)

for plugin_name in REQUIRED_PLUGINS:
    _enable_kolibri_plugin(plugin_name)

for plugin_name in OPTIONAL_PLUGINS:
    _enable_kolibri_plugin(plugin_name, optional=True)

# Ensure that the pidfile is removed on startup
try:
    os.unlink(PID_FILE)
except FileNotFoundError:
    pass


def start_kolibri_with_usb():
    key_uris = get_endless_key_uris()

    if key_uris is None:
        try:
            key_uris = choose_endless_key_uris()
        except PermissionsWrongFolderError:
            evaluate_javascript("show_wrong_folder()")
            return
        except PermissionsCancelledError:
            evaluate_javascript("show_permissions_cancelled()")
            return

    provision_endless_key_database(key_uris)
    set_endless_key_uris(key_uris)
    start_kolibri()


def start_kolibri():
    # we need to initialize Kolibri to allow us to access the app key
    initialize()

    # start kolibri server
    logging.info("Starting kolibri server via Android service...")
    start_service("server")

    # Tie up this thread until the server is running
    wait_for_status(STATUS_RUNNING, timeout=120)

    _, port, _, _ = _read_pid_file(PID_FILE)

    start_url = (
        "http://127.0.0.1:{port}".format(port=port) + interface.get_initialize_url()
    )
    loadUrl(start_url)

    start_service("remoteshell")


while True:
    if callable(TO_RUN_IN_MAIN):
        repeat = TO_RUN_IN_MAIN()
        if not repeat:
            TO_RUN_IN_MAIN = None
        # Wait a bit after each main function call
        time.sleep(0.5)
    time.sleep(0.05)
