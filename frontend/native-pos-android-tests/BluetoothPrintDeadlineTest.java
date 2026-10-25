package com.foodchainservice.takeaway;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.IOException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BluetoothPrintDeadlineTest {
    @Test public void successfulOperationDoesNotAbort() throws Exception {
        AtomicInteger aborts = new AtomicInteger();
        BluetoothPrintDeadline.run(1000, () -> {}, aborts::incrementAndGet);
        assertEquals(0, aborts.get());
    }
    @Test public void timeoutClosesBlockedTransportWithoutRetry() throws Exception {
        AtomicInteger sends = new AtomicInteger();
        AtomicInteger aborts = new AtomicInteger();
        CountDownLatch closed = new CountDownLatch(1);
        try {
            BluetoothPrintDeadline.run(20, () -> {
                sends.incrementAndGet();
                assertTrue(closed.await(2, TimeUnit.SECONDS));
            }, () -> { aborts.incrementAndGet(); closed.countDown(); });
            fail("Expected timeout");
        } catch (IOException expected) {
            assertEquals(1, sends.get()); assertEquals(1, aborts.get());
        }
    }
    @Test public void transportErrorIsNotRetried() throws Exception {
        AtomicInteger sends = new AtomicInteger();
        try {
            BluetoothPrintDeadline.run(1000, () -> { sends.incrementAndGet(); throw new IOException("unplugged"); }, () -> {});
            fail("Expected disconnect");
        } catch (IOException expected) { assertEquals(1, sends.get()); }
    }
}
