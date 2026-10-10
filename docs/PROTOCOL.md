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

The reserved header fields at `0x20` and `0x28` contain a 64-bit host generation
nonce and its Minecraft acknowledgement. A fresh Host publishes a new nonzero
nonce; state and heartbeat stay offline until initialization is complete. The
client acknowledges the nonce before becoming active, resets per-session caches
even if the Blender PID is unchanged, and rejects stale ring/overlay commits.
Zero denotes a legacy v11 peer or an offline host. A successful Minecraft mapping
handle stays open for the process lifetime so a stopped/restarted Blender Host
reattaches to the same named Windows mapping.

A render snapshot commits CLEAR before ATLAS and retries either rejected stage.
Meshes wait until the atlas is accepted; an accepted CLEAR is never repeated by
an atlas retry. Sky textures have independent retry state. Blender producers do
not block for a full render ring; retained world records retry on later frames.

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

Additional read-only record 12 fields support gameplay verification:

- `targetEntity`: numeric runtime id, UUID and registry type; living targets also
  include health and maximum health. Absent when the crosshair targets no entity.
- `heldStack`: item, count, enchanted flag and durability damage. The same
  stack fields accompany container/carried stacks. `enchanted` reports
  `ItemStack.isEnchanted()`; it is not an exported enchantment list.
- `feetBlock`: the block state at the player's feet, including portal axis.
- `enchantmentOffers`: menu indices, required levels, numeric registry clue ids
  and clue levels while an enchantment menu is open. These are session data,
  not a stable cross-version enchantment registry.

These fields observe ordinary Minecraft state; they do not perform attacks,
enchant items or change dimensions. The integration driver uses Blender input
for those actions and server command responses to verify the result.

The development diagnostics inbox `.local/control/` accepts specific JSON actions
only. It is not a general Python executor. `blender_event` uses Blender's own
event simulation and requires launching Blender with `--enable-event-simulate`.
Use `scripts/control.py` to enqueue diagnostic actions; normal users play through
the add-on's modal operator.
Producers publish complete files using a temporary file and atomic rename. The
consumer processes sorted JSON names and waits on transient Windows sharing
violations to preserve input order. It renames an action to `.claimed` before
dispatch and later removes that file. Failed cleanup never replays an action;
after a crash, claimed actions are discarded because their outcome is unknown.
This diagnostic queue provides at-most-once dispatch, not crash-safe delivery.
