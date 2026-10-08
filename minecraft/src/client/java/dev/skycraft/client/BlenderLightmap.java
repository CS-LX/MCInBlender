package dev.skycraft.client;

import com.mojang.blaze3d.systems.RenderSystem;
import com.mojang.renderpearl.api.buffers.GpuBuffer;
import dev.skycraft.link.SkyLink;
import net.minecraft.client.Minecraft;

/** Small asynchronous readback of vanilla's final 16x16 block/sky light palette. */
final class BlenderLightmap {
    private static GpuBuffer buffer;
    private static volatile boolean ready;
    private static boolean pending;
    private static int generation;

    static void capture(Minecraft mc) {
        if (ready) {
            try (var mapped = buffer.map(true, false)) {
                if (generation == SkyLink.generation())
                    SkyLink.tryWriteRender(13, mapped.data().duplicate().limit(16 * 16 * 4), null);
            }
            pending = ready = false;
        }
        if (pending) return;
        if (buffer == null) buffer = RenderSystem.getDevice().createBuffer(() -> "MCInBlender lightmap readback", 9, 16 * 16 * 4);
        pending = true;
        generation = SkyLink.generation();
        RenderSystem.getDevice().createCommandEncoder().copyTextureToBuffer(
            mc.gameRenderer.levelLightmap().texture(), buffer, 0L, () -> ready = true, 0);
    }
}
