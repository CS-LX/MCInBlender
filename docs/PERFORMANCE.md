# Dust II viewport performance

Measured on 2026-10-09 with Steam Blender 5.0.1, Minecraft 26.3, an RTX 4060 Laptop
GPU, and the generated Dust II whitebox (740 objects, 445 colliders).
The viewport was 2098 × 1314, solid shading, cavity disabled. Measurements used
the same T spawn `(0, 203, 42)`, yaw 180°, pitch 10°, and an unpaused survival world.
Minecraft environment lighting was disabled in both runs. Each phase sampled
16–20 seconds after world loading; FPS counts actual Blender draw callbacks,
not Minecraft's faster hidden rendering loop.

| Configuration | Before | After |
|---|---:|---:|
| Minecraft terrain visible, 1724 × 1080 HUD | 19.8 FPS | 27.4 FPS |
| Terrain hidden, 1724 × 1080 HUD | 28.5 FPS | 31.6 FPS |
| Terrain hidden, approximately 1150 × 720 HUD | 36.9 FPS | 40.9 FPS |
| Visible-terrain GPU draw calls | 842 | 161 |
| Visible-terrain callback time | 27.3 ms | 15.1 ms |

The optimized visible-terrain run retained 2548 sections versus 2490 in the
baseline as nearby chunks settled. These are short local samples, not a 60 FPS
guarantee or a benchmark of every viewing direction. Walking around the map and
turning on hidden terrain again were checked separately.

Changes:

- Combine nearby opaque triangles into 64-block cells. Transparent sections
  retain the original sorting and geometry.
- Stop invisible world export in the matching Minecraft mod. Older mods can
  still connect; the Blender side defers their hidden GPU uploads.
- Reuse the float conversion buffer for hand/HUD uploads; offer 720p and 1080p.
  The world and Blender meshes still render at the viewport resolution.
- Account for update time in the host timer, instead of adding 16.7 ms after
  every update. Report FPS when only the Blender scene and HUD are visible too.

Validation: CPU tests cover negative-coordinate batching, replacement and
deletion. `scripts/verify_render_updates.py` runs in a Blender draw callback and
compares GPU pixels for HUD buffer reuse, flip, resize, batching, transparency
and deletion. Live checks cover walking/collision and a fresh world snapshot
after re-enabling terrain. Local detailed samples are saved under
`artifacts/dust2-performance/` and are intentionally not included in releases.
