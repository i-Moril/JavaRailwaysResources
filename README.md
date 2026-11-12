# JavaRailways Resources

独立保存 JavaRailways 客户端资源包源码、生成工具和既有分发包。这里的文件从 JavaRailways 工作区整理而来；具体客户端格式以各包 `pack.mcmeta` 为准。服务器模型配置和示例不属于本仓库。

- `s100-and-rail/`：S100 资源包源码，当前同时包含轨道模型资源；`distributions/` 保存既有版本及 S100 显示覆盖包。`build_s100_transparency_pack.py` 生成 control 和透明度两个版本。
- `rail/`：独立轨道客户端资源包的既有 ZIP。
- `signals/jr-four-light/`：四灯客户端资源源码和 26.1.2 分发包；源码声明 1.21.11，ZIP 声明 26.1.2，两者元数据不同。
- `signals/route-indicator/`：进路表示器客户端资源源码、资源包 ZIP 和含服务器模型的历史完整交付 ZIP。
- `editor-markers/`：编辑器标记资源源码、纹理生成工具和既有 ZIP。

`distributions/` 保留原始文件，不代表所有 ZIP 与当前源码一致：S100 基础 ZIP 的内容与源码有差异，进路表示器完整 ZIP 中的 README 未同步。实际客户端效果和版本兼容性需要各自验证。

## 生成

运行 `node editor-markers/generate-texture.mjs` 重新生成标记纹理。
运行 `python3 s100-and-rail/build_s100_transparency_pack.py --help` 查看 S100 资源包构建参数；默认输出会覆盖同目录中的两个分发 ZIP，请按需通过参数指定其他输出。
