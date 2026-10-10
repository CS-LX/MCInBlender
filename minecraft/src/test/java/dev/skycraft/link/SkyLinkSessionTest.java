package dev.skycraft.link;

import static dev.skycraft.link.Proto.*;
import static java.lang.foreign.ValueLayout.*;
import static org.junit.jupiter.api.Assertions.*;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;

/** Exercises the actual Windows heartbeat/poll path with an isolated mapped-header substitute. */
@EnabledOnOs(OS.WINDOWS)
class SkyLinkSessionTest {
    private Arena arena;
    private MemorySegment header;

    private static void field(String name, Object value) throws ReflectiveOperationException {
        var field = SkyLink.class.getDeclaredField(name);
        field.setAccessible(true);
        field.set(null, value);
    }

    @BeforeEach void setup() throws ReflectiveOperationException {
        arena = Arena.ofShared();
        header = arena.allocate(0x12000, 64);
        field("shm", header);
        field("generation", 0);
        field("hostGeneration", 0L);
        field("skyrimPid", 0);
        header.set(JAVA_INT, H_MAGIC, MAGIC);
        header.set(JAVA_INT, H_VERSION, VERSION);
        header.set(JAVA_INT, H_SKYRIM_PID, 1234);
        header.set(JAVA_INT, OFF_SKY_STATE + SS_SEQ, 2);
        start(10);
    }

    @AfterEach void cleanup() throws ReflectiveOperationException {
        field("shm", null);
        arena.close();
    }

    private void start(long nonce) {
        header.set(JAVA_LONG, H_HOST_GENERATION, nonce);
        header.set(JAVA_LONG, H_CLIENT_GENERATION, 0);
        header.set(JAVA_LONG, H_MC_HEARTBEAT, 0);
        header.set(JAVA_LONG, H_SKYRIM_HEARTBEAT, SkyLink.tickCount());
    }

    @Test void rapidSameProcessRestartRequiresNewAcknowledgement() {
        SkyLink.poll();
        assertTrue(SkyLink.active());
        assertEquals(10, header.get(JAVA_LONG, H_CLIENT_GENERATION));
        int firstGeneration = SkyLink.generation();
        // No missed-heartbeat timeout or PID change, exactly like opening another .blend.
        start(11);
        assertFalse(SkyLink.active());
        SkyLink.poll();
        assertTrue(SkyLink.active());
        assertEquals(firstGeneration + 1, SkyLink.generation());
        assertEquals(11, header.get(JAVA_LONG, H_CLIENT_GENERATION));
        assertTrue(header.get(JAVA_LONG, H_MC_HEARTBEAT) > 0);
        SkyLink.poll();
        assertEquals(firstGeneration + 1, SkyLink.generation());
    }

    @Test void zeroStateIsNeverAcknowledgedAndOrdinarySeqlockWriteDoesNotDisconnect() {
        header.set(JAVA_INT, OFF_SKY_STATE + SS_SEQ, 0);
        SkyLink.poll();
        assertFalse(SkyLink.active());
        assertEquals(0, header.get(JAVA_LONG, H_MC_HEARTBEAT));
        assertEquals(0, header.get(JAVA_LONG, H_CLIENT_GENERATION));
        header.set(JAVA_INT, OFF_SKY_STATE + SS_SEQ, 2);
        SkyLink.poll();
        assertTrue(SkyLink.active());
        header.set(JAVA_INT, OFF_SKY_STATE + SS_SEQ, 3);
        assertTrue(SkyLink.active());
    }

    @Test void stoppedOrFutureHeartbeatIsOffline() {
        SkyLink.poll();
        header.set(JAVA_LONG, H_SKYRIM_HEARTBEAT, 0);
        assertFalse(SkyLink.active());
        header.set(JAVA_LONG, H_SKYRIM_HEARTBEAT, SkyLink.tickCount() + 10000);
        assertFalse(SkyLink.active());
    }

    @Test void olderBlenderHostStillUsesPidAcknowledgement() {
        start(0);
        SkyLink.poll();
        assertTrue(SkyLink.active());
        int generation = SkyLink.generation();
        header.set(JAVA_INT, H_MC_PID, 0);
        SkyLink.poll();
        assertEquals(generation + 1, SkyLink.generation());
    }

    @Test void delayedOverlayDoesNotPublishIntoReplacementHost() {
        SkyLink.poll();
        int captured = SkyLink.generation();
        start(11);
        SkyLink.poll();
        SkyLink.publishOverlay(640, 360, true, 100, captured);
        assertEquals(0, header.get(JAVA_INT, OFF_OVERLAY_CTL + OC_STATE));
        SkyLink.publishOverlay(640, 360, true, 101, SkyLink.generation());
        assertNotEquals(0, header.get(JAVA_INT, OFF_OVERLAY_CTL + OC_STATE) & OVERLAY_DIRTY);
    }

    @Test void hostResetInsideInputCallbackCannotPublishOldTail() {
        SkyLink.poll();
        header.set(JAVA_LONG, OFF_INPUT_RING + IR_HEAD, 1);
        SkyLink.drainInput((type, code, a, b, c) -> {
            start(11);
            header.set(JAVA_LONG, OFF_INPUT_RING + IR_HEAD, 0);
            header.set(JAVA_LONG, OFF_INPUT_RING + IR_TAIL, 0);
            SkyLink.poll(); // already live again: checking only active() is insufficient
        });
        assertEquals(0, header.get(JAVA_LONG, OFF_INPUT_RING + IR_TAIL));
        SkyLink.poll();
        header.set(JAVA_LONG, OFF_INPUT_RING + IR_HEAD, 1);
        int[] count = {0};
        SkyLink.drainInput((type, code, a, b, c) -> count[0]++);
        assertEquals(1, count[0]);
        assertEquals(1, header.get(JAVA_LONG, OFF_INPUT_RING + IR_TAIL));
    }

    @Test void incompleteClientAcknowledgementIsOffline() {
        SkyLink.poll();
        header.set(JAVA_LONG, H_CLIENT_GENERATION, 0);
        assertFalse(SkyLink.active());
        SkyLink.poll();
        assertTrue(SkyLink.active());
    }
}
