from android_utils import get_activity
from jnius import java_method
from jnius import PythonJavaClass

# Keep a reference to all the registered classes so that python doesn't
# garbage collect them.
_registered = set()


class ActivityLifecycleCallbacks(PythonJavaClass):
    """Callback class for handling PythonActivity lifecycle transitions"""

    __javainterfaces__ = ["android/app/Application$ActivityLifecycleCallbacks"]

    def __init__(self, callbacks):
        super().__init__()

        # It would be nice to use keyword arguments, but PythonJavaClass
        # doesn't allow that in its __cinit__ method.
        if not isinstance(callbacks, dict):
            raise ValueError("callbacks must be a dict instance")
        self.callbacks = callbacks

    def _callback(self, name, *args):
        func = self.callbacks.get(name)
        if func:
            func(*args)

    @java_method("(Landroid/app/Activity;Landroid/os/Bundle;)V")
    def onActivityCreated(self, activity, savedInstanceState):
        self._callback("onActivityCreated", activity, savedInstanceState)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityDestroyed(self, activity):
        self._callback("onActivityDestroyed", activity)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPaused(self, activity):
        self._callback("onActivityPaused", activity)

    @java_method("(Landroid/app/Activity;Landroid/os/Bundle;)V")
    def onActivityPostCreated(self, activity, savedInstanceState):
        self._callback("onActivityPostCreated", activity, savedInstanceState)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPostDestroyed(self, activity):
        self._callback("onActivityPostDestroyed", activity)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPostPaused(self, activity):
        self._callback("onActivityPostPaused", activity)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPostResumed(self, activity):
        self._callback("onActivityPostResumed", activity)

    @java_method("(Landroid/app/Activity;Landroid/os/Bundle;)V")
    def onActivityPostSaveInstanceState(self, activity, outState):
        self._callback("onActivityPostSaveInstanceState", activity, outState)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPostStarted(self, activity):
        self._callback("onActivityPostStarted", activity)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPostStopped(self, activity):
        self._callback("onActivityPostStopped", activity)

    @java_method("(Landroid/app/Activity;Landroid/os/Bundle;)V")
    def onActivityPreCreated(self, activity, savedInstanceState):
        self._callback("onActivityPreCreated", activity, savedInstanceState)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPreDestroyed(self, activity):
        self._callback("onActivityPreDestroyed", activity)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPrePaused(self, activity):
        self._callback("onActivityPrePaused", activity)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPreResumed(self, activity):
        self._callback("onActivityPreResumed", activity)

    @java_method("(Landroid/app/Activity;Landroid/os/Bundle;)V")
    def onActivityPreSaveInstanceState(self, activity, outState):
        self._callback("onActivityPreSaveInstanceState", activity, outState)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPreStarted(self, activity):
        self._callback("onActivityPreStarted", activity)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityPreStopped(self, activity):
        self._callback("onActivityPreStopped", activity)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityResumed(self, activity):
        self._callback("onActivityResumed", activity)

    @java_method("(Landroid/app/Activity;Landroid/os/Bundle;)V")
    def onActivitySaveInstanceState(self, activity, outState):
        self._callback("onActivitySaveInstanceState", activity, outState)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityStarted(self, activity):
        self._callback("onActivityStarted", activity)

    @java_method("(Landroid/app/Activity;)V")
    def onActivityStopped(self, activity):
        self._callback("onActivityStopped", activity)


def register_activity_lifecycle_callbacks(**callbacks):
    """Register ActivityLifecycleCallbacks instance

    The callbacks are supplied as keyword arguments corresponding to the
    Application.ActivityLifecycleCallbacks methods such as
    onActivityStarted. See the ActivityLifecycleCallbacks documentation
    for the signature of each method.

    The ActivityLifecycleCallbacks instance is returned so it can be
    supplied to unregister_activity_lifecycle_callbacks if needed.
    """
    instance = ActivityLifecycleCallbacks(callbacks)
    _registered.add(instance)

    activity = get_activity()
    if hasattr(activity, "registerActivityLifecycleCallbacks"):
        activity.registerActivityLifecycleCallbacks(instance)
    else:
        app = activity.getApplication()
        app.registerActivityLifecycleCallbacks(instance)
    return instance


def unregister_activity_lifecycle_callbacks(instance):
    """Unregister ActivityLifecycleCallbacks instance"""
    activity = get_activity()
    if hasattr(activity, "registerActivityLifecycleCallbacks"):
        activity.unregisterActivityLifecycleCallbacks(instance)
    else:
        app = activity.getApplication()
        app.unregisterActivityLifecycleCallbacks(instance)

    try:
        _registered.remove(instance)
    except KeyError:
        pass
