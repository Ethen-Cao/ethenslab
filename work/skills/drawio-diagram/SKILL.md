---
name: drawio-diagram
description: 生成或修改原生可编辑的 .drawio 架构图，将已确认的组件、分层和控制/数据路径转换为真实容器、节点与绑定连接线，并用本地 draw.io 渲染验收。适用于新建 draw.io 图、架构 JSON/HTML 转换和既有 draw.io 调整；不以整图 SVG/PNG 导入代替可编辑结构。
---

# Draw.io Diagram

交付的是可逐项编辑的 `.drawio`，不是一张放进 draw.io 的图片。优先复用已确认的模型和布局，不因更换格式重新解释技术架构。

## Scope and dependencies

- **架构规则**：复用同级 [architecture-diagram](../architecture-diagram/SKILL.md) 的命名、部署、分层、英文文字、用途配色和走线规则；该 skill 的 HTML 输出要求在本任务中由原生 `.drawio` 替代，不要求额外生成 HTML。建模或改变架构时完整读取其指定的 modeling / layout / schema 参考。
- **生成依赖**：现有 Node.js 18+、同级 `architecture-diagram` 的 v2 模型校验器、theme 和离线字体。转换器只用 Node 内置模块，不需要 npm、draw.io 桌面端或网络。依赖不在同级时使用 `--architecture-skill <directory>`，模型对比检查同时传 `--theme <directory>/assets/theme.json`；不要复制出第二套样式。
- **检查依赖**：结构检查只需 Python 3.9+ 标准库；渲染及 roundtrip 需要可用的本地 draw.io。先发现可执行文件并查 `--help`，不硬编码安装路径或假定版本。缺少渲染环境时仍可生成，但必须明确“未渲染验收”，不自行安装软件、字体或修改系统缓存。
- **保存边界**：只写用户指定的产物；除明确要求外，不替换原 HTML / Markdown。不要上传项目图到在线服务。

## Choose the working source

1. **已有 `.diagram.json`**：以它为技术与几何来源，先通过模型校验；不要从 HTML 截图重新猜节点、父级或调用关系。
2. **只有 HTML / 文档**：先提取已有结构模型；没有模型时依据材料建立 v2 模型，遵守架构部署与组件角色关口。截图只能参考布局，不能建立未知组件或协议事实。
3. **修改既有 `.drawio`**：先检查原文件并保留其原生 ID、父级、端口和用户调整。直接修改指定实体，不从旧 JSON 全量覆盖用户手工布局。仅用户明确要求重新生成时才重新转换。

JSON → `.drawio` 是单向导出，没有自动双向同步。用户开始手工编辑后，`.drawio` 是其编辑成果；旧 JSON 不自动获得这些修改。

## Native editability contract

构建或修复 XML 前完整读取 [native-format.md](references/native-format.md)。以下不是可省略的视觉建议：

- 每个组件和容器使用原生 vertex / group；容器真实嵌套，子坐标相对父容器。视觉上被框住不等于具有父子关系。
- 每条架构关系是原生 edge，`source` / `target` 指向真实节点；端点为归一化 entry / exit 端口。不能用自由线、独立箭头三角形或 SVG path 冒充连接。
- 跨容器边属于两端最近共同祖先，折点相对该祖先；优先保留已审阅的正交路径，使用原生 arc 跨线桥，不增加非必要交叉。
- 连线标签是该 edge 的相对 vertex 子项；共享内存用可编辑的堆叠矩形组；真实分支使用原生实心点。不得把标签、装饰内存面或图例算作技术组件。
- 容器标题左上、内容在 header 下；节点主名居中、副标题在下。大小、配色、字体、圆角和线宽复用公共 tokens；不缩字、不改名来适配。
- 字体离线内嵌并保留许可证；仅设置 `fontFamily` 或 `extFonts` 不证明 CLI 已加载字体。遵循参考中的注册方式，并检查实际渲染。

## Build

以下命令在本 skill 目录执行，输入 / 输出使用实际的绝对路径：

```bash
node scripts/build-drawio.mjs /path/input.diagram.json /path/output.drawio
python scripts/check-drawio.py /path/output.drawio --model /path/input.diagram.json
```

构建器默认拒绝覆盖已有输出。`--overwrite` 只用于已明确授权的替换，或本次任务自己生成的临时文件；否则选择新文件名。来源图例默认使用泛称，不把所有 Vendor 当 Qualcomm；目标平台已确认时可传 `--origin-labels '{"vendor":"Qualcomm"}'`。技术模式不按来源染色，责任模式不拿来源代替责任。

首轮转换的 `--model` 检查比较身份、包含、几何与关系；手工移动后的原生文件使用不带 `--model` 的检查，再复核实际变更，不把旧坐标当新布局的验收目标。结构工具检查原生 router 与显式折点，不把移动后的“当前端点 + 旧折点”当实际渲染路线；结构通过不证明技术事实、字体加载、无遮挡或走线美观。

## Verify and deliver

渲染前读取 [local-verification.md](references/local-verification.md)，使用独立临时 profile，不干扰用户已有编辑会话。

1. **结构**：检查 XML / ID、父子关系、原生节点和绑定边、NCA、端口、正交折点和相对标签；首次导出与源模型比对。
2. **渲染**：用本地 draw.io 导出 PNG 或 SVG，检查全局部署布局及可读尺寸的各软件区域；重点看标题 header、长名称、内存堆叠、箭头端点、标签与跨线弧。
3. **Roundtrip**：由 draw.io 导出未压缩 XML 后再次检查；成功导出图片不等于原生结构被完整保留。
4. **编辑性抽查**：在临时副本移动主链节点或容器，不重建模型，确认边仍绑定、标签仍跟随；同时看最后进入方向、折点和交叉。绑定不丢失不等于所有复杂线路自动整齐，必要时用原生折点微调。
5. **交付**：链接 `.drawio` 和已检查的预览，说明结构 / 渲染 / roundtrip / 移动测试实际完成哪些。不得把结构通过说成全部架构正确；没有查看截图不能称视觉验收通过。

预览不是编辑源。draw.io CLI 可能把 SVG 中的 HTML 文字变成局部位图，不影响原生 `.drawio`；据实际结果描述“渲染预览”，不要宣称必然是全矢量。跨线弧方向、文本度量可能与 HTML renderer 不同，应验证可读性与关系，不承诺逐像素一致。

## OTA reference

已验证的实例：[OTA model](../../h56ez-ota-architecture-redrawn.diagram.json)、[editable diagram](../../h56ez-ota-architecture.drawio)。用于检查转换结果，不是其他系统的固定组件清单或唯一布局。实例不在当前仓库时不影响此 skill 的执行。
