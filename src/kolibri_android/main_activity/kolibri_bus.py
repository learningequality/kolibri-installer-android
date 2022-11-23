from kolibri.plugins.app.utils import interface
from kolibri.utils.server import BaseKolibriProcessBus
from kolibri.utils.server import KolibriServerPlugin
from kolibri.utils.server import ZeroConfPlugin
from kolibri.utils.server import ZipContentServerPlugin
from magicbus.plugins import SimplePlugin


class KolibriAppProcessBus(BaseKolibriProcessBus):
    def __init__(self, *args, enable_zeroconf=True, **kwargs):
        super(KolibriAppProcessBus, self).__init__(*args, **kwargs)

        if enable_zeroconf:
            ZeroConfPlugin(self, self.port).subscribe()

        KolibriServerPlugin(self, self.port).subscribe()

        ZipContentServerPlugin(self, self.zip_port).subscribe()


class AppPlugin(SimplePlugin):
    def __init__(self, bus, application):
        self.application = application
        self.bus = bus
        self.bus.subscribe("SERVING", self.SERVING)

    @staticmethod
    def register_share_file_interface(share_file):
        interface.register(share_file=share_file)

    def SERVING(self, port):
        start_url = (
            "http://127.0.0.1:{port}".format(port=port) + interface.get_initialize_url()
        )
        self.application.load_url(start_url)
        self.application.start_service("workers")
