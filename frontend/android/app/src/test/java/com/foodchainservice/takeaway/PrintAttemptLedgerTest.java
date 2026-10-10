package com.foodchainservice.takeaway;
import org.junit.Test;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import static org.junit.Assert.*;

public class PrintAttemptLedgerTest {
    @Test public void duplicateAndRestartNeverReserveOrTransmitAgain() throws Exception {
        Map<String, String> values = new HashMap<>();
        PrintAttemptLedger.Store store = new PrintAttemptLedger.Store() {
            public boolean contains(String key) { return values.containsKey(key); }
            public boolean put(String key, String value) { values.put(key, value); return true; }
        };
        String id = "11111111-1111-4111-8111-111111111111";
        new PrintAttemptLedger(store).reserve(id, "AA:BB:CC:DD:EE:FF");
        try { new PrintAttemptLedger(store).reserve(id, "AA:BB:CC:DD:EE:FF"); fail(); } catch (IOException expected) { }
        assertEquals(1, values.size());
        new PrintAttemptLedger(store).reserve("22222222-2222-4222-8222-222222222222", "AA:BB:CC:DD:EE:FF");
        assertEquals(2, values.size());
    }
    @Test public void persistenceFailureAndMissingIdentityFailClosed() throws Exception {
        PrintAttemptLedger ledger = new PrintAttemptLedger(new PrintAttemptLedger.Store() {
            public boolean contains(String key) { return false; }
            public boolean put(String key, String value) { return false; }
        });
        for (String id : new String[] {null, "bad", "11111111-1111-4111-8111-111111111111"}) {
            try { ledger.reserve(id, "printer"); fail(); } catch (IOException expected) { }
        }
    }
}
