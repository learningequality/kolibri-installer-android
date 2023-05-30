import logging
from contextlib import contextmanager
from threading import Condition

from jnius import autoclass
from jnius import java_method
from jnius import PythonJavaClass

logger = logging.getLogger(__name__)

InstallReferrerClient = autoclass(
    "com.android.installreferrer.api.InstallReferrerClient"
)
InstallReferrerResponse = autoclass(
    "com.android.installreferrer.api.InstallReferrerClient$InstallReferrerResponse"
)


class ReferrerStateListener(PythonJavaClass):
    """Implements InstallReferrerStateListener interface from Install Referrer"""

    __javainterfaces__ = [
        "com/android/installreferrer/api/InstallReferrerStateListener",
    ]
    __javacontext__ = "app"

    def __init__(self):
        super().__init__()

        self._state = None
        self._ready = Condition()

    def _state_is_available(self):
        return self._state is not None

    def get_state(self, timeout=5):
        """Get the current state, blocking for up to timeout seconds"""
        with self._ready:
            if not self._ready.wait_for(self._state_is_available, timeout=timeout):
                logger.warning(
                    f"Referrer setup did not complete within {timeout} seconds"
                )
                return None
            return self._state

    @java_method("()V")
    def onInstallReferrerServiceDisconnected(self):
        with self._ready:
            logger.info("Install Referrer service disconnected")
            self._state = InstallReferrerResponse.SERVICE_DISCONNECTED
            self._ready.notify_all()

    @java_method("(I)V")
    def onInstallReferrerSetupFinished(self, responseCode):
        with self._ready:
            if responseCode == InstallReferrerResponse.OK:
                logger.info("Install Referrer service connected")
            else:
                if responseCode == InstallReferrerResponse.DEVELOPER_ERROR:
                    reason = "Developer error"
                elif responseCode == InstallReferrerResponse.FEATURE_NOT_SUPPORTED:
                    reason = "Feature not supported by Play Store app"
                elif responseCode == InstallReferrerResponse.SERVICE_DISCONNECTED:
                    reason = "Play Store service is not connected now"
                elif responseCode == InstallReferrerResponse.FEATURE_NOT_SUPPORTED:
                    reason = "Feature not supported by Play Store app"
                else:
                    reason = "Unknown"
                logger.error(f"Install Referrer connection failed: {reason}")

            self._state = responseCode
            self._ready.notify_all()


@contextmanager
def referrer_client(app_context):
    """InstallReferrerClient context closing connection upon exit"""
    client = InstallReferrerClient.newBuilder(app_context).build()
    try:
        yield client
    finally:
        client.endConnection()


def get_referrer_details(context, timeout=5):
    """Retrieve install referrer details"""
    with referrer_client(context) as client:
        listener = ReferrerStateListener()
        client.startConnection(listener)
        state = listener.get_state(timeout=timeout)
        if state != InstallReferrerResponse.OK:
            return None
        return client.getInstallReferrer()
