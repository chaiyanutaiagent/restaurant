package com.foodchainservice.nativepos;

import android.content.Context;
import android.app.Activity;
import android.content.Intent;
import android.content.ClipData;
import androidx.core.content.FileProvider;
import java.io.File;
import java.io.FileOutputStream;
import java.util.UUID;
import android.net.Uri;
import androidx.activity.result.ActivityResult;
import com.getcapacitor.JSObject;
import com.getcapacitor.annotation.ActivityCallback;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;
import android.print.PrintAttributes;
import android.print.PrintManager;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/** Android print-service/PDF fallback for existing HTML receipts and QR bills. */
@CapacitorPlugin(name = "NativeDocumentPrinter")
public class NativeDocumentPrinter extends Plugin {
    private final AtomicBoolean saving = new AtomicBoolean(false);

    @PluginMethod
    public void shareCsv(PluginCall call) {
        String name = call.getString("filename");
        String content = call.getString("content");
        if (name == null || !name.matches("[A-Za-z0-9_-]{1,150}\\.csv")
                || content == null || content.getBytes(StandardCharsets.UTF_8).length > 5 * 1024 * 1024) {
            call.reject("Invalid CSV file or file exceeds 5 MB"); return;
        }
        if (!saving.compareAndSet(false, true)) { call.reject("Preparing another file"); return; }
        getBridge().execute(() -> {
            try {
                // App-private cache only: no automatic file in the user's Downloads.
                // Unique folders preserve in-progress shares when another export is made.
                File directory = new File(getContext().getCacheDir(), "csv-share-" + UUID.randomUUID());
                if (!directory.mkdir()) throw new IllegalStateException("Unable to prepare export");
                File file = new File(directory, name);
                try (OutputStream output = new FileOutputStream(file)) {
                    output.write(content.getBytes(StandardCharsets.UTF_8));
                }
                Uri uri = FileProvider.getUriForFile(getContext(), getContext().getPackageName() + ".fileprovider", file);
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("text/csv");
                send.putExtra(Intent.EXTRA_STREAM, uri);
                send.setClipData(ClipData.newRawUri(name, uri));
                send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                getActivity().runOnUiThread(() -> {
                    try {
                        getActivity().startActivity(Intent.createChooser(send, "แชร์รายงาน CSV"));
                        // Opening the menu is not proof of sending or saving a file.
                        JSObject response = new JSObject(); response.put("opened", true); call.resolve(response);
                    } catch (Exception error) {
                        call.reject("Unable to open Android share menu", error);
                    } finally { saving.set(false); }
                });
            } catch (Exception error) {
                saving.set(false); call.reject("Unable to prepare CSV for sharing", error);
            }
        });
    }

    @PluginMethod
    public void saveCsv(PluginCall call) {
        String name = call.getString("filename");
        String content = call.getString("content");
        if (name == null || !name.matches("[A-Za-z0-9_-]{1,150}\\.csv")
                || content == null || content.getBytes(StandardCharsets.UTF_8).length > 5 * 1024 * 1024) {
            call.reject("Invalid CSV file or file exceeds 5 MB");
            return;
        }
        if (!saving.compareAndSet(false, true)) { call.reject("A save dialog is already open"); return; }
        getActivity().runOnUiThread(() -> {
            try {
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("text/csv");
                intent.putExtra(Intent.EXTRA_TITLE, name);
                startActivityForResult(call, intent, "csvDestination");
            } catch (Exception error) {
                saving.set(false);
                call.reject("Unable to open Android file picker", error);
            }
        });
    }

    @ActivityCallback
    private void csvDestination(PluginCall call, ActivityResult result) {
        if (call == null) { saving.set(false); return; }
        if (result.getResultCode() != Activity.RESULT_OK) {
            saving.set(false);
            JSObject response = new JSObject(); response.put("saved", false); call.resolve(response);
            return;
        }
        Uri uri = result.getData() == null ? null : result.getData().getData();
        if (uri == null || !"content".equals(uri.getScheme())) {
            saving.set(false); call.reject("No writable destination selected"); return;
        }
        getBridge().execute(() -> {
            try {
                String content = call.getString("content");
                if (content == null) throw new IllegalStateException("CSV content unavailable; export again");
                try (OutputStream output = getContext().getContentResolver().openOutputStream(uri, "wt")) {
                    if (output == null) throw new IllegalStateException("Unable to write selected file");
                    output.write(content.getBytes(StandardCharsets.UTF_8));
                    output.flush();
                }
                JSObject response = new JSObject(); response.put("saved", true); call.resolve(response);
            } catch (Exception error) {
                call.reject("Unable to save CSV; check destination and free space", error);
            } finally { saving.set(false); }
        });
    }

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
