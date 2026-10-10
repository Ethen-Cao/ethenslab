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
- 节点只画实体（进程、库/类、驱动、硬件、内存）。文档里的职责分组、要点列表和“XX 面”不画成节点，也不让连线穿过它们。
- 跨 VM / 跨域通信：Hypervisor 的公共承载层只画一次（见“布局”），HAB 等传输层按真实实体及各 VM 内的驱动建模；消息通道画成直接连接两端用户态组件的连线，按真实方向标注通道与消息；建立通道、映射共享页属于配置关系，需展开时用配置线表示，否则放在详情中。
- 同一块物理内存只画一个实体，放在硬件区，副标题写明分配方与导入方；不在各 VM 和 Hypervisor 里重复建节点。
- 像素/数据线只连接真正读写数据的组件和内存；只传 index、fd 或句柄的组件走控制或通知线。
- 成对的跨域操作（export / import、发送 / 接收）两侧在同一层级建模：都从用户态发起方画，或都从内核驱动画。同一职责只归一个节点，连线从该节点出发，不在另一个节点的副标题里重复声明。
- 画完后对照源文档逐条核对消息方向、发起方和接收方；每条跨域链路都应两端落在实体上。

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
- Hypervisor 共同承载多个并列 VM 时，画成它们下方的独立横向层带：左边界对齐最左 VM，右边界对齐最右 VM 的外边界，覆盖 VM 之间的间隔；不缩成某个 VM 下方的小组件，也不延伸到不受其承载的域。
  - 用中性容器表示层带，标题使用实际名称，如 `Gunyah Hypervisor`；需要展开的实现组件放在层带内部，按来源着色，不重复绘制同一 Hypervisor。
  - 层带表示共同承载，不是所有数据必经的处理节点。像素/数据线仍连接实际读写组件与内存，可经过层带空白区域但不得穿过标题或内部组件；不因穿越层带而添加箭头或连接点。Hypervisor 的实际调用与配置关系另行明确表达。
- 系统级 Android 可用 Applications → Framework/Runtime → Native/HAL → Kernel；Android 子模块按 Java → Native → HAL → Linux kernel 分层。其他 OS 按实际架构划分。
- 子模块的进程用独立容器，库/类放在所属进程内；同级依赖并列，不因布局方便伪造成串行调用。
- 同层对齐、统一间距，跨列/跨层路径预留走线通道；不同 OS 无需强凑同名层。
- 按数据交接关系布局硬件与内存：物理 I/O 链按真实连接顺序排列；Buffer／共享内存作为独立资源，优先布置在实际读写它的硬件单元与软件组件之间。通过位置和箭头明确谁写入、谁读取，使主数据流连续、少折返，不把内存当作物理链路中的串行处理节点。软件在上、物理接口在下时，内存通常位于两者之间；不强制内存固定在硬件上方。
  - 采集方向：物理输入 → 采集硬件 → 内存 → 软件处理。
  - 输出方向：软件生成 → 内存 → 输出硬件 → 物理输出。
- 涉及显示硬件时，将处理单元、共享图像内存和显示接口组织在硬件区域，物理输出链放在下一行；内存用堆叠矩形。
- 容器标题占顶部：domain 50、process 40、layer 48（含分隔线），子容器和节点放在其下，memory 节点另留 8；越界时模板直接报错。连线不穿过容器标题，也不贴着容器边框走（间距至少 6）。
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
纵向主链默认接上下边中心，横向主链默认接左右边中心。
节点某条边只接一条连线（或多条连线共用同一点）时，必须接在该边中心，检查脚本对偏移报错。需要直线时移动或调宽节点使中心对齐，或加折点，不用偏移凑直线。用户明确指定的偏移锚点保留，在该连线上设 `keepAnchor: true`，并在交付说明里写明。
多路输入时主链保留中心入口，其他线路分配独立入口；不堆叠箭头，不合并不同机制。入口按来向排列，左侧来的线接左侧，避免两条线在目标前交换左右；同一对连线最多交叉一次。
连线留在两端共同所在的最小容器内，不绕出再绕回。被整宽的进程或层挡住时调整布局（把进程并排、换层或留走线通道），不借域间空隙绕行；域间空隙不堆多条平行长线。一条线拐 5 次以上，先改布局。
不可避免的非连接交叉使用跨线弧，真实分支使用实心点；先优化布局，再处理交叉。
跨线弧由模板的 `routeCrossingBridges()` 自动生成，只支持单段绝对坐标正交 `M/H/V/L` 路径（其他写法模板直接报错）。交点距线段端点或拐点不足 9、同一线段上相邻交点间距小于 16、或弧线会碰到附近线路时不加弧，需调整走线。
扇出分支在 `junctions` 中列出共享前缀的连线，实心点自动落在分叉处，不手写坐标。
标签只写必要的接口、协议或数据名称，不遮挡连线。
端点用 `fromSide`/`toSide` 与 `fromOffset`/`toOffset` 由节点边界计算，折点用 `via`；移动节点后连线、跨线弧和分支点自动重算，手写 `lx`/`ly` 的标签需复核。

## 修改与验收

- 修改现有图时保留已确认的命名、层次和锚点，只调整相关节点与路径，避免无关重排。
- 用 [check-diagram.js](scripts/check-diagram.js) 做几何检查：`errors` 必须为空，`warnings` 逐条修正或确认合理。它检查重复 ID、未知端点、节点/容器归属、节点压住容器标题、连线穿过标题或节点、贴边框走线、箭头贴边与方向、单线锚点居中、绕出容器、重复交叉、同节点连线互相交叉、走线过繁、节点重叠、文字溢出、主标题缩字、箭头堆叠、交叉缺弧、连线重合和标签遮挡：

  ```js
  await page.goto('file:///<path>/diagram.html?theme=dark');
  await page.addScriptTag({path: '<skill>/scripts/check-diagram.js'});
  const report = await page.evaluate(() => checkDiagram());
  ```

- 在浏览器截图检查全图、关键局部及亮暗主题（URL 加 `?theme=dark` 可直接切换）；核对箭头、标签、跨线弧和交互。只跑检查脚本不算预览；未能截图时明确说明。
- 再核对技术关系；几何通过不等于架构正确。
- 交付说明必须包含：检查脚本的 errors / warnings 数量，每条 warning 的处理（已修正，或保留及理由）；截图检查看了哪些视图、发现了什么；与源文档不一致、未确认或被省略的内容。不要只写“验证通过”。
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
