---
name: architecture-diagram
description: 创建或修改独立 HTML 软件架构图，先建立部署骨架与技术分层，再表达真实组件、运行归属和控制/数据路径。适用于 Android、Linux、QNX、多 OS/VM 及硬件/共享内存；不用于一般业务流程或 PPT。
---

# Architecture Diagram

生成独立、静态、全英文 HTML：标题、架构图、必要图例。无工具栏、主题切换、详情面板或 PPT 布局。使用本 skill 的模型与公共 renderer，不重新拼一套 HTML/CSS/SVG；字体、圆角、线宽统一取自 `assets/theme.json`，Block 主名称基准为 24px，构建器内嵌固定字体，加载成功后才测量与绘制。用户当前明确要求优先；示例提供合规建模与布局，不提供其他平台的技术事实。

## Decide the scope

先明确图要回答的问题，并记录独立维度：

- **粒度**：`system` 展示真实子系统、层次和关键依赖；`subsystem` 展示实际进程、库、核心类、内核接口及相关资源。
- **视图**：`layered` 为分层主图，可叠加关键控制/数据流；`dataflow` 是路径补充视图，不能替代用户要求的主图。
- **用途**：`technical` 默认只解释技术实现；`origin` 才按组件来源着色；`responsibility` 明确一种项目责任后按责任方着色。来源、责任和技术层次不能相互推断。

部署分类同时写入模型的 `deployment.profile`：单域 `single-domain`、多个独立域 `multi-domain`、同一 SoC 上的 VM `virtualized-soc`。图的粒度不改变其真实部署关系。

只在缺失信息影响部署骨架或主链正确性时询问；非关键细节停留在已确认父组件，不伪造 SO、类名或功能性 Block。材料未提及不等于平台不存在：保留同一目标系统已经确认的承载关系，不能因当前文档只讲业务而删除它。

## Read the relevant rules

绘制或修改前完整读取：

1. [modeling.md](references/modeling.md)：类别适用范围、命名、Android / Linux / QNX 分层、跨 VM 与硬件/内存条件规则。
2. [layout.md](references/layout.md)：必须满足的相对布局、英文文字、容器 header、节点、端点、走线、标签、用途配色与最小间距。
3. [schema.md](references/schema.md)：版本 2 模型、构建命令、校验及交付要求。

只有用户要求更新文章或发布到本站时读取 [publishing.md](references/publishing.md)。普通简单流程/时序无需强行使用本架构模型。

## Non-negotiable boundaries

- **MUST**：大软件层次按主要能力依赖自上而下；同层可以横排或竖排。强制架构语义，不强制复制模板坐标、列数或宽高。
- **MUST**：先锁定部署骨架，再展开各域软件。虚拟化 SoC 使用共同 SoC 边界，VM 并列、Hypervisor 在其下、共同硬件更低；独立 MCU 在 SoC 外并列。参与的 TEE 在 SoC 内、VM 左侧，不放进 VM 或 Hypervisor。详见条件规则。
- **MUST**：层名描述技术能力类别，Block 名描述实现实体，进程容器描述运行归属。一层只有一个实现组件也合理，不为填满层带增加组件。实际 SO / 类归属正确；`.so` 后缀、实现语言或开发方都不能直接决定层次。
- **MUST**：可以省略无关实体，不能省略仍参与主图的承载关系、把调用步骤升格成大软件层，或为短连线移动独立域。`Jobs` / `Flash` / `Activation` 一类阶段不是软件层。
- **MUST**：系统级允许有真实边界的子系统名称；子模块使用已确认实体名。职责只作副标题。内核文件接口为 `path · module`，无文件路径时不编造。
- **MUST**：图内所有可见文字及无障碍说明用英文，真实标识符保留拼写；图外讨论可用中文。
- **MUST**：保留真实边界与传输机制；数据、控制、通知、配置分开。Hypervisor 只覆盖实际承载 VM；内存按实际读写链定位，不强制放硬件区。
- **MUST**：静态、自包含、无网络依赖；不增加未要求的控制面板、PPT 分支或装饰说明。
- **MUST**：修改时保留已确认名称与归属；技术或布局原因确需更改时说明，不无故恢复旧结果。

参考中 `MUST` 为验收约束，`SHOULD` 为可因实际内容调整的建议；示例不是组件清单。若规则与旧图冲突，按现行规则生成，不能以旧图为例外依据。

## Deployment skeleton reference

以下是用户指定的布局参考，适用于涉及这些域的系统级或跨 VM 主图。可以省略无关部分；参与的对象必须保持图中的包含、并列和上下关系。括号中的 OS 角色及硬件清单是可选示例，按目标平台的实际名称、归属与证据选择，不要求全部出现。

