import errno
import json
import logging
import os
import re
import shutil
import stat
import sys
from contextlib import closing
from enum import auto
from enum import Enum
from functools import partial
from pathlib import Path
from queue import Queue
from urllib.parse import urlparse

from android.activity import bind
from android.activity import unbind
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from jnius import autoclass
from jnius import cast
from jnius import JavaException
from jnius import jnius

from .runnable import Runnable


logger = logging.getLogger(__name__)

Activity = autoclass("android.app.Activity")
AndroidString = autoclass("java.lang.String")
BuildConfig = autoclass("org.endlessos.Key.BuildConfig")
Context = autoclass("android.content.Context")
Document = autoclass("android.provider.DocumentsContract$Document")
DocumentsContract = autoclass("android.provider.DocumentsContract")
Environment = autoclass("android.os.Environment")
File = autoclass("java.io.File")
FileProvider = autoclass("androidx.core.content.FileProvider")
FirebaseAnalytics = autoclass("com.google.firebase.analytics.FirebaseAnalytics")
FirebaseCrashlytics = autoclass("com.google.firebase.crashlytics.FirebaseCrashlytics")
Intent = autoclass("android.content.Intent")
Log = autoclass("android.util.Log")
NotificationBuilder = autoclass("android.app.Notification$Builder")
NotificationManager = autoclass("android.app.NotificationManager")
PackageManager = autoclass("android.content.pm.PackageManager")
PendingIntent = autoclass("android.app.PendingIntent")
PythonActivity = autoclass("org.kivy.android.PythonActivity")
Secure = autoclass("android.provider.Settings$Secure")
SystemProperties = autoclass("android.os.SystemProperties")
Timezone = autoclass("java.util.TimeZone")
Toast = autoclass("android.widget.Toast")
Uri = autoclass("android.net.Uri")
FirebaseApp = autoclass("com.google.firebase.FirebaseApp")

ANDROID_VERSION = autoclass("android.os.Build$VERSION")
RELEASE = ANDROID_VERSION.RELEASE
SDK_INT = ANDROID_VERSION.SDK_INT

# Chrome OS constant UUID for the My Files volume. In Android this shows
# up as a removable volume, which throws off the detection of USB
# devices. Below it's filtered out from removable storage searches.
#
# https://source.chromium.org/chromium/chromium/src/+/main:ash/components/arc/volume_mounter/arc_volume_mounter_bridge.cc;l=51
MY_FILES_UUID = "0000000000000000000000000000CAFEF00D2019"

# System property configuring Analytics and Crashlytics.
ANALYTICS_SYSPROP = "debug.org.endlessos.key.analytics"


USB_CONTENT_FLAG_FILENAME = "usb_content_flag"


# Globals to keep references to Java objects
# See https://github.com/Android-for-Python/Android-for-Python-Users#pyjnius-memory-management
_choose_directory_intent = None
_notification_builder = None
_notification_intent = None
_send_intent = None

# Path.is_relative_to only on python 3.9+.
if not hasattr(Path, "is_relative_to"):

    def _path_is_relative_to(self, *other):
        try:
            self.relative_to(*other)
            return True
        except ValueError:
            return False

    Path.is_relative_to = _path_is_relative_to


class PermissionsCancelledError(Exception):
    pass


class PermissionsWrongFolderError(Exception):
    pass


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


def get_android_node_id():
    return Secure.getString(get_activity().getContentResolver(), Secure.ANDROID_ID)


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


def get_preferences():
    activity = get_activity()
    return activity.getSharedPreferences(
        activity.getPackageName(), Activity.MODE_PRIVATE
    )


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


def get_log_root():
    """Root path for log files"""
    return os.path.join(get_home_folder(), "logs")


def get_initial_content_pack_id():
    preferences = get_preferences()
    pack_id = preferences.getString("initial_content_pack_id", None)
    logger.debug("Initial content pack ID: %s", pack_id)
    return pack_id


