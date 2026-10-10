---
name: architecture-diagram
description: 创建或修改独立 HTML 软件架构图（框图、block diagram、软件栈图、模块调用与数据流图），统一系统级与子模块级图的配色、分层、组件命名和连线。适用于软件栈、多 OS/VM、SoC/MCU 以及模块调用与数据流；不用于一般业务流程图、时序图，也不用于文章内可用 mermaid / PlantUML 代码块表达的简单图。
---

# 软件架构图

输出可独立打开的 HTML，使用 HTML/CSS/SVG 绘制。用户明确要求优先于本规范；参考图只提供布局，不是其他平台的技术事实。
需要分域分层、交互聚焦或精细排版时才用本 skill；文章内的简单流程、时序、类图直接用 mermaid / PlantUML 代码块（ethenslab 的 PlantUML 样式见 `content/others/PlantUML 元素规范.md`）。

## 起点与参考

新图复制 [base-template.html](assets/base-template.html)，只改顶部数据段：`META`、`containers`、`nodes`、`edges`、`junctions`、`views`、`flows`。主题、节点、连线、跨线弧、分支点、缩放、聚焦、图例和嵌入高度已实现；数据错误会在控制台抛出。

以下参考只看布局，路径相对于本 skill；不要每次读取全部 HTML。

- 单 OS 系统概览：[android_architecture.html](assets/architecture_diagrams/android_architecture.html)。
- 多 OS/VM 系统概览：[multios_architecture.html](assets/architecture_diagrams/multios_architecture.html)。
- SoC/MCU 系统概览：[soc_mcu_architecture.html](assets/architecture_diagrams/soc_mcu_architecture.html)。
- 简单子模块分层：[display_architecture.html](assets/architecture_diagrams/display_architecture.html)。
- 复杂子模块、进程边界、控制/数据流：[pvm-graphics-stack-architecture.html](assets/architecture_diagrams/pvm-graphics-stack-architecture.html)。参考大图的分栏、用户态/内核态边界和硬件区排布，不照搬业务节点和坐标。
- 跨安全域、多 OS 播放链路与显示输出：[cockpit-drm-playback-architecture.html](assets/architecture_diagrams/cockpit-drm-playback-architecture.html)。重点参考 TEE / QNX / Android 分区、受保护内存、串行显示链路及不同输出配置的布局；其配色、字号和英文界面不沿用。

参考模板的配色和实现不一致，一律以本规范和 base-template 为准。参考资源是 skill 内的独立快照，不自动反向覆盖发布文件。

## 技术模型与粒度

- 先确定组件实体、所属域/层/进程，以及关系的方向、机制和依据，再布局。
- 系统级展示责任域、软件层与核心能力；只画必要的跨域接口，不展开全部库和类。
- 子模块级展示实际进程、库/类、内核接口和相关硬件；保留解释主要路径所必需的细节。
- 区分包含、调用、IPC、数据读写、通知和配置。共享内存承载的数据与 doorbell/IRQ 通知分别建模。
- 不为缩短连线而省略必要的跨进程/跨 VM/硬件接口，也不将资源授权误画成每次数据都经过的处理节点。
- 未确认的实体和机制不得猜测。重要不确定项简短标明或询问；证据、分析过程和详细限制放节点详情或注释。

## 统一视觉

组件填充色表达来源或实体类别；域、软件层和进程由位置、容器和标题表达，容器不着来源色。

来源颜色为强制要求，亮暗主题取值相同，且不用于其他含义：

| 来源 | 颜色 |
| --- | --- |
| OEM 自研 | 蓝 `#4285F4` |
| 系统原生（AOSP / QNX / Linux 等） | 绿 `#34A853` |
| Vendor / Tier1（SoC 厂商、Tier1、第三方方案） | 黄 `#FBBC04` |

其他类别：

| 类别 | 填充 | 描边 / 文字 |
| --- | --- | --- |
| 硬件 / 寄存器 / 内存 | 亮 `#9AA0A6`，暗 `#5F6368` | 文字亮 `#202124`、暗 `#fff`；内存用堆叠矩形 |
| 硬件区域面板变体 | 亮 `#edf0f2`，暗 `#3c4043` | 描边用硬件灰，副标题用 muted |
| 来源未确定 | process 色 | muted 实线描边，ink 文字 |
| 仅配置 / 未启用 | process 色 | muted 虚线 `5 4`，muted 文字 |

