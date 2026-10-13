---
name: cockpit-system-diagram
description: 使用原生可编辑 draw.io 绘制、重构智能座舱系统上下文和硬件连接架构图，统一器件符号、紧凑尺寸、物理边界、信号配色与布线。适用于 SoC、MCU、板卡、接插件和音视频外设；不把硬件连接布局套到软件分层或 VM 部署图。
---

# Cockpit System Diagram

交付可逐项编辑的 `.drawio` 和经过目视检查的预览。图内文字使用英文，真实型号和接口标识保留原拼写。这里的颜色和尺寸是本项目约定，不是汽车行业强制标准。

## 先选择视图，不先摆器件

| 视图 | 回答的问题 | 布局依据与本 skill 范围 |
| --- | --- | --- |
| System context | 座舱与哪些外部系统交互？ | 系统边界、外部接口；使用本 skill，不要求展开内部芯片 |
| Hardware connectivity | 芯片、板卡和外设如何连接？ | 物理组成、直接连接者、端口和信号链；本 skill 的主要视图 |
| Runtime deployment | OS、VM、TEE 运行在哪里？ | 承载与隔离；不是芯片连接图，需要另外明确部署模型 |
| Software layering | 软件如何依赖和提供能力？ | 技术层次、进程归属；不使用本 skill 的硬件卡片布局代替分层 |
| Subsystem collaboration | Camera、Audio 等内部如何工作？ | 硬件路径使用本 skill；涉及软件时保留其真实分层，必要时另页展开 |

根据请求选择，不要求用户逐项填写分类。不知道具体 SoC 型号时可写 `Cockpit SoC`；不知道具体协议、端口、板卡边界时不能把模板当作平台事实。软件或 VM 视图可配合同级 `architecture-diagram` / `drawio-diagram` skill，但仅在需要该视图时读取；本 skill 的硬件图生成与检查不依赖它们。

## 必读规则与资产

新建或重构前完整读取 [visual-contract.md](references/visual-contract.md)；操作 draw.io 文件及验收前完整读取 [native-workflow.md](references/native-workflow.md)。

- **当前模板**：[cockpit-hardware-symbols.drawio](assets/cockpit-hardware-symbols.drawio)。依次包含器件符号、连接与边界、外部 DSP 音频示例、接插件符号四页。复制需要的原生元素，不把整页图片嵌入结果。
- **唯一尺寸与样式参数**：[tokens.json](assets/tokens.json)。使用模板内嵌的离线字体；不下载字体、不新增网络依赖。
- **预览**：[器件](assets/previews/01-symbols.png)、[连接](assets/previews/02-connections.png)、[音频](assets/previews/03-audio-example.png)、[接插件](assets/previews/04-connector-symbols.png)。只看本次需要的页面；预览不是编辑源。

模板来自已审阅的 `cockpit-symbol-library-review/cockpit-hardware-symbols.drawio`，在本目录内落实紧凑尺寸规则。旧审阅图的高卡片不再作为尺寸依据；模板中的拓扑只演示表达方法，不证明目标系统具有该硬件。

## 必须保持的约束

1. **关系优先级**：真实连接与物理边界 → 功能链清晰 → 减少交叉和绕线 → 局部左进右出 → 对齐与均衡。不能为了“输入左、输出右”改接外设、重复器件或制造长回路线。
2. **围绕直接连接者布局**：Mic、Speaker 接到外部 DSP 时围绕 DSP 组织音频链。`External DSP` 仅表示在 SoC 外，不代表在 ECU 或板卡外。MCU 可以按实际板卡关系放在 SoC 下方，不套用 VM 部署图的并列要求。
3. **实体与边界真实**：芯片、模块、接插件、板卡、外部设备分别建模。物理包含使用真实父子容器；功能分组不暗示共板。一个 J1 只有一个实体，必要时在它内部展开端口。
4. **不猜技术事实**：保留来源中的实体与已确认修正。未确认的 GNSS 连接、协议、芯片型号、连接器制式等不补画；关键主链矛盾询问，其余在图外列出未知项。Reserved / Optional / DNP 明示文字，不能只靠灰色。
5. **固定紧凑节点**：普通器件高度 80，接插件高度 48；SoC / MCU 可随端口调整。普通 DSP / SerDes 不因外围设备多而拉高。多端子展开容器是独立类型，不是任意高度的豁免标签。
6. **图标与文字成组**：普通器件左图标、右侧左对齐文字组；按实际行数垂直居中。不让单行名称占据多行高度，不让说明框填满剩余空间。接插件优先单行，例如 `J11 (FAKRA ×4)`；宽度按标签内容收紧到 8 px 网格，不统一拉长或撑满示例列。
7. **符号不代替事实**：Coax / Shielded / USB Type-A / USB Type-C 表示已知物理形态；GMSL、FPD-Link、USB 是链路标签，不自动决定连接器外形。图标内触点数不是引脚定义。
8. **颜色只表达一个维度**：硬件节点中性，线色表达信号族；不用厂商颜色为芯片填色。需要按来源或职责配色时先明确另一种视图，不沿用本模板颜色解释。
9. **原生连接**：真实边绑定 source / target 和端口；标签归属于边。先消除非必要交叉，再用原生跨线弧表示不连接；真实分支才使用连接点，独立摄像头通道不得合并成一根总线。
10. **保留用户编辑**：修改现有 `.drawio` 时保留 ID、父级与用户布局，针对指定元素编辑。不能从旧生成脚本全量覆盖已手调文件。除用户要求，不改原文、已发布图片或其他 skill。

## 工作流程

1. 从材料列出：实体 / 类型 / 物理归属 / 接口 / 信号方向 / 证据 / 状态。区分确认事实、通用示意和未知项；这份小清单即可，不强制另造大型 JSON 模型。
2. 先摆 ECU / Board 边界与处理核心，再按实际连接组织 Camera / Display / Audio / Vehicle I/O 等链路。只保留参与视图的区域，不为凑模板填入无关模块。
3. 复用模板符号和 tokens。先确定紧凑节点与端口顺序，再规划独立走线通道，最后放标签。长名称优先加宽，只有接插件允许在约定范围内调整字号。
4. 运行检查，渲染全图及可读尺寸的局部；处理文字截断、穿框、绕线、标签归属和端点方向。完成 draw.io 保存往返和临时副本移动检查。无法渲染时保留可编辑产物，明确缺少的验收项。
5. 交付 `.drawio` 和预览，简要报告检查结果与未确认关系。不要把结构检查通过说成技术事实全部正确。

在本 skill 目录执行（输入使用实际路径）：

```bash
python3 scripts/check-drawio.py /absolute/path/result.drawio
```

现有图缺少本 skill 的布局元数据时，先检查实际原生结构；不能将“无法按本约定校验”解释为文件损坏，或借此重建整张图。

## 维护本 skill

尺寸或符号更新必须同时更新 tokens、构建函数、模板和预览；不只修改文字规则。生成器用于维护**本技能的四页模板**，不是任意目标架构的自动布局器。

```bash
node scripts/build-template.mjs --output /absolute/path/template-review.drawio
python3 scripts/check-drawio.py /absolute/path/template-review.drawio
python3 scripts/test-check-drawio.py
```

先在新文件验证，确认后再替换 canonical asset；`--overwrite` 仅用于本次自建产物或已明确授权的替换。模板要始终留在本目录，不能依赖 `work/` 下审阅草稿的相对路径。