def get_endless_key_uris():
    preferences = get_preferences()
    content_uri = preferences.getString("key_content_uri", None)
    db_uri = preferences.getString("key_db_uri", None)
    logger.debug("Stored Endless Key URIs: content=%s, db=%s", content_uri, db_uri)

    if content_uri and db_uri:
        return {"content": content_uri, "db": db_uri}

    return None


def choose_endless_key_uris():
    """Call the file picker and validate the chosen folder"""
    activity = get_activity()
    data_uri = choose_directory(activity, msg="Select the KOLIBRI_DATA folder")

    if data_uri is None:
        logger.info("User cancelled Endless Key selection")
        raise PermissionsCancelledError()

    tree_uri = Uri.parse(data_uri)
    tree_doc_id = DocumentsContract.getTreeDocumentId(tree_uri)
    tree_doc_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, tree_doc_id)

    content_resolver = activity.getContentResolver()
    tree_files = document_tree_list_files(tree_doc_uri, content_resolver)

    content = tree_files.get("content")
    if not content or content["mime_type"] != Document.MIME_TYPE_DIR:
        logger.info("The selected folder does not contain a content folder")
        raise PermissionsWrongFolderError()
    content_uri = content["uri"].toString()

    preseeded_home = tree_files.get("preseeded_kolibri_home")
    if not preseeded_home or preseeded_home["mime_type"] != Document.MIME_TYPE_DIR:
        logger.info(
            "The selected folder does not contain a preseeded_kolibri_home folder"
        )
        raise PermissionsWrongFolderError()
    preseeded_home_files = document_tree_list_files(
        preseeded_home["uri"], content_resolver
    )

    db = preseeded_home_files.get("db.sqlite3")
    if not db or ["mime_type"] == Document.MIME_TYPE_DIR:
        logger.info(
            "The selected folder does not contain a db.sqlite3 file in the preseeded_kolibri_home folder"
        )
        raise PermissionsWrongFolderError()
    db_uri = db["uri"].toString()

    logger.info("Found Endless Key URIs: content=%s, db=%s", content_uri, db_uri)
    return {"content": content_uri, "db": db_uri}


def set_endless_key_uris(endless_key_uris):
    if endless_key_uris is None:
        return

    content_uri = endless_key_uris["content"]
    db_uri = endless_key_uris["db"]
    if content_uri and db_uri:
        logger.info("Setting Endless Key URIs: content=%s, db=%s", content_uri, db_uri)
        editor = get_preferences().edit()
        editor.putString("key_content_uri", content_uri)
        editor.putString("key_db_uri", db_uri)
        editor.commit()


def is_document_uri(path, context=None):
    if not urlparse(path).scheme:
        return False

    uri = Uri.parse(path)
    if context is None:
        context = get_activity()
    return DocumentsContract.isDocumentUri(context, uri)


def document_opener(path, flags, content_resolver=None):
    """File opener function for use with DocumentsContract"""
    # Convert from open flags to Java File modes.
    #
    # https://developer.android.com/reference/android/os/ParcelFileDescriptor#parseMode(java.lang.String)
    logger.debug("Requested opening %s with flags %s", path, bin(flags))
    if flags & os.O_RDWR:
        mode = "rw"
    elif flags & os.O_WRONLY:
        mode = "w"
    else:
        mode = "r"

    if flags & os.O_APPEND:
        mode += "a"
    if flags & os.O_TRUNC:
        mode += "t"

    # Get the file descriptor for the document. Note that neither the
    # AssetFileDescriptor nor the ParcelFileDescriptor need to be closed
    # since the raw file descriptor is detached.
    if content_resolver is None:
        content_resolver = get_activity().getContentResolver()
    uri = Uri.parse(path)
    afd = content_resolver.openAssetFileDescriptor(uri, mode)
    pfd = afd.getParcelFileDescriptor()
    return pfd.detachFd()


