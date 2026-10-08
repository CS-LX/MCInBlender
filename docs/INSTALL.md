# 安装 MCInBlender（无需编译）

## 要求

- Windows 10/11 **x64**；当前不支持 ARM64、Linux 或 macOS。
- Blender **5.0+**，已在 Steam 版 **5.0.1** 上验证。Steam 与官网版本安装方法相同。
- 自己拥有的 Minecraft Java 版账号，以及 Prism Launcher、HMCL 或其他支持 Fabric 的启动器。
- Minecraft **26.3**、Fabric Loader **0.19.5**、Java **25**。整合包锁定游戏和 Loader 版本；Java 由启动器管理。
- 首次导入需要联网下载游戏和 Fabric；发布包不包含 Minecraft 本体、素材、Java、账户或存档。

普通用户**不需要 Git、Python、JDK、Gradle、GCC 或 Visual Studio**。

## 1. 下载发布包

打开 [GitHub Releases](https://github.com/CS-LX/MCInBlender/releases)。优先选择没有
`Pre-release` 标记的正式版，下载 `MCInBlender-release-vX.X.X.X-windows-x64-bundle.zip`。
CI 预览包文件名包含 `-ci-`、四段版本号和短提交号，不会与正式版混淆。

解压 bundle，里面包含：

| 文件 | 用途 |
| --- | --- |
| `*-addon.zip` | 直接安装到 Blender；已包含 Windows DLL 和同版 Minecraft 整合包 |
| `*-minecraft.mrpack` | 导入 Minecraft 启动器；已包含编译好的桥接模组及 Fabric API |
| `mods/*.jar` | 不支持 MRPACK 的启动器手动安装时使用 |
| `build-info.json` | 版本、渠道、完整提交 SHA、游戏依赖及协议版本 |
| `INSTALL.md` / `USAGE.md` | 本说明和使用说明 |

也可以只下载独立 `-addon.zip` 和 `.mrpack`。不要把整个 bundle ZIP 当作 Blender 插件安装。
Release 附带 `SHA256SUMS.txt`；用 PowerShell `Get-FileHash 文件名 -Algorithm SHA256` 可核对下载。

## 2. 安装 Blender 插件

1. 打开 Steam 安装的 Blender。
2. **Edit → Preferences → Add-ons**，右上角菜单选择 **Install from Disk**。
3. 选择 `*-addon.zip`，保留 ZIP，不要先解压。
4. 启用 **Minecraft in Blender**。如未开启自动保存偏好，点击 **Save Preferences**。
5. 回到 3D 视图，按 **N** 展开右侧栏，找到 **Minecraft**。

这是兼容 Blender 5 的传统 Add-on ZIP，可通过 Install from Disk 安装。
不需要修改 Steam 游戏目录。[Blender 官方安装说明](https://docs.blender.org/manual/en/5.0/editors/preferences/addons.html)

## 3. 安装 Minecraft 实例

### Prism / HMCL：导入 MRPACK

1. 在启动器中选择导入本地整合包，选择 `*-minecraft.mrpack`。
2. 建议实例名称使用 **MCInBlender**；登录你自己的 Minecraft 账号。
3. 允许启动器下载 Minecraft 26.3 和 Fabric Loader 0.19.5。
4. 选择 Java 25；Prism 可在 Java 设置中启用自动选择/下载 Java。建议分配 4 GB 内存。

不要导入自己的主力存档作为第一次尝试。此实例会创建独立的 `MCInBlender Survival`
存档，模型仍保存在你自己的 `.blend` 文件中。

[Prism 导入实例](https://prismlauncher.org/wiki/getting-started/create-instance/) ·
[Prism Java 设置](https://prismlauncher.org/wiki/help-pages/java-settings/)

### PCL / 不支持 MRPACK 的启动器

创建独立 **Minecraft 26.3 + Fabric Loader 0.19.5** 实例，选择 Java 25。
将 bundle 中 `mods/` 的两个 JAR 放入该实例实际使用的 `mods/` 目录。
桥接模组默认使用 Blender 宿主和正常生存世界，**无需额外 JVM 参数**。
不要同时装入原始 SkyCraft 模组：二者使用同一模组 ID。

## 4. 开始玩

1. 打开 Blender 场景；没有模型也可以先用空场景。
2. 在 Minecraft 侧栏点击 **Start Blender Host**。
3. 在启动器中启动刚导入的 MCInBlender 实例。
4. Minecraft 连接后会隐藏自己的窗口，自动打开独立存档；Blender 显示地形及 HUD。
5. Blender 侧栏显示 **Connected** 后，点击 **Capture Input / Play**。

如果先启动了 Minecraft，也可以再启动 Blender Host；连接前 Minecraft 窗口会保持可见。
第一次生成世界可能需要等待。只有一套 Blender 宿主和 Minecraft 桥接实例能同时运行。

可选：在 Blender 的插件偏好里设置 **Prism Launcher** 的 EXE 路径和 **Prism instance ID**，
以后启动宿主后可以点击 **Launch Minecraft (Prism)**。实例 ID 是实例文件夹名，未必等于显示名。
HMCL/PCL 直接从自己的启动器启动即可。插件不读取账户令牌或接管登录。

## 更新、卸载与存档

- 更新前点击 **Save & Quit Minecraft**，正常保存 `.blend` 并关闭 Blender。
- 将新版 `-addon.zip` 安装到 Blender；Minecraft 实例内只保留同版桥接 JAR 和匹配的 Fabric API。
  也可重新导入新版 MRPACK 到新实例，再通过启动器复制自己的存档。
- 更新插件不会删除游戏存档。游戏存档属于启动器实例的 `saves/`，模型属于 `.blend`；两者都应备份。
- 卸载：在 Blender 偏好中禁用/移除插件；从启动器删除相应实例或两个模组。不会自动删除模型文件。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| Waiting for Minecraft | 确认启动的是导入的 Fabric 实例，游戏版本为 26.3，模组目录有两个 JAR |
| 缺少 Java / 版本不对 | 在启动器中选 Java 25，不需要 JDK 或编译工具 |
| 载入 DLL 失败 | 下载 Windows x64 包，确认系统/Blender 为 x64；重新解压安装，检查下载校验值 |
| 没有 Minecraft 侧栏 | 启用插件，并在 3D Viewport 中按 N；节点/文本编辑器没有该面板 |
| 鼠标不能编辑 Blender | 按 Shift+Esc 释放游戏输入，再编辑模型 |
| 黑屏或桥接报错 | 插件偏好 → Open MCInBlender Logs / Data；同时查看启动器实例的 logs/latest.log |
| 多实例冲突 | 关闭另一套宿主或游戏；不要重复点击启动多个游戏实例 |

插件日志在 Blender 用户配置目录的 `mciblender/logs/host-status.json`，通常为
`%APPDATA%/Blender Foundation/Blender/5.0/config/mciblender/`。不会写入 Steam 安装目录。
正式安装默认关闭开发测试输入文件队列。

当前支持和已知限制见 [STATUS.md](STATUS.md)。正式版表示固定版本、经过安装和运行检查的发布包；
不代表所有第三方模组、显卡或 Blender 后续版本均已验证。
