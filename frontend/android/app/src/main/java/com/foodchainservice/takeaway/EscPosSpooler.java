package com.foodchainservice.takeaway;

import java.io.IOException;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;

/** Length-aware SPP spooling. Never scan binary pixels for command delimiters. */
final class EscPosSpooler {
    static final int MAX_BYTES = 1024 * 1024;
    static final int CHUNK_BYTES = 512;
    static final int CHUNK_PAUSE_MS = 60;
    static final int BAND_PAUSE_MS = 120;
    static final int DRAIN_PAUSE_MS = 500;
    interface Sleeper { void sleep(long millis) throws InterruptedException; }
    interface Connection { boolean isConnected(); }
    static final class Part {
        final int offset, length, pause;
        Part(int offset, int length, int pause) { this.offset = offset; this.length = length; this.pause = pause; }
    }
    static final class Job {
        final byte[] bytes;
        final List<Part> parts;
        Job(byte[] bytes, List<Part> parts) { this.bytes = bytes; this.parts = parts; }
    }

    /** Each independently validated receipt ends in GS V 65 n (feed + FULL cut). */
    static Job compound(byte[][] receipts) throws IOException {
        if (receipts == null || receipts.length < 1 || receipts.length > 2) throw new IOException("One or two copies required");
        List<Part> parts = new ArrayList<>();
        int total = 0;
        for (byte[] receipt : receipts) {
            if (receipt == null) throw new IOException("Missing copy");
            require(receipt, 0, new int[] {27,64,27,97,0});
            for (Part part : plan(receipt)) parts.add(new Part(total + part.offset, part.length, part.pause));
            total += receipt.length;
            if (total > MAX_BYTES) throw new IOException("Compound job exceeds 1 MB");
        }
        byte[] bytes = new byte[total]; int offset = 0;
        for (byte[] receipt : receipts) { System.arraycopy(receipt, 0, bytes, offset, receipt.length); offset += receipt.length; }
        return new Job(bytes, parts);
    }

    static Job cutterTest() throws IOException {
        byte[] sample = {27,64,27,97,0,29,118,48,0,1,0,1,0,(byte)255,27,100,4,29,86,65,16};
        return compound(new byte[][] {sample, sample});
    }

    static List<Part> plan(byte[] bytes) throws IOException {
        if (bytes == null || bytes.length == 0 || bytes.length > MAX_BYTES) throw new IOException("Invalid print byte limit");
        List<Part> parts = new ArrayList<>();
        if (bytes.length == 5 && bytes[0] == 27 && bytes[1] == 112 && (bytes[2] == 0 || bytes[2] == 1)) {
            parts.add(new Part(0, 5, DRAIN_PAUSE_MS)); return parts;
        }
        require(bytes, 0, new int[] {27, 64, 27, 97, 0});
        parts.add(new Part(0, 5, CHUNK_PAUSE_MS));
        int offset = 5, bands = 0;
        while (offset < bytes.length - 7) {
            require(bytes, offset, new int[] {29, 118, 48, 0});
            if (offset + 8 > bytes.length) throw new IOException("Incomplete raster header");
            int width = (bytes[offset + 4] & 255) | ((bytes[offset + 5] & 255) << 8);
            int rows = (bytes[offset + 6] & 255) | ((bytes[offset + 7] & 255) << 8);
            if (width < 1 || width > 72 || rows < 1 || rows > 64) throw new IOException("Invalid raster band dimensions");
            int end = offset + 8 + width * rows;
            if (end > bytes.length - 7) throw new IOException("Truncated raster pixels");
            parts.add(new Part(offset, 8, 0)); // Entire header in one write.
            offset += 8;
            int rowChunk = (CHUNK_BYTES / width) * width;
            while (offset < end) {
                int length = Math.min(rowChunk, end - offset);
                // Only split the declared binary data, at whole-row boundaries.
                parts.add(new Part(offset, length, offset + length == end ? BAND_PAUSE_MS : CHUNK_PAUSE_MS));
                offset += length;
            }
            bands++;
        }
        if (bands == 0 || offset != bytes.length - 7) throw new IOException("Missing raster body or final cut");
        require(bytes, offset, new int[] {27, 100, 4, 29, 86, 65, 16});
        parts.add(new Part(offset, 7, DRAIN_PAUSE_MS));
        return parts;
    }

    private static void require(byte[] bytes, int offset, int[] expected) throws IOException {
        if (offset + expected.length > bytes.length) throw new IOException("Truncated ESC/POS command");
        for (int i = 0; i < expected.length; i++) if ((bytes[offset + i] & 255) != expected[i]) throw new IOException("Unsupported ESC/POS command sequence");
    }

    static void send(byte[] bytes, OutputStream out, Connection connected, Sleeper sleeper) throws IOException, InterruptedException {
        send(new Job(bytes, plan(bytes)), out, connected, sleeper);
    }

    static void send(Job job, OutputStream out, Connection connected, Sleeper sleeper) throws IOException, InterruptedException {
        for (Part part : job.parts) {
            if (!connected.isConnected()) throw new IOException("Bluetooth disconnected; partial print possible");
            out.write(job.bytes, part.offset, part.length); // Blocking write provides transport backpressure.
            out.flush(); // Flush is NOT an acknowledgement from the print head.
            if (part.pause > 0) sleeper.sleep(part.pause);
        }
        if (!connected.isConnected()) throw new IOException("Bluetooth disconnected before drain completed");
    }
}
