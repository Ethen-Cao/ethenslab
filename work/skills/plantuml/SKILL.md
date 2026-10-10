---
name: plantuml
description: 按 ethenslab 统一样式编写 PlantUML 图：架构 / 组件图、流程（活动）图和时序图（sequence diagram），深色画布、Google 蓝绿实色块、方角细边框。适用于文章内的 plantuml 代码块和独立 .puml 文件；需要多域分层、交互聚焦或精细排版的软件架构图改用 architecture-diagram skill。
---

# PlantUML 图

规范来源是 `content/others/PlantUML 元素规范.md`，本 skill 是它的执行版。修改配色、字体或模板时，两处同步更新。

## 选图

| 图种 | 回答的问题 | 模板 |
| --- | --- | --- |
| 架构 / 组件图 | 系统由什么组成，边界在哪里 | [architecture.puml](assets/architecture.puml) |
| 流程（活动）图 | 满足某个条件后，下一步做什么 | [flow.puml](assets/flow.puml) |
| 时序图 | 谁在什么时候向谁发送什么 | [sequence.puml](assets/sequence.puml) |

- 一张图只回答一个问题：不用时序图表达静态分层，不用架构图表达调用先后。复杂细节拆成局部图。
- 跨多个 VM / 芯片、需要交互聚焦或精细排版的架构图用 architecture-diagram skill（独立 HTML）；文章内的简单结构图、流程图和时序图用本 skill。

## 使用模板

- 复制对应模板，保留从 `!theme plain` 到元素定义之前的整段样式区，只改标题、元素、条件和消息。不在后面追加其他 `!theme`，也不使用远程 `!include`。
- 别名用稳定的英文（如 `API`、`Worker`），显示名写在引号里；节点先写名称，再用 `\n` 换行写一行职责。
- 字号沿用模板：正文和标签 14，标题 18。图放不下时先减少内容，再调整方向与间距，不缩小字号。
- 文件存为 UTF-8。

## 配色

默认使用职责配色：

| 用途 | 颜色 |
| --- | --- |
| 画布 | `#282A2D` |
| 执行域、逻辑分组、流程分区、时序 `box` | `#202124` |
| 时序分组标题栏、激活条、判断、注释、外部参与者 | `#3C4043` |
| 本图范围内的组件、处理步骤 | `#34A853` |
| 数据、队列、请求、结果、同步对象 | `#4285F4` |
| 蓝 / 绿块内文字 | `#FFFFFF` |
| 常规文字 | `#E8EAED` |
| 边框、生命线 | `#5F6368` |
| 连线、箭头、流程起止符号 | `#BDC1C6` |

图中没有数据对象时，不必为凑齐配色加入蓝色块。

需要表达代码归属时，整张图改用归属配色（与 architecture-diagram 一致）：

| 归属 | 填充 | 文字 |
| --- | --- | --- |
| OEM 自研 | `#4285F4` | `#FFFFFF` |
| 系统原生 | `#34A853` | `#FFFFFF` |
| Vendor / Tier1 | `#FBBC04` | `#202124` |
| 硬件 / 内存 | `#5F6368` | `#FFFFFF` |
| 来源未确定 | `#3C4043` | `#E8EAED` |

- 一张图只用一套颜色含义。归属视图中蓝色只表示 OEM：数据和请求写在连线标签上，确需画出的 Buffer / 内存用硬件灰。
- 在样式区末尾加入下面的 stereotype 配色，给每个元素标注归属，并用 `legend` 说明颜色：

  ```plantuml
  skinparam rectangle<<oem>> {
      BackgroundColor #4285F4
      FontColor #FFFFFF
  }
  skinparam rectangle<<native>> {
      BackgroundColor #34A853
      FontColor #FFFFFF
  }
  skinparam rectangle<<vendor>> {
      BackgroundColor #FBBC04
      FontColor #202124
  }
  skinparam rectangle<<hw>> {
      BackgroundColor #5F6368
      FontColor #FFFFFF
  }
  skinparam rectangle<<unknown>> {
      BackgroundColor #3C4043
      FontColor #E8EAED
  }
  hide stereotype

  rectangle "AVM App\n显示与交互" as App <<oem>>
  ```

## 元素

| 元素 | 用法 |
| --- | --- |
| `rectangle` | 职责块或逻辑层，模板中默认绿色 |
| `package` | 逻辑分组、子系统或进程边界（深灰底、方角）；标签写明是逻辑域还是实际进程 |
| `component` | 强调接口或依赖的软件组件，外观与 `rectangle` 一致 |
| `node` | 主机、VM、设备等运行环境；只在部署关系重要时使用 |
| `frame` | 整张图的讨论范围，可选；不与多层容器重复表达同一边界 |
| `database`、`queue` | 明确的存储或队列；简化视图可用矩形，名称写明用途 |

