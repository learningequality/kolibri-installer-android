import logging
import time
from urllib.parse import urlparse

from jnius import autoclass

from ..android_utils import choose_endless_key_uris
from ..android_utils import get_endless_key_uris
from ..android_utils import get_preferences
from ..android_utils import has_any_external_storage_device
from ..android_utils import PermissionsCancelledError
from ..android_utils import PermissionsWrongFolderError
from ..android_utils import provision_endless_key_database
from ..android_utils import set_endless_key_uris
from ..android_utils import share_by_intent
from ..android_utils import StartupState
from ..android_utils import stat_file
from ..application import BaseActivity
from ..kolibri_utils import init_kolibri
from ..runnable import Runnable


PythonActivity = autoclass("org.kivy.android.PythonActivity")
FullScreen = autoclass("org.learningequality.FullScreen")


@Runnable
def configure_webview(*args):
    FullScreen.configureWebview(*args)


@Runnable
def load_url_in_webview(url):
    PythonActivity.mWebView.loadUrl(url)


@Runnable
def get_current_url():
    return PythonActivity.mWebView.getUrl()


@Runnable
def evaluate_javascript(js_code):
    PythonActivity.mWebView.evaluateJavascript(js_code, None)


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
        evaluate_javascript("WelcomeApp.setHasUSB(true)")
        return True
    except FileNotFoundError:
        evaluate_javascript("WelcomeApp.setHasUSB(false)")
        return False


def wait_until_endless_key_is_reachable():
    repeat = not is_endless_key_reachable()
    return repeat


def _build_kolibri_process_bus(application):
    from .kolibri_bus import AppPlugin
    from .kolibri_bus import KolibriAppProcessBus

    AppPlugin.register_share_file_interface(share_by_intent)

    kolibri_bus = KolibriAppProcessBus(enable_zeroconf=True)
    AppPlugin(kolibri_bus, application).subscribe()

    return kolibri_bus


class MainActivity(BaseActivity):
    TO_RUN_IN_MAIN = None
    _last_has_any_check = None
    _kolibri_bus = None

    def __init__(self):
        super().__init__()

        configure_webview(
            PythonActivity.mActivity,
            Runnable(self._on_start_with_network),
            Runnable(self._on_start_with_usb),
            Runnable(self._on_loading_ready),
        )

    def on_activity_stopped(self, activity):
        super().on_activity_stopped(activity)

        self.save_last_kolibri_path()

        if self._kolibri_bus is not None:
            self._kolibri_bus.transition("STOP")

    def on_activity_resumed(self, activity):
        super().on_activity_resumed(activity)
        if self._kolibri_bus is not None:
            self._kolibri_bus.transition("RUN")

    def run(self):
        self.load_url("file:///android_asset/_load.html")

        while True:
            if callable(self.TO_RUN_IN_MAIN):
                repeat = self.TO_RUN_IN_MAIN()
                if not repeat:
                    self.TO_RUN_IN_MAIN = None
                # Wait a bit after each main function call
                time.sleep(0.5)
            time.sleep(0.05)

    def read_last_kolibri_path(self):
        preferences = get_preferences()
        return preferences.getString("last_kolibri_path", None)

    def save_last_kolibri_path(self):
        if self._kolibri_bus is None:
            return None

        current_url = get_current_url()

        if self._kolibri_bus.is_kolibri_url(current_url):
            last_kolibri_path = (
                urlparse(current_url)._replace(scheme="", netloc="").geturl()
            )
        else:
            last_kolibri_path = None

        logging.info(f"Saving Kolibri path: '{last_kolibri_path or ''}'")

        editor = get_preferences().edit()
        editor.putString("last_kolibri_path", last_kolibri_path)
        editor.commit()

    def load_url(self, url):
        load_url_in_webview(url)

    def start_kolibri(self):
        # TODO: Wait until external storage is available
        #       <https://phabricator.endlessm.com/T33974>

        init_kolibri(debug=True)

        self._kolibri_bus = _build_kolibri_process_bus(self)

        # start kolibri server
        logging.info("Starting kolibri server.")

        self._kolibri_bus.run()

    def start_kolibri_with_usb(self):
        key_uris = get_endless_key_uris()

        if key_uris is None:
            try:
                key_uris = choose_endless_key_uris()
            except PermissionsWrongFolderError:
                evaluate_javascript("WelcomeApp.showPermissionsWrongFolder()")
                return
            except PermissionsCancelledError:
                evaluate_javascript("WelcomeApp.showPermissionsCancelled()")
                return

        provision_endless_key_database(key_uris)
        set_endless_key_uris(key_uris)

        self.start_kolibri()

    def _on_start_with_network(self):
        self.TO_RUN_IN_MAIN = self.start_kolibri

    def _on_start_with_usb(self):
        self.TO_RUN_IN_MAIN = self.start_kolibri_with_usb

    def _on_loading_ready(self):
        startup_state = StartupState.get_current_state()
        if startup_state == StartupState.FIRST_TIME:
            logging.info("First time")
            evaluate_javascript("WelcomeApp.showWelcome()")

            self.TO_RUN_IN_MAIN = self.check_has_any_external_storage_device

        elif startup_state == StartupState.USB_USER:
            logging.info("Starting USB mode")
            # If it's USB we should have the permissions here so it's not needed to
            # ask again

            if not is_endless_key_reachable():
                evaluate_javascript("WelcomeApp.showConnectKeyRequired()")
                self.TO_RUN_IN_MAIN = wait_until_endless_key_is_reachable
            else:
                self.TO_RUN_IN_MAIN = self.start_kolibri_with_usb

        else:
            logging.info("Starting network mode")
            self.TO_RUN_IN_MAIN = self.start_kolibri

    def check_has_any_external_storage_device(self):
        # Memorize the last check to avoid evaluating javascript when not
        # needed:
        has_any = has_any_external_storage_device()
        if has_any != self._last_has_any_check:
            self._last_has_any_check = has_any
            if has_any:
                evaluate_javascript("WelcomeApp.setHasUSB(true)")
            else:
                evaluate_javascript("WelcomeApp.setHasUSB(false)")
        # By returning True the main loop calls this function over and
        # over again, until another function TO_RUN_IN_MAIN is set.
        return True
