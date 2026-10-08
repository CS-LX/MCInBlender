package dev.skycraft.client;

import com.google.gson.JsonObject;
import com.google.gson.JsonArray;
import dev.skycraft.SkyCraft;
import dev.skycraft.link.SkyLink;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import dev.skycraft.client.mixin.ContainerScreenAccessor;

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
            if (mc.hitResult instanceof BlockHitResult hit && hit.getType() == HitResult.Type.BLOCK) {
                var pos = hit.getBlockPos();
                JsonObject target = new JsonObject();
                target.addProperty("x", pos.getX());
                target.addProperty("y", pos.getY());
                target.addProperty("z", pos.getZ());
                target.addProperty("state", mc.level.getBlockState(pos).toString());
                info.add("targetBlock", target);
            }
        }
        if (mc.player != null) {
            info.addProperty("health", mc.player.getHealth());
            info.addProperty("food", mc.player.getFoodData().getFoodLevel());
            info.addProperty("experience", mc.player.experienceLevel);
            info.addProperty("heldItem", mc.player.getMainHandItem().getItem().toString());
            JsonObject inventory = new JsonObject();
            for (int i = 0; i < mc.player.getInventory().getContainerSize(); i++) {
                ItemStack stack = mc.player.getInventory().getItem(i);
                if (stack.isEmpty()) continue;
                String item = stack.getItem().toString();
                int count = inventory.has(item) ? inventory.get(item).getAsInt() : 0;
                inventory.addProperty(item, count + stack.getCount());
            }
            info.add("inventory", inventory);
            info.add("carried", stackInfo(mc.player.containerMenu.getCarried()));
        }
        if (mc.gui.screen() instanceof AbstractContainerScreen<?> screen) {
            ContainerScreenAccessor access = (ContainerScreenAccessor) screen;
            info.addProperty("menuLeft", access.mciblender$left());
            info.addProperty("menuTop", access.mciblender$top());
            info.addProperty("guiWidth", screen.width);
            info.addProperty("guiHeight", screen.height);
            JsonArray slots = new JsonArray();
            for (Slot slot : screen.getMenu().slots) {
                JsonObject entry = stackInfo(slot.getItem());
                entry.addProperty("index", slot.index);
                entry.addProperty("x", slot.x);
                entry.addProperty("y", slot.y);
                entry.addProperty("active", slot.isActive());
                slots.add(entry);
            }
            info.add("menuSlots", slots);
        }
        if (mc.gameMode != null) info.addProperty("gameMode", mc.gameMode.getPlayerMode().getName());
        SkyLink.tryWriteRender(12, ByteBuffer.wrap(info.toString().getBytes(StandardCharsets.UTF_8)), null);
    }

    private static JsonObject stackInfo(ItemStack stack) {
        JsonObject info = new JsonObject();
        info.addProperty("item", stack.getItem().toString());
        info.addProperty("count", stack.getCount());
        return info;
    }
}
