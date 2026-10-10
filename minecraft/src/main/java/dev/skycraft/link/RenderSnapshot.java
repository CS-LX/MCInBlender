package dev.skycraft.link;

import java.util.function.BooleanSupplier;

/** An ordered clear/atlas transaction that survives a full shared-memory ring. */
public final class RenderSnapshot {
    private boolean cleared;
    private boolean complete;

    public void reset() {
        cleared = complete = false;
    }

    /** Never resend an accepted clear: doing so would erase assets sent during an atlas retry. */
    public boolean send(BooleanSupplier clear, BooleanSupplier atlas) {
        if (complete) return true;
        if (!cleared) {
            if (!clear.getAsBoolean()) return false;
            cleared = true;
        }
        complete = atlas.getAsBoolean();
        return complete;
    }
}
