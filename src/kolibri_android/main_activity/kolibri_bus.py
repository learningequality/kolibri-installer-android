import logging
from urllib.parse import urljoin
from urllib.parse import urlparse

from kolibri.plugins.app.utils import interface
from kolibri.utils.server import BaseKolibriProcessBus
from kolibri.utils.server import get_urls
from kolibri.utils.server import KolibriServerPlugin
from kolibri.utils.server import ServicesPlugin
from kolibri.utils.server import ZeroConfPlugin
from kolibri.utils.server import ZipContentServerPlugin
from magicbus.plugins import SimplePlugin


class KolibriAppProcessBus(BaseKolibriProcessBus):
    def __init__(self, *args, enable_zeroconf=True, **kwargs):
        super(KolibriAppProcessBus, self).__init__(*args, **kwargs)

        ServicesPlugin(self).subscribe()

        if enable_zeroconf:
            ZeroConfPlugin(self, self.port).subscribe()

        KolibriServerPlugin(self, self.port).subscribe()

        ZipContentServerPlugin(self, self.zip_port).subscribe()

    def is_kolibri_url(self, url):
        if not self.port:
            return False

        _, server_urls = get_urls(self.port)

        if not server_urls:
            return False

        url_parts = urlparse(url)

        for server_url in server_urls:
            server_url_parts = urlparse(server_url)
            if (
                url_parts.scheme == server_url_parts.scheme
                and url_parts.netloc == server_url_parts.netloc
            ):
                return True

        return False


class AppPlugin(SimplePlugin):
    def __init__(self, bus, application):
        self.application = application
        self.bus = bus
        self.bus.subscribe("SERVING", self.SERVING)

    @staticmethod
    def register_share_file_interface(share_file):
        interface.register(share_file=share_file)

    def SERVING(self, port):
        base_url = "http://127.0.0.1:{port}".format(port=port)
        initialize_url = interface.get_initialize_url(
            next_url=self.application.read_last_kolibri_path()
        )
        logging.info(f"Using initialize URL '{initialize_url}'")
        start_url = urljoin(base_url, initialize_url)
        self.application.load_url(start_url)
