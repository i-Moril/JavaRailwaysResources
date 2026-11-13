# JavaRailways Resources

独立保存 JavaRailways 客户端资源包源码、生成工具和分发包。所有资源包均支持 Minecraft Java Edition 1.21.11（资源格式 75.0）；具体支持范围以各包 `pack.mcmeta` 为准。服务器模型配置和示例不属于本仓库。

- `s100-and-rail/`：S100 资源包源码，当前同时包含轨道模型资源；`distributions/` 保存基础包、control、透明度和 S100 显示覆盖包。`build_s100_transparency_pack.py` 生成 control 和透明度两个版本。
- `rail/`：独立轨道客户端资源源码、分发包及含服务器轨道配置的完整交付 ZIP。
- `signals/jr-four-light/`：四灯客户端资源源码和分发包，支持 1.21.11–26.1.2。
- `signals/route-indicator/`：进路表示器客户端资源源码、资源包 ZIP 和含服务器模型的完整交付 ZIP。
- `editor-markers/`：编辑器标记资源源码、纹理生成工具和分发 ZIP。

`distributions/` 中的客户端资源从当前源码生成，完整交付 ZIP 内的资源包副本也会同步。已有分发文件名保持不变；名称带 `26.1.2` 的编辑器标记和四灯 ZIP 同样支持 1.21.11。服务器配置在重建时保持原内容。

## 生成

运行 `python3 build_packs.py` 重建全部资源包和交付 ZIP 内的副本。

服务器统一下发包为 `distributions/javarailways.zip`，合并 S100 透明度包（已含轨道、显示字体）、四灯、进路表示器和编辑器标记。保留 S100 的版本元数据及 overlay；其他包只加入资源文件，不覆盖根 `pack.mcmeta`。同路径存在不同内容时构建失败，避免静默丢失资源。

测试服 RoseResourcepack 只配置 `joinPacks: [main]`，将这个合包作为 `main` 下发，下载地址为 `http://mc.art1st.work:29090/main.zip`。已核实 RoseResourcepack 3.5.0 的多包分支连续调用 `Player.setResourcePack`；当前 Folia 的实现会在每次调用时移除之前的服务器包，因此不能把四个独立包直接列入 `joinPacks`。统一下发修复不改变车包的 `item-model` 约定。

运行 `node editor-markers/generate-texture.mjs` 重新生成标记纹理；运行 `python3 editor-markers/build_pack.py` 将可复现的编辑器资源包写入 `editor-markers/distributions/`。
运行 `python3 s100-and-rail/build_s100_transparency_pack.py --help` 查看 S100 资源包构建参数；默认输出会覆盖同目录中的两个分发 ZIP，请按需通过参数指定其他输出。
运行 `python3 s100-and-rail/build_display_overlay.py` 生成 S100 显示字体及客户端 overlay，输出至 `s100-and-rail/distributions/`。

显示覆盖包为 `s100-and-rail/distributions/resourcepack-s100-displays-1.21.11-26.2.zip`；在客户端将它放在原 S100 资源包上方启用。包含 `javarailways:cabin_text` 中英文字体（Noto Sans CJK SC、Roboto）和 `javarailways:display_geometry` 圈点字形。TTF 字体、字体定义和各自的 OFL 许可证均保存在 `s100-and-rail/resourcepack/assets/javarailways/font/`，上述构建命令会一并打包。

S100 的铁粒和铁锭 CustomModelData 映射使用 `assets/minecraft/items/` 下的 `minecraft:range_dispatch`，与命名物品入口共用相同模型和 tint。26.2 透明度拆层仅在格式 88 的 overlay 中生效，1.21.11 使用基础模型。

格式依据：[Minecraft Java Edition 1.21.11 官方更新说明](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-11)。静态构建和引用检查不能代替游戏内的列车、信号、轨道和文字显示验收。
