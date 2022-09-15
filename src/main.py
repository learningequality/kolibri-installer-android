import logging

import initialization  # noqa: F401 keep this first, to ensure we're set up for other imports
from android_utils import get_main_port
from android_utils import share_by_intent
from android_utils import start_service
from jnius import autoclass
from runnable import Runnable

PythonActivity = autoclass("org.kivy.android.PythonActivity")

FullScreen = autoclass("org.learningequality.FullScreen")
configureWebview = Runnable(FullScreen.configureWebview)
configureWebview(PythonActivity.mActivity)

loadUrl = Runnable(PythonActivity.mWebView.loadUrl)
cached, port = get_main_port()

if cached:
    loadUrl("http://127.0.0.1:{port}".format(port=port))


from kolibri.main import enable_plugin  # noqa: E402
from kolibri.plugins.app.utils import interface  # noqa: E402
from kolibri.utils.cli import initialize  # noqa: E402
from kolibri.utils.server import BaseKolibriProcessBus  # noqa: E402
from kolibri.utils.server import KolibriServerPlugin  # noqa: E402
from kolibri.utils.server import ZeroConfPlugin  # noqa: E402
from kolibri.utils.server import ZipContentServerPlugin  # noqa: E402
from magicbus.plugins import SimplePlugin  # noqa: E402


class AppPlugin(SimplePlugin):
    def __init__(self, bus):
        self.bus = bus
        self.bus.subscribe("SERVING", self.SERVING)

    def SERVING(self, _):
        if not cached:
            start_url = (
                "http://127.0.0.1:{port}".format(port=port)
                + interface.get_initialize_url()
            )
            loadUrl(start_url)

        start_service("workers")


logging.info("Initializing Kolibri and running any upgrade routines")

# activate app mode
enable_plugin("kolibri.plugins.app")

# we need to initialize Kolibri to allow us to access the app key
initialize()

interface.register(share_file=share_by_intent)

kolibri_bus = BaseKolibriProcessBus(port=port)
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
