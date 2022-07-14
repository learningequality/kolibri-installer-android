import logging
import os
import re
import stat
from wsgiref.headers import Headers

from android_utils import get_activity
from android_utils import open_file
from django.contrib.staticfiles import finders
from kolibri.utils import kolibri_whitenoise
from kolibri.utils.kolibri_whitenoise import compressed_file_extensions
from kolibri.utils.kolibri_whitenoise import EndRangeStaticFile
from kolibri.utils.kolibri_whitenoise import FileFinder
from kolibri.utils.kolibri_whitenoise import NOT_FOUND
from whitenoise import WhiteNoise
from whitenoise.httpstatus_backport import HTTPStatus
from whitenoise.responders import MissingFileError
from whitenoise.responders import NOT_ALLOWED_RESPONSE
from whitenoise.responders import Response
from whitenoise.string_utils import decode_path_info

logger = logging.getLogger(__name__)


class AndroidEndRangeStaticFile(EndRangeStaticFile):
    def __init__(self, path, headers, context, content_resolver, **kwargs):
        super().__init__(path, headers, **kwargs)
        self.context = context
        self.content_resolver = content_resolver

    def get_response(self, method, request_headers):
        if method not in ("GET", "HEAD"):
            return NOT_ALLOWED_RESPONSE
        if self.is_not_modified(request_headers):
            return self.not_modified_response
        path, headers = self.get_path_and_headers(request_headers)
        if method != "HEAD":
            file_handle = open_file(
                path, "rb", context=self.context, content_resolver=self.content_resolver
            )
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


class DynamicWhiteNoise(WhiteNoise):
    index_file = "index.html"

    def __init__(
        self, application, dynamic_locations=None, static_prefix=None, **kwargs
    ):
        whitenoise_settings = {
            # Use 120 seconds as the default cache time for static assets
            "max_age": 120,
            # Add a test for any file name that contains a semantic version number
            # or a 32 digit number (assumed to be a file hash)
            # these files will be cached indefinitely
            "immutable_file_test": r"((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)|[a-f0-9]{32})",
            "autorefresh": os.environ.get("KOLIBRI_DEVELOPER_MODE", False),
        }
        kwargs.update(whitenoise_settings)
        super(DynamicWhiteNoise, self).__init__(application, **kwargs)
        self.context = get_activity()
        self.content_resolver = self.context.getContentResolver()
        self.dynamic_finder = FileFinder(dynamic_locations or [])
        # Generate a regex to check if a path matches one of our dynamic
        # location prefixes
        self.dynamic_check = (
            re.compile("^({})".format("|".join(self.dynamic_finder.prefixes)))
            if self.dynamic_finder.prefixes
            else None
        )
        if static_prefix is not None and not static_prefix.endswith("/"):
            raise ValueError("Static prefix must end in '/'")
        self.static_prefix = static_prefix

    def __call__(self, environ, start_response):
        path = decode_path_info(environ.get("PATH_INFO", ""))
        if self.autorefresh:
            static_file = self.find_file(path)
        else:
            static_file = self.files.get(path)
        if static_file is None:
            static_file = self.find_and_cache_dynamic_file(path)
        if static_file is None:
            return self.application(environ, start_response)
        return self.serve(static_file, environ, start_response)

    def find_and_cache_dynamic_file(self, url):
        path = self.get_dynamic_path(url)
        if path:
            file_stat = os.stat(path)
            # Only try to do matches for regular files.
            if stat.S_ISREG(file_stat.st_mode):
                stat_cache = {path: os.stat(path)}
                for ext in compressed_file_extensions:
                    try:
                        comp_path = "{}.{}".format(path, ext)
                        stat_cache[comp_path] = os.stat(comp_path)
                    except (IOError, OSError):
                        pass
                self.add_file_to_dictionary(url, path, stat_cache=stat_cache)
        elif (
            path is None
            and self.static_prefix is not None
            and url.startswith(self.static_prefix)
        ):
            self.files[url] = NOT_FOUND
        return self.files.get(url)

    def get_dynamic_path(self, url):
        if self.static_prefix is not None and url.startswith(self.static_prefix):
            return finders.find(url[len(self.static_prefix) :])
        if self.dynamic_check is not None and self.dynamic_check.match(url):
            return self.dynamic_finder.find(url)

    def candidate_paths_for_url(self, url):
        paths = super(DynamicWhiteNoise, self).candidate_paths_for_url(url)
        for path in paths:
            yield path
        path = self.get_dynamic_path(url)
        if path:
            yield path

    def get_static_file(self, path, url, stat_cache=None):
        """
        Vendor this function from source to substitute in our
        own StaticFile class that can properly handle ranges.
        """
        # Optimization: bail early if file does not exist
        if stat_cache is None and not os.path.exists(path):
            raise MissingFileError(path)
        headers = Headers([])
        self.add_mime_headers(headers, path, url)
        self.add_cache_headers(headers, path, url)
        if self.allow_all_origins:
            headers["Access-Control-Allow-Origin"] = "*"
        if self.add_headers_function:
            self.add_headers_function(headers, path, url)
        return AndroidEndRangeStaticFile(
            path,
            headers.items(),
            self.context,
            self.content_resolver,
            stat_cache=stat_cache,
            encodings={"gzip": path + ".gz", "br": path + ".br"},
        )


def monkeypatch_whitenoise():
    logger.info("Applying DynamicWhiteNoise workarounds")
    kolibri_whitenoise.DynamicWhiteNoise = DynamicWhiteNoise
