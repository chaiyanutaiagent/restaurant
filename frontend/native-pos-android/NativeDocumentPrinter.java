package com.foodchainservice.nativepos;

import android.content.Context;
import android.print.PrintAttributes;
import android.print.PrintManager;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/** Android print-service/PDF fallback for existing HTML receipts and QR bills. */
@CapacitorPlugin(name = "NativeDocumentPrinter")
public class NativeDocumentPrinter extends Plugin {
    @PluginMethod
    public void print(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            try {
                PrintManager manager = (PrintManager) getActivity().getSystemService(Context.PRINT_SERVICE);
                if (manager == null) { call.reject("Android Print Service unavailable"); return; }
                manager.print("Foodchainservice UAT", getBridge().getWebView().createPrintDocumentAdapter("Foodchainservice UAT"), new PrintAttributes.Builder().build());
                call.resolve();
            } catch (Exception error) {
                call.reject("Unable to open Android Print Service", error);
            }
        });
    }
}
