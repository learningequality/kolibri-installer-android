package org.kivy.android;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.os.Build;
import android.provider.Settings;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public class PythonContext {
    public static final String PACKAGE = "org.learningequality.Kolibri";
    public static PythonContext mInstance;

    private final Context context;
    private final ConnectivityManager connectivityManager;
    private final ConnectivityManager.NetworkCallback networkCallback;
    private final AtomicBoolean isMetered = new AtomicBoolean(false);
    private final String externalFilesDir;
    private final String versionName;
    private final String certificateInfo;
    private final String nodeId;

    private PythonContext(Context context) {
        this.context = context;
        this.connectivityManager = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);

        this.networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(Network network) {
                super.onAvailable(network);
                isMetered.set(connectivityManager.isActiveNetworkMetered());
            }

            @Override
            public void onLost(Network network) {
                super.onLost(network);
                isMetered.set(false);
            }
        };

        NetworkRequest networkRequest = new NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build();

        this.connectivityManager.registerNetworkCallback(networkRequest, this.networkCallback);

        this.externalFilesDir = context.getExternalFilesDir(null).toString();

        PackageInfo packageInfo = getPackageInfo();
        this.versionName = packageInfo.versionName;

        PackageInfo certificateInfo = getPackageInfo(PackageManager.GET_SIGNATURES);
        this.certificateInfo = certificateInfo.signatures[0].toCharsString();

        this.nodeId = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID);
    }

    public static PythonContext getInstance(Context context) {
        if (mInstance == null) {
            synchronized (PythonContext.class) {
                if (mInstance == null) {
                    mInstance = new PythonContext(
                            context.getApplicationContext()
                    );
                }
            }
        }
        return PythonContext.mInstance;
    }

    // TODO: remove this, and don't store context on the class
    public static Context get() {
        if (PythonContext.mInstance == null) {
            return null;
        }
        return PythonContext.mInstance.context;
    }

    public static String getLocale() {
        return Locale.getDefault().toLanguageTag();
    }

    public static Boolean isActiveNetworkMetered() {
        if (PythonContext.mInstance == null) {
            return null;
        }
        return PythonContext.mInstance.isMetered.get();
    }

    public static String getExternalFilesDir() {
        if (PythonContext.mInstance == null) {
            return null;
        }
        return PythonContext.mInstance.externalFilesDir;
    }

    public static String getVersionName() {
        if (PythonContext.mInstance == null) {
            return null;
        }
        return PythonContext.mInstance.versionName;
    }

    public static String getCertificateInfo() {
        if (PythonContext.mInstance == null) {
            return null;
        }
        return PythonContext.mInstance.certificateInfo;
    }

    public static String getNodeId() {
        if (PythonContext.mInstance == null) {
            return null;
        }
        return PythonContext.mInstance.nodeId;
    }

    public static void destroy() {
        if (PythonContext.mInstance != null) {
            PythonContext.mInstance.connectivityManager.unregisterNetworkCallback(PythonContext.mInstance.networkCallback);
            PythonContext.mInstance = null;
        }
    }

    protected PackageInfo getPackageInfo() {
        return getPackageInfo(0);
    }

    protected PackageInfo getPackageInfo(int flags) {
        PackageManager packageManager = context.getPackageManager();
        try {
            if (android.os.Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                return packageManager.getPackageInfo(PACKAGE, PackageManager.PackageInfoFlags.of(flags));
            } else {
                return packageManager.getPackageInfo(PACKAGE, flags);
            }
        } catch (PackageManager.NameNotFoundException e) {
            throw new RuntimeException("Kolibri is not installed");
        }
    }
}
