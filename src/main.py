import importlib
import logging
import time

import initialization  # noqa: F401 keep this first, to ensure we're set up for other imports
from android_utils import choose_endless_key_uris
from android_utils import get_endless_key_uris
from android_utils import has_any_external_storage_device
from android_utils import PermissionsCancelledError
from android_utils import PermissionsWrongFolderError
from android_utils import provision_endless_key_database
from android_utils import set_endless_key_uris
from android_utils import share_by_intent
from android_utils import start_service
from android_utils import StartupState
from android_utils import stat_file
from jnius import autoclass
from kolibri.main import disable_plugin
from kolibri.main import enable_plugin
from kolibri.plugins import config as plugins_config
from kolibri.plugins.app.utils import interface
from kolibri.utils.cli import initialize
from kolibri.utils.server import BaseKolibriProcessBus
from kolibri.utils.server import KolibriServerPlugin
from kolibri.utils.server import ZeroConfPlugin
from kolibri.utils.server import ZipContentServerPlugin
from lifecycle import register_activity_lifecycle_callbacks
from magicbus.plugins import SimplePlugin
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
_last_has_any_check = None


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


def check_has_any_external_storage_device():
    # Memorize the last check to avoid evaluating javascript when not
    # needed:
    global _last_has_any_check
    has_any = has_any_external_storage_device()
    if has_any != _last_has_any_check:
        _last_has_any_check = has_any
        if has_any:
            evaluate_javascript("setHasUSB(true)")
        else:
            evaluate_javascript("setHasUSB(false)")
    # By returning True the main loop calls this function over and
    # over again, until another function TO_RUN_IN_MAIN is set.
    return True


def is_endless_key_reachable():
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


def wait_until_endless_key_is_reachable():
    repeat = not is_endless_key_reachable()
    return repeat


def on_loading_ready():
    global TO_RUN_IN_MAIN

    startup_state = StartupState.get_current_state()
    if startup_state == StartupState.FIRST_TIME:
        logging.info("First time")
        evaluate_javascript("show_welcome()")

        TO_RUN_IN_MAIN = check_has_any_external_storage_device

    elif startup_state == StartupState.USB_USER:
        logging.info("Starting USB mode")
        # If it's USB we should have the permissions here so it's not needed to
        # ask again

        if not is_endless_key_reachable():
            evaluate_javascript("show_endless_key_required()")
            TO_RUN_IN_MAIN = wait_until_endless_key_is_reachable
        else:
            TO_RUN_IN_MAIN = start_kolibri_with_usb

    else:
        logging.info("Starting network mode")
        TO_RUN_IN_MAIN = start_kolibri


def on_activity_started(activity):
    logging.info("onActivityStarted")


def on_activity_paused(activity):
    logging.info("onActivityPaused")


def on_activity_resumed(activity):
    logging.info("onActivityResumed")


def on_activity_stopped(activity):
    logging.info("onActivityStopped")


def on_activity_destroyed(activity):
    logging.info("onActivityDestroyed")


register_activity_lifecycle_callbacks(
    onActivityStarted=on_activity_started,
    onActivityPaused=on_activity_paused,
    onActivityResumed=on_activity_resumed,
    onActivityStopped=on_activity_stopped,
    onActivityDestroyed=on_activity_destroyed,
)

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


class AppPlugin(SimplePlugin):
    def __init__(self, bus):
        self.bus = bus
        self.bus.subscribe("SERVING", self.SERVING)

    def SERVING(self, port):
        start_url = (
            "http://127.0.0.1:{port}".format(port=port) + interface.get_initialize_url()
        )
        loadUrl(start_url)
        start_service("workers")


logging.info("Initializing Kolibri and running any upgrade routines")

loadUrl("file:///android_asset/_load.html")

for plugin_name in DISABLED_PLUGINS:
    _disable_kolibri_plugin(plugin_name)

for plugin_name in REQUIRED_PLUGINS:
    _enable_kolibri_plugin(plugin_name)

for plugin_name in OPTIONAL_PLUGINS:
    _enable_kolibri_plugin(plugin_name, optional=True)


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

    interface.register(share_file=share_by_intent)

    # start kolibri server
    logging.info("Starting kolibri server.")

    kolibri_bus = BaseKolibriProcessBus()
    # Setup zeroconf plugin
    zeroconf_plugin = ZeroConfPlugin(kolibri_bus, kolibri_bus.port)
    zeroconf_plugin.subscribe()
    kolibri_server = KolibriServerPlugin(
        kolibri_bus,
        kolibri_bus.port,
    )

    alt_port_server = ZipContentServerPlugin(
        kolibri_bus,
        kolibri_bus.zip_port,
    )
    # Subscribe these servers
    kolibri_server.subscribe()
    alt_port_server.subscribe()
    app_plugin = AppPlugin(kolibri_bus)
    app_plugin.subscribe()
    kolibri_bus.run()


while True:
    if callable(TO_RUN_IN_MAIN):
        repeat = TO_RUN_IN_MAIN()
        if not repeat:
            TO_RUN_IN_MAIN = None
        # Wait a bit after each main function call
        time.sleep(0.5)
    time.sleep(0.05)
