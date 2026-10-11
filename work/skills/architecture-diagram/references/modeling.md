# Classification and technical modeling

本文件规定技术建模，不规定固定坐标。`MUST` 为验收约束；`SHOULD` 为可按内容调整的建议；示例不是必须出现的层或组件清单。

## 1. Classify before drawing

先确定以下独立维度。已能从用户需求判断时直接记录，不为填表反复询问。

| 维度 | 选项与作用 |
| --- | --- |
| 粒度 | `system`：系统边界、真实子系统、核心能力与主要依赖；`subsystem`：实现该功能的进程、库、类、内核接口、硬件与资源 |
| 表达重点 | 分层、部署、调用依赖可以组合；`dataflow` 为数据路径补充视图，不能替代用户要求的分层主图 |
| 图的用途 | `technical`（默认）：技术实现；`origin`：技术实现及组件来源；`responsibility`：明确的一种项目责任 |
| 部署范围 | 实际参与的 OS / VM / SoC / MCU；出现对应对象时才启用其条件规则 |

`MUST`：技术依赖决定层次，运行边界决定容器，用途决定节点配色。不得从开发方、文件后缀或模板位置反推层级。图中所有文字均用英文，真实标识符保留大小写和拼写；图外说明可用中文。

## 2. Entity identity and abstraction

- **System / MUST**：允许准确、边界明确的子系统或能力名称，例如 `Graphics Subsystem`。展开其实现时放入明确的容器，不把整个子系统与内部某个类无说明地当成同粒度的同级实体。
- **Subsystem / MUST**：用户态 Block 使用已确认的实际进程、SO 文件名、核心类或实际接口名；职责只作为简短副标题，不以 `Composition Policy`、`Driver Interface` 等职责描述伪造组件。
- **All / MUST**：来源只写 `Application` 并不建立真实可执行文件或进程身份。系统总览可将其表达为逻辑分组，不标成已知进程；子模块请求若缺少主链所需进程身份或传输机制，先询问，或与用户确认缩小展开范围，不把泛称转换成看似具体的进程名。
- **All / MUST**：主名称与职责分开存储。内核对外文件接口由已确认的文件路径和模块名组成，显示为 `/dev/hgsl · qcom_hgsl`。无设备文件的接口不能补造路径。协议名一般放在线上；仅当确有独立协议实现组件时才画该实体。
- **All / MUST**：名称或机制未确认时停留在已确认的父组件，不新增功能描述型占位节点，不猜 `.so` 后缀。缺失信息影响主链正确性时先询问；其他不影响主链的省略在图外交付说明中列出。
- **All / MUST**：每个实体和关系有可追溯的依据；使用文档路径、源码位置或官方资料，不能把另一张图的坐标或名称当技术证据。证据保存在模型，不在主图堆叠基线免责声明。
- **Editing / MUST**：保留已经确认的名称、归属和接口；若证据要求变化，说明原因，不因重新生成而恢复旧命名。

## 3. Layers, processes and dependencies

### Shared rules

- **Layered view / MUST**：单个 OS / VM 内，大层次按主要能力依赖自上而下排列。只画实际存在且与主题有关的层，不为套模板增加空 HAL、Kernel 或 Hypervisor。
- **Within a layer / MUST**：同层组件可横向或纵向布局；A 服务依赖 B 服务不自动产生新的全局层。同层依赖是否串行由技术关系决定，不由坐标决定。
- **All / MUST**：层表达技术角色；进程表达运行归属。客户端库仍在应用进程，服务端库仍在服务进程；一个 `.so` 不是一个独立服务，也不是一种软件层。
- **All / MUST**：进程内的多个服务类不自动成为多个进程；父容器关系不自动代表调用。逻辑分层图没有展开进程时，不宣称层带就是运行边界。
- **Subsystem / MUST**：用户态库、类和接口归属其真实进程。真实的内核、Hypervisor 或固件内部实现通过有依据的 `executionContext` 明确执行环境，不强塞进虚构用户态进程；不能用该字段绕过尚未查清的用户态归属。
- **All / MUST**：依赖、调用、IPC、数据读写、通知、配置分别建模。上行回调和硬件输入数据可以向上走，不为统一箭头方向改变层次。
- **All / MUST**：IPC 的机制必须是有依据的传输或协议；`Client connection`、`Local IPC` 仅重述关系类别，不构成机制。来源只建立依赖时使用 dependency，不编造 IPC；主链必须解释通信而机制尚不明确时，先询问或确认较窄的图范围。

### Android example

