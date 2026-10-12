# Classification and technical modeling

本文件规定技术建模，不规定固定坐标。`MUST` 为验收约束；`SHOULD` 为可按内容调整的建议；示例不是必须出现的层或组件清单。

## 1. Classify before drawing

先确定以下独立维度。已能从用户需求判断时直接记录，不为填表反复询问。

| 维度 | 选项与作用 |
| --- | --- |
| 粒度 | `system`：系统边界、真实子系统、核心能力与主要依赖；`subsystem`：实现该功能的进程、库、类、内核接口、硬件与资源 |
| 表达重点 | 分层、部署、调用依赖可以组合；`dataflow` 为数据路径补充视图，不能替代用户要求的分层主图 |
| 图的用途 | `technical`（默认）：技术实现；`origin`：技术实现及组件来源；`responsibility`：明确的一种项目责任 |
| 部署骨架 | `single-domain`：单个执行域或域内子模块；`multi-domain`：多个独立域；`virtualized-soc`：同一 SoC 上承载 VM，启用 SoC / VM / Hypervisor / Hardware 关系规则 |

`MUST`：技术依赖决定层次，运行边界决定容器，用途决定节点配色。不得从开发方、文件后缀或模板位置反推层级。图中所有文字均用英文，真实标识符保留大小写和拼写；图外说明可用中文。

### Deployment gate

先确定资料描述的是哪一个目标系统，列出参与域及承载关系，再选择骨架。当前材料未提及某层，不表示该层不存在；可以使用同一目标系统已由用户或证据确认的上下文。不同平台、版本或参考模板不能混作部署证据，存在冲突时先澄清。

省略规则：不相关的 TEE、外设或软件层可以省略；已经参与主图的域必须保留其真实承载关系。跨 VM 的控制流仍然发生在 VM 上，不能把 VM 改标为普通 OS 或删除 Hypervisor 来满足检查。纯单进程子模块不强制添加 SoC / VM / Kernel；软件局部视图的缩小范围须明确，不得悄悄替代用户要求的系统主图。

单 VM 内实现切片可以保持真实 VM 身份而不重复完整 SoC：必须为 `subsystem`，使用 `single-domain` 并声明 `domain`、`excerpt: true` 与证据；只包含这一个执行域、无跨域端点，也不展开芯片硬件。它不能充当跨 VM 或涉及硬件承载关系的主图；不能仅靠改 `scope` 获得豁免。

### Component-role gate

在赋予坐标前逐项核对以下映射；映射可直接记录在模型，不在主图添加审查表或免责声明。

| 核对项 | 必须能回答的问题 |
| --- | --- |
| Identity | 这是实际进程、库、类、接口，还是系统级逻辑子系统？主名称依据是什么？ |
| Deployment | 它属于哪一个 OS / VM / 独立域？硬件和共享资源属于谁？ |
| Technical role | 它是应用、客户端 API、服务实现、HAL、内核能力或固件？不是“第几步执行”？ |
| Runtime ownership | 库/类实际在哪个进程或执行环境？逻辑层是否被误当成进程？ |
| Relationship | 是同进程调用、IPC、依赖、数据访问还是通知？箭头两端是否为真实端点？ |
| Evidence / omission | 每项判断有何依据？省略中间实现后，是否仍保留边界且没有暗示直接硬件访问？ |

关键映射缺失先补证据或询问，不能通过改 `scope`、`specimen`、`platform` 或 `executionContext` 绕过问题。

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

- **Layered view / MUST**：单个 OS / VM 内，大层次按技术角色及主要能力依赖自上而下排列。省略无关软件层，不增加虚构 HAL / PAL；部署骨架的承载关系按 Deployment gate 保留。
- **Layered view / MUST**：`Jobs`、`Download`、`Flash`、`Activation` 等是工作流阶段，不能仅凭调用顺序成为全局层。调用到客户端 API 的服务不会因此变成位于 Framework 之上的“新层”；同层依赖在层内布局。
- **Within a layer / MUST**：同层组件可横向或纵向布局；A 服务依赖 B 服务不自动产生新的全局层。同层依赖是否串行由技术关系决定，不由坐标决定。
- **All / MUST**：层名表达技术能力类别，Block 名表达该粒度下的实现实体，进程容器表达运行归属；不要把某个进程名称用作通用技术层名。一层只有一个实现组件完全合理，不为凑数量添加其他进程或重复层名作为组件。客户端库仍在应用进程，服务端库仍在服务进程；一个 `.so` 不是一个独立服务，也不是一种软件层。
- **All / MUST**：宏观层角色与类的局部职责分开。服务内部的消息客户端、私有封装类可以留在服务实现区，不能凭 `Client` / `Manager` 名称自动归入 Framework；真正的公共 Framework API 则保持 API 层身份。子模块展开时同时保留实际进程归属。
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
- Framework API 的技术角色不因调用者或执行时机改变：应用或服务调用某个 Java Framework API，仍把该 API 放在 Framework 区。回调、上行调用可以朝上，不改变大层次。
- 展开 Native 服务时，把它作为服务实现及真实进程，不当成普通共享库；不要求每条路径经过 ART、HAL。若没有该路径的 HAL，省略 HAL，而不是虚构一层。

