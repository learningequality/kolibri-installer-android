import json
import os
import re
import socket

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from jnius import autoclass
from jnius import cast


def is_service_context():
    return "PYTHON_SERVICE_ARGUMENT" in os.environ


def get_service():
    assert (
        is_service_context()
    ), "Cannot get service, as we are not in a service context."
    PythonService = autoclass("org.kivy.android.PythonService")
    return PythonService.mService


def get_timezone_name():
    Timezone = autoclass("java.util.TimeZone")
    return Timezone.getDefault().getDisplayName()


def start_service(service_name, service_args=None):
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    service_args = service_args or {}
    service = autoclass(
        "org.learningequality.Kolibri.Service{}".format(service_name.title())
    )
    service.start(PythonActivity.mActivity, json.dumps(dict(service_args)))


def get_service_args():
    assert (
        is_service_context()
    ), "Cannot get service args, as we are not in a service context."
    return json.loads(os.environ.get("PYTHON_SERVICE_ARGUMENT") or "{}")


def get_package_info(package_name="org.learningequality.Kolibri", flags=0):
    return get_activity().getPackageManager().getPackageInfo(package_name, flags)


def get_version_name():
    return get_package_info().versionName


ACTIVITY = None


def get_activity():
    global ACTIVITY
    if ACTIVITY is None:
        if is_service_context():
            ACTIVITY = cast("android.app.Service", get_service())
        else:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            ACTIVITY = PythonActivity.mActivity
    return ACTIVITY


HOME_FILE = None


def get_external_files_dir():
    global HOME_FILE
    if HOME_FILE is None:
        HOME_FILE = get_activity().getExternalFilesDir(None).toString()
    return HOME_FILE


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
    get_activity().startActivity(sendIntent)


def make_service_foreground(title, message):
    service = get_service()
    Drawable = autoclass("{}.R$drawable".format(service.getPackageName()))
    app_context = service.getApplication().getApplicationContext()

    ANDROID_VERSION = autoclass("android.os.Build$VERSION")
    SDK_INT = ANDROID_VERSION.SDK_INT
    AndroidString = autoclass("java.lang.String")
    Context = autoclass("android.content.Context")
    Intent = autoclass("android.content.Intent")
    NotificationBuilder = autoclass("android.app.Notification$Builder")
    NotificationManager = autoclass("android.app.NotificationManager")
    PendingIntent = autoclass("android.app.PendingIntent")
    PythonActivity = autoclass("org.kivy.android.PythonActivity")

    if SDK_INT >= 26:
        NotificationChannel = autoclass("android.app.NotificationChannel")
        notification_service = cast(
            NotificationManager,
            get_activity().getSystemService(Context.NOTIFICATION_SERVICE),
        )
        channel_id = get_activity().getPackageName()
        app_channel = NotificationChannel(
            channel_id,
            "Kolibri Background Server",
            NotificationManager.IMPORTANCE_DEFAULT,
        )
        notification_service.createNotificationChannel(app_channel)
        notification_builder = NotificationBuilder(app_context, channel_id)
    else:
        notification_builder = NotificationBuilder(app_context)

    notification_builder.setContentTitle(AndroidString(title))
    notification_builder.setContentText(AndroidString(message))
    notification_intent = Intent(app_context, PythonActivity)
    notification_intent.setFlags(
        Intent.FLAG_ACTIVITY_CLEAR_TOP
        | Intent.FLAG_ACTIVITY_SINGLE_TOP
        | Intent.FLAG_ACTIVITY_NEW_TASK
    )
    notification_intent.setAction(Intent.ACTION_MAIN)
    notification_intent.addCategory(Intent.CATEGORY_LAUNCHER)
    intent = PendingIntent.getActivity(service, 0, notification_intent, 0)
    notification_builder.setContentIntent(intent)
    notification_builder.setSmallIcon(Drawable.icon)
    notification_builder.setAutoCancel(True)
    new_notification = notification_builder.getNotification()
    service.startForeground(1, new_notification)


def get_signature_key_issuer():
    PackageManager = autoclass("android.content.pm.PackageManager")
    signature = get_package_info(flags=PackageManager.GET_SIGNATURES).signatures[0]
    cert = x509.load_der_x509_certificate(
        signature.toByteArray().tostring(), default_backend()
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


def next_free_port(port=9000, max_port=65535):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while port <= max_port:
        try:
            sock.bind(("", port))
            sock.close()
            return port
        except OSError:
            port += 1
    raise IOError("No free ports")


def get_main_port():
    port_cache_key = "PORT"
    from_cache = True
    port = value_cache.get(port_cache_key)
    if port is None:
        from_cache = False
        port = next_free_port()
        value_cache.set(port_cache_key, str(port))
    return from_cache, int(port)
