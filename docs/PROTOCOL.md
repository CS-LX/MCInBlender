# Blender host protocol

The host implements SkyCraft protocol 11 at pinned upstream commit
`bfcaf178524b92c2cdeb88e4ce0f13ef9ded6f32`. The original wire declaration is
in `protocol/skycraft_protocol.h`; Python offsets are in `blender_minecraft/protocol.py`.

The default Windows mapping is `Local\MCInBlender_SkyCraft_v11`. A separate named
mutex prevents two Blender hosts from initializing the same mapping. The host owns
the mapping and heartbeat, input/collision producers and render/event consumers.
The small `native/atomic.c` helper provides real Windows interlocked operations;
build it with `python scripts/build_native.py`.

The host publishes its initial state before its first heartbeat. In normal mode,
teleport sequence zero adopts the existing Minecraft player position; explicit
host teleports use a positive sequence. Reconnecting or restarting the host must
never move a survival player to a default Blender origin.
Resetting the host clears the Minecraft PID acknowledgement in the header.
Once initialized state and a live heartbeat are present, Minecraft acknowledges
its PID again and advances the connection generation. This also forces a complete
atlas/geometry/environment resend for Stop/Start within the same Blender process.

Coordinates are meters/blocks: Minecraft `(x,y,z)` maps to Blender `(x,-z,y)`.
Triangles retain their winding because this is a rotation, not a reflection.
Section vertices are local to their 16-block origin; scene vertices are world
coordinates; avatar vertices are relative to the player.

The Minecraft overlay uses three exclusive slots. The Blender reader exchanges
its previously owned slot with the atomic middle slot before reading. Never read
the writer's back buffer directly or replace the exchange with a plain store.
While editing without a visible overlay, the host still consumes the newest
shared frame but defers its GPU upload until the overlay is visible again.

For Blender hosts, unloaded client sections are evicted using existing zero-count
section/light/solid/dug messages. Full-ring sends retry before forgetting a key.
Revisiting a chunk generates fresh meshes through Minecraft's normal load updates.

Render kind 8 is also consumed by optional native Blender lighting. The payload
starts with `int32 sectionX, sectionY, sectionZ, uint32 count`, followed by `count`
eight-byte emitters: local `uint8 x,y,z,emission` and packed `uint32 color`.
Coordinates and emission are 0–15. The low three color bytes are RGB; the top
byte contains light-kind/hazard metadata. These colors are SkyCraft's visual
approximation, not vanilla colored light. A zero count removes the section's
emitters. Selection is bounded by native model bounds, influence radius and a
user-adjustable light cap. Native Blender point/sun lights use this data and the
actual lightmap/celestial state; no native mesh or material conversion is needed.

## Optional Blender extensions

These are emitted/accepted only with `-Dmciblender.host=true`, so the original
SkyCraft Skyrim host is unaffected. Existing v11 record layouts are unchanged.

| Direction | Record | Payload |
| --- | --- | --- |
| MC → Blender render ring | 12 | UTF-8 JSON, schema 1: dimension, vanilla mode, screen name, pause/time/weather, health/food/XP, held item, game mode, inventory counts, carried stack, container slots and GUI origin, targeted block |
| MC → Blender render ring | 13 | 1,024 bytes: vanilla's current 16×16 RGBA8 lightmap, x=block light and y=sky light |
| MC → Blender render ring | 14 | Four little-endian uint32 values: texture id, width, height, reserved zero; then RGBA8 pixels. Separate environment texture namespace: sun=0, moon=1, rain=2, snow=3, End sky=4 |
| Blender → MC input ring | 9 | No payload; release input and request normal Minecraft shutdown, which saves the integrated world |

Record 12's optional `atmosphere` object includes Minecraft's skybox type, sky/fog
colors, celestial angles, star/rain intensity, face shading, spherical and
horizontal fog ranges, and rain/snow columns. These are gameplay-camera values;
precipitation columns retain Minecraft's terrain/biome clipping around the player.
The host projects them using the actual Blender view. Lightmap readback is
asynchronous and generation-checked. Environment PNGs come from the installed
game/resource pack at runtime; none are stored in this repository.

The development diagnostics inbox `.local/control/` accepts specific JSON actions
only. It is not a general Python executor. `blender_event` uses Blender's own
event simulation and requires launching Blender with `--enable-event-simulate`.
Use `scripts/control.py` to enqueue diagnostic actions; normal users play through
the add-on's modal operator.
