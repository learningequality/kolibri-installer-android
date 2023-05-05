import logging
import stat
from urllib.parse import urlparse

from django.utils.functional import cached_property
from evil_kolibri.utils.kolibri_whitenoise import compressed_file_extensions
from evil_kolibri.utils.kolibri_whitenoise import DynamicWhiteNoise
from evil_kolibri.utils.kolibri_whitenoise import EndRangeStaticFile
from evil_kolibri.utils.kolibri_whitenoise import FileFinder
from jnius import autoclass
from whitenoise.httpstatus_backport import HTTPStatus
from whitenoise.responders import NOT_ALLOWED_RESPONSE
from whitenoise.responders import Response

from .android_utils import document_exists
from .android_utils import document_tree_join
from .android_utils import is_document_uri
from .android_utils import open_file
from .android_utils import stat_file

# We import from evil_kolibri so we can monkey-patch DynamicWhiteNoise from
# kolibri without creating a circular dependency.

logger = logging.getLogger(__name__)

Uri = autoclass("android.net.Uri")


class AndroidDynamicWhiteNoise(DynamicWhiteNoise):
    @staticmethod
    def encode_root(root):
        if urlparse(root).scheme:
            root = "/" + root
        return root

    @staticmethod
    def decode_root(root):
        decoded = root.lstrip("/")
        if urlparse(decoded).scheme:
            root = decoded
        return root

    @classmethod
    def decode_locations(cls, locations):
        return [(prefix, cls.decode_root(root)) for prefix, root in locations]

    @cached_property
    def dynamic_finder(self):
        return AndroidFileFinder(self.decode_locations(self._dynamic_locations or []))

    def find_and_cache_dynamic_file(self, url, remote_baseurl):
        path = self.get_dynamic_path(url)
        if path:
            file_stat = stat_file(path)
            # Only try to do matches for regular files.
            if stat.S_ISREG(file_stat.st_mode):
                stat_cache = {path: file_stat}
                for ext in compressed_file_extensions:
                    try:
                        comp_path = "{}.{}".format(path, ext)
                        stat_cache[comp_path] = stat_file(comp_path)
                    except (IOError, OSError):
                        pass
                self.add_file_to_dictionary(url, path, stat_cache=stat_cache)
            return self.files.get(url)
        else:
            return super().find_and_cache_dynamic_file(url, remote_baseurl)

    def _create_end_range_static_file(self, path, headers, **kwargs):
        logger.info(f"Creating EndRangeStaticFile for path {path}")
        return AndroidEndRangeStaticFile(path, headers, **kwargs)

    def _create_streaming_range_static_file(self, path, headers, remote_url, **kwargs):
        # TODO: We should probably implement this.
        logger.info(f"Creating StreamingStaticFile for path {path}")
        raise NotImplementedError()


class AndroidFileFinder(FileFinder):
    @cached_property
    def document_roots(self):
        # Create a set of location roots that are DocumentsProvider URIs
        # to avoid calling isDocumentUri() repeatedly.
        result = set()
        for _, root in self.locations:
            if is_document_uri(root):
                result.add(root)
        return result

    def find_location(self, root, path, prefix=None):
        """
        Finds a requested static file in a location, returning the found
        absolute path (or ``None`` if no match).
        Vendored from Django to handle being passed a URL path instead of a file path.
        """

        logger.info(f"Finding path {path} in root {root}")

        document_uri = self.__get_document_uri(root, path, prefix=prefix)

        if document_uri and document_exists(document_uri):
            return document_uri.toString()
        else:
            return super().find_location(root, path, prefix=prefix)

    def __get_document_uri(self, root, path, prefix=None):
        if root not in self.document_roots:
            return None

        if prefix:
            prefix = prefix + "/"
            if not path.startswith(prefix):
                return None
            path = path[len(prefix) :]

        return document_tree_join(Uri.parse(root), path)


class AndroidEndRangeStaticFile(EndRangeStaticFile):
    def get_response(self, method, request_headers):
        if method not in ("GET", "HEAD"):
            return NOT_ALLOWED_RESPONSE
        if self.is_not_modified(request_headers):
            return self.not_modified_response
        path, headers = self.get_path_and_headers(request_headers)
        if method != "HEAD":
            file_handle = open_file(path, "rb")
        else:
            file_handle = None
        range_header = request_headers.get("HTTP_RANGE")
        if range_header:
            try:
                return self.get_range_response(range_header, headers, file_handle)
            except ValueError:
                # If we can't interpret the Range request for any reason then
                # just ignore it and return the standard response (this
                # behaviour is allowed by the spec)
                pass
        return Response(HTTPStatus.OK, headers, file_handle)
