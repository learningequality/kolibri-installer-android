package org.learningequality;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.view.View;
import android.content.Context;
import android.content.SharedPreferences;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.webkit.JavascriptInterface;
import org.kivy.android.PythonActivity;

import android.util.Log;
import java.lang.Runnable;


public class FullScreen {
    private static FullScreen fullScreen;

    public PythonActivity mActivity;
    public WebView mMainWebView;
    public WebView mLoadingWebView;
    public MyChrome mChrome;

    private boolean clearHistoryOnPageFinished = false;

    private FullScreen(PythonActivity activity) {
        mActivity = activity;
        mMainWebView = activity.getMainWebView();
        mLoadingWebView = activity.getLoadingWebView();
        mChrome = new MyChrome(activity);
    }

    public static void initialize(PythonActivity activity) {
        fullScreen = new FullScreen(activity);
    }

    public static FullScreen getInstance() {
        return fullScreen;
    }

    public String getUrl() {
        return mMainWebView.getUrl();
    }

    public void replaceUrl(String url) {
        // It is important that we call mMainWebView.clearHistory after navigation
        // is completed, so we will set clearHistoryOnPageFinished and do the
        // work of clearing history in the onPageFinished callback.
        clearHistoryOnPageFinished = true;
        mActivity.loadUrl(url);
    }

    public void showLoadingPage(String loadingUrl) {
        if (loadingUrl != null && !mLoadingWebView.getUrl().equals(loadingUrl)) {
            mLoadingWebView.loadUrl(loadingUrl);
        }
        mActivity.displayLoadingWebView();
    }

    public void setAppKeyCookie(String url, String appKey) {
        CookieManager.getInstance().setCookie(url, "app_key_cookie=" + appKey);
    }

    // Configure the WebView to allow fullscreen based on:
    // https://stackoverflow.com/questions/15768837/playing-html5-video-on-fullscreen-in-android-webview/56186877#56186877
    public void configure(final Runnable startWithNetwork, final Runnable startWithUSB, final Runnable loadingReady) {
        Log.i("Endless Key", "FullScreen configure");

        mLoadingWebView.setWebViewClient(new WebViewClient() {
            private boolean mInWelcome = false;

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return mActivity.tryOpenExternalLink(url);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                Log.i("Endless Key", "mLoadingWebView onPageFinished " + url);

                mLoadingWebView.evaluateJavascript("WelcomeApp.setNeedsPermission(true)", null);

                if (!mInWelcome && url.contains("welcomeScreen/index.html")) {
                    loadingReady.run();
                    mInWelcome = true;
                }
            }
        });
        mLoadingWebView.addJavascriptInterface(new Object() {
            @JavascriptInterface
            public void startWithNetwork(String packId) {
                SharedPreferences sharedPref =  mActivity.getSharedPreferences(mActivity.getPackageName(), Context.MODE_PRIVATE);
                SharedPreferences.Editor editor = sharedPref.edit();
                editor.putString("initial_content_pack_id", packId);
                editor.commit();
                Log.v("Endless Key", packId);
                startWithNetwork.run();
            }
            @JavascriptInterface
            public void startWithUSB() {
                startWithUSB.run();
            }
        } , "WelcomeWrapper");

        mLoadingWebView.getSettings().setAllowFileAccess(true);

        mMainWebView.setWebContentsDebuggingEnabled(true);
        mMainWebView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                Log.i("Endless Key", "mMainWebView shouldOverrideUrlLoading? " + url);
                if (mActivity.tryOpenExternalLink(url)) {
                    Log.i("Endless Key", "mMainWebView shouldOverrideUrlLoading? true");
                    return true;
                } else {
                    Log.i("Endless Key", "mMainWebView shouldOverrideUrlLoading? false");
                    return false;
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                Log.i("Endless Key", "mMainWebView onPageFinished " + url);

                mActivity.displayMainWebView();

                if (clearHistoryOnPageFinished) {
                    mMainWebView.clearHistory();
                    clearHistoryOnPageFinished = false;
                }
            }
        });
        mMainWebView.setWebChromeClient(mChrome);

        mMainWebView.getSettings().setAllowFileAccess(true);
    }

    private class MyChrome extends WebChromeClient {

        private View mCustomView;
        private WebChromeClient.CustomViewCallback mCustomViewCallback;
        protected FrameLayout mFullscreenContainer;
        private int mOriginalOrientation;
        private int mOriginalSystemUiVisibility;
        public PythonActivity mActivity = null;

        MyChrome(PythonActivity activity) {
            mActivity = activity;
        }

        public Bitmap getDefaultVideoPoster()
        {
            if (mCustomView == null) {
                return null;
            }
            return BitmapFactory.decodeResource(mActivity.getApplicationContext().getResources(), 2130837573);
        }

        public void onHideCustomView()
        {
            ((FrameLayout)mActivity.getWindow().getDecorView()).removeView(this.mCustomView);
            this.mCustomView = null;
            mActivity.getWindow().getDecorView().setSystemUiVisibility(this.mOriginalSystemUiVisibility);
            mActivity.setRequestedOrientation(this.mOriginalOrientation);
            this.mCustomViewCallback.onCustomViewHidden();
            this.mCustomViewCallback = null;
        }

        public void onShowCustomView(View paramView, WebChromeClient.CustomViewCallback paramCustomViewCallback)
        {
            if (this.mCustomView != null)
            {
                onHideCustomView();
                return;
            }
            this.mCustomView = paramView;
            this.mOriginalSystemUiVisibility = mActivity.getWindow().getDecorView().getSystemUiVisibility();
            this.mOriginalOrientation = mActivity.getRequestedOrientation();
            this.mCustomViewCallback = paramCustomViewCallback;
            ((FrameLayout)mActivity.getWindow().getDecorView()).addView(this.mCustomView, new FrameLayout.LayoutParams(-1, -1));
            mActivity.getWindow().getDecorView().setSystemUiVisibility(3846 | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }
    }
}