模板中对应 `kind`：`oem` / `native` / `vendor` / `hardware` / `neutral`；修饰属性 `memory`（堆叠）、`zone`（硬件面板）、`configured`（仅配置）。

蓝、绿、黄节点文字统一用 `#102116`。主题 token：

| token | 亮 | 暗 |
| --- | --- | --- |
| page | `#f8f9fa` | `#202124` |
| panel | `#fff` | `#282a2d` |
| domain | `#f5f6f7` | `#242629` |
| process | `#fff` | `#303337` |
| ink | `#202124` | `#e8eaed` |
| muted | `#5f6368` | `#afb5be` |
| line | `#cbd1d8` | `#565c66` |

参考模板中以下配色不沿用：

- 黄色表示“汽车专属 / Car Services”、灰色表示 HAL / BSP / 虚拟化：车辆功能、HAL、虚拟化按来源着色，灰色只用于硬件实体。
- 蓝→绿渐变表示“OEM 定制原生组件”：按代码主体来源着色，副标题注明“OEM 定制”。
- 域边框按 OS 着色：容器保持中性。
- cockpit 中蓝色表示 External services：外部服务按来源着色，来源不明用中性色。
- 统一灰色箭头：连线颜色按机制区分，见“连线”。

固件按来源着色并标明 firmware，不与硬件寄存器混为实体。
主题、字体和节点样式以 base-template 为准：节点主标题 16、副标题 12、线标签 13（SVG 逻辑单位）。
不要混用其他模板的字号体系或近似颜色（如 cockpit 的绿线 `#28854d`）。
容器低对比，组件清晰；图例只列本图实际使用的语义。

## 布局

- 先排容器和节点，再规划连线，最后放标签。
- 横向表达并行域、OS/VM 或服务链；纵向表达依赖层次。容器嵌套表示归属，不暗示调用。
- 系统级 Android 可用 Applications → Framework/Runtime → Native/HAL → Kernel；Android 子模块按 Java → Native → HAL → Linux kernel 分层。其他 OS 按实际架构划分。
- 子模块的进程用独立容器，库/类放在所属进程内；同级依赖并列，不因布局方便伪造成串行调用。
- 同层对齐、统一间距，跨列/跨层路径预留走线通道；不同 OS 无需强凑同名层。
- 涉及显示硬件时，将处理单元、共享图像内存和显示接口组织在硬件区域，物理输出链放在下一行；内存用堆叠矩形。
- 容器标题占顶部：domain 约 50、process 约 40、layer 约 48（含分隔线），节点和连线放在其下。
- 内容过多时扩大画布（`WIDTH`/`HEIGHT`）、加局部放大（`views`）或路径聚焦（`flows`），或拆图；不缩小字体塞进固定宽高比。

## 命名与文字

- 系统级允许准确的能力、服务和子系统名称；子模块用户态优先实际进程名、SONAME 或核心类名。
- 实体名称与职责分开：`libsdmcore.so` 是组件名，“合成策略”是副标题，不单独伪装成组件。
- 内核对外接口写“文件路径 · 模块名”，如 `/dev/hgsl · qcom_hgsl`；没有设备文件时不编造路径。
- 硬件、固件、寄存器和共享内存明确区分。主标题通常 1–2 行，职责副标题简短。
- 不添加左侧装饰编号、教学口号、大段解释或核验免责声明。保留影响理解的“仅配置”“可选”等状态。
- 界面、图例、详情和容器说明用中文；组件名、接口、协议和硬件术语保留原文。

## 连线

- 调用/控制：蓝色细实线，亮色 `#356dc9` / 深色 `#8ab4f8`，线宽 2.1。
- 数据/像素：绿色较粗实线，亮色 `#237a44` / 深色 `#81c995`，线宽 3.3。
- 密文数据（需与明文或受保护数据区分时）：muted 灰实线，线宽 2。
- 通知/doorbell/IRQ：蓝色点线，线宽 2.1，间隔 `3 5`。
- 配置/分配：muted 灰虚线，线宽 1.8，间隔 `6 5`；不表示逐次执行路径。

