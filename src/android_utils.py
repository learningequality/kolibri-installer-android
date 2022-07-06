import json
import logging
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from android.permissions import check_permission
from android.permissions import Permission
from android.permissions import request_permissions
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from jnius import autoclass
from jnius import cast
from jnius import jnius


logger = logging.getLogger(__name__)

AndroidString = autoclass("java.lang.String")
Context = autoclass("android.content.Context")
Environment = autoclass("android.os.Environment")
File = autoclass("java.io.File")
FileProvider = autoclass("android.support.v4.content.FileProvider")
Intent = autoclass("android.content.Intent")
NotificationBuilder = autoclass("android.app.Notification$Builder")
NotificationManager = autoclass("android.app.NotificationManager")
PackageManager = autoclass("android.content.pm.PackageManager")
PendingIntent = autoclass("android.app.PendingIntent")
PythonActivity = autoclass("org.kivy.android.PythonActivity")
Settings = autoclass("android.provider.Settings")
Timezone = autoclass("java.util.TimeZone")
Uri = autoclass("android.net.Uri")

ANDROID_VERSION = autoclass("android.os.Build$VERSION")
RELEASE = ANDROID_VERSION.RELEASE
SDK_INT = ANDROID_VERSION.SDK_INT


USB_CONTENT_FLAG_FILENAME = "usb_content_flag"


# Path.is_relative_to only on python 3.9+.
if not hasattr(Path, "is_relative_to"):

    def _path_is_relative_to(self, *other):
        try:
            self.relative_to(*other)
            return True
        except ValueError:
            return False

    Path.is_relative_to = _path_is_relative_to


def is_service_context():
    return "PYTHON_SERVICE_ARGUMENT" in os.environ


def get_service():
    assert (
        is_service_context()
    ), "Cannot get service, as we are not in a service context."
    PythonService = autoclass("org.kivy.android.PythonService")
    return PythonService.mService


def get_timezone_name():
    return Timezone.getDefault().getDisplayName()


def start_service(service_name, service_args=None):
    service_args = service_args or {}
    service = autoclass("org.endlessos.Key.Service{}".format(service_name.title()))
    service.start(PythonActivity.mActivity, json.dumps(dict(service_args)))


def get_service_args():
    assert (
        is_service_context()
    ), "Cannot get service args, as we are not in a service context."
    return json.loads(os.environ.get("PYTHON_SERVICE_ARGUMENT") or "{}")


def get_package_info(package_name="org.endlessos.Key", flags=0):
    return get_activity().getPackageManager().getPackageInfo(package_name, flags)


def get_version_name():
    return get_package_info().versionName


def get_activity():
    if is_service_context():
        return cast("android.app.Service", get_service())
    else:
        return PythonActivity.mActivity


def is_app_installed(app_id):

    manager = get_activity().getPackageManager()

    try:
        manager.getPackageInfo(app_id, PackageManager.GET_ACTIVITIES)
    except jnius.JavaException:
        return False

    return True


# TODO: check for storage availability, allow user to chose sd card or internal
def get_home_folder():
    kolibri_home_file = get_activity().getExternalFilesDir(None)
    return os.path.join(kolibri_home_file.toString(), "KOLIBRI_DATA")


def get_endless_key_paths():
    def _get_directory_path(volume):
        if SDK_INT < 30:
            uuid = volume.getUuid()
            if uuid is None:
                return None
            return os.path.join("/storage", uuid)
        else:
            directory_file = volume.getDirectory()
            if directory_file is None:
                return None
            return directory_file.toString()

    storageManager = get_activity().getSystemService(Context.STORAGE_SERVICE)
    volumesList = storageManager.getStorageVolumes()
    for i in range(volumesList.size()):
        volume = volumesList.get(i)
        state = volume.getState()
        is_removable = volume.isRemovable()
        directory_path = _get_directory_path(volume)
        logger.debug(
            f"Found volume UUID: {volume.getUuid()} state: {state} "
            f" is removable: {is_removable} mount path: {directory_path}"
        )
        if is_removable and state == "mounted" and directory_path is not None:
            kolibri_data_path = os.path.join(directory_path, "KOLIBRI_DATA")
            content_path = os.path.join(kolibri_data_path, "content")
            db_path = os.path.join(
                kolibri_data_path, "preseeded_kolibri_home", "db.sqlite3"
            )
            if os.path.exists(content_path) and os.path.exists(db_path):
                return {"content_path": content_path, "db_path": db_path}
    return None


def provision_endless_key_database(endless_key_paths):
    if endless_key_paths is not None:
        home_folder = get_home_folder()
        if os.path.exists(os.path.join(home_folder, "db.sqlite3")):
            logger.debug("EK database already exists, skipping.")
            return
        if not os.path.exists(home_folder):
            os.mkdir(home_folder)
        if has_all_files_access():
            shutil.copy(endless_key_paths["db_path"], home_folder)
            logger.debug("EK database provisioned.")
        else:
            logger.debug("EK database found in external storage bu user didn't allow.")


