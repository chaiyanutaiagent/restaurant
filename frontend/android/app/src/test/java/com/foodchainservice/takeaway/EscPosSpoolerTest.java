package com.foodchainservice.takeaway;

import org.junit.Test;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.Assert.*;

public class EscPosSpoolerTest {
    @Test public void compoundIsExactlyCustomerCutPreparationCutAndPreservesPacing() throws Exception {
        byte[] customer = receipt(4), preparation = receipt(7);
        EscPosSpooler.Job job = EscPosSpooler.compound(new byte[][] {customer, preparation});
        ByteArrayOutputStream out = new ByteArrayOutputStream(); List<Long> sleeps = new ArrayList<>();
        EscPosSpooler.send(job, out, () -> true, sleeps::add);
        ByteArrayOutputStream expected = new ByteArrayOutputStream(); expected.write(customer); expected.write(preparation);
        assertArrayEquals(expected.toByteArray(), out.toByteArray());
        int cuts = 0;
        for (EscPosSpooler.Part part : job.parts) {
            assertTrue(part.length <= 512);
            if (part.length == 7) {
                assertArrayEquals(new byte[] {27,100,4,29,86,65,16}, Arrays.copyOfRange(job.bytes, part.offset, part.offset + 7));
                assertEquals(500, part.pause); cuts++;
            }
        }
        assertEquals(2, cuts);
        assertEquals(11, sleeps.stream().filter(ms -> ms == 120).count());
    }
    @Test public void failureAtEverySegmentIncludingBothCutsNeverRetries() throws Exception {
        EscPosSpooler.Job job = EscPosSpooler.compound(new byte[][] {receipt(1), receipt(1)});
        for (int failAt = 0; failAt < job.parts.size(); failAt++) {
            final int failing = failAt; AtomicInteger attempts = new AtomicInteger();
            ByteArrayOutputStream out = new ByteArrayOutputStream() {
                @Override public void flush() throws IOException { if (attempts.getAndIncrement() == failing) throw new IOException("uncertain transport"); }
            };
            try { EscPosSpooler.send(job, out, () -> true, ms -> {}); fail(); } catch (IOException expected) { }
            assertEquals(failAt + 1, attempts.get());
            int prefix = job.parts.get(failAt).offset + job.parts.get(failAt).length;
            assertArrayEquals(Arrays.copyOf(job.bytes, prefix), out.toByteArray());
        }
    }
    @Test public void validatesSecondCopyBeforeAnyBytesAndIndividualRecoveryHasOneCut() throws Exception {
        byte[] broken = receipt(1); broken[broken.length - 4] = 0;
        try { EscPosSpooler.compound(new byte[][] {receipt(1), broken}); fail(); } catch (IOException expected) { }
        EscPosSpooler.Job single = EscPosSpooler.compound(new byte[][] {receipt(1)});
        assertEquals(1, single.parts.stream().filter(p -> p.length == 7).count());
        assertEquals(2, EscPosSpooler.cutterTest().parts.stream().filter(p -> p.length == 7).count());
        try { EscPosSpooler.compound(new byte[][] {{27,112,0,25,(byte)250}}); fail(); } catch (IOException expected) { }
    }
    private byte[] receipt(int bands) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(new byte[] {27,64,27,97,0});
        for (int band = 0; band < bands; band++) {
            int rows = band == bands - 1 ? 17 : 64;
            out.write(new byte[] {29,118,48,0,72,0,(byte) rows,0});
            byte[] pixels = new byte[72 * rows];
            for (int i = 0; i < pixels.length; i++) pixels[i] = (byte) (i * 31 + band);
            // Binary pixels can contain any command-looking sequence.
            System.arraycopy(new byte[] {27,100,4,29,86,65,16,29,118,48,0}, 0, pixels, 0, 11);
            out.write(pixels);
        }
        out.write(new byte[] {27,100,4,29,86,65,16}); return out.toByteArray();
    }
    @Test public void longReceiptReconstructsExactlyWithWholeHeadersRowsAndOneCut() throws Exception {
        byte[] job = receipt(100);
        List<Integer> lengths = new ArrayList<>();
        AtomicInteger flushes = new AtomicInteger();
        ByteArrayOutputStream out = new ByteArrayOutputStream() {
            @Override public void write(byte[] bytes, int offset, int length) { lengths.add(length); super.write(bytes, offset, length); }
            @Override public void flush() { flushes.incrementAndGet(); }
        };
        List<Long> pauses = new ArrayList<>();
        EscPosSpooler.send(job, out, () -> true, pauses::add);
        assertArrayEquals(job, out.toByteArray());
        assertEquals(lengths.size(), flushes.get());
        assertEquals(100, lengths.stream().filter(n -> n == 8).count());
        assertEquals(1, lengths.stream().filter(n -> n == 7).count());
        for (int length : lengths) assertTrue(length <= 512);
        for (EscPosSpooler.Part part : EscPosSpooler.plan(job)) {
            if (part.length != 5 && part.length != 7 && part.length != 8) assertEquals(0, part.length % 72);
        }
        assertEquals(100, pauses.stream().filter(n -> n == EscPosSpooler.BAND_PAUSE_MS).count());
        assertEquals(Long.valueOf(500), pauses.get(pauses.size() - 1));
    }
    @Test public void disconnectStopsWithoutRetryOrCut() throws Exception {
        byte[] job = receipt(3); ByteArrayOutputStream out = new ByteArrayOutputStream();
        AtomicInteger checks = new AtomicInteger();
        try { EscPosSpooler.send(job, out, () -> checks.incrementAndGet() <= 3, ms -> {}); fail(); }
        catch (IOException expected) { assertTrue(expected.getMessage().contains("disconnected")); }
        assertTrue(out.size() > 0 && out.size() < job.length);
        assertArrayEquals(Arrays.copyOf(job, out.size()), out.toByteArray());
    }
    @Test public void flushFailureIsReportedWithoutRetry() throws Exception {
        AtomicInteger writes = new AtomicInteger();
        ByteArrayOutputStream out = new ByteArrayOutputStream() {
            @Override public void write(byte[] b, int off, int len) { writes.incrementAndGet(); super.write(b, off, len); }
            @Override public void flush() throws IOException { throw new IOException("SPP failed"); }
        };
        try { EscPosSpooler.send(receipt(2), out, () -> true, ms -> {}); fail(); }
        catch (IOException expected) { assertEquals("SPP failed", expected.getMessage()); }
        assertEquals(1, writes.get()); assertEquals(5, out.size());
    }
    @Test public void validatesEntireJobBeforeWritingAndRejectsLimits() throws Exception {
        byte[] good = receipt(2), broken = good.clone(); broken[broken.length - 1] = 0;
        for (byte[] job : new byte[][] {new byte[0], new byte[EscPosSpooler.MAX_BYTES + 1], broken, Arrays.copyOf(good, good.length - 1)}) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            try { EscPosSpooler.send(job, out, () -> true, ms -> {}); fail(); }
            catch (IOException expected) { assertEquals(0, out.size()); }
        }
    }
    @Test public void rejectsWideOrUnboundedBands() throws Exception {
        for (int index : new int[] {9, 11}) {
            byte[] job = receipt(2); job[index] = (byte) 129;
            try { EscPosSpooler.plan(job); fail(); } catch (IOException expected) { }
        }
    }
    @Test public void interruptionDoesNotContinueAndDrainDisconnectFails() throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try { EscPosSpooler.send(receipt(2), out, () -> true, ms -> { throw new InterruptedException(); }); fail(); }
        catch (InterruptedException expected) { assertEquals(5, out.size()); }
        byte[] job = receipt(1); AtomicInteger checks = new AtomicInteger();
        int count = EscPosSpooler.plan(job).size();
        try { EscPosSpooler.send(job, new ByteArrayOutputStream(), () -> checks.incrementAndGet() <= count, ms -> {}); fail(); }
        catch (IOException expected) { assertTrue(expected.getMessage().contains("drain")); }
    }
    @Test public void drawerPulsePreservedWithoutAddingCut() throws Exception {
        byte[] pulse = {27,112,0,25,(byte)250}; ByteArrayOutputStream out = new ByteArrayOutputStream();
        EscPosSpooler.send(pulse, out, () -> true, ms -> {}); assertArrayEquals(pulse, out.toByteArray());
    }
}
