# Native draw.io mapping

这些约束针对原生模型；无需每次重新反编译已安装的 draw.io。变更实现或遇到版本差异时再查实际应用或 [官方文件格式说明](https://github.com/jgraph/drawio/wiki/File-Format)。本 skill 的构建器生成未压缩 `mxfile → diagram → mxGraphModel → root` XML，利于检查与局部修改；编辑器可能将其保存为压缩格式，不能因此断言损坏。

## Cells, identity and hierarchy

| 对象 | 原生实现 |
| --- | --- |
| Domain / layer / process | `mxCell vertex="1"`，实际 `parent`，`container=1;recursiveResize=0;collapsible=0` |
| 软件 / 硬件 Block | 原生矩形 vertex；真实名称和类型保存在 `object` metadata，名称与职责分别显示 |
| 内存 / 存储 | 原生 group 加三层矩形；group 本身无边框、无填色，正面拥有标签，连接指向 group |
| 架构关系 | `mxCell edge="1" source="node-id" target="node-id"`；不可只设置自由 `sourcePoint` / `targetPoint` |
| 标签 | 原生 vertex，`parent=edge-id`，`mxGeometry relative="1"`，`edgeLabel=1` |
| 真实分支点 | 同色原生 ellipse，作为共用路径的 edge-child；不增加虚构软件节点 |
| 图例线 | 允许自由端点，明确 `legend-` ID；不混入真实边计数 |

`object` / `UserObject` 包裹 cell 时，逻辑 ID 在 wrapper 上；内部 cell 不重复赋相同 ID。组件使用稳定 `modelId / canonicalName / entityType / evidence`；页标题和 ID 来自目标模型，不写死 `OTA`。

容器不要加 `part=1`、自动 `childLayout` 或锁定整个图来维持整洁，它们会削弱用户的正常拖动和尺寸调整。内存装饰面不作为可连端点。

模型坐标是全局坐标，native vertex 坐标是父容器相对坐标：`child.x = model.x − parent.x`，y 同理。根部画布偏移只计一次。跨容器 edge 归属 source / target 的最近共同祖先（NCA），其 waypoints 同样减去 NCA 全局原点；不能统一把所有线塞在页根后又使用局部坐标。

## Bound connectors and labels

已审阅正交路线使用 `edgeStyle=segmentEdgeStyle` 加 `<Array as="points">` 的中间折点。不要使用 `noEdgeStyle=1` 来模拟正交：移动节点后可能出现斜向首尾段。新路径可选原生 orthogonal router，但必须重新审阅，不假定自动排线优于人工规划。

固定端口使用 `exitX/exitY` 与 `entryX/entryY`，`exitPerimeter=0;entryPerimeter=0`。side 上 offset 是像素，转换为：

- top / bottom：`x = (width / 2 + offset) / width`，`y = 0 / 1`。
- left / right：`x = 0 / 1`，`y = (height / 2 + offset) / height`。

不要把像素坐标写入这些 0…1 参数。单端口居中，多端口按来向排序；端口属于实际节点边界。内存堆叠 group 的视觉边界与连接端点要一起检查。

`jumpStyle=arc;jumpSize=10` 是当前主题下的原生跨线桥，10 来自 `2 × bridgeRadius`，不是随意画出的 Bézier 装饰。先消除可消除的交叉；共享真分支才画实心点，不把交叉当连接。原生跨线桥与 HTML 的弧向、避让策略不保证完全相同。

标签相对 geometry 的 `x ∈ [-1,1]` 由沿路径的距离比例确定；`offset` 保留标签相对该位置的位移。它不是一个跟线无关的绝对坐标文本框。移动后依旧要检查标签是否接近所属线段、避开拐点和箭头。

即使 entry / exit 固定，手工折点也可能在移动后改变末段来向或造成穿框。保留绑定并不保证自动重排；不要只做“节点移动了、箭头还在”的验收。`segmentEdgeStyle` 会在渲染时加入正交连接段，XML 中移动后的端点与旧折点不直接相连；基础检查不能用二者的斜向差值误判原生线路已变成斜线，实际来向仍须渲染检查。

## Theme and fonts

读取同级 `architecture-diagram/assets/theme.json`；普通 Roboto、库 / 设备接口主名 Roboto Mono，类名仍是 Sans。当前圆角4 / 8 / 12px；`absoluteArcSize=1` 下 native `arcSize` 使用相应直径8 / 16 / 24，不将其作为百分比。

用途、节点来源或责任配色与线条语义独立。图例只包含使用的项目，数据线图例写 **Data**。不要固定所有图都显示 Qualcomm，也不按所在 OS 染色。硬件 / 内存和容器中性；configured 对象中性虚线。

本地 draw.io 32.4.1 的实测：仅 `fontFamily` 可能回退，仅 `mxGraphModel.extFonts` 也不足以保证 CLI 加载。构建器同时保存：

1. `extFonts="Family^data:font/woff2;base64,...|OtherFamily^..."`。
2. 原生 cell style 的单 family `fontFamily` 与 `fontSource=encodeURIComponent(dataURL)`，以便导出时注册两种字体。Mono 注册 cell 可为空，不新增可见说明。
3. 富文本标签内部的 CSS family 与现代后备字体栈。
4. 固定字体 SHA-256 校验、字体清单和 OFL 许可证元数据。

不要把 CSS 后备栈当离线资源；不要为 Fontconfig 警告安装字体、清理缓存或改软件。字体声明 / 数据存在只是结构证据，仍需渲染查看。预览 SVG 的局部位图与 `.drawio` 的原生组件是两回事。
