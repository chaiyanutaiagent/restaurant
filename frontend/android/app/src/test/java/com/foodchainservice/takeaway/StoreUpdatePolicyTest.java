package com.foodchainservice.takeaway;

import org.junit.Test;
import java.net.URL;
import static org.junit.Assert.*;

public class StoreUpdatePolicyTest {
    private static final String UAT = "com.foodchainservice.takeaway.uat";
    private static final String PROD = "com.foodchainservice.takeaway";

    @Test public void channelIsBoundToInstalledPackage() throws Exception {
        URL uat = new URL("https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/a.apk");
        URL prod = new URL("https://downloads.foodchainservice.com/downloads/takeaway-store/a.apk");
        assertTrue(StoreUpdatePolicy.allowedUrl(uat, UAT));
        assertTrue(StoreUpdatePolicy.allowedUrl(prod, PROD));
        assertFalse(StoreUpdatePolicy.allowedUrl(uat, PROD));
        assertFalse(StoreUpdatePolicy.allowedUrl(prod, UAT));
        assertFalse(StoreUpdatePolicy.allowedUrl(uat, "another.package"));
    }

    @Test public void untrustedDestinationsAreRejected() throws Exception {
        for (String value : new String[] {
            "http://uat-takeaway.foodchainservice.com/downloads/takeaway-store/a.apk",
            "https://uat-takeaway.foodchainservice.com.evil.test/downloads/takeaway-store/a.apk",
            "https://user@uat-takeaway.foodchainservice.com/downloads/takeaway-store/a.apk",
            "https://uat-takeaway.foodchainservice.com:444/downloads/takeaway-store/a.apk",
            "https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/a.apk?token=secret",
            "https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/a.apk#fragment",
            "https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/../a.apk",
            "https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/%2e%2e/a.apk"
        }) assertFalse(value, StoreUpdatePolicy.allowedUrl(new URL(value), UAT));
    }

    @Test public void missingOrDifferentCertificatesFailClosed() {
        byte[][] one = { {1, 2} };
        assertFalse(StoreUpdatePolicy.sameCertificates(null, one));
        assertFalse(StoreUpdatePolicy.sameCertificates(one, null));
        assertFalse(StoreUpdatePolicy.sameCertificates(new byte[0][], new byte[0][]));
        assertFalse(StoreUpdatePolicy.sameCertificates(new byte[][] {null}, new byte[][] {null}));
        assertFalse(StoreUpdatePolicy.sameCertificates(new byte[][] {{}}, new byte[][] {{}}));
        assertFalse(StoreUpdatePolicy.sameCertificates(one, new byte[][] {{1, 3}}));
        assertFalse(StoreUpdatePolicy.sameCertificates(one, new byte[][] {{1, 2}, {3}}));
    }

    @Test public void certificateComparisonIgnoresOrderButNotMultiplicity() {
        assertTrue(StoreUpdatePolicy.sameCertificates(new byte[][] {{1}, {2}}, new byte[][] {{2}, {1}}));
        assertFalse(StoreUpdatePolicy.sameCertificates(new byte[][] {{1}, {1}}, new byte[][] {{1}, {2}}));
    }
}
