package com.foodchainservice.restaurant.uat;

import com.getcapacitor.BridgeActivity;
import android.os.Bundle;
import com.foodchainservice.takeaway.TakeawayPrinterPlugin;

public class MainActivity extends BridgeActivity {
    @Override public void onCreate(Bundle savedInstanceState) {
        registerPlugin(TakeawayPrinterPlugin.class);
        registerPlugin(com.foodchainservice.nativepos.NativeDocumentPrinter.class);
        super.onCreate(savedInstanceState);
    }
}
