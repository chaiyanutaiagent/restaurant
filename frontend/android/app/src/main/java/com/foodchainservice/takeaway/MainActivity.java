package com.foodchainservice.takeaway;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(TakeawayPrinterPlugin.class);
        registerPlugin(TakeawayUpdaterPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
