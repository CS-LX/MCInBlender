package dev.skycraft.link;

import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class RenderSnapshotTest {
    @Test void rejectedClearDoesNotPublishAtlas() {
        RenderSnapshot transfer = new RenderSnapshot();
        assertFalse(transfer.send(() -> false, () -> fail("atlas preceded clear")));
        assertTrue(transfer.send(() -> true, () -> true));
    }

    @Test void retriesAtlasWithoutErasingAssetsSentWhileWaiting() {
        RenderSnapshot transfer = new RenderSnapshot();
        List<String> accepted = new ArrayList<>();
        assertFalse(transfer.send(() -> { accepted.add("clear"); return true; }, () -> false));
        accepted.add("sky textures");
        assertTrue(transfer.send(() -> fail("clear repeated"), () -> { accepted.add("atlas"); return true; }));
        assertTrue(transfer.send(() -> fail("completed clear repeated"), () -> fail("completed atlas repeated")));
        assertEquals(List.of("clear", "sky textures", "atlas"), accepted);
    }

    @Test void reconnectRestartsBothStages() {
        RenderSnapshot transfer = new RenderSnapshot();
        assertTrue(transfer.send(() -> true, () -> true));
        transfer.reset();
        assertFalse(transfer.send(() -> false, () -> fail("new host needs clear first")));
        assertTrue(transfer.send(() -> true, () -> true));
    }
}
