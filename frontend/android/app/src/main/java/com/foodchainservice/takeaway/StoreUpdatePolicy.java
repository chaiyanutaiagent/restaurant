package com.foodchainservice.takeaway;

import java.net.URL;
import java.util.Arrays;

/** Pure policy so unsupported Android versions and missing certificates fail closed. */
final class StoreUpdatePolicy {
    static boolean allowedUrl(URL url, String packageName) {
        String host;
        if ("com.foodchainservice.takeaway.uat".equals(packageName)) host = "uat-takeaway.foodchainservice.com";
        else if ("com.foodchainservice.takeaway".equals(packageName)) host = "downloads.foodchainservice.com";
        else return false;
        return "https".equalsIgnoreCase(url.getProtocol()) && host.equalsIgnoreCase(url.getHost())
            && url.getUserInfo() == null && (url.getPort() == -1 || url.getPort() == 443)
            && url.getQuery() == null && url.getRef() == null
            && url.getPath().startsWith("/downloads/takeaway-store/") && url.getPath().endsWith(".apk")
            && !url.getPath().contains("%") && !url.getPath().contains("/../") && !url.getPath().contains("/./");
    }

    static boolean sameCertificates(byte[][] installed, byte[][] candidate) {
        if (installed == null || candidate == null || installed.length == 0 || installed.length != candidate.length) return false;
        boolean[] matched = new boolean[candidate.length];
        for (byte[] certificate : installed) {
            if (certificate == null || certificate.length == 0) return false;
            boolean found = false;
            for (int i = 0; i < candidate.length; i++) {
                if (!matched[i] && Arrays.equals(certificate, candidate[i])) {
                    matched[i] = true;
                    found = true;
                    break;
                }
            }
            if (!found) return false;
        }
        return true;
    }
}
