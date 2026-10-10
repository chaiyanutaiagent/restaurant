package com.foodchainservice.takeaway;

import android.Manifest;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import android.os.Build;
import android.content.SharedPreferences;
import android.util.Base64;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.io.OutputStream;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

@CapacitorPlugin(
    name = "TakeawayPrinter",
    permissions = {
        @Permission(
            alias = "bluetooth",
            strings = { Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_SCAN }
        )
    }
)
public class TakeawayPrinterPlugin extends Plugin {
    private static final UUID SERIAL_PORT_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
    private final AtomicBoolean printing = new AtomicBoolean(false);
    private SharedPreferences printPreferences() {
        return getContext().getSharedPreferences("takeaway-print-v2", 0);
    }

    @PluginMethod
    public void getCapabilities(PluginCall call) {
        String address = call.getString("address", "");
        JSObject result = new JSObject();
        result.put("protocolVersion", 2);
        result.put("autoCutter", printPreferences().getBoolean("full-cut:" + address, false) ? "operator_verified_full_cut" : "unverified");
        result.put("cutCommand", "GS V 65 16");
        call.resolve(result);
    }

    @PluginMethod
    public void confirmCutter(PluginCall call) {
        String address = call.getString("address", "");
        boolean confirmed = Boolean.TRUE.equals(call.getBoolean("fullCut"));
        String testId = call.getString("testId", "");
        if (confirmed && (testId.isEmpty() || !testId.equals(printPreferences().getString("cut-test:" + address, "")))) {
            call.reject("ต้องทดสอบการตัดบนเครื่องนี้ก่อนยืนยัน"); return;
        }
        if (!printPreferences().edit().putBoolean("full-cut:" + address, confirmed).remove("cut-test:" + address).commit()) {
            call.reject("บันทึกความสามารถเครื่องพิมพ์ไม่สำเร็จ"); return;
        }
        call.resolve();
    }

    @PluginMethod
    public void testCutter(PluginCall call) {
        try {
            String address = call.getString("address", "");
            if (!printPreferences().edit().putBoolean("full-cut:" + address, false).remove("cut-test:" + address).commit()) {
                call.reject("บันทึกสถานะทดสอบตัดไม่สำเร็จ ยังไม่ได้ส่งกระดาษ"); return;
            }
            sendJob(call, address, EscPosSpooler.cutterTest(), UUID.randomUUID().toString(), UUID.randomUUID().toString());
        } catch (Exception error) { call.reject("สร้างงานทดสอบตัดไม่ได้", error); }
    }

    @PluginMethod
    public void printBatch(PluginCall call) {
        String address = call.getString("address", "");
        if (!printPreferences().getBoolean("full-cut:" + address, false)) {
            call.reject("ยังไม่ยืนยัน Auto Cutter แบบตัดขาดจริง กรุณาทดสอบในตั้งค่าเครื่องพิมพ์ก่อน"); return;
        }
        try {
            String jobId = call.getString("jobId");
            if (jobId == null || !jobId.matches("[0-9a-fA-F-]{36}")) throw new IllegalArgumentException("Job ID required");
            JSONArray copies = call.getArray("copies");
            if (copies == null || copies.length() < 1 || copies.length() > 2) throw new IllegalArgumentException("One or two copies required");
            byte[][] receipts = new byte[copies.length()][];
            for (int i = 0; i < copies.length(); i++) {
                JSONObject copy = copies.getJSONObject(i);
                String type = copy.getString("copyType");
                if (!type.equals("customer") && !type.equals("preparation")) throw new IllegalArgumentException("Unknown copy type");
                if (copies.length() == 2 && !type.equals(i == 0 ? "customer" : "preparation")) throw new IllegalArgumentException("Customer must precede preparation");
                String data = copy.getString("data");
                if (data.length() > ((EscPosSpooler.MAX_BYTES + 2) / 3) * 4) throw new IllegalArgumentException("Copy too large");
                receipts[i] = Base64.decode(data, Base64.DEFAULT);
            }
            sendJob(call, address, EscPosSpooler.compound(receipts), jobId, null);
        } catch (Exception error) { call.reject("ข้อมูลชุดพิมพ์ไม่ถูกต้อง", error); }
    }

    private boolean needsRuntimePermission() {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
            && getPermissionState("bluetooth") != PermissionState.GRANTED;
    }

    @PluginMethod
    public void requestBluetoothPermission(PluginCall call) {
        if (!needsRuntimePermission()) {
            call.resolve();
            return;
        }
        requestPermissionForAlias("bluetooth", call, "bluetoothPermissionCallback");
    }

    @PermissionCallback
    private void bluetoothPermissionCallback(PluginCall call) {
        if (getPermissionState("bluetooth") == PermissionState.GRANTED) {
            call.resolve();
        } else {
            call.reject("ไม่ได้รับอนุญาตให้ใช้ Bluetooth");
        }
    }