def prompt_all_files_access():
    if SDK_INT < 30:
        request_permissions([Permission.WRITE_EXTERNAL_STORAGE])
    else:
        askIntent = Intent(
            Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
            Uri.parse("package:org.endlessos.Key"),
        )
        get_activity().startActivity(askIntent)


def has_all_files_access():
    if SDK_INT < 30:
        return check_permission("android.permission.WRITE_EXTERNAL_STORAGE")
    else:
        return Environment.isExternalStorageManager()


def ask_all_files_access():
    timeout = False
    if not has_all_files_access():
        prompt_all_files_access()
    start_time = datetime.now()
    while not has_all_files_access() and not timeout:
        time.sleep(0.5)
        delta_time = datetime.now() - start_time
        # FIXME: handle user denying access to external storage
        # from the UI. For now just give up after 2 minutes.
        timeout = delta_time.total_seconds() > 120

    return not timeout


def send_whatsapp_message(msg):
    share_by_intent(message=msg, app="com.whatsapp")


def share_by_intent(path=None, filename=None, message=None, app=None, mimetype=None):

    assert (
        path or message or filename
    ), "Must provide either a path, a filename, or a msg to share"

    sendIntent = Intent()
    sendIntent.setAction(Intent.ACTION_SEND)
    if path:
        uri = FileProvider.getUriForFile(
            Context.getApplicationContext(),
            "org.endlessos.Key.fileprovider",
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
    signature = get_package_info(flags=PackageManager.GET_SIGNATURES).signatures[0]
    cert = x509.load_der_x509_certificate(
        signature.toByteArray().tostring(), default_backend()
    )

    return cert.issuer.rfc4514_string()


def get_signature_key_issuing_organization():
    signer = get_signature_key_issuer()
    orgs = re.findall(r"\bO=([^,]+)", signer)
    return orgs[0] if orgs else ""


def is_external_app_path(path):
    path = Path(path).resolve()
    activity = get_activity()

    for app_dir in activity.getExternalFilesDirs(None):
        if app_dir is None or not Environment.isExternalStorageRemovable(app_dir):
            continue
        if path.is_relative_to(Path(app_dir.toString())):
            return True
    return False


def _android11_ext_storage_workarounds():
    """Workarounds for Android 11 external storage bugs

    See https://issuetracker.google.com/issues/232290073 for details.
    """
    if RELEASE != "11":
        return

    from os import access as _os_access
    from os import listdir as _os_listdir

    logger.info("Applying Android 11 workarounds")

    def access(path, mode, *, dir_fd=None, effective_ids=False, follow_symlinks=True):
        can_access = _os_access(
            path,
            mode,
            dir_fd=dir_fd,
            effective_ids=effective_ids,
            follow_symlinks=follow_symlinks,
        )

        # Workaround a bug on Android 11 where access with W_OK on an
        # external app private directory returns EACCESS even though
        # those directories are obviously writable for the app.
        if (
            not can_access
            # If dir_fd is set, we can't determine the full path.
            and dir_fd is None
            # Both effective_ids and follow_symlinks use faccessat. For
            # now don't bother handling those.
            and not effective_ids
            and follow_symlinks
            # Finally, match on a writable test for an external directory.
            and mode & os.W_OK
            and os.path.isdir(path)
            and is_external_app_path(path)
        ):
            logger.warning(
                "Forcing os.access to True for writable test on external app directory %s",
                path,
            )
            can_access = True

        return can_access

    def listdir(path=None):
        try:
            return _os_listdir(path)
        except PermissionError as err:
            # If given a path (not an open directory fd) in external app
            # storage, ignore PermissionError and return an empty list
            # to workaround an Android bug where opendir returns
            # EACCESS. The empty list is not useful, but it's better
            # than failing in a case that shouldn't.
            if path is None:
                path = "."
            if isinstance(path, (str, bytes, os.PathLike)) and is_external_app_path(
                path
            ):
                logger.warning(
                    "Ignoring os.listdir error %s on external app directory",
                    err,
                )
                return []

            raise

    os.access = access
    os.listdir = listdir


def apply_android_workarounds():
    _android11_ext_storage_workarounds()


class StartupState:
    FIRST_TIME = 1
    USB = 2
    NETWORK = 3

    @classmethod
    def get_current_state(cls):
        """
        Returns the current app startup state that could be:
            * FIRST_TIME
            * USB
            * NETWORK
        """
        home = get_home_folder()

        # if there's no home folder this is the first launch
        db_path = os.path.join(home, "db.sqlite3")
        if not os.path.exists(db_path):
            return cls.FIRST_TIME

        # If the usb content flag file exists in the home, the app has been
        # started with an Endless Key USB
        usb_content_flag_file = os.path.join(home, USB_CONTENT_FLAG_FILENAME)
        if os.path.exists(usb_content_flag_file):
            return cls.USB

        # in other case, the app is initialized but with content downloaded
        # using the network
        return cls.NETWORK

    @classmethod
    def create_usb_content_flag(cls):
        home = get_home_folder()
        usb_content_flag_file = os.path.join(home, USB_CONTENT_FLAG_FILENAME)
        if not os.path.exists(usb_content_flag_file):
            f = open(usb_content_flag_file, "w")
            f.close()