箭头、标签文字和分支实心点与所在连线同色。

优先正交、独立通道、少折返，不穿过无关节点、标题或标签。
纵向主链默认接上下边中心，横向主链默认接左右边中心；用户指定锚点应保留。
多路输入时主链保留中心入口，其他线路分配独立入口；不堆叠箭头，不合并不同机制。
不可避免的非连接交叉使用跨线弧，真实分支使用实心点；先优化布局，再处理交叉。
跨线弧由模板的 `routeCrossingBridges()` 自动生成，只支持单段绝对坐标正交 `M/H/V/L` 路径（其他写法模板直接报错）。交点距线段端点或拐点不足 9、同一线段上相邻交点间距小于 16、或弧线会碰到附近线路时不加弧，需调整走线。
扇出分支在 `junctions` 中列出共享前缀的连线，实心点自动落在分叉处，不手写坐标。
标签只写必要的接口、协议或数据名称，不遮挡连线。
端点用 `fromSide`/`toSide` 与 `fromOffset`/`toOffset` 由节点边界计算，折点用 `via`；移动节点后连线、跨线弧和分支点自动重算，手写 `lx`/`ly` 的标签需复核。

## 修改与验收

- 修改现有图时保留已确认的命名、层次和锚点，只调整相关节点与路径，避免无关重排。
- 用 [check-diagram.js](scripts/check-diagram.js) 做几何检查：`errors` 必须为空，`warnings` 逐条修正或确认合理。它检查重复 ID、未知端点、节点/容器归属、箭头贴边与方向、穿过节点、节点重叠、文字溢出、主标题缩字、箭头堆叠、交叉缺弧、连线重合和标签遮挡：

  ```js
  await page.goto('file:///<path>/diagram.html?theme=dark');
  await page.addScriptTag({path: '<skill>/scripts/check-diagram.js'});
  const report = await page.evaluate(() => checkDiagram());
  ```

- 在浏览器检查全图、关键局部及亮暗主题（URL 加 `?theme=dark` 可直接切换）；核对箭头、标签、跨线弧和交互。不能只检查源码；未能预览时明确说明。
- 再核对技术关系；几何通过不等于架构正确。交付时简短说明结果与关键未确认项。
- 默认不改参考资源或原始文章。

## 发布与嵌入（ethenslab）

- 图写入 `static/diagrams/<name>.html`，发布地址为 `/ethenslab/diagrams/<name>.html`；`docs/` 由 Hugo 生成，不手工编辑。
- 文章里的 iframe 和备用链接用相对路径：`../` 的个数等于文章 URL 在 `/ethenslab/` 之后的层数。`content/gunyah/foo.md`（`/ethenslab/gunyah/foo/`）写 `../../diagrams/<name>.html`；`content/android-dev/media/foo.md` 写 `../../../diagrams/<name>.html`。不要写 `static/` 前缀，Hugo 构建后会失效。
- 模板在 iframe 中向父页面发送 `{type: '<DIAGRAM_ID>-height', height}`。文章按下列写法接收，并校验来源窗口与 origin：

  ```html
  <iframe id="<DIAGRAM_ID>" src="../../diagrams/<name>.html" title="<图标题>" loading="lazy" style="display:block;box-sizing:border-box;width:100%;height:720px;border:1px solid #dadce0;border-radius:8px;overflow:hidden;"></iframe>
  <script>
  (() => {
    const frame = document.getElementById('<DIAGRAM_ID>');
    const origin = new URL(frame.src, document.baseURI).origin;
    window.addEventListener('message', event => {
      if (event.source !== frame.contentWindow || event.origin !== origin || event.data?.type !== '<DIAGRAM_ID>-height') return;
      const height = Number(event.data.height);
      if (Number.isFinite(height) && height > 0) frame.style.height = `${Math.min(2400, Math.ceil(height) + 2)}px`;
    });
  })();
  </script>

  [独立打开架构图](../../diagrams/<name>.html)
  ```
