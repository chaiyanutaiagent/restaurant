package com.foodchainservice.pos.uat;

import android.content.Context;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.print.PageRange;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintManager;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/** System print dialog/PDF for table QR and HTML receipts; no sale is created here. */
@CapacitorPlugin(name = "PosDocumentPrint")
public class PosDocumentPrintPlugin extends Plugin {
    private WebView printView;

    @PluginMethod
    public void printHtml(PluginCall call) {
        String html = call.getString("html");
        if (html == null || html.length() > 5_000_000) { call.reject("เอกสารพิมพ์ไม่ถูกต้องหรือใหญ่เกินไป"); return; }
        getActivity().runOnUiThread(() -> {
            if (printView != null) { call.reject("กรุณาปิดหน้าพิมพ์เดิมก่อน"); return; }
            PrintManager manager = (PrintManager) getActivity().getSystemService(Context.PRINT_SERVICE);
            if (manager == null) { call.reject("อุปกรณ์ไม่มีบริการพิมพ์"); return; }
            WebView view = new WebView(getActivity());
            printView = view;
            view.getSettings().setJavaScriptEnabled(false);
            view.getSettings().setAllowFileAccess(false);
            view.getSettings().setAllowContentAccess(false);
            view.getSettings().setBlockNetworkLoads(true);
            view.setWebViewClient(new WebViewClient() {
                private boolean started;
                @Override public void onPageFinished(WebView webView, String url) {
                    if (started) return;
                    started = true;
                    PrintDocumentAdapter delegate = view.createPrintDocumentAdapter("Foodchainservice POS");
                    PrintDocumentAdapter adapter = new PrintDocumentAdapter() {
                        @Override public void onStart() { delegate.onStart(); }
                        @Override public void onLayout(PrintAttributes oldAttrs, PrintAttributes newAttrs, CancellationSignal signal, LayoutResultCallback result, Bundle extras) {
                            delegate.onLayout(oldAttrs, newAttrs, signal, result, extras);
                        }
                        @Override public void onWrite(PageRange[] pages, ParcelFileDescriptor destination, CancellationSignal signal, WriteResultCallback result) {
                            delegate.onWrite(pages, destination, signal, result);
                        }
                        @Override public void onFinish() { delegate.onFinish(); view.destroy(); printView = null; }
                    };
                    try { manager.print("Foodchainservice POS", adapter, new PrintAttributes.Builder().build()); call.resolve(); }
                    catch (Exception error) { view.destroy(); printView = null; call.reject("เปิดบริการพิมพ์ไม่ได้", error); }
                }
            });
            view.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
        });
    }
}
