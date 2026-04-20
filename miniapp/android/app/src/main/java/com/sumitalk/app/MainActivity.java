package com.sumitalk.app;

import android.os.Bundle;
import android.webkit.WebSettings;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        WebSettings settings = getBridge().getWebView().getSettings();
        if (settings != null) {
            settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        }
        getBridge().getWebView().clearCache(true);
        getBridge().getWebView().loadUrl("https://duxy-home.com/miniapp?ts=" + System.currentTimeMillis());
    }
}
