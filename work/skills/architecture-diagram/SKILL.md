---
name: architecture-diagram
description: 创建或修改独立 HTML 软件架构图，统一系统级与子模块级的技术分层、真实组件命名、进程归属、数据路径和连线布局。适用于 Android、Linux、QNX、多 OS/VM 及硬件/共享内存.
---

# Architecture Diagram

生成独立、静态、全英文 HTML：标题、架构图、必要图例。无工具栏、主题切换、详情面板或 PPT 布局。使用本 skill 的模型与公共 renderer，不重新拼一套 HTML/CSS/SVG；字体、圆角、线宽统一取自 `assets/theme.json`，构建器内嵌固定字体，加载成功后才测量与绘制。用户当前明确要求优先；示例提供合规建模与布局，不提供其他平台的技术事实。

## Decide the scope

先明确图要回答的问题，并记录独立维度：

- **粒度**：`system` 展示真实子系统、层次和关键依赖；`subsystem` 展示实际进程、库、核心类、内核接口及相关资源。
- **视图**：`layered` 为分层主图，可叠加关键控制/数据流；`dataflow` 是路径补充视图，不能替代用户要求的主图。
- **用途**：`technical` 默认只解释技术实现；`origin` 才按组件来源着色；`responsibility` 明确一种项目责任后按责任方着色。来源、责任和技术层次不能相互推断。

只在缺失信息影响主链正确性时询问；非关键细节停留在已确认父组件，不伪造 SO、类名或功能性 Block。

## Read the relevant rules

绘制或修改前完整读取：

1. [modeling.md](references/modeling.md)：类别适用范围、命名、Android / Linux / QNX 分层、跨 VM 与硬件/内存条件规则。
2. [layout.md](references/layout.md)：必须满足的相对布局、英文文字、容器 header、节点、端点、走线、标签、用途配色与最小间距。
3. [schema.md](references/schema.md)：版本 2 模型、构建命令、校验及交付要求。

只有用户要求更新文章或发布到本站时读取 [publishing.md](references/publishing.md)。普通简单流程/时序无需强行使用本架构模型。

## Non-negotiable boundaries

- **MUST**：大软件层次按主要能力依赖自上而下；同层可以横排或竖排。强制架构语义，不强制复制模板坐标、列数或宽高。
- **MUST**：层是技术角色，进程是运行归属。实际 SO / 类归属正确；`.so` 后缀、实现语言或开发方都不能直接决定层次。
- **MUST**：系统级允许有真实边界的子系统名称；子模块使用已确认实体名。职责只作副标题。内核文件接口为 `path · module`，无文件路径时不编造。
- **MUST**：图内所有可见文字及无障碍说明用英文，真实标识符保留拼写；图外讨论可用中文。
- **MUST**：保留真实边界与传输机制；数据、控制、通知、配置分开。Hypervisor 只覆盖实际承载 VM；内存按实际读写链定位，不强制放硬件区。
- **MUST**：静态、自包含、无网络依赖；不增加未要求的控制面板、PPT 分支或装饰说明。
- **MUST**：修改时保留已确认名称与归属；技术或布局原因确需更改时说明，不无故恢复旧结果。

参考中 `MUST` 为验收约束，`SHOULD` 为可因实际内容调整的建议；示例不是组件清单。若规则与旧图冲突，按现行规则生成，不能以旧图为例外依据。

## Choose one relevant example

模型源位于 `assets/models/`，以下 HTML 均由同一 renderer 生成；只读取当前任务有关的模型/示例。

| Example | 适用问题 |
| --- | --- |
| [android-system.html](assets/architecture_diagrams/android-system.html) | 官方宏观层次；Core Android APIs 与 Car APIs 同层，System Services 可展开真实进程 |
| [linux-system.html](assets/architecture_diagrams/linux-system.html) | 应用/客户端接口/服务/内核依赖，非强制 PAL 的嵌入式 Linux 骨架 |
| [qnx-system.html](assets/architecture_diagrams/qnx-system.html) | 客户端、服务、用户态驱动与 `procnto`，避免把驱动全部放入 Kernel |
| [multi-domain-system.html](assets/architecture_diagrams/multi-domain-system.html) | 并列 VM、各域纵向分层、公共 Hypervisor 与不受其承载的独立域 |
| [process-library-subsystem.html](assets/architecture_diagrams/process-library-subsystem.html) | 实际进程、内部库/类、并列依赖、IPC 与内核接口 |
| [shared-memory-io.html](assets/architecture_diagrams/shared-memory-io.html) | 输入/输出方向、唯一 Buffer、真实读写者与通知分离 |
| [layout-primitives.html](assets/architecture_diagrams/layout-primitives.html) | 抽象布局小样：标题、长名称、多路入口、真分支与跨线弧；不作技术事实来源 |

`assets/legacy/` 保存历史快照供追溯，不是默认示例。不要从中复制旧命名、配色、中文界面、交互或幻灯片代码。

## Generate and verify

1. 先确定部署骨架，确定实体、层次、运行归属、关系与证据，逐项确定组件的技术层与运行归属，自我审查通过后才按规则布置容器、节点、线和标签。
2. 从 `assets/base-model.json` 或所选模型起步，按 schema 修改 JSON；运行 `node scripts/build-diagram.mjs <model.json> <output.html>`。`assets/base-template.html` 是生成预览，不手工修改。
3. 模型校验、浏览器几何校验、截图目视和技术证据复核分别完成；模型/渲染数量必须准确对应，不能让空 DOM 的检查冒充通过。命令和判定标准见 schema。
4. 报告输出与源模型路径、错误/警告计数、实际检查的视图及未确认或省略内容。未进行浏览器检查必须明说；自动检查不证明架构事实正确。

除用户明确要求外，不改原文或已发布图。维护本 skill 时改公共源和模型后统一重建示例，不逐份修补生成 HTML。