def open_document(uri, mode="r", **kwargs):
    """open wrapper using DocumentsContract opener"""
    kwargs["opener"] = document_opener
    return open(uri, mode=mode, **kwargs)


def open_file(path, mode="r", context=None, content_resolver=None, **kwargs):
    if context is None:
        context = get_activity()
    if content_resolver is None:
        content_resolver = context.getContentResolver()
    if is_document_uri(path, context):
        kwargs["opener"] = partial(
            document_opener,
            content_resolver=content_resolver,
        )
    return open(path, mode=mode, **kwargs)


def stat_document(uri, content_resolver=None):
    if content_resolver is None:
        content_resolver = get_activity().getContentResolver()

    # Like with document_exists(), assume that
    # java.lang.IllegalArgumentException means the file doesn't exist.
    columns = (
        Document.COLUMN_DOCUMENT_ID,
        Document.COLUMN_SIZE,
        Document.COLUMN_LAST_MODIFIED,
    )
    try:
        with closing(content_resolver.query(uri, columns, None, None)) as cursor:
            if not cursor.moveToFirst():
                # Emulate ENOENT from os.stat on missing file.
                raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), uri)

            doc_id = cursor.getString(0)
            size = cursor.getLong(1)
            last_modified = cursor.getLong(2)
    except JavaException as err:
        if err.classname == "java.lang.IllegalArgumentException":
            # Emulate ENOENT from os.stat on missing file.
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), uri
            ) from err
        raise

    # Treat this as a regular, non-executable file.
    mode = 0o0644 | stat.S_IFREG

    # Make up a unique inode number just in case the caller is trying to
    # make a device+inode set. Since the document ID is unique, convert
    # it to an integer.
    inode = int.from_bytes(doc_id.encode("utf-8"), sys.byteorder)

    # COLUMN_LAST_MODIFIED is in milliseconds while the stat timestamps
    # are in seconds.
    mtime = int(last_modified / 1000)

    # Fill in a stat_result as well as possible. See
    # https://docs.python.org/3/library/os.html#os.stat_result for the
    # order of the tuple entries.
    return os.stat_result(
        (
            mode,  # st_mode
            inode,  # st_ino
            0,  # st_dev
            1,  # st_nlink
            0,  # st_uid
            0,  # st_gid
            size,  # st_size
            mtime,  # st_atime
            mtime,  # st_mtime
            mtime,  # st_ctime
        )
    )


def stat_file(path, context=None, content_resolver=None):
    if context is None:
        context = get_activity()
    if content_resolver is None:
        content_resolver = context.getContentResolver()
    if is_document_uri(path, context):
        return stat_document(Uri.parse(path), content_resolver)
    return os.stat(path)


def document_exists(uri, content_resolver=None):
    if content_resolver is None:
        content_resolver = get_activity().getContentResolver()

    # It seems that if you query for a non-existent document, an
    # IllegalArgumentException will be thrown rather than returning
    # empty results. Since you can't tell if that's a rethrown
    # FileNotFoundException without scraping the message, just assume
    # that's what IllegalArgumentException means.
    #
    # DocumentFile.exists() ignores any exception, so this isn't
    # unfounded.
    columns = (Document.COLUMN_DOCUMENT_ID,)
    try:
        with closing(content_resolver.query(uri, columns, None, None)) as cursor:
            return cursor.getCount() > 0
    except JavaException as err:
        if err.classname == "java.lang.IllegalArgumentException":
            return False
        raise


def document_tree_join(tree_doc_uri, path, content_resolver=None):
    if os.path.isabs(path):
        raise ValueError("path must be relative")

    if content_resolver is None:
        content_resolver = get_activity().getContentResolver()

    # This is almost certainly wrong since the document ID is supposed
    # to be an opaque string used by the DocumentsProvider. However, the
    # document ID *is* the directory path, so just join the desired path
    # to it.
    tree_doc_id = DocumentsContract.getDocumentId(tree_doc_uri)
    path_id = os.path.join(tree_doc_id, path)
    logger.debug(
        "Resolved document tree ID %s path %s ID to %s", tree_doc_id, path, path_id
    )

    # Now convert the path document ID to a document URI.
    path_uri = DocumentsContract.buildDocumentUriUsingTree(tree_doc_uri, path_id)
    logger.debug(
        "Resolved path %s in document tree %s to URI %s",
        path,
        tree_doc_uri.toString(),
        path_uri.toString(),
    )
    return path_uri


