# MCInBlender

Play Minecraft **inside Blender**, using a Blender host for the SkyCraft protocol.
Blender owns the window, camera, input, scene rendering and host geometry. A hidden
Minecraft Java process supplies Minecraft's simulation, inventories, crafting,
entities and UI. Minecraft meshes are drawn inside Blender's 3D viewport, alongside
the user's scene. This is not a Minecraft host displaying Blender screenshots.

**Status: active development; not yet a complete playable release.**

Windows x64, Blender 5.0+, Minecraft Java 26.3, JDK 25. Minecraft requires a
separately owned copy. No Minecraft binaries, assets, account data or saves are
included in this repository.

The `minecraft/` module is derived from [chasmlol/SkyCraft](https://github.com/chasmlol/SkyCraft),
pinned at `bfcaf178524b92c2cdeb88e4ce0f13ef9ded6f32` (protocol 11).
See `THIRD-PARTY-NOTICES.md` and `licenses/SkyCraft-MIT.txt`.

## Development

The Blender add-on lives in `blender_minecraft/`. Local runtime installations,
test saves, downloaded assets and diagnostic captures are ignored by Git.
The implementation and verification ledger is in `docs/STATUS.md`.

