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
        if not url:
            return False

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
        # Work around an issue where interface.get_initialize_url returns ""
        # if next_url is empty. This is resolved in Kolibri v0.16.0-alpha8:
        # <https://github.com/learningequality/kolibri/commit/0ed2ccdd5d613e96721f80bc03d8bc56ae7a0e7f>
        # TODO: Remove this workaround when we update Kolibri.
        next_url = self.application.get_default_kolibri_path() or "/"
        initialize_url = interface.get_initialize_url(next_url=next_url)
        logging.info(f"Using initialize URL '{initialize_url}'")
        start_url = urljoin(base_url, initialize_url)
        self.application.replace_url(start_url)