以 [Android Platform architecture](https://developer.android.com/guide/platform) 的架构图为宏观分层参考，不复制其配色：`System Apps` / `Java API Framework` / 并列的 `Native C/C++ Libraries` 与 `Android Runtime` / `Hardware Abstraction Layer` / `Linux Kernel`。根据主题展开关键组件，不要求每条依赖经过所有层。

- `Java API Framework` 内并列展示 `Core Android APIs` 与 `Car APIs`，不使用含义混杂的 `Car Framework` Block 同时代表 API 和服务实现。
- 需要解释实现时添加 `System Services` 展开区域，区分 `system_server` 与 `com.android.car` 的进程边界，后者承载 `CarService`；这是本图的实现展开，不声称官方平台图原有独立的 System Services 层。
- API 侧 Manager 与服务端实现通过实际 Binder 接口通信；不能把两者放进同一个进程。参考 [Car Framework Core](https://source.android.com/docs/automotive/car-framework-core) 的 API / Service 关系。
- Native 与 HAL 分别展示，不合并成含糊层；C/C++ 实现的系统服务不因此全部归入 Native Libraries。ART 是运行时，不是所有服务调用的必经串行节点。

### Embedded Linux example

建议骨架：`Applications` → `Frameworks & Client APIs` → `Services` → `Platform Adaptation` → `Linux Kernel` → `Hardware`。这是一种绘图骨架，不是统一行业标准。

服务可按主题区分领域服务与基础系统服务，不能按 OEM / Vendor / upstream 来源分层。客户端 API、服务内部实现、HAL 都可能是 `.so`。`systemd` 管理进程生命周期，不代表被管理服务的业务请求都经过它。无真实平台适配组件时省略该层，不发明一个 PAL。

### QNX example

建议区分应用、客户端接口、服务 / Resource Managers / 用户态驱动，以及 `procnto` 提供的系统能力。大量 QNX 服务和驱动位于用户态，不能全部塞入 Kernel。展开 `procnto` 时区分微内核与进程管理职能，不能把包含用户态管理部分的整个进程等同于纯内核。参考 [QNX System processes](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.sys_arch/topic/intro_System_processes.html)。

## 4. Conditional topology rules

### Multiple VMs / Hypervisor

- **MUST**：公共 Hypervisor 只画一次，在实际承载的并列 VM 下方形成层带，覆盖这些 VM 及其中间空隙；不承载的 MCU / OS 不纳入其范围。
- **MUST**：承载关系不是逐次数据处理路径。穿过层带空白位置不意味着调用 Hypervisor；真实调用、资源授权与配置单独表示。
- **MUST**：跨域边落在实际发送 / 接收端，保留解释主链所需的传输前后端、驱动与机制。可以连接不同执行层的真实端点，不强制两端都是用户态或同一执行层。
- **SHOULD**：系统总览允许抽象一段通道；子模块实现图不得用抽象直线掩盖关键边界或造成 Guest 直接访问受限硬件的错觉。

### Memory and physical I/O

- **MUST**：同一共享存储对象只画一个资源实体；如必须呈现各进程映射，使用明确的 mapping / view 表达，并关联唯一的底层资源，不能画成几份独立物理 Buffer。
- **MUST**：数据线只连接真实读写者与资源；fd、handle、index 的传递是控制 / 通知，不是像素传输。DMA / 共享内存读写与 doorbell / IRQ 分开。
- **MUST**：按生产、处理、存储、消费关系定位内存，不强制放入硬件区，也不强制高于所有硬件。输入可按物理源 → 采集硬件 → Buffer → 软件；输出可按软件 → Buffer → 输出硬件 → 物理终端组织。
- **MUST**：内存不是物理链中的串行处理器；硬件、固件、寄存器、存储资源分别命名。固件标明 firmware，不以硬件类别掩盖其实现身份。

## 5. Diagram purpose and color

配色方案只能选一种用途，单张图不混用含义；颜色取值见 [layout.md](layout.md)。

| 模式 | MUST |
| --- | --- |
| `technical` | 使用中性或统一色系节点，位置与容器表达层次；无需猜测来源或组织责任。硬件 / 内存形状可区分实体类别 |
| `origin` | 按已确认代码 / 组件来源区分 `native`、`vendor`、`oem`；未知保持中性。不能根据所在层默认 Kernel / HAL 都是 Vendor |
| `responsibility` | 先明确展示开发、交付、集成或维护中的哪一种责任，再按已确认责任方配色。多个责任维度应拆图或配图外责任表，不让一种填色承担全部含义 |

原生组件可以由 Tier1 集成、由 OEM 验收：来源与责任分别记录。所有模式中域、层、进程容器保持中性，连线语义保持一致。