- `package` 不等于独立进程，`component` 不等于独立线程；部署和线程边界由标签说明。
- 结构层次控制在两至三层，通过容器、留白和背景区分。
- 判断菱形、起止圆点、生命线和激活条保留原有形状，方角规则只用于普通模块和容器。

## 连线

| 图种 | 记法 | 含义 |
| --- | --- | --- |
| 架构 | `A --> B : 写入数据` | 有方向的关系，具体含义由标签动词说明（调用、读取、写入、依赖） |
| 架构 | `A ..> B : 依赖配置` | 静态依赖，不表示异步 |
| 流程 | 活动间箭头 | 控制流；判断的每个出口都标明条件或“是／否” |
| 时序 | `A -> B : 调用` | 同步调用 |
| 时序 | `A ->> B : 投递任务` | 异步消息或通知 |
| 时序 | `B --> A : 返回结果` | 只表示返回或响应；回应的是同步调用还是异步请求，由之前的消息决定 |

- 虚线不等于异步。PlantUML 只负责画线，是否阻塞由作者按真实交互选择记法。
- `-[hidden]->` 只用于排版，不表示依赖，加入后检查是否造成可见连线交叉。`linetype ortho` 会改变标签位置，需重新检查。

## 各图种要点

### 架构 / 组件图

- 分层图用命名矩形表示 App、Framework、Native/HAL、Kernel 等层，用容器说明 GVM / PVM 等范围；只在需要解释某层内部职责时才展开组件。
- 默认 `top to bottom direction`；横向关系较多时改用 `left to right direction`。

### 流程图

- 判断写成可回答的问题，两个出口都标注；错误出口用 `stop` 结束，不再流入后续分区。
- 循环显式更新计数，退出条件同时覆盖成功和次数上限；写明哪些失败允许重试，不可重试的错误直接进入失败出口。
- 活动节点用动宾短语，不放大段代码。输入、输出类活动可用数据蓝 `#4285F4`。
- `partition` 表示处理阶段；强调不同角色之间的交接时改用泳道。

### 时序图

- 参与者按主要交互顺序从左到右排列，每个参与者含义稳定（进程、线程或服务对象）。本图范围内的参与者用绿色，并用 `box` 圈出范围；范围外的调用方和外部服务用灰色。
- `activate` / `deactivate` 表示执行或调用范围，不表示一直占用 CPU，也不表示 GPU 等异步单元已经完成。
- `opt` 表示可选步骤，`alt` 的分支互斥；缓存命中即可返回时，用“命中／未命中”的 `alt`。
- 自动编号便于引用，不代表所有分支都会执行；纵向间距不表示耗时，需要时显式标注时间。

## 亮色版本

默认交付深色。需要白底打印时整套替换下列颜色，蓝 / 绿块及其白字不变：

| 用途 | 深色 | 亮色 |
| --- | --- | --- |
| 画布 | `#282A2D` | `#FFFFFF` |
| 分组背景 | `#202124` | `#F1F3F4` |
| 分组标题、注释、判断 | `#3C4043` | `#E8EAED` |
| 常规文字 | `#E8EAED` | `#202124` |
| 边框、生命线 | `#5F6368` | `#BDC1C6` |
| 箭头 | `#BDC1C6` | `#5F6368` |

同时修改节点和 `box` 上的显式颜色、外部参与者的文字颜色，以及 `<style>` 中 `root`、`arrow` 的 `LineColor` 与 `FontColor`。只改 `backgroundColor` 会留下浅色文字和边框。

## 渲染与验收

- 在仓库根目录本地渲染；需要位图时把 `-tsvg` 换成 `-tpng`。组件图依赖 Graphviz（`dot`）：

  ```bash
  java -Djava.awt.headless=true -Xmx256m \
    -jar assets/plantuml-1.2025.4.jar \
    -charset UTF-8 -failfast2 -tsvg diagram.puml
  ```

- 发布到 ethenslab 时，文章里直接写 `plantuml` 代码块。站点在浏览器端把源码编码后交给 `www.plantuml.com` 公共服务器渲染成 SVG（见 `layouts/partials/extend_footer.html`），线上的 PlantUML 版本和字体可能与本地 jar 不同，发布前用 `hugo server -D` 预览确认。源码会随请求发到该服务器，不写入非公开信息。
- 图片在正文中按宽度缩放，宽图要确认缩放后文字仍可读。
- “预览 + 折叠源码”结构只用于规范文章本身；普通文章只放 `plantuml` 代码块。
- 交付前检查：
  - 图种与问题一致，标题说明范围。
  - 只用一套颜色含义，图例或 note 与之一致；外部参与者不会被误读为内部组件。
  - 分支和循环有明确出口；同步、异步和返回的记法没有混用。
  - 中文、长名称和箭头标签没有遮挡。
  - 本地编译无报错，并实际看过渲染图。交付说明写明渲染方式、检查结果和未确认的内容。
