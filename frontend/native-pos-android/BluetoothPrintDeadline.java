package com.foodchainservice.takeaway;

import java.io.IOException;
import java.util.Timer;
import java.util.TimerTask;
import java.util.concurrent.atomic.AtomicBoolean;

/** A socket must be closed on timeout: a JS-only timeout leaves native IO busy. */
public final class BluetoothPrintDeadline {
    public interface Operation { void run() throws Exception; }
    public static void run(long milliseconds, Operation operation, Runnable abort) throws Exception {
        AtomicBoolean finished = new AtomicBoolean(false);
        AtomicBoolean timedOut = new AtomicBoolean(false);
        Timer timer = new Timer("pos-print-deadline", true);
        timer.schedule(new TimerTask() {
            @Override public void run() {
                if (finished.compareAndSet(false, true)) {
                    timedOut.set(true);
                    abort.run();
                }
            }
        }, milliseconds);
        try {
            operation.run();
        } finally {
            finished.set(true);
            timer.cancel();
            if (timedOut.get()) throw new IOException("หมดเวลารอ Bluetooth กรุณาตรวจเครื่องและกระดาษก่อนพิมพ์ซ้ำ");
        }
    }
}
