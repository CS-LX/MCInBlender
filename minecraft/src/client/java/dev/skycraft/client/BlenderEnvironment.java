package dev.skycraft.client;

import com.google.gson.JsonObject;
import dev.skycraft.SkyCraft;
import dev.skycraft.link.SkyLink;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import net.minecraft.client.Minecraft;

/** Optional Blender render record 12. SkyCraft v11's existing messages stay unchanged. */
public final class BlenderEnvironment {
    private static long next;
    private static String lastDimension = "";

    public static void send(Minecraft mc) {
        String dimension = mc.level == null ? "" : mc.level.dimension().identifier().toString();
        long now = System.nanoTime();
        if (now < next && dimension.equals(lastDimension)) return;
        next = now + 100_000_000L;
        lastDimension = dimension;
        JsonObject info = new JsonObject();
        info.addProperty("schema", 1);
        info.addProperty("dimension", dimension);
        info.addProperty("vanilla", SkyCraft.VANILLA);
        info.addProperty("screen", mc.gui.screen() == null ? "" : mc.gui.screen().getClass().getSimpleName());
        info.addProperty("paused", mc.isPaused());
        if (mc.level != null) {
            info.addProperty("gameTime", mc.level.getGameTime());
            info.addProperty("raining", mc.level.isRaining());
            info.addProperty("thundering", mc.level.isThundering());
        }
        if (mc.player != null) {
            info.addProperty("health", mc.player.getHealth());
            info.addProperty("food", mc.player.getFoodData().getFoodLevel());
            info.addProperty("experience", mc.player.experienceLevel);
            info.addProperty("heldItem", mc.player.getMainHandItem().getItem().toString());
        }
        if (mc.gameMode != null) info.addProperty("gameMode", mc.gameMode.getPlayerMode().getName());
        SkyLink.tryWriteRender(12, ByteBuffer.wrap(info.toString().getBytes(StandardCharsets.UTF_8)), null);
    }
}
