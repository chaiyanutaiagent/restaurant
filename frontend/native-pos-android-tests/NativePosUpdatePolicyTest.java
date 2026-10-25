package com.foodchainservice.nativepos;
import org.junit.Test;
import static org.junit.Assert.*;
import java.net.URL;

public class NativePosUpdatePolicyTest {
    private final String pkg="com.foodchainservice.retail.uat";
    private final String url="https://uat-retail.foodchainservice.com/downloads/native-pos-0.1.0-uat.6/foodchainservice-retail-0.1.0-uat.6.apk";
    @Test public void onlyExactProductHostAndVersionedApkAllowed() throws Exception {
        assertTrue(NativePosUpdatePolicy.allowedUrl(new URL(url),pkg));
        for(String invalid:new String[]{url.replace("https:","http:"),url+"?redirect=1",url+"#x",url.replace(".com/",".com.evil/"),url.replace("/downloads/","/downloads/../"),url.replace("foodchainservice-retail-","foodchainservice-restaurant-"),url.replace("https://","https://user@")})
            assertFalse(invalid,NativePosUpdatePolicy.allowedUrl(new URL(invalid),pkg));
        assertFalse(NativePosUpdatePolicy.allowedUrl(new URL(url),"com.foodchainservice.restaurant.uat"));
        assertFalse(NativePosUpdatePolicy.allowedUrl(new URL(url),"com.foodchainservice.retail"));
    }
    @Test public void certificatesFailClosed() {
        assertFalse(NativePosUpdatePolicy.sameCertificates(null,null));
        assertFalse(NativePosUpdatePolicy.sameCertificates(new byte[][]{},new byte[][]{}));
        assertFalse(NativePosUpdatePolicy.sameCertificates(new byte[][]{{1}},new byte[][]{{2}}));
        assertTrue(NativePosUpdatePolicy.sameCertificates(new byte[][]{{1},{2}},new byte[][]{{2},{1}}));
    }
    @Test public void channelsAreIndependent() {
        assertTrue(NativePosUpdatePolicy.manifestUrl(pkg).endsWith("/retail.json"));
        assertTrue(NativePosUpdatePolicy.manifestUrl("com.foodchainservice.restaurant.uat").contains("uat-pos.foodchainservice.com"));
    }
}
