package com.foodchainservice.takeaway;

import java.io.IOException;

/** Persist BEFORE transport. A reserved ID is never automatically retransmitted, even after restart. */
final class PrintAttemptLedger {
    interface Store { boolean contains(String key); boolean put(String key, String value); }
    private final Store store;
    PrintAttemptLedger(Store store) { this.store = store; }
    synchronized void reserve(String id, String address) throws IOException {
        if (id == null || !id.matches("[0-9a-fA-F-]{36}")) throw new IOException("Invalid print attempt ID");
        String key = "print-attempt:" + id;
        if (store.contains(key)) throw new IOException("Print outcome already reserved; inspect paper, never auto retry");
        if (!store.put(key, address + ":unknown")) throw new IOException("Cannot persist print attempt safely");
    }
}
