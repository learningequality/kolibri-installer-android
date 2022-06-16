package org.endlessos.Key;
import android.webkit.JavascriptInterface;
import android.util.Log;

public class WelcomeScreenInterface {

    private static final String TAG = "WelcomeScreen";

    public void test() {
        Log.d(TAG, "test called!");
    }

    @JavascriptInterface
    public void load() {
        Log.d(TAG, "load called!");
    }
    @JavascriptInterface
    public void loadWithUSB() {
        Log.d(TAG, "loadWithUSB called!");
    }
}
