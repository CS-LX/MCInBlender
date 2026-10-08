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

Coordinates are meters/blocks: Minecraft `(x,y,z)` maps to Blender `(x,-z,y)`.
Triangles retain their winding because this is a rotation, not a reflection.
Section vertices are local to their 16-block origin; scene vertices are world
coordinates; avatar vertices are relative to the player.

The Minecraft overlay uses three exclusive slots. The Blender reader exchanges
its previously owned slot with the atomic middle slot before reading. Never read
the writer's back buffer directly or replace the exchange with a plain store.

## Optional Blender extensions

These are emitted/accepted only with `-Dmciblender.host=true`, so the original
SkyCraft Skyrim host is unaffected. Existing v11 record layouts are unchanged.

| Direction | Record | Payload |
| --- | --- | --- |
| MC → Blender render ring | 12 | UTF-8 JSON, schema 1: dimension, vanilla mode, screen name, pause/time/weather, health/food/XP, held item, game mode |
| Blender → MC input ring | 9 | No payload; release input and request normal Minecraft shutdown, which saves the integrated world |

The development diagnostics inbox `.local/control/` accepts specific JSON actions
only. It is not a general Python executor. `blender_event` uses Blender's own
event simulation and requires launching Blender with `--enable-event-simulate`.
Use `scripts/control.py` to enqueue diagnostic actions; normal users play through
the add-on's modal operator.