    @PluginMethod
    public void pairedDevices(PluginCall call) {
        if (needsRuntimePermission()) {
            call.reject("ต้องอนุญาต Bluetooth ก่อนค้นหาเครื่องพิมพ์");
            return;
        }
        BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null) {
            call.reject("อุปกรณ์นี้ไม่มี Bluetooth");
            return;
        }
        if (!adapter.isEnabled()) {
            call.reject("กรุณาเปิด Bluetooth");
            return;
        }
        JSArray devices = new JSArray();
        try {
            Set<BluetoothDevice> bonded = adapter.getBondedDevices();
            for (BluetoothDevice device : bonded) {
                JSObject item = new JSObject();
                item.put("name", device.getName() == null ? "Bluetooth printer" : device.getName());
                item.put("address", device.getAddress());
                devices.put(item);
            }
            JSObject result = new JSObject();
            result.put("devices", devices);
            call.resolve(result);
        } catch (SecurityException error) {
            call.reject("ไม่มีสิทธิ์อ่านอุปกรณ์ Bluetooth", error);
        }
    }

    @PluginMethod
    public void printBase64(PluginCall call) {
        if (needsRuntimePermission()) {
            call.reject("ต้องอนุญาต Bluetooth ก่อนพิมพ์");
            return;
        }
        String address = call.getString("address");
        String data = call.getString("data");
        if (address == null || data == null || address.isEmpty() || data.isEmpty()) {
            call.reject("ต้องระบุเครื่องพิมพ์และข้อมูลพิมพ์");
            return;
        }
        if (data.length() > ((EscPosSpooler.MAX_BYTES + 2) / 3) * 4) {
            call.reject("ข้อมูลพิมพ์เกิน 1 MB"); return;
        }
        if (!address.matches("(?i)^[0-9A-F]{2}(?::[0-9A-F]{2}){5}$")) {
            call.reject("รูปแบบ Bluetooth address ไม่ถูกต้อง");
            return;
        }
        byte[] printBytes;
        try {
            printBytes = Base64.decode(data, Base64.DEFAULT);
        } catch (IllegalArgumentException error) {
            call.reject("ข้อมูลพิมพ์ไม่ใช่ Base64 ที่ถูกต้อง", error);
            return;
        }
        try { EscPosSpooler.plan(printBytes); }
        catch (Exception error) { call.reject("ข้อมูลแถบพิมพ์ไม่ถูกต้อง", error); return; }
        try { sendJob(call, address, new EscPosSpooler.Job(printBytes, EscPosSpooler.plan(printBytes)), null, null); }
        catch (Exception error) { call.reject("ข้อมูลพิมพ์ไม่ถูกต้อง", error); }
    }

    private void sendJob(PluginCall call, String address, EscPosSpooler.Job job, String attemptId, String cutTestId) {
        if (needsRuntimePermission()) { call.reject("ต้องอนุญาต Bluetooth ก่อนพิมพ์"); return; }
        if (address == null || !address.matches("(?i)^[0-9A-F]{2}(?::[0-9A-F]{2}){5}$")) { call.reject("Bluetooth address ไม่ถูกต้อง"); return; }
        if (!printing.compareAndSet(false, true)) { call.reject("มีงานพิมพ์กำลังส่งอยู่ กรุณารอ"); return; }
        if (attemptId != null) {
            try {
                SharedPreferences prefs = printPreferences();
                new PrintAttemptLedger(new PrintAttemptLedger.Store() {
                    public boolean contains(String key) { return prefs.contains(key); }
                    public boolean put(String key, String value) { return prefs.edit().putString(key, value).commit(); }
                }).reserve(attemptId, address);
            } catch (Exception error) { printing.set(false); call.reject("งานนี้เคยส่งหรือยังไม่ทราบผล ตรวจดูกระดาษก่อนกู้คืน", error); return; }
        }
        new Thread(() -> {
            BluetoothSocket socket = null;
            AtomicReference<BluetoothSocket> active = new AtomicReference<>();
            AtomicBoolean timedOut = new AtomicBoolean(false);
            ScheduledExecutorService watchdog = Executors.newSingleThreadScheduledExecutor();
            Runnable abort = () -> {
                timedOut.set(true);
                BluetoothSocket current = active.get();
                if (current != null) try { current.close(); } catch (Exception ignored) { }
            };
            ScheduledFuture<?> deadline = null;
            try {
                BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
                if (adapter == null || !adapter.isEnabled()) {
                    call.reject("Bluetooth ยังไม่พร้อมใช้งาน");
                    return;
                }
                BluetoothDevice device = adapter.getRemoteDevice(address);
                socket = device.createRfcommSocketToServiceRecord(SERIAL_PORT_UUID);
                active.set(socket);
                adapter.cancelDiscovery();
                deadline = watchdog.schedule(abort, 15, TimeUnit.SECONDS);
                socket.connect();
                deadline.cancel(false);
                if (timedOut.get()) throw new java.io.IOException("Bluetooth connection timed out");
                deadline = watchdog.schedule(abort, 180, TimeUnit.SECONDS);
                OutputStream output = socket.getOutputStream();
                BluetoothSocket connectedSocket = socket;
                EscPosSpooler.send(job, output, () -> !timedOut.get() && connectedSocket.isConnected(), Thread::sleep);
                if (cutTestId != null && !printPreferences().edit().putString("cut-test:" + address, cutTestId).commit()) {
                    throw new java.io.IOException("Could not persist cutter test; capability remains unverified");
                }
                JSObject result = new JSObject();
                result.put("outcome", "sent_unconfirmed");
                if (cutTestId != null) result.put("testId", cutTestId);
                call.resolve(result);
            } catch (Exception error) {
                call.reject("ส่งข้อมูล Bluetooth ไม่ครบ อาจพิมพ์ออกบางส่วนแล้ว ตรวจดูกระดาษและปิด/เปิดเครื่องพิมพ์ก่อนลองใหม่", error);
            } finally {
                if (deadline != null) deadline.cancel(false);
                watchdog.shutdownNow();
                if (socket != null) {
                    try { socket.close(); } catch (Exception ignored) { }
                }
                printing.set(false);
            }
        }).start();
    }
}
