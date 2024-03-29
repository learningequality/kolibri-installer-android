import logging
from uuid import uuid4

import initialization  # noqa: F401 keep this first, to ensure we're set up for other imports
from android_utils import get_dummy_user_name
from android_utils import share_by_intent
from jnius import autoclass
from kolibri.main import enable_plugin
from kolibri.plugins.app.utils import interface
from kolibri.utils.cli import initialize
from kolibri.utils.server import BaseKolibriProcessBus
from kolibri.utils.server import KolibriServerPlugin
from kolibri.utils.server import ZeroConfPlugin
from kolibri.utils.server import ZipContentServerPlugin
from magicbus.plugins import SimplePlugin
from runnable import Runnable

# from android_utils import is_active_network_metered


PythonActivity = autoclass("org.kivy.android.PythonActivity")

FullScreen = autoclass("org.learningequality.FullScreen")
configureWebview = Runnable(FullScreen.configureWebview)
configureWebview(PythonActivity.mActivity)

loadUrl = Runnable(PythonActivity.mWebView.loadUrl)

auth_token_value = uuid4().hex


def os_user(auth_token):
    if auth_token == auth_token_value:
        return (get_dummy_user_name(), True)
    return None, False


class AppPlugin(SimplePlugin):
    def __init__(self, bus):
        self.bus = bus
        self.bus.subscribe("SERVING", self.SERVING)

    def SERVING(self, port):
        start_url = "http://127.0.0.1:{port}".format(
            port=port
        ) + interface.get_initialize_url(auth_token=auth_token_value)
        loadUrl(start_url)


logging.info("Initializing Kolibri and running any upgrade routines")

# activate app mode
enable_plugin("kolibri.plugins.app")
enable_plugin("android_app_plugin")

# we need to initialize Kolibri to allow us to access the app key
initialize()

interface.register(share_file=share_by_intent)
# interface.register(check_is_metered=is_active_network_metered)
interface.register(get_os_user=os_user)

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
