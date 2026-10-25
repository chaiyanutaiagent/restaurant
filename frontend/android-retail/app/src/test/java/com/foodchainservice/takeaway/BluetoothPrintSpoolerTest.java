package com.foodchainservice.takeaway;
import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.util.*;

public class BluetoothPrintSpoolerTest {
    @Test public void preservesBytesBoundsWritesAndDrainsAfterCut() throws Exception {
        byte[] data = new byte[2057];
        new Random(7).nextBytes(data);
        byte[] tail = {27,100,4,29,86,65,16};
        System.arraycopy(tail,0,data,data.length-tail.length,tail.length);
        List<Long> pauses = new ArrayList<>();
        ByteArrayOutputStream output = new ByteArrayOutputStream() {
            @Override public synchronized void write(byte[] bytes,int offset,int length) {
                assertTrue(length <= 512); super.write(bytes,offset,length);
            }
        };
        BluetoothPrintSpooler.send(data,output,pauses::add);
        assertArrayEquals(data,output.toByteArray());
        assertEquals(Arrays.asList(60L,60L,60L,60L,60L,500L),pauses);
    }
    @Test public void failureDoesNotRetry() throws Exception {
        final int[] writes = {0};
        try {
            BluetoothPrintSpooler.send(new byte[1024],new OutputStream() {
                public void write(int b) throws IOException { writes[0]++; throw new IOException("Disconnected"); }
            },ms -> {});
            fail("Expected failure");
        } catch (IOException expected) { assertEquals(1,writes[0]); }
    }
    @Test public void cutterOnlyDataUnchanged() throws Exception {
        byte[] bytes={27,64,27,100,4,29,86,65,16};
        ByteArrayOutputStream out=new ByteArrayOutputStream();
        BluetoothPrintSpooler.send(bytes,out,ms -> {});
        assertArrayEquals(bytes,out.toByteArray());
    }
}
