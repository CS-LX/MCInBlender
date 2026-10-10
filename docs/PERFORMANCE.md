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

## Architecture review, 2026-10-10

The measurements above belong to the previous optimization; they are not results
for the reconnect and upload changes below. Their detailed samples
help identify the remaining bottleneck: the visible-terrain run measured about
77 Minecraft frames per second but only 27.4 Blender viewport frames per second.
The host update took about 1.6 ms, while the 1080p hand/HUD upload took about
9.7 ms. At 720p, the upload took about 4.3 ms. These are local callback timings,
not isolated GPU execution times or evidence of a fixed 30 FPS limit.

The upstream SkyCraft revision is still `bfcaf178524b92c2cdeb88e4ce0f13ef9ded6f32`.
Its native C++ host reuses a D3D11 RGBA8 overlay texture and copies byte pixels
into it. The current implementation does not use the GPU-sharing path proposed
in its design document. It also starts a void mirror world, so a demonstration
with only player-placed blocks is not the same workload as rendering Blender's
scene together with thousands of normal Minecraft terrain sections. The public
repository does not provide a standardized host-FPS comparison.
See the actual [overlay implementation](https://github.com/chasmlol/SkyCraft/blob/bfcaf178524b92c2cdeb88e4ce0f13ef9ded6f32/skse/src/Overlay.cpp#L156)
and [mirror-world creation](https://github.com/chasmlol/SkyCraft/blob/bfcaf178524b92c2cdeb88e4ce0f13ef9ded6f32/fabric/src/client/java/dev/skycraft/client/MirrorWorld.java#L13).

Blender 5.0.1's Python `GPUTexture` constructor accepts only FLOAT buffers and
does not expose a texture update method. The existing RGBA8 overlay upload
therefore expands each four-byte pixel to sixteen bytes of CPU float data and
creates a new texture. A supported alternative is to upload four U8 vertex
components per pixel, let `INT_TO_FLOAT_UNIT` normalize them on the GPU, and
rasterize one point per texel into a reusable RGBA8 framebuffer. This avoids
CPU float expansion while adding a GPU raster pass; live measurements must
determine its net benefit. The Python vertex buffer is static and cannot be
refilled after its first draw, so this approach still creates a vertex buffer
for each uploaded image.
See Blender's [texture constructor](https://github.com/blender/blender/blob/v5.0.1/source/blender/python/gpu/gpu_py_texture.cc#L178),
[vertex formats](https://github.com/blender/blender/blob/v5.0.1/source/blender/python/gpu/gpu_py_vertex_format.cc#L23),
and [vertex-buffer upload](https://github.com/blender/blender/blob/v5.0.1/source/blender/python/gpu/gpu_py_vertex_buffer.cc#L97).

Frame pacing is another candidate for measurement. The inherited Minecraft
pacer waits up to 25 ms for a new host state before treating the host as stalled;
subsequent frames can run without that wait. A Blender frame taking more than
25 ms can therefore trigger this fallback during ordinary play. Reducing busy
waiting and avoiding unnecessary Minecraft frames may reduce contention, but
that is a code-based hypothesis until tested with viewport FPS, Minecraft FPS,
and input latency recorded separately.

Any upload change needs pixel comparisons covering premultiplied alpha, image
orientation, resize, repeated frames, and framebuffer state restoration. Actual
viewport draw intervals, rather than submission-only GPU timings or Minecraft's
hidden FPS counter, remain the performance metric for the playable result.

## Reconnect and upload update, 0.1.0.3

Measured on the same PC on 2026-10-10, comparing main `876c9d1` with this update.
Both runs use the original 740-object Dust II scene, 445 colliders, 2548 cached
terrain sections, solid shading without cavity, a 2098 × 1314 viewport, and
position `(0, 201.8333, 33.5853)`, yaw 180°, pitch 10°. Sky/weather is enabled.
Each stationary phase lasts 16–20 seconds after a 75-second initial warmup.
These are local samples on a shared desktop, not a controlled hardware benchmark.

| Configuration | Before | After |
|---|---:|---:|
| Terrain enabled, 1080p HUD | 24.8 FPS | 36.3 FPS |
| Terrain enabled, 720p HUD | 31.2 FPS | 41.0 FPS |
| Terrain disabled, 720p HUD | 36.7 FPS | 48.0 FPS |
| 1080p HUD upload callback | 11.7 ms | 1.9 ms |
| 720p HUD upload callback | 5.0 ms | 0.9 ms |
| Minecraft render loop, terrain enabled / 720p | 82.3 FPS | 41.0 FPS |

The lower Minecraft render-loop rate is intentional: it now follows Blender's
presentation cadence instead of producing unused frames and busy-waiting. There
is no fixed 30 FPS cap removed by this change. The new byte upload retains exact
RGBA pixels, reuses its target texture, skips identical images, and falls back
to the previous float path if the GPU backend rejects the byte path. Camera RNA
fields are only rewritten when changed; the sidebar refreshes separately from
the game viewport. The terrain-disabled after-run still renders the Minecraft
sky, unlike the old implementation which hid sky together with terrain.

**Streaming limitation:** after turning terrain back on, a 16-second walking
sample while the new snapshot was still loading measured **22.4 FPS**, with
about **14.6 ms** in mesh uploads and **67.7 ms** p95 frame intervals. This is not
a steady walking benchmark. Large cell rebuilds can still exceed the nominal
upload budget; stable 60 FPS across scene sizes and chunk streaming is not yet
achieved. Do not present the stationary results as a guarantee during play.

Validation covers 39 Python tests, 31 Java tests, actual Blender file reloads
and failed-cleanup recovery, exact GPU pixels (including clipping, flip, resize,
repeat frames and fallback), independent sky visibility, and an actual Minecraft
process surviving rapid host replacement, a 1.2-second disconnect, HUD resize,
two seconds of render-ring back pressure, and a hidden→visible world transition.
The latter requires a fresh atlas, section geometry and all five environment
textures after CLEAR, verifies the SDL window stays hidden, and saves/exits
Minecraft normally. See `scripts/verify_host_lifecycle.py`,
`scripts/verify_render_updates.py`, and `scripts/verify_reconnect.py`.
Local timing/capture evidence is in `artifacts/reconnect-performance/`; reconnect
evidence is in `artifacts/host-reconnect/`. These are excluded from release ZIPs.
