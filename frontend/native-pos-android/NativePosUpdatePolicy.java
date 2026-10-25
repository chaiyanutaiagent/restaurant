package com.foodchainservice.nativepos;
import java.net.URL;
import java.util.Arrays;

public final class NativePosUpdatePolicy {
    static String product(String packageName) {
        if ("com.foodchainservice.retail.uat".equals(packageName)) return "retail";
        if ("com.foodchainservice.restaurant.uat".equals(packageName)) return "restaurant";
        throw new SecurityException("Unsupported update channel");
    }
    static String host(String packageName) {
        return product(packageName).equals("retail") ? "uat-retail.foodchainservice.com" : "uat-pos.foodchainservice.com";
    }
    public static String manifestUrl(String packageName) {
        return "https://" + host(packageName) + "/downloads/native-pos-updates/" + product(packageName) + ".json";
    }
    public static boolean allowedUrl(URL url, String packageName) {
        try {
            return "https".equals(url.getProtocol()) && host(packageName).equals(url.getHost())
                && url.getUserInfo() == null && (url.getPort() == -1 || url.getPort() == 443)
                && url.getQuery() == null && url.getRef() == null
                && url.getPath().matches("/downloads/native-pos-[0-9]+\\.[0-9]+\\.[0-9]+-uat\\.[0-9]+/foodchainservice-" + product(packageName) + "-[0-9]+\\.[0-9]+\\.[0-9]+-uat\\.[0-9]+\\.apk");
        } catch (SecurityException error) { return false; }
    }
    public static boolean sameCertificates(byte[][] installed, byte[][] candidate) {
        if (installed == null || candidate == null || installed.length == 0 || installed.length != candidate.length) return false;
        boolean[] matched = new boolean[candidate.length];
        for (byte[] certificate : installed) {
            if (certificate == null || certificate.length == 0) return false;
            boolean found = false;
            for (int i = 0; i < candidate.length; i++) {
                if (!matched[i] && Arrays.equals(certificate, candidate[i])) { matched[i] = true; found = true; break; }
            }
            if (!found) return false;
        }
        return true;
    }
}