def document_tree_list_files(tree_doc_uri, content_resolver=None):
    if content_resolver is None:
        content_resolver = get_activity().getContentResolver()

    tree_doc_id = DocumentsContract.getDocumentId(tree_doc_uri)
    children_uri = DocumentsContract.buildChildDocumentsUriUsingTree(
        tree_doc_uri, tree_doc_id
    )

    columns = (
        Document.COLUMN_DISPLAY_NAME,
        Document.COLUMN_DOCUMENT_ID,
        Document.COLUMN_LAST_MODIFIED,
        Document.COLUMN_MIME_TYPE,
        Document.COLUMN_SIZE,
    )
    listing = {}
    with closing(content_resolver.query(children_uri, columns, None, None)) as cursor:
        while cursor.moveToNext():
            doc_id = cursor.getString(1)
            doc_uri = DocumentsContract.buildDocumentUriUsingTree(tree_doc_uri, doc_id)

            listing[cursor.getString(0)] = {
                "id": doc_id,
                "uri": doc_uri,
                "last_modified": cursor.getLong(2),
                "mime_type": cursor.getString(3),
                "size": cursor.getLong(4),
            }

    return listing


def provision_endless_key_database(endless_key_uris):
    if endless_key_uris is not None:
        home_folder = get_home_folder()
        dst_path = os.path.join(home_folder, "db.sqlite3")
        if os.path.exists(dst_path):
            logger.debug("EK database already exists, skipping.")
            return
        if not os.path.exists(home_folder):
            os.mkdir(home_folder)

        src_uri = endless_key_uris["db"]
        with open_document(src_uri, "rb") as src:
            with open(dst_path, "wb") as dst:
                # The file metadata on the database is irrelevant, so we
                # only need to copy the content.
                shutil.copyfileobj(src, dst)
        logger.debug("EK database provisioned.")


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


def _get_open_document_intent(volume):
    # Compatibility with SDK 28 and eariler
    # https://developer.android.com/sdk/api_diff/29/changes/android.os.storage.StorageVolume#android.os.storage.StorageVolume.createOpenDocumentTreeIntent_added()
    if SDK_INT < 29:
        return volume.createAccessIntent(None)
    else:
        return volume.createOpenDocumentTreeIntent()


def has_any_external_storage_device():
    activity = get_activity()
    storage_manager = activity.getSystemService(Context.STORAGE_SERVICE)

    found = False

    for volume in storage_manager.getStorageVolumes():
        if volume is None or volume.getUuid() == MY_FILES_UUID:
            continue

        elif volume.isRemovable() and volume.getState() == "mounted":
            found = True
            break

    return found


