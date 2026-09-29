package com.foodchainservice.takeaway;

import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.core.content.FileProvider;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

@CapacitorPlugin(name = "TakeawayUpdater")
public class TakeawayUpdaterPlugin extends Plugin {
    private static final long MAX_APK_BYTES = 250L * 1024L * 1024L;
    private static final Set<String> ALLOWED_HOSTS = new HashSet<>(Arrays.asList(
        "uat-takeaway.foodchainservice.com",
        "downloads.foodchainservice.com"
    ));

    @PluginMethod
    public void getStatus(PluginCall call) {
        try {
            PackageInfo info = getContext().getPackageManager().getPackageInfo(getContext().getPackageName(), 0);
            JSObject result = new JSObject();
            result.put("packageId", info.packageName);
            result.put("versionName", info.versionName == null ? "" : info.versionName);
            result.put("versionCode", versionCode(info));
            result.put("installPermission", canInstallPackages());
            call.resolve(result);
        } catch (Exception error) {
            call.reject("อ่านเวอร์ชันแอปไม่สำเร็จ", error);
        }
    }

    @PluginMethod
    public void installUpdate(PluginCall call) {
        String apkUrl = call.getString("apkUrl");
        String expectedSha256 = call.getString("apkSha256");
        Integer expectedVersionCode = call.getInt("versionCode");
        if (apkUrl == null || expectedSha256 == null || expectedVersionCode == null
            || !expectedSha256.matches("(?i)^[a-f0-9]{64}$")) {
            call.reject("ข้อมูลอัปเดตไม่ครบถ้วน");
            return;
        }
        URL source;
        try {
            source = new URL(apkUrl);
            validateUrl(source);
        } catch (Exception error) {
            call.reject("URL อัปเดตไม่ได้รับอนุญาต", error);
            return;
        }
        if (!canInstallPackages()) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                Intent settings = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + getContext().getPackageName()));
                settings.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                getContext().startActivity(settings);
            }
            call.reject("กรุณาเปิดสิทธิ์ติดตั้งแอป แล้วกลับมากดติดตั้งอีกครั้ง", "INSTALL_PERMISSION_REQUIRED");
            return;
        }
        new Thread(() -> downloadAndInstall(call, source, expectedSha256.toLowerCase(Locale.US), expectedVersionCode)).start();
    }

    private void downloadAndInstall(PluginCall call, URL source, String expectedSha256, int expectedVersionCode) {
        File directory = new File(getContext().getCacheDir(), "updates");
        File target = new File(directory, "takeaway-store-update.apk");
        HttpURLConnection connection = null;
        try {
            if (!directory.exists() && !directory.mkdirs()) throw new IllegalStateException("สร้างพื้นที่อัปเดตไม่ได้");
            connection = (HttpURLConnection) source.openConnection();
            connection.setConnectTimeout(15_000);
            connection.setReadTimeout(60_000);
            connection.setInstanceFollowRedirects(true);
            connection.connect();
            validateUrl(connection.getURL());
            if (connection.getResponseCode() < 200 || connection.getResponseCode() >= 300) {
                throw new IllegalStateException("ดาวน์โหลดไม่สำเร็จ (" + connection.getResponseCode() + ")");
            }
            long declaredSize = connection.getContentLength();
            if (declaredSize <= 0 || declaredSize > MAX_APK_BYTES) throw new IllegalStateException("ขนาด APK ไม่ถูกต้อง");
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long total = 0;
            try (BufferedInputStream input = new BufferedInputStream(connection.getInputStream());
                 FileOutputStream output = new FileOutputStream(target, false)) {
                byte[] buffer = new byte[32 * 1024];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    total += read;
                    if (total > MAX_APK_BYTES) throw new IllegalStateException("APK ใหญ่เกินกำหนด");
                    output.write(buffer, 0, read);
                    digest.update(buffer, 0, read);
                }
                output.flush();
            }
            String actualSha256 = toHex(digest.digest());
            if (!MessageDigest.isEqual(actualSha256.getBytes(), expectedSha256.getBytes())) {
                throw new SecurityException("SHA-256 ของ APK ไม่ตรงกับ release");
            }
            PackageManager packageManager = getContext().getPackageManager();
            PackageInfo candidate = packageManager.getPackageArchiveInfo(target.getAbsolutePath(), PackageManager.GET_SIGNING_CERTIFICATES);
            if (candidate == null || !getContext().getPackageName().equals(candidate.packageName)) {
                throw new SecurityException("APK ไม่ใช่แอป Takeaway Store ชุดนี้");
            }
            if (versionCode(candidate) != expectedVersionCode) throw new SecurityException("Version code ของ APK ไม่ตรงกับ release");
            PackageInfo installed = packageManager.getPackageInfo(getContext().getPackageName(), PackageManager.GET_SIGNING_CERTIFICATES);
            if (versionCode(candidate) <= versionCode(installed)) throw new SecurityException("APK ไม่ใช่เวอร์ชันใหม่กว่า");
            if (!sameSigner(installed, candidate)) throw new SecurityException("ลายเซ็น APK ไม่ตรงกับแอปที่ติดตั้ง");

            Uri uri = FileProvider.getUriForFile(getContext(), getContext().getPackageName() + ".fileprovider", target);
            Intent installer = new Intent(Intent.ACTION_INSTALL_PACKAGE);
            installer.setData(uri);
            installer.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(installer);
            call.resolve();
        } catch (Exception error) {
            if (target.exists()) target.delete();
            call.reject(error.getMessage() == null ? "ดาวน์โหลดหรือตรวจสอบ APK ไม่สำเร็จ" : error.getMessage(), error);
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private boolean canInstallPackages() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O || getContext().getPackageManager().canRequestPackageInstalls();
    }

    private void validateUrl(URL url) {
        if (!"https".equalsIgnoreCase(url.getProtocol()) || !ALLOWED_HOSTS.contains(url.getHost().toLowerCase(Locale.US))) {
            throw new SecurityException("ต้องเป็น HTTPS ของ Foodchainservice เท่านั้น");
        }
    }

    private long versionCode(PackageInfo info) {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.P ? info.getLongVersionCode() : info.versionCode;
    }

    private boolean sameSigner(PackageInfo installed, PackageInfo candidate) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P || installed.signingInfo == null || candidate.signingInfo == null) return true;
        return Arrays.equals(installed.signingInfo.getApkContentsSigners(), candidate.signingInfo.getApkContentsSigners());
    }

    private String toHex(byte[] bytes) {
        StringBuilder value = new StringBuilder(bytes.length * 2);
        for (byte item : bytes) value.append(String.format(Locale.US, "%02x", item));
        return value.toString();
    }
}
