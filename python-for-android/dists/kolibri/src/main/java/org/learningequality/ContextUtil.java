package org.learningequality;

import android.app.ActivityManager;
import android.content.Context;
import android.os.Process;

import org.kivy.android.PythonActivity;
import org.learningequality.Kolibri.WorkerService;

public class ContextUtil {
    public static Context getApplicationContext() {
        if (isServiceContext()) {
            return WorkerService.mService.getApplicationContext();
        }
        if (isActivityContext()) {
            return PythonActivity.mActivity.getApplicationContext();
        }
        return null;
    }

    public static boolean isActivityContext() {
        return PythonActivity.mActivity != null;
    }

    public static boolean isServiceContext() {
        return WorkerService.mService != null;
    }

    /**
     * Get the name of the current process.
     *
     * @param context - the context to use
     * @return the name of the current process as a string, or an empty string if not found
     */
    public static String getCurrentProcessName(Context context) {
        int pid = Process.myPid();
        ActivityManager manager = (ActivityManager) context.getSystemService(Context.ACTIVITY_SERVICE);
        for (ActivityManager.RunningAppProcessInfo processInfo : manager.getRunningAppProcesses()) {
            if (processInfo.pid == pid) {
                return processInfo.processName;
            }
        }
        return "";
    }
}