def create_open_kolibri_data_intent(context):
    """Create an ACTION_OPEN_DOCUMENT_TREE using KOLIBRI_DATA URI"""
    storage_manager = context.getSystemService(Context.STORAGE_SERVICE)
    for volume in storage_manager.getStorageVolumes():
        if volume is None:
            continue
        state = volume.getState()
        is_removable = volume.isRemovable()
        uuid = volume.getUuid()
        path = _get_directory_path(volume)
        logger.debug(
            "Found volume UUID=%s, state=%s, removable=%s, mount=%s",
            uuid,
            state,
            is_removable,
            path,
        )

        if not is_removable or state != "mounted" or uuid == MY_FILES_UUID:
            continue

        # Create an ACTION_OPEN_DOCUMENT_TREE intent with the URI of the
        # volume root as the EXTRA_INITIAL_URI.
        intent = _get_open_document_intent(volume)
        intent_data = intent.getParcelableExtra(DocumentsContract.EXTRA_INITIAL_URI)

        if not intent_data:
            continue

        # Extract the initial URI from the intent and then adjust it so
        # it includes the expected KOLIBRI_DATA path. If that path
        # doesn't exist, then the file picker will use the default
        # internal storage root.
        initial_uri = cast("android.net.Uri", intent_data)
        logger.debug(
            "Volume %s OPEN_DOCUMENT_TREE initial URI: %s", uuid, initial_uri.toString()
        )
        root_id = DocumentsContract.getRootId(initial_uri)
        kolibri_data_id = f"{root_id}:KOLIBRI_DATA"
        kolibri_data_uri = DocumentsContract.buildDocumentUri(
            initial_uri.getAuthority(), kolibri_data_id
        )
        logger.debug(
            "Volume %s OPEN_DOCUMENT_TREE KOLIBRI_DATA URI: %s",
            uuid,
            kolibri_data_uri.toString(),
        )
        intent.putExtra(
            DocumentsContract.EXTRA_INITIAL_URI,
            cast("android.os.Parcelable", kolibri_data_uri),
        )

        return intent

    # No removable volume found, return the default OPEN_DOCUMENT_TREE
    # intent.
    return Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)


def choose_directory(activity=None, msg=None, timeout=None):
    """Run the file picker to choose a directory"""
    global _choose_directory_intent

    if activity is None:
        activity = get_activity()
    content_resolver = activity.getContentResolver()

    data_queue = Queue(1)
    OPEN_DIRECTORY_REQUEST_CODE = 0xF11E

    def on_activity_result(request, result, intent):
        if request != OPEN_DIRECTORY_REQUEST_CODE:
            return

        if result != Activity.RESULT_OK:
            if result == Activity.RESULT_CANCELED:
                logger.info("Open directory request cancelled")
            else:
                logger.info("Open directory request result %d", result)
            data_queue.put(None, timeout=timeout)
            return

        if intent is None:
            logger.warning("Open directory result contains no data")
            data_queue.put(None, timeout=timeout)
            return

        uri = intent.getData()
        uri_str = uri.toString()
        logger.info("Open directory request returned URI %s", uri_str)

        logger.debug("Persisting read permissions for %s", uri_str)
        flags = intent.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION
        content_resolver.takePersistableUriPermission(uri, flags)

        data_queue.put(uri_str, timeout=timeout)

    _choose_directory_intent = create_open_kolibri_data_intent(activity)
    logger.info("Open directory intent: %s", _choose_directory_intent.toString())
    extras = _choose_directory_intent.getExtras()
    if extras:
        logger.info("Open directory intent extras: %s", extras.toString())

    bind(on_activity_result=on_activity_result)
    try:
        activity.startActivityForResult(
            _choose_directory_intent,
            OPEN_DIRECTORY_REQUEST_CODE,
        )
        if msg:
            show_toast(activity, msg, Toast.LENGTH_LONG)
        return data_queue.get(timeout=timeout)
    finally:
        unbind(on_activity_result=on_activity_result)
        _choose_directory_intent = None


def show_toast(context, msg, duration):
    """Helper to create and show a Toast message"""

    def func():
        Toast.makeText(context, AndroidString(msg), duration).show()

    runnable = Runnable(func)
    runnable()


def send_whatsapp_message(msg):
    share_by_intent(message=msg, app="com.whatsapp")