```txt
+-------------------------------------------------------------------------------+    +-------------------+
|SoC                                                                            |    |                   |
|                                                                               |    |                   |
|  +---------------+  +--------------------------+  +------------------------+  |    |                   |
|  |               |  |           PVM            |  |          GVM           |  |    |                   |
|  |               |  |    (QNX/Linux Cluster)   |  |     (Android IVI)      |  |    |                   |
|  |               |  +--------------------------+  +------------------------+  |    |                   |
|  |      TEE      |  +------------------------------------------------------+  |    |    Vehicle MCU    |
|  |  (TrustZone)  |  |                 Hypervisor                           |  |    | (Independent Dom) |
|  |               |  |               (hosts: ["pvm", "gvm"])                |  |    |                   |
|  +---------------+  +------------------------------------------------------+  |    |                   |
|                                                                               |    |                   |
|  +-------------------------------------------------------------------------+  |    |                   |
|  |                               Hardware                                  |  |    |                   |
|  |      (SoC eMMC、Network、CPU、Memory、GPU、NPU、VPU、DPU、aDSP、A2B,etc.)  |  |    |                   |
|  +-------------------------------------------------------------------------+  |    |                   |
+-------------------------------------------------------------------------------+    +-------------------+
```

SoC 包含参与的 TEE、并列 PVM / GVM、承载它们的 Hypervisor 和下方 Hardware；Vehicle MCU 是 SoC 外的独立域。Hypervisor 仅跨越其承载 VM 的左右边界，MCU 外框与 SoC 顶底对齐；各 VM 的内部软件仍须按技术层次自上而下展开。

## Choose the skeleton and relevant expansions

模型源位于 `assets/models/`，以下 HTML 均由同一 renderer 生成。先按部署选择骨架，再按参与的 OS 读取展开示例：跨 Android / QNX VM 的图必须同时参考多域、Android、QNX 示例，不能只选某个业务或进程小样。只读取有关的模型/示例。

| Example | 适用问题 |
| --- | --- |
| [android-system.html](assets/architecture_diagrams/android-system.html) | 官方宏观层次；Core Android APIs 与 Car APIs 同层，System Services 可展开真实进程 |
| [linux-system.html](assets/architecture_diagrams/linux-system.html) | 应用/客户端接口/服务/内核依赖，非强制 PAL 的嵌入式 Linux 骨架 |
| [qnx-system.html](assets/architecture_diagrams/qnx-system.html) | 客户端、服务、用户态驱动与 `procnto`，避免把驱动全部放入 Kernel |
| [multi-domain-system.html](assets/architecture_diagrams/multi-domain-system.html) | SoC 边界、并列 VM、公共 Hypervisor、共同硬件与 SoC 外独立 MCU |
| [soc-vm-mcu-layout.html](assets/architecture_diagrams/soc-vm-mcu-layout.html) | 完整部署布局小样：TEE / VM / Hypervisor / Hardware / MCU；只示范相对关系，不证明某平台有 TEE |
| [process-library-subsystem.html](assets/architecture_diagrams/process-library-subsystem.html) | 实际进程、内部库/类、并列依赖、IPC 与内核接口 |
| [shared-memory-io.html](assets/architecture_diagrams/shared-memory-io.html) | 输入/输出方向、唯一 Buffer、真实读写者与通知分离 |
| [layout-primitives.html](assets/architecture_diagrams/layout-primitives.html) | 抽象布局小样：标题、长名称、多路入口、真分支与跨线弧；不作技术事实来源 |

`assets/legacy/` 保存历史快照供追溯，不是默认示例。不要从中复制旧命名、配色、中文界面、交互或幻灯片代码。

## Generate and verify

1. **部署关口**：从资料和已确认上下文列出实际域、承载关系、硬件归属与可省略对象，选择骨架，填写 `deployment`。关键关系未知或冲突先询问，不先猜坐标。
2. **分层关口**：逐项确定实体名 → 所属域 → 技术角色 → 实际运行归属 → 证据。平台写入 `platform`，层写入 `role`，组件写入 `layerRole`。用 [modeling.md](references/modeling.md) 的检查表审查；调用顺序不能替代分层，不通过则不进入走线。
3. **布局与构建**：从所选模型起步，替换事实与坐标；先容器、再节点、后线路与标签。运行 `node scripts/build-diagram.mjs <model.json> <output.html>`；生成 HTML 不手工修补。
4. **验收**：依次完成结构/角色校验、技术证据复核、浏览器几何校验和截图目视；分别记录结论。自动检查只能证明其覆盖的约束，不能以“零错误”宣称全部技术事实正确。
5. **交付**：报告 HTML 与源模型、各类检查结果、实际检查视图及非主链省略。任一部署或技术关口未通过，不作为合格架构图交付。未进行浏览器检查必须明说。

除用户明确要求外，不改原文或已发布图。维护本 skill 时改公共源和模型后统一重建示例，不逐份修补生成 HTML。
