package com.foodchainservice.pos.uat;

import com.getcapacitor.BridgeActivity;
import android.os.Bundle;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(TakeawayPrinterPlugin.class);
        registerPlugin(PosDocumentPrintPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
