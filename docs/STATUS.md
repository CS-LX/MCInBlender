# Implementation and verification ledger

## Objective

Build and publish a public GitHub project in this directory that lets the user
play Minecraft in Blender using SkyCraft. Blender must be the actual host. Aim
for the complete Minecraft experience; do not declare completion after a mock,
a streamed full-screen Minecraft image, or a limited block placement demo.

User clarification: preserve both applications' capabilities, with Blender models
entering the Minecraft gameplay scene. Editing Minecraft blocks as Blender meshes
is explicitly not required. Provide first person, third person and Blender views.

## Architecture

- Blender window and modal operator receive all keyboard, pointer, text and UI input.
- Blender renders SkyCraft section geometry, animated entity batches and textures
  in its own viewport. Native Blender scene geometry participates in depth testing.
- Minecraft provides gameplay/simulation, emits render protocol messages and the
  transparent hand/HUD/screen overlay. It remains a separate hidden process.
- Host scene collision travels back to MC; actor, host-water and damage integration
  remain incomplete as tracked below.
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

## Stage 2 — Blender models and gameplay coexist

- Release input to restore Blender orbit/pan/zoom, overlays and modeling tools.
  Returning to play preserves the editor view for the next editing session.
- View selector: first person, behind-player third person, front-facing third
  person and Blender camera. In Blender camera mode the player remains controllable
  from a fixed viewport angle.
- Evaluated model geometry and modifiers update game collision automatically,
  throttled to four updates/second. Updates replace regions without clearing the
  entire collision world, so unchanged ground remains available.
- Generic closed mesh volume and open mesh shells feed 1/8-block occupancy to
  mobs and fluids. Player contact still uses exact triangles. Large/complex
  meshes and continuously moving platforms need further optimization/physics work.
- `--blend` loads the user's existing scene, keeping its native Blender data.
  Game saves and `.blend` scene saves remain separate.
- Read-only inventory, container-slot and targeted-block state aids diagnostics.
  Real gameplay still uses ordinary keyboard/mouse handling.

Real session checks (all passed):

| Check | Evidence |
| --- | --- |
| 2x2 crafting | One log → four planks → one crafting table, using real slot clicks |
| Place and use crafted workbench | Placed table, opened 3x3 grid, crafted four sticks |
| Chest | Deposited five apples, closed/reopened, withdrew the same five |
| Furnace | Inserted raw iron and coal, waited for smelting, collected iron ingot |
| Redstone | Mouse-clicked lever, server verified lamp off → on → off |
| Water | Used bucket; server verified source and adjacent flow, mesh updates observed |
| Live Blender model creation/movement | Player stood at model top y=102; moving model let player fall to MC floor y=100 |
| Evaluated modifier collision | Player stood on a beveled Blender mesh using its evaluated triangles |
| Generic model volume | Live cow settled at y=102.125 on a model with top y=102 (subvoxel shell tolerance) |
| Four view choices | Actual MC modes 1/2/0; player moved 3.79 blocks while Blender camera stayed fixed |
| Scene persistence | Saved/reopened native `.blend`, reconnected game and retained Blender view |

Test drivers: `scripts/verify_gameplay.py` and `scripts/verify_fusion_in_blender.py`.
Local results: `artifacts/gameplay-tests.json`, `artifacts/fusion/tests.json`.
The fusion tests save an ordinary Blender model scene in `artifacts/fusion/`.
They do not bake or edit Minecraft geometry.

## Remaining work

- Combat, physical portal traversal, enchantment and more vanilla systems need
  end-to-end tests; tested systems still need broader item/recipe/block coverage.
- Sky, weather, fog, night lighting, some special entity effects and sound routing
  need host-specific presentation. Audio currently comes from Minecraft.
- Section culling/eviction, performance and long-session memory require work.
- Fast animated Blender objects, riding moving platforms, Blender actor damage,
  destruction, host water and light integration are incomplete.
  Light/solid/dug protocol messages are currently retained only.
- Developer launcher only: authenticated production launch, multiplayer validation,
  distributable add-on/runtime packaging and install/update UX are unfinished.
- Texture-pack/mod compatibility and non-Windows platforms are unverified.

Do not mark the overall objective complete after this stage.
