# Native draw.io workflow

## Dependencies and preservation

复制模板及手工编辑不依赖 Node 或 Python。维护模板的生成器只需 Node.js 18+；结构检查需要 Python 3 标准库；PNG / XML 导出验收需要可用的本地 draw.io。所有字体和生成资源位于本 skill，不依赖原审阅目录或同级软件架构 skill。不要上传项目图到在线编辑器。

先检查已有 `.drawio`：压缩格式不等于损坏。保留原始 ID、parent、端口及用户手动位置；只修改本次范围。生成脚本与 draw.io 不是双向同步，手动编辑后的文件不能由旧脚本无条件覆盖。

## Native contract

- 节点 / 容器使用原生 vertex / group；实际 parent 对应包含关系，子坐标相对父容器。不要靠背景大框伪装嵌套。
- 器件 / 内存节点的 object metadata 至少记录 `canonicalName`、`symbolType`、`layoutClass`；目标图还记录来源 / 未知项。普通器件为 `device`，紧凑接插件为 `connector`，SoC / MCU 为 `processor`；真实端子展开可为 `port-strip`。
- ECU / Board / 功能容器用 `kind=physical-enclosure` / `board` / `functional-group` 标识；它们不使用硬件卡片的 `layoutClass`，不要添加未定义的 `layoutClass=container`。标题、图例和装饰元素同样不伪装为器件节点。
- 表现模式在 `mxGraphModel.nodeStyle` 与卡片 object 的 `nodeStyle` 上记录 `icons` / `plain`；旧图省略时按 `icons` 兼容。同页不混用；无图标新页和卡片都显式写 `plain`，不以缺少图标反推模式。
- 无图标页同时在现有页面标题 object 保存唯一的 `kind=page-contract`、`nodeStyle=plain`，不新增可见提示。draw.io 保存时可能移除 `mxGraphModel` 的自定义属性，检查器在该属性缺失时读取此原生标记；多个标记或相互冲突的声明都报错。复制整页或导出新页时须一并保留标记。
- 图标版卡片内部使用 `<id>-icon`、`<id>-name` 和可选 `<id>-description`。图标组里的图形仍是可编辑原生元素；装饰线标记 `kind=decoration` 或 `legend-` ID，不能混作技术连线。无图标版仅创建名称和可选说明，不创建隐藏图标或空图标 group；其 `symbolType` 仍保留实体类别，不代表必须绘制图形。
- 复制元素时为整个子树重映射 ID / parent / source / target，保持引用一致。连接实际实体或端口，不连接装饰引脚、文本框或图标内部矩形。
- 每条架构关系必须有 source / target，entry / exit 在 0…1 范围；不能只放自由 sourcePoint / targetPoint。边放在两端最近共同祖先，折点使用该祖先的相对坐标。
- 新的直连优先使用原生 `orthogonalEdgeStyle` 并留出至少 16 的端点避让；已有明确审阅折点的路线使用 `segmentEdgeStyle`。两者都须渲染检查，不保证任意移动后自动避障。不要用 `noEdgeStyle=1` 模拟布局。不可避免交叉使用 `jumpStyle=arc;jumpSize=10`；不要独立画假弧。
- 标签是 edge 的相对 vertex 子项，`edgeLabel=1`、`relative=1`；不能是飘在边旁边的独立文本。真实 junction 是独立原生点，由相关边绑定。
- 不锁住整图、不把整图做成 image cell、不使用自动容器布局抹掉手动端口设计。
- 模板离线字体同时通过 extFonts 和带 fontSource 的注册 cell 保留。复制到新页时保留字体注册及许可证信息；仅写 fontFamily 不证明导出使用了该字体。

### Reusable legend entries

复制模板的完整 `kind=legend-entry` 原生组，不只复制名称。信号项声明 `legendType=signal`、`signalClass`；方向项声明 `legendType=direction`、`legendValue=single|bidirectional|physical`；虚线项声明 `legendType=linestyle`、`legendValue=dashed`，名称说明具体语义。

组内 `<id>-sample` 为 `kind=legend-sample` 的原生 edge，`<id>-label` 为非空原生文字。样本可以使用明确的 sourcePoint / targetPoint，无需伪造器件端点；它不是系统关系，不能连到正文器件。样本与名称均为该组的直接子项。信号族项的样本用对应色、实线、无箭头，方向或虚线由独立项解释。

## Checks

```bash
python3 scripts/check-drawio.py /absolute/path/result.drawio
```

检查覆盖模式一致性、布局元数据、对应模式的固定高度、指定文本字号与几何、原生身份 / 层级、绑定端点和相对标签；无图标版还检查残留图标与占位偏移。对可识别的信号关系，还检查图例样本与名称是否存在、信号族覆盖、线色 / 线宽、方向和虚线示例。旧图无可识别信号元数据 / 配色时仍需人工确认图例；不要把“未纳入此项检查”称为覆盖通过。连接点和实际跨线示例的完整性仍须目视检查。

检查不证明技术连接正确，不测量真实字形宽度，不保证自动 router 的实际路径无交叉。缺失元数据需要补充真实类型，不能为通过检查乱标 `processor` 或 `port-strip`。

## Local render and roundtrip

发现实际安装程序并查看 `--help`，不要硬编码平台路径或版本。创建专用临时目录，使用独立 profile，避免干扰用户编辑会话。以下是在本地已使用的 CLI 参数形式；以实际版本支持为准：

```bash
diagram_qa_dir=$(mktemp -d /tmp/cockpit-diagram-qa-XXXXXX)
drawio --export --format png --scale 1 --border 24 --theme light \
  --output "$diagram_qa_dir/preview.png" \
  --user-data-dir="$diagram_qa_dir/profile" --disable-update --timeout 45 \
  /absolute/path/result.drawio
drawio --export --format xml --uncompressed \
  --output "$diagram_qa_dir/roundtrip.xml" \
  --user-data-dir="$diagram_qa_dir/profile" --disable-update --timeout 45 \
  /absolute/path/result.drawio
python3 scripts/check-drawio.py "$diagram_qa_dir/roundtrip.xml"
```

多页模板逐页导出；先核对当前版本的页码选项。必须实际查看预览，确认长标签、图标缩放、节点高度、端口方向、布线和跨线桥。输出存在和退出码成功都不能代替目视检查。

若沙箱阻止 Electron，使用正常授权流程；不加 `--no-sandbox`，不修改安装包、字体缓存或全局设置。每次失败有明确修正依据才重试，最多两次；无法导出时停止重复启动，交付源文件并报告尚未完成渲染。

## Movement test and delivery

只在临时副本移动一个多连接节点与一个物理容器，保留 ID / source / target，不先重建或重写折点。重新导出并查看绑定端点、边标签、末段来向与穿框情况。

固定折点不保证移动后自动整齐；如需微调原生路径，应如实记录，不能把“边仍绑定”称为“任意拖动都保持美观”。测试副本不能覆盖正式产物。

交付时区分结构检查、目视、保存往返和移动测试的实际完成情况；提供 `.drawio` 与预览链接。用户未要求时不附大量中间模型、不改原 Markdown、不将示例中的未知项写成平台事实。