### Embedded Linux example

建议骨架：`Applications` → `Frameworks & Client APIs` → `Services` → `Platform Adaptation` → `Linux Kernel` → `Hardware`。

服务可按主题区分领域服务与基础系统服务，不能按 OEM / Vendor / upstream 来源分层。客户端 API、服务内部实现、HAL 都可能是 `.so`。`systemd` 管理进程生命周期，不代表被管理服务的业务请求都经过它。无真实平台适配组件时省略该层，不发明一个 PAL。

### QNX example

按技术角色自上而下：`Applications` → `Client APIs & Libraries` → `Services / Resource Managers / User-space Drivers` → `Microkernel & Process Manager` → 相关硬件。平台适配组件若真实存在，可在其主要依赖位置展开；不发明统一 PAL。

- 工具、脚本通常属于应用/工具角色；服务进程按服务角色定位，不能因为被某工具调用就放入“任务阶段”层。具体分类以其实现职责为依据，文件后缀不决定层次。
- 用户态驱动与 Resource Manager 不归入 Kernel。`procnto` 同时包含 Microkernel 与 Process Manager，底部层不得标成纯驱动层或宣称它只有内核。
- `Microkernel & Process Manager` 是技术层名，内部使用实际模块名 `procnto`（具体目标若使用其他已确认变体，保留实际名字）。该层主要由这个模块实现；可在更细粒度展开其内部能力，但不把它们画成独立服务进程，也不把网络、文件系统或用户态驱动搬入本层。
- 客户端库和服务内部库按真实进程归属展开；库可以出现在不同技术角色的进程中，不用 `.so` 建立统一“中间件层”。

## 4. Conditional topology rules

### Multiple VMs / Hypervisor

- **MUST / virtualized-soc**：使用 `domainType: soc` 的共同父容器；参与 VM、Hypervisor、共同硬件区与参与的 TEE 是其子容器。SoC 是芯片部署边界，Hardware 是其底部资源区，两者不能互相替代。
- **MUST / virtualized-soc**：VM 在 SoC 内左右并列、顶部对齐，各自软件由上至下展开；主图保留 VM 身份，不把它们当成脱离 SoC 的独立 OS。
- **MUST**：公共 Hypervisor 只画一次，在实际承载的并列 VM 下方形成层带，覆盖这些 VM 及其中间空隙；不承载的 MCU / OS 不纳入其范围。
- **MUST / participating TEE**：TEE 在 SoC 内的 VM 左侧；顶部与 VM 对齐、底部与 Hypervisor 对齐，不作为 VM 内组件，也不纳入 Hypervisor 的 `hosts`。这是本 skill 的部署视图约定，不推断具体平台的安全世界实现；实际承载不同先据证据调整并说明。
- **MUST / shared hardware**：共同 Hardware 区在 VM / Hypervisor / TEE 下，左右覆盖参与的 TEE 与 VM。芯片内物理资源在其内；跨域共享内存仍按读写链布局，不能因此复制物理资源。
- **MUST / independent MCU**：MCU 是 SoC 外的并列独立域，域外框顶底与 SoC 对齐，内部自行分层。不得为对齐 RPC、SPI 等某个端点把整个 MCU 降到图的下半部；独立域可以在 SoC 左侧或右侧。
- **MUST**：承载关系不是逐次数据处理路径。穿过层带空白位置不意味着调用 Hypervisor；真实调用、资源授权与配置单独表示。
- **MUST**：跨域边落在实际发送 / 接收端，保留解释主链所需的传输前后端、驱动与机制。可以连接不同执行层的真实端点，不强制两端都是用户态或同一执行层。
- **SHOULD**：系统总览允许抽象一段通道；子模块实现图不得用抽象直线掩盖关键边界或造成 Guest 直接访问受限硬件的错觉。

使用 `assets/models/multi-domain-system.json` 作为有证据的骨架；`soc-vm-mcu-layout.json` 是完整相对布局小样，包含可选 TEE，但不证明目标平台实际具有它。

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