def share_by_intent(path=None, filename=None, message=None, app=None, mimetype=None):
    global _send_intent

    assert (
        path or message or filename
    ), "Must provide either a path, a filename, or a msg to share"

    _send_intent = Intent()
    _send_intent.setAction(Intent.ACTION_SEND)
    if path:
        uri = FileProvider.getUriForFile(
            Context.getApplicationContext(),
            "org.endlessos.Key.fileprovider",
            File(path),
        )
        parcelable = cast("android.os.Parcelable", uri)
        _send_intent.putExtra(Intent.EXTRA_STREAM, parcelable)
        _send_intent.setType(AndroidString(mimetype or "*/*"))
        _send_intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    if message:
        if not path:
            _send_intent.setType(AndroidString(mimetype or "text/plain"))
        _send_intent.putExtra(Intent.EXTRA_TEXT, AndroidString(message))
    if app:
        _send_intent.setPackage(AndroidString(app))
    _send_intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    get_activity().startActivity(_send_intent)
    _send_intent = None


def init_firebase_app():
    app_context = get_service().getApplication().getApplicationContext()
    FirebaseApp.initializeApp(app_context)


def make_service_foreground(title, message):
    global _notification_builder
    global _notification_intent

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
        _notification_builder = NotificationBuilder(app_context, channel_id)
    else:
        _notification_builder = NotificationBuilder(app_context)

    _notification_builder.setContentTitle(AndroidString(title))
    _notification_builder.setContentText(AndroidString(message))
    _notification_intent = Intent(app_context, PythonActivity)
    _notification_intent.setFlags(
        Intent.FLAG_ACTIVITY_CLEAR_TOP
        | Intent.FLAG_ACTIVITY_SINGLE_TOP
        | Intent.FLAG_ACTIVITY_NEW_TASK
    )
    _notification_intent.setAction(Intent.ACTION_MAIN)
    _notification_intent.addCategory(Intent.CATEGORY_LAUNCHER)
    intent = PendingIntent.getActivity(service, 0, _notification_intent, 0)
    _notification_builder.setContentIntent(intent)
    _notification_builder.setSmallIcon(Drawable.icon)
    _notification_builder.setAutoCancel(True)
    new_notification = _notification_builder.getNotification()
    service.startForeground(1, new_notification)
    _notification_builder = None
    _notification_intent = None


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


def setup_analytics():
    """Enable or disable Firebase Analytics and Crashlytics

    For release builds, they're enabled by default. For debug builds,
    they're disabled by default. They can be explicitly enabled or
    disabled using the debug.org.endlessos.key.analytics system
    property. For example, `adb shell setprop
    debug.org.endlessos.key.analytics true`.
    """
    if BuildConfig.DEBUG:
        logger.debug("Debug build, analytics default disabled")
        analytics_default = False
    else:
        logger.debug("Release build, analytics default enabled")
        analytics_default = True

    # Allow explicitly enabling or disabling using a system property.
    analytics_enabled = SystemProperties.getBoolean(
        ANALYTICS_SYSPROP,
        analytics_default,
    )
    if analytics_enabled is not analytics_default:
        logger.debug(
            "Analytics %s from %s system property",
            "enabled" if analytics_enabled else "disabled",
            ANALYTICS_SYSPROP,
        )

    # Analytics and Crashlytics collection enablement persists across
    # executions, so actively enable or disable based on the current
    # settings.
    logging.info(
        "%s Firebase Analytics and Crashlytics",
        "Enabling" if analytics_enabled else "Disabling",
    )
    context = get_activity()
    analytics = FirebaseAnalytics.getInstance(context)
    crashlytics = FirebaseCrashlytics.getInstance()
    analytics.setAnalyticsCollectionEnabled(analytics_enabled)
    crashlytics.setCrashlyticsCollectionEnabled(analytics_enabled)


class StartupState(Enum):
    FIRST_TIME = auto()
    USB_USER = auto()
    NETWORK_USER = auto()

    @classmethod
    def get_current_state(cls):
        """
        Returns the current app startup state that could be:
            * FIRST_TIME
            * USB_USER
            * NETWORK_USER
        """
        home = get_home_folder()

        # if there's no database in the home folder this is the first launch
        db_path = os.path.join(home, "db.sqlite3")
        if not os.path.exists(db_path):
            return cls.FIRST_TIME

        # If there are Endless Key URIs in the preferences, the app has
        # been started with an Endless Key USB.
        if get_endless_key_uris():
            return cls.USB_USER

        # in other case, the app is initialized but with content downloaded
        # using the network
        return cls.NETWORK_USER


