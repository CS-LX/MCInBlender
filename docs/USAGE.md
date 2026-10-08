# 使用 MCInBlender

Blender 是窗口、输入、摄像机和场景渲染的宿主。Minecraft 在后台负责原版模拟、
存档和 UI；游戏地形以 GPU 几何绘制在 Blender 视图中，模型继续是原生 Blender 对象。

## 操作

| 操作 | 输入 |
| --- | --- |
| 进入游戏控制 | Minecraft 侧栏 → Capture Input / Play |
| 移动、跳跃 | WASD、空格 |
| 视角、挖掘、放置/使用 | 鼠标、左键、右键 |
| 背包、快捷栏 | E、数字键/滚轮 |
| 切换游戏视角 | F5 |
| Minecraft 菜单 | Esc |
| 返回 Blender 编辑 | Shift+Esc |

Shift+Esc 后可以继续使用 Blender 的建模、材质、修改器和自由视图。
游戏可能继续模拟；需要暂停时先打开 Minecraft 的 Esc 菜单。

## 四种视角

- **First Person**：第一人称。
- **Third Person — Behind**：身后跟随。
- **Third Person — Front**：面向玩家。
- **Blender View**：保留 Blender 的自由视图。释放输入后调整视角，重新 Capture Input 后从固定视角控制玩家。

## 把 Blender 模型放入游戏

在当前场景添加/导入网格即可。开启 **Live Blender collision** 后，变换和求值后的修改器
网格自动参与碰撞，最多每秒更新四次。可暂时关闭它，再手动 **Update Blender Collision**。

坐标换算：Minecraft `(x,y,z)` 对应 Blender `(x,-z,y)`，一个 Blender 单位对应一格。
例如 Minecraft `(10,100,20)` 的位置在 Blender 是 `(10,-20,100)`。
正常生存世界的海拔可能较高，模型放在 Blender 原点时不一定出现在玩家附近。
开发存档允许在侧栏发送 `tp @s 10 100 20` 等普通 Minecraft 命令。

模型材质和修改器会保留。玩家使用三角形碰撞；生物/流体使用 1/8 方块体积近似。
封闭网格适合实体碰撞，开放网格形成薄壳。给装饰模型设置自定义属性
`mc_collision = false` 可以关闭其游戏碰撞。`mc_collider = "BOX"` 使用较快的包围盒碰撞。

不需要也不会把 Minecraft 方块变成可编辑的 Blender 网格。
大型高面数模型、快速动画和移动平台仍有性能/物理限制。

**Create Blender Playground** 会创建新的 Blender 场景并保留原场景。
它只创建原生模型示例，不会修改 Minecraft 启动器所选的世界模式。
发布整合包默认是正常生存世界。

## 显示与灯光

- **Show live Minecraft world** 控制 Minecraft 几何可见性。
- **Minecraft sky, lighting and weather** 控制游戏天空、雾、昼夜和降水。
- **Light Blender models from Minecraft** 使用材质预览和临时灯光，让原生模型受到游戏昼夜和附近发光方块照射。

临时灯光会在停止宿主、禁用或保存 `.blend` 时清理。原有灯光/材质不会被替换。
目前 Minecraft 方块对原生对象的阴影遮挡、原生对象的 Minecraft 雾效和屋顶挡雨尚不完整。

## 保存与退出

- `.blend` 保存模型、材质和场景；Minecraft 实例的 `saves/` 保存游戏世界和背包。
- **Save & Quit Minecraft** 正常保存游戏并退出后台进程，保留 Blender 窗口。
- 正常关闭 Blender 后，连接过的 Minecraft 也会保存退出。
- **Stop Host** 停止桥接。重新启动宿主后可重连仍在运行的游戏；若已退出则从启动器再启动。

发布包没有包含开发测试存档，也不会自动操作你其他 Minecraft 实例的存档。
