import os
import re
from functools import cache

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from i18n import get_string
from jnius import autoclass
from jnius import cast


def get_timezone_name():
    Timezone = autoclass("java.util.TimeZone")
    return Timezone.getDefault().getDisplayName()


def get_version_name():
    PythonContext = autoclass("org.kivy.android.PythonContext")
    return PythonContext.getVersionName()


def get_node_id():
    PythonContext = autoclass("org.kivy.android.PythonContext")
    return PythonContext.getNodeId()


@cache
def get_context():
    PythonContext = autoclass("org.kivy.android.PythonContext")
    return PythonContext.get()


@cache
def get_external_files_dir():
    PythonContext = autoclass("org.kivy.android.PythonContext")
    return PythonContext.getExternalFilesDir()


# TODO: check for storage availability, allow user to chose sd card or internal
def get_home_folder():
    return os.path.join(get_external_files_dir(), "KOLIBRI_DATA")


class AndroidValueCache:
    """
    A helper class to cache values to disk that might otherwise be expensive to
    query from Android APIs, and that we are pretty sure will be static.
    """

    __slots__ = "_storage_path", "_dict"

    def __init__(self):
        self._dict = {}
        self._storage_path = None

    def _load(self, key):
        try:
            with open(os.path.join(self._storage_path, key)) as f:
                self._dict[key] = f.read().strip()
        except FileNotFoundError:
            pass

    def _ensure_storage(self):
        if self._storage_path is None:
            # Store this in the parent of the Kolibri home dir to prevent collisions.
            self._storage_path = os.path.join(get_external_files_dir(), ".value_cache")
            if not os.path.exists(self._storage_path):
                os.mkdir(self._storage_path)

    def get(self, key):
        self._ensure_storage()
        if key not in self._dict:
            self._load(key)
        return self._dict.get(key)

    def set(self, key, value):
        self._ensure_storage()
        self._dict[key] = value
        self._save(key)

    def _save(self, key):
        with open(os.path.join(self._storage_path, key), "w") as f:
            f.write(self._dict[key])


value_cache = AndroidValueCache()


def send_whatsapp_message(msg):
    share_by_intent(message=msg, app="com.whatsapp")


def share_by_intent(path=None, filename=None, message=None, app=None, mimetype=None):

    assert (
        path or message or filename
    ), "Must provide either a path, a filename, or a msg to share"
    AndroidString = autoclass("java.lang.String")
    Context = autoclass("android.content.Context")
    File = autoclass("java.io.File")
    FileProvider = autoclass("android.support.v4.content.FileProvider")
    Intent = autoclass("android.content.Intent")

    sendIntent = Intent()
    sendIntent.setAction(Intent.ACTION_SEND)
    if path:
        uri = FileProvider.getUriForFile(
            Context.getApplicationContext(),
            "org.learningequality.Kolibri.fileprovider",
            File(path),
        )
        parcelable = cast("android.os.Parcelable", uri)
        sendIntent.putExtra(Intent.EXTRA_STREAM, parcelable)
        sendIntent.setType(AndroidString(mimetype or "*/*"))
        sendIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    if message:
        if not path:
            sendIntent.setType(AndroidString(mimetype or "text/plain"))
        sendIntent.putExtra(Intent.EXTRA_TEXT, AndroidString(message))
    if app:
        sendIntent.setPackage(AndroidString(app))
    sendIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    get_context().startActivity(sendIntent)


def get_signature_key_issuer():
    PythonContext = autoclass("org.kivy.android.PythonContext")
    signature = PythonContext.getCertificateInfo()
    cert = x509.load_der_x509_certificate(
        signature, default_backend()
    )

    return cert.issuer.rfc4514_string()


def get_signature_key_issuing_organization():
    cache_key = "SIGNATURE_KEY_ORG"
    value = value_cache.get(cache_key)
    if value is None:
        signer = get_signature_key_issuer()
        orgs = re.findall(r"\bO=([^,]+)", signer)
        value = orgs[0] if orgs else ""
        value_cache.set(cache_key, value)
    else:
        print("Using cached value for issuing org")
    return value


def get_dummy_user_name():
    cache_key = "DUMMY_USER_NAME"
    value = value_cache.get(cache_key)
    if value is None:
        PythonContext = autoclass("org.kivy.android.PythonContext")
        currentLocale = PythonContext.getLocale()
        value = get_string("Learner", currentLocale)
        value_cache.set(cache_key, value)
    return value


def is_active_network_metered():
    PythonContext = autoclass("org.kivy.android.PythonContext")
    return PythonContext.isActiveNetworkMetered()