class AndroidLogHandler(logging.Handler):
    """Logging handler dispatching to android.util.Log

    Converts Python logging records to Android log messages viewable
    with "adb logcat". The handler converts logging levels to log
    priorities, which allows filtering by priority with logcat or other
    Android log analysis tools.
    """

    def __init__(self, tag=None):
        super().__init__()

        self.tag = tag or get_activity().getPackageName()

    def emit(self, record):
        try:
            msg = self.format(record)
            priority = self.level_to_priority(record.levelno)
            Log.println(priority, self.tag, msg)
        except:  # noqa: E722
            self.handleError(record)

    @staticmethod
    def level_to_priority(level):
        if level >= logging.CRITICAL:
            return Log.ASSERT
        elif level >= logging.ERROR:
            return Log.ERROR
        elif level >= logging.WARNING:
            return Log.WARN
        elif level >= logging.INFO:
            return Log.INFO
        elif level >= logging.DEBUG:
            return Log.DEBUG
        else:
            return Log.VERBOSE


def get_logging_config(LOG_ROOT, debug=False, debug_database=False):
    """Logging configuration

    This is customized from
    kolibri.utils.logger.get_default_logging_config(), which is the
    basis for the logging configuration used in Kolibri.
    """
    # This is the general level
    DEFAULT_LEVEL = "INFO" if not debug else "DEBUG"
    DATABASE_LEVEL = "INFO" if not debug_database else "DEBUG"
    DEFAULT_HANDLERS = ["android", "file"]

    return {
        "version": 1,
        "disable_existing_loggers": False,
        # No filters are used here, but kolibri adds some and expects
        # the top level filters dict to exist.
        "filters": {},
        "formatters": {
            "simple": {
                "format": "%(name)s: %(message)s",
            },
            "full": {
                "format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "android": {
                "class": "kolibri_android.android_utils.AndroidLogHandler",
                # Since Android loggingthat already has timestamps and
                # priority levels, they aren't needed here.
                "formatter": "simple",
            },
            "file": {
                # Kolibri uses a customized version of
                # logging.handlers.TimedRotatingFileHandler. We don't
                # want to use that here to avoid importing kolibri too
                # early. IMO, the regular rotating handler based on size
                # is better in the Android case so the total disk space
                # used for logs is managed.
                "class": "logging.handlers.RotatingFileHandler",
                "filename": os.path.join(LOG_ROOT, "kolibri.txt"),
                "maxBytes": 5 << 20,  # 5 Mib
                "backupCount": 5,
                "formatter": "full",
            },
        },
        "loggers": {
            "": {
                "handlers": DEFAULT_HANDLERS,
                "level": DEFAULT_LEVEL,
            },
            "kolibri_android": {
                # Always log our code at debug level.
                "level": "DEBUG",
            },
            "jnius": {
                # jnius debug logs are very noisy, so limit it to info.
                "level": "INFO",
            },
            "kolibri": {
                # kolibri expects the handlers list to exist so it can
                # append django's email handler.
                "handlers": [],
            },
            # For now, we do not fetch debugging output from this
            # We should introduce custom debug log levels or log
            # targets, i.e. --debug-level=high
            "kolibri.core.tasks.worker": {
                "level": "INFO",
            },
            "django": {
                # kolibri expects the handlers list to exist so it can
                # append django's email handler.
                "handlers": [],
            },
            "django.db.backends": {
                "level": DATABASE_LEVEL,
            },
            "django.request": {
                # kolibri expects the handlers list to exist so it can
                # append django's email handler.
                "handlers": [],
            },
            "django.template": {
                # Django template debug is very noisy, only log INFO and above.
                "level": "INFO",
            },
        },
    }
