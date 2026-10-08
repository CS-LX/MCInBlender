# MCInBlender

Play Minecraft **inside Blender**, using a Blender host for the SkyCraft protocol.
Blender owns the window, camera, input, scene rendering and host geometry. A hidden
Minecraft Java process supplies Minecraft's simulation, inventories, crafting,
entities and UI. Minecraft meshes are drawn inside Blender's 3D viewport, alongside
the user's scene. This is not a Minecraft host displaying Blender screenshots.

**Status: playable developer prototype.** Native Blender ground collision,
Minecraft block interaction, inventories, survival terrain, three camera modes,
pause and dimension transitions have been tested in a real Blender + Minecraft
session. See [verified features and gaps](docs/STATUS.md).

![Minecraft geometry, mobs and HUD inside a native Blender scene](docs/images/blender-native-world.png)

Windows x64, Blender 5.0+, Minecraft Java 26.3, JDK 25. Minecraft requires a
separately owned copy. No Minecraft binaries, assets, account data or saves are
included in this repository.

The `minecraft/` module is derived from [chasmlol/SkyCraft](https://github.com/chasmlol/SkyCraft),
pinned at `bfcaf178524b92c2cdeb88e4ce0f13ef9ded6f32` (protocol 11).
See `THIRD-PARTY-NOTICES.md` and `licenses/SkyCraft-MIT.txt`.

## 在 Blender 里启动

目前支持 Windows x64、Blender 5.0+、JDK 25，以及 Python 3.10+。
首次构建还需要 GCC 或 Visual Studio 的 C++ Build Tools，用于编译共享内存原子操作的小型 DLL。
Minecraft/Fabric 开发依赖由 Gradle 下载，首次启动需要等待。

1. 克隆仓库，进入目录。
2. 如果无法自动找到 Blender 或 JDK，把 `config.example.json` 复制到
   `.local/config.json`，修改为实际安装路径。也支持 `PATH` 中的 Blender 和 `JAVA_HOME`。
3. 执行以下命令之一：

```powershell
# 在原生 Blender 地面、桥梁、台阶上玩 Minecraft
python scripts/launch.py --world scene

# 在 Blender 中玩正常生成的 Minecraft 生存世界
python scripts/launch.py --world normal
```

启动后在 3D 视图右侧边栏选择 **Minecraft → Capture Input / Play**。
WASD 移动，鼠标看向/挖掘/放置，空格跳跃，E 背包，数字键和滚轮选择快捷栏，
F5 切换视角，Esc 打开游戏菜单。**Shift+Esc 释放输入回到 Blender**。
菜单内的鼠标和文本输入同样由 Blender 转发。

`scene` 模式创建一个新的 Blender 场景，不覆盖现有场景；玩家碰撞使用 Blender
求值后的网格三角形。带 `mc_collider="BOX"` 的对象还提供生物与流体所需的体素碰撞。
编辑场景后点击 **Update Blender Collision** 更新。普通 Minecraft 方块由 Minecraft
管理，渲染到 Blender 视图的深度缓冲中。

`normal` 模式使用原版地形、自然出生位置、生存规则与维度。两个模式使用独立存档，
都保存在被 Git 忽略的 `minecraft/run/saves/` 下。初始开发存档允许命令，便于测试。
原版 Esc 菜单可保存并退出到标题画面。

当前启动器使用 Fabric 的 `runClient` 开发实例。它不读取个人启动器的账户或存档，
也不是已完成的正版启动器/多人联机发行包。正式认证启动、安装包和更多玩法验证仍在进行。

![Vanilla survival inventory in Blender](docs/images/survival-inventory.png)

## Architecture

| Component | Responsibility |
| --- | --- |
| Blender add-on | Window, modal input, camera, GPU geometry and texture rendering, native scene collision |
| SkyCraft-derived Fabric bridge | Vanilla gameplay, saves, mobs, block states, animation meshes, transparent hand/HUD/UI |
| Windows shared memory | SkyCraft v11 rings, seqlocks and atomic triple buffering |

Minecraft world geometry is rendered by Blender; only hand/HUD/menu pixels are
composited as a transparent overlay. Minecraft's simulation runs in a hidden Java
process. The current viewport meshes are GPU batches, not editable Blender objects
and not yet available to offline Cycles renders.

## Development and verification

```powershell
python scripts/launch.py --only build
python -m pip install numpy
python -m unittest discover -s tests -v

# Real gameplay test in a running scene-mode developer session
python scripts/verify_runtime.py

# Real Blender modal-input and dimension tests in a normal-mode session
python scripts/launch.py --world normal --test-input
python scripts/verify_survival.py
```

Run one developer session at a time. The live tests change the isolated development
world. Python tests require NumPy; Blender already supplies it for the add-on.
Gradle compilation/test output is in `logs/build.log`; game output is in
`logs/minecraft-build.log`. Blender status and errors are in `logs/host-status.json`.
Live test JSON and screenshots go into ignored `artifacts/`.

The Blender add-on lives in `blender_minecraft/`. Local runtime installations,
test saves, downloaded assets and diagnostic captures are ignored by Git.
See [protocol notes](docs/PROTOCOL.md) and the [implementation ledger](docs/STATUS.md).

