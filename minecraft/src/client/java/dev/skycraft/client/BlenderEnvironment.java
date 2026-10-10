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
import net.minecraft.world.inventory.EnchantmentMenu;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.HitResult;
import dev.skycraft.client.mixin.ContainerScreenAccessor;
import org.joml.Vector3fc;

/** Optional Blender render record 12. SkyCraft v11's existing messages stay unchanged. */
public final class BlenderEnvironment {
    private static long next;
    private static String lastDimension = "";
    private static int assetGeneration = Integer.MIN_VALUE;
    private static int assetMask;
    private static String assetMoon = "";
    private static net.minecraft.client.renderer.SkyRenderer skyExtractor;

    public static void invalidateAssets() {
        assetGeneration = Integer.MIN_VALUE;
        assetMask = 0;
        assetMoon = "";
        next = 0;
    }

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
        info.addProperty("windowHidden", (org.lwjgl.sdl.SDLVideo.SDL_GetWindowFlags(mc.getWindow().handle()) &
            org.lwjgl.sdl.SDLVideo.SDL_WINDOW_HIDDEN) != 0);
        if (mc.level != null) {
            info.addProperty("gameTime", mc.level.getGameTime());
            info.addProperty("raining", mc.level.isRaining());
            info.addProperty("thundering", mc.level.isThundering());
            var level = mc.gameRenderer.gameRenderState().levelRenderState;
            var sky = new net.minecraft.client.renderer.state.level.SkyRenderState();
            var weather = new net.minecraft.client.renderer.state.level.WeatherRenderState();
            float partial = mc.getDeltaTracker().getGameTimeDeltaPartialTick(false);
            // Linked mode skips LevelRenderer.render(), which normally creates its SkyRenderer.
            if (skyExtractor == null) skyExtractor = new net.minecraft.client.renderer.SkyRenderer(
                mc.getTextureManager(), mc.getAtlasManager(), mc.gameRenderer.mainRenderTarget());
            skyExtractor.extractRenderState(mc.level, partial, mc.gameRenderer.mainCamera(), sky);
            mc.levelRenderer.weatherEffectRenderer().extractRenderState(mc.level, partial, mc.gameRenderer.mainCamera().position(), weather);
            String moon = sky.moonPhase == null ? "full_moon" : sky.moonPhase.toString().toLowerCase(java.util.Locale.ROOT);
            if (assetGeneration != SkyLink.generation()) {
                assetGeneration = SkyLink.generation();
                assetMask = 0;
                assetMoon = "";
            }
            // Retry each rejected asset independently; a full ring or a missing
            // resource must not continuously re-read/re-upload the other images.
            String[] names = { "celestial/sun", "rain", "snow", "end_sky" };
            int[] ids = { 0, 2, 3, 4 };
            for (int i = 0; i < names.length; i++) {
                if ((assetMask & (1 << i)) == 0 && sendTexture(mc, ids[i], names[i])) assetMask |= 1 << i;
            }
            if (!moon.equals(assetMoon) && sendTexture(mc, 1, "celestial/moon/" + moon)) assetMoon = moon;
            JsonObject atmosphere = new JsonObject();
            atmosphere.addProperty("skybox", sky.skybox == null ? "NONE" : sky.skybox.toString());
            atmosphere.add("skyColor", vector(sky.skyColor));
            atmosphere.addProperty("sunAngle", sky.sunAngle);
            atmosphere.addProperty("moonAngle", sky.moonAngle);
            atmosphere.addProperty("stars", sky.starBrightness);
            atmosphere.addProperty("rainBrightness", sky.rainBrightness);
            atmosphere.addProperty("rain", weather.intensity);
            atmosphere.addProperty("skyFactor", mc.gameRenderer.gameRenderState().lightmapRenderState.skyFactor);
            JsonArray faceShade = new JsonArray();
            for (var direction : net.minecraft.core.Direction.values()) faceShade.add(mc.level.cardinalLighting().byFace(direction));
            atmosphere.add("faceShade", faceShade);
            if (level.cameraRenderState != null && level.cameraRenderState.fogData != null) {
                var fog = level.cameraRenderState.fogData;
                atmosphere.add("fogColor", vector(new org.joml.Vector3f(fog.color.x, fog.color.y, fog.color.z)));
                atmosphere.addProperty("fogStart", fog.environmentalStart);
                atmosphere.addProperty("fogEnd", fog.environmentalEnd);
                atmosphere.addProperty("distanceStart", fog.renderDistanceStart);
                atmosphere.addProperty("distanceEnd", fog.renderDistanceEnd);
                atmosphere.addProperty("fogType", level.cameraRenderState.fogType.toString());
            }
            JsonArray rain = new JsonArray(), snow = new JsonArray();
            for (var c : weather.rainColumns) rain.add(column(c));
            for (var c : weather.snowColumns) snow.add(column(c));
            atmosphere.add("rainColumns", rain);
            atmosphere.add("snowColumns", snow);
            info.add("atmosphere", atmosphere);
            BlenderLightmap.capture(mc);
            if (mc.hitResult instanceof BlockHitResult hit && hit.getType() == HitResult.Type.BLOCK) {
                var pos = hit.getBlockPos();
                JsonObject target = new JsonObject();
                target.addProperty("x", pos.getX());
                target.addProperty("y", pos.getY());
                target.addProperty("z", pos.getZ());
                target.addProperty("state", mc.level.getBlockState(pos).toString());
                info.add("targetBlock", target);
            }
            if (mc.hitResult instanceof EntityHitResult hit) {
                var entity = hit.getEntity();
                JsonObject target = new JsonObject();
                target.addProperty("id", entity.getId());
                target.addProperty("type", net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString());
                target.addProperty("uuid", entity.getUUID().toString());
                if (entity instanceof LivingEntity living) {
                    target.addProperty("health", living.getHealth());
                    target.addProperty("maxHealth", living.getMaxHealth());
                }
                info.add("targetEntity", target);
            }
        }
        if (mc.player != null) {
            info.addProperty("health", mc.player.getHealth());
            info.addProperty("food", mc.player.getFoodData().getFoodLevel());
            info.addProperty("experience", mc.player.experienceLevel);
            info.addProperty("heldItem", mc.player.getMainHandItem().getItem().toString());
            info.add("heldStack", stackInfo(mc.player.getMainHandItem()));
            info.addProperty("feetBlock", mc.player.level().getBlockState(mc.player.blockPosition()).toString());
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
            if (screen.getMenu() instanceof EnchantmentMenu menu) {
                JsonArray offers = new JsonArray();
                for (int i = 0; i < menu.costs.length; i++) {
                    JsonObject offer = new JsonObject();
                    offer.addProperty("index", i);
                    offer.addProperty("requiredLevel", menu.costs[i]);
                    offer.addProperty("enchantmentId", menu.enchantClue[i]);
                    offer.addProperty("enchantmentLevel", menu.levelClue[i]);
                    offers.add(offer);
                }
                info.add("enchantmentOffers", offers);
            }
        }
        if (mc.gameMode != null) info.addProperty("gameMode", mc.gameMode.getPlayerMode().getName());
        SkyLink.tryWriteRender(12, ByteBuffer.wrap(info.toString().getBytes(StandardCharsets.UTF_8)), null);
    }

    private static boolean sendTexture(Minecraft mc, int id, String name) {
        var resource = mc.getResourceManager().getResource(net.minecraft.resources.Identifier.withDefaultNamespace("textures/environment/" + name + ".png"));
        if (resource.isEmpty()) return false;
        try (var input = resource.get().open(); var image = com.mojang.blaze3d.platform.NativeImage.read(input)) {
            int w = image.getWidth(), h = image.getHeight();
            ByteBuffer pixels = ByteBuffer.allocate(w * h * 4);
            for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) {
                int argb = image.getPixel(x, y);
                pixels.put((byte)(argb >> 16)).put((byte)(argb >> 8)).put((byte)argb).put((byte)(argb >>> 24));
            }
            ByteBuffer header = ByteBuffer.allocate(16).order(java.nio.ByteOrder.LITTLE_ENDIAN).putInt(id).putInt(w).putInt(h).putInt(0).flip();
            return SkyLink.tryWriteRender(14, header, pixels.flip());
        } catch (java.io.IOException e) {
            SkyCraft.LOG.warn("MCInBlender: cannot read environment texture {}", name, e);
            return false;
        }
    }

    private static JsonArray vector(Vector3fc value) {
        JsonArray result = new JsonArray();
        result.add(value == null ? 0 : value.x());
        result.add(value == null ? 0 : value.y());
        result.add(value == null ? 0 : value.z());
        return result;
    }

    private static JsonArray column(net.minecraft.client.renderer.WeatherEffectRenderer.ColumnInstance c) {
        JsonArray result = new JsonArray();
        result.add(c.x()); result.add(c.z()); result.add(c.bottomY()); result.add(c.topY());
        result.add(c.uOffset()); result.add(c.vOffset()); result.add(c.lightCoords());
        return result;
    }

    private static JsonObject stackInfo(ItemStack stack) {
        JsonObject info = new JsonObject();
        info.addProperty("item", stack.getItem().toString());
        info.addProperty("count", stack.getCount());
        info.addProperty("enchanted", stack.isEnchanted());
        info.addProperty("damage", stack.getDamageValue());
        return info;
    }
}
