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

## Evidence so far

- Empty project directory inspected; GitHub CLI authenticated as CS-LX.
- SkyCraft source pinned; protocol 11 sends native meshes and textures.
- Blender 5.0.1 found at E:/Games/Steam/steamapps/common/Blender/blender.exe.
- Minecraft launcher runtime includes a JDK 25 at its local epsilon runtime.
- No gameplay or rendering verified yet.

## Next

Implement and test the shared-memory transport, viewport renderer and input host;
build the SkyCraft-derived client; perform actual Blender + Minecraft integration
tests and fix observed failures. Track unsupported features explicitly.
