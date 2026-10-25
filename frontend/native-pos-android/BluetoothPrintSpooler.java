package com.foodchainservice.takeaway;

import java.io.IOException;
import java.io.OutputStream;

/** Bounded SPP writes with a final drain interval. No automatic receipt retries. */
public final class BluetoothPrintSpooler {
    public interface Sleeper { void sleep(long milliseconds) throws InterruptedException; }
    public static void send(byte[] bytes, OutputStream output, Sleeper sleeper) throws IOException, InterruptedException {
        if (bytes == null || bytes.length == 0 || bytes.length > 1024 * 1024) throw new IOException("Invalid print job size");
        for (int offset = 0; offset < bytes.length; offset += 512) {
            output.write(bytes, offset, Math.min(512, bytes.length - offset));
            output.flush();
            sleeper.sleep(60);
        }
        // flush() is not a printer acknowledgement; allow the BT stack to drain.
        sleeper.sleep(500);
    }
}
