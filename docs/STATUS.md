# Implementation and verification ledger

## Objective

Build and publish a public GitHub project in this directory that lets the user
play Minecraft in Blender using SkyCraft. Blender must be the actual host. Aim
for the complete Minecraft experience; do not declare completion after a mock,
a streamed full-screen Minecraft image, or a limited block placement demo.

## Architecture

- Blender window and modal operator receive all keyboard, pointer, text and UI input.
- Blender renders SkyCraft section geometry, animated entity batches and textures
  in its own viewport. Native Blender scene geometry participates in depth testing.
- Minecraft provides gameplay/simulation, emits render protocol messages and the
  transparent hand/HUD/screen overlay. It remains a separate hidden process.
- Host scene collision, actors, water, damage and interactions travel back to MC.
- Save/load, death/respawn, survival/creative, inventory/crafting, block entities,
  redstone, fluids, mobs, combat, dimensions and multiplayer need real verification.

## Stage 1 — playable host, 2026-10-09

Implemented:

- SkyCraft v11 named shared-memory ownership, bounded rings, seqlock snapshots,
  atomic overlay triple buffering, MC/Blender coordinate conversion.
- Native section, entity, avatar, dropped-item, projectile and crack meshes;
  animated textures; transparent materials and target outline.
- Blender camera and F5 modes; modal keyboard, mouse, wheel and text forwarding;
  focus-loss release and Shift+Esc escape from capture.
- Static Blender triangle collision for players; box voxel occupancy for
  mobs/fluids; manual collision refresh after scene edits.
- Scene playground and normal vanilla survival mode, with separate local saves.
- Vanilla spawn, dimension transitions, pause, water-flow and sneak-edge behavior
  preserved in normal mode. Scene-mode host-specific rules stay separate.
- Transparent HUD/hand/screens, title/loading menus, environment diagnostics and
  graceful Minecraft shutdown input.
- Automatic internet sharing and Discord presence disabled for this host.

## Verification

Environment: Windows x64, Blender 5.0.1, Minecraft Java 26.3, JDK 25,
NVIDIA OpenGL. Tests use isolated development saves under `minecraft/run/`.

| Evidence | Result |
| --- | --- |
| Python wire protocol, startup handshake, buffer ownership/backpressure, geometry tests | 12 passed |
| Fabric bridge build and inherited Java collision tests | Successful; 21 tests |
| Native Blender floor walking | Player moved 1.72 blocks without falling through the floor |
| Place/break block on Blender ground | Real section updates and visible edits, both passed |
| Inventory through shared-memory input | Open/close passed |
| Actual Blender modal E key | Opened vanilla InventoryScreen |
| Actual Blender modal F5 key | Cycled camera modes 1 → 2 → 0 |
| Actual Blender modal Esc key | PauseScreen; gameTime stopped while paused |
| Actual Blender modal Shift+Esc | Released capture without errors |
| Overworld → Nether → End → Overworld | Each replaced geometry and retained correct destination |
| Native scene coexistence | Blender floor/pillars/stairs, MC wall/chest/cow and HUD visually inspected |
| Save and shutdown | Server logged saving players and all three dimensions before clean exit |
| Death and respawn through Blender Tab/Enter | DeathScreen at health 0, natural surface spawn at health 20 |
| Restart Blender while MC keeps running | Position stayed exactly `(-29.5,90,-6.5)`; geometry resent without errors |

Live tests: `scripts/verify_runtime.py` and `scripts/verify_survival.py`.
The restart regression is `scripts/verify_reconnect.py` (normal mode).
Machine-generated local records: `artifacts/runtime-tests.json` and
`artifacts/survival-tests.json`. Only selected screenshots are committed.
Dimension tests use normal commands, not portal traversal. Block placement tests
check mesh changes and visible behavior, not every block type. Protocol tests
exercise real Windows shared memory under separate test mapping names.

A restart regression initially exposed an unintended teleport to the default
Blender origin. The fix publishes state before heartbeat and reserves sequence
zero for adopting a vanilla player's position; the live restart regression passed.

## Remaining work

- Crafting, containers, furnaces, redstone, fluids, combat, portals,
  enchantment and other vanilla systems need broader end-to-end gameplay tests.
- Sky, weather, fog, night lighting, some special entity effects and sound routing
  need host-specific presentation. Audio currently comes from Minecraft.
- Section culling/eviction, performance and long-session memory require work.
- Generic meshes need volumetric collision for mobs/fluids; dynamic Blender
  objects, Blender actor damage, destruction, host water and light integration
  are incomplete. Light/solid/dug protocol messages are currently retained only.
- No mesh baking to editable Blender objects or offline Blender render support.
- Developer launcher only: authenticated production launch, multiplayer validation,
  distributable add-on/runtime packaging and install/update UX are unfinished.
- Texture-pack/mod compatibility and non-Windows platforms are unverified.

Do not mark the overall objective complete after this stage.
