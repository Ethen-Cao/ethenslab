+++
date = '2025-08-27T11:36:11+08:00'
lastmod = '2026-10-09'
draft = false
title = '智能座舱 DRM 视频播放方案建议书'
description = '基于 Android、QNX 与 TEE 的座舱 DRM 播放方案，覆盖客户端、许可证、密钥、显示保护及量产验收。'
aliases = ['/android-dev/media/widevine-l1-verification-process/']
+++

本方案面向 QNX Host、Android Guest 的智能座舱，采用 Widevine 作为首期 DRM 方案。交付目标是：指定内容服务通过指定客户端，在允许的屏幕和车辆状态下，按授权画质播放。

Widevine L1 是底层安全能力。内容服务支持、客户端准入、画质和输出保护要求，需要分别确认。本文状态为方案提案；源码中存在组件，不代表整机已完成集成或通过服务商验收。

## 1. 产品范围

### 1.1 需要冻结的需求

| 维度 | 产品需要确定的内容 |
| :--- | :--- |
| 内容服务 | 服务商、目标国家与地区、车型及年款、账户与订阅要求 |
| 播放客户端 | 自研浏览器、第三方浏览器、服务商官方 App，是否另行开发播放器 |
| 视频与音频 | 分辨率、帧率、Codec、HDR、音轨、声道、字幕 |
| 屏幕 | 中控、副驾、后排；每块屏幕是否允许播放、复制、迁移和独立播放 |
| 车辆状态 | 驻车、行驶、倒车、车辆状态未知时的启动、暂停、隐藏及恢复行为 |
| 并发与离线 | 同时播放数量、下载资格、许可有效期、存储额度、用户隔离 |
| 中断与恢复 | 电话、语音、导航、告警、熄火、休眠、异常断电后的行为 |
| 输出限制 | 截图、录屏、投屏、外接屏、远程显示、PiP 和后台播放 |
| 体验指标 | 首帧时间、卡顿率、音画同步、恢复时间、功耗与热限制；数值待产品冻结 |

前排与后排分别定义车辆状态策略，不采用全车统一开关。状态不可用时的行为也应纳入需求。

### 1.2 服务支持矩阵

每个商用组合单独记录，不用“支持 Netflix”代替具体条件。

| 内容服务 | 客户端 | 市场／车型 | 屏幕与车辆状态 | 画质／音频 | HDCP 要求 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Netflix | 官方 App | 待确认 | 待确认 | 待确认 | 待确认 | 待服务商确认 |
| Netflix | 自研／第三方浏览器，分别评估 | 待确认 | 待确认 | 待确认 | 待确认 | 待服务商确认 |
| 其他 OTT 服务 | 按服务及客户端分别建项 | 待确认 | 待确认 | 待确认 | 待确认 | 待服务商确认 |
| 自有或获授权的测试内容 | 原生参考播放器 | 工程样机 | 先验证一块目标屏幕 | 测试集定义 | 测试许可证定义 | 用于平台验证 |

Netflix 官方已支持部分车载系统，但支持范围因车型、年款和市场而异，不能据此认定本项目获得支持。[Netflix 车载支持说明](https://help.netflix.com/en/node/133243)

## 2. 客户端选择

| 方案 | 技术入口 | 主要工作 | 适用条件 |
| :--- | :--- | :--- | :--- |
| 服务商官方 App | 服务商自己的播放器与 DRM 集成 | 商用合作、安装与升级渠道、车载适配、整机验收 | 服务商明确支持目标车型、市场和版本 |
| 自研浏览器 | Web Player → EME → 浏览器媒体桥接 → Android DRM／Codec | 浏览器内核、DRM 配置协商、安全解码、站点兼容性和版本维护 | 站点允许该客户端，并确认可用画质 |
| 第三方浏览器 | 浏览器提供的 EME／CDM 实现 | 核验供应商交付范围、系统适配、更新和内容兼容性 | 浏览器能力与内容服务准入均有依据 |
| 自研原生播放器 | Media3／MediaDrm／MediaCodec | 业务鉴权、许可证请求、播放控制、车载体验 | 自有内容，或内容方提供合法集成接口 |

建议先用原生参考播放器和获授权测试内容验证平台，再接入目标客户端。平台验证通过与商用服务可用，分别验收。Media3 可作为原生验证入口。[Android Media3 DRM](https://developer.android.com/media/media3/exoplayer/drm)

浏览器要记录网页请求的 `robustness`、最终选中的配置和实际安全解码器。设备具备 L1，不保证每次网页会话都会使用 L1。具体内核行为按交付版本核对。

## 3. 系统总体架构

绿色表示 QNX／AOSP 平台模块，黄色表示设备侧 Widevine 组件及供应商闭源实现，灰色表示硬件，蓝色表示云服务。Player／Browser 的交付来源待选型，使用白色。

<iframe src="../../../diagrams/cockpit-drm-playback-architecture.html" title="Cockpit DRM Playback Architecture" loading="lazy" style="display:block;width:100%;height:850px;border:1px solid #dadce0;border-radius:8px;overflow:hidden;"></iframe>

[独立打开系统架构图](../../../diagrams/cockpit-drm-playback-architecture.html)

### 3.1 模块职责

| 区域 | 组件 | 来源／类别 | 职责 |
| :--- | :--- | :--- | :--- |
| Cloud | Content CDN | 外部服务 | 分发清单、DRM 初始化数据和加密媒体分片 |
| Cloud | Partner License Proxy | 内容平台服务 | 校验账户与订阅等业务权限，代理许可证请求并传递策略 |
| Cloud | Widevine License Service | DRM 后端服务 | 生成含受保护内容密钥及播放策略的许可证响应 |
| Cloud | Provisioning Service | 设备凭据服务 | 处理设备凭据配置请求，与播放许可证服务分开 |
| TEE | Credential & Key Services | 供应商安全实现 | 管理设备绑定凭据和密钥材料，限制普通系统访问 |
| TEE | Output Protection Policy | 安全侧职责抽象 | 关联许可证限制与可信输出状态，生成保护要求；具体安全侧实现待确认 |
| TEE | Widevine TA | Widevine／芯片方交付 | 执行密钥运算、受保护解密及安全策略 |
| QNX | OPS Listener / Display Bridge | 高通预编译组件 | 通过 QSEECom listener 接收保护命令，执行时钟请求、最低加密等级和 OEM 安全端口配置，返回处理结果 |
| QNX | OpenWFD OEM Secure Gate | QNX 平台扩展 | 接受 OEM secure 配置，在安全源绑定时检查端口属性并阻断不满足条件的绑定 |
| QNX | QNX Screen | QNX 平台 | 管理本地窗口和图形表面，向显示后端提供 Host 显示源 |
| QNX | Guest Display Backend | QNX／BSP 源码 | 接收 Android 显示请求和 Buffer 引用；核验导入后的 protected 属性 |
| QNX | OpenWFD Source / Pipeline | QNX 显示平台 | 关联显示源、Pipeline 与 Port，配置允许输出的显示源 |
| QNX | Display Driver | BSP 源码 | 配置显示控制器、扫描输出和相关显示资源 |
| Android | Player / Browser | 客户端选型待定 | 获取内容和授权，转发 DRM 消息；取得 sessionId 后关联 MediaCrypto 并配置 MediaCodec |
| Android | MediaDrm | AOSP | 管理 DRM 会话，取得许可证／配置请求，将网络响应交回插件 |
| Android | MediaCodec / MediaCrypto | AOSP | 关联 DRM 会话与解码器，提交加密 Sample 及元数据，管理解码输出 |
| Android | Widevine HAL / CDM | Google／Widevine 代码 | 本图采用本地 AIDL 构建定义的 `libwvaidl.so`，包含两个 Plugin、共享 CDM Core、通用加密接口及 OEMCrypto Adapter；图内箭头表示关键函数调用 |
| Android | Widevine DRM Plugin | Google／Widevine 代码 | 实现 DRM HAL 接口；会话及许可证操作交给 CDM Core，通用加密操作交给 WVGenericCryptoInterface |
| Android | Widevine Crypto Plugin | Google／Widevine 代码 | 实现 Crypto HAL 接口，将 Sample 解密请求及安全目标 Buffer Handle 交给 CDM Core |
| Android | Widevine CDM Core | Google／Widevine 代码 | 处理许可证协议、会话与密钥状态、策略检查，通过动态 OEMCrypto 适配调用安全实现；以 `libcdm.a` 链接进 HAL 实现库 |
| Android | WVGenericCryptoInterface | Google／Widevine 代码 | 处理 DRM Plugin 的通用 encrypt／decrypt／sign／verify 及 RSA 操作，调用 OEMCrypto API，绕过这些操作的 CDM Core 入口 |
| Android | OEMCrypto API / Adapter | Google／Widevine 代码 | 封装 OEMCrypto API，按会话分派至 L1／L3 实现；本图仅展开 L1 后端 |
| Android | L1 Platform Libraries | 高通闭源库 | 提供 liboemcrypto.so 的 L1 平台实现，以及安全应用加载和输出保护相关平台库；不表示每次解密依次调用所列全部库 |
| Android | SurfaceFlinger | AOSP | 管理图层和受保护表面，协调合成及显示提交 |
| Android | Hardware Composer | AOSP 接口／BSP 实现 | 识别受保护图层，配置硬件合成并向显示后端提交 Buffer 引用 |
| Hypervisor | Hypervisor | 平台隔离层 | 管理 VM 隔离、内存归属及设备分配／虚拟化 |
| Hardware | Protected Compressed Buffers | 受保护内存 | 保存解密后的压缩视频，限制普通系统读取 |
| Hardware | Secure Video Decoder | VPU | 读取受保护码流，解码并输出受保护像素帧 |
| Hardware | Protected Video Frames | 受保护内存 | 保存解码像素，普通侧通过受限 Buffer 引用参与显示控制 |
| Hardware | Display Processing Unit | DPU | 读取受保护帧，执行显示处理和扫描输出 |
| Display Output | Display Link | SerDes／面板链路 | 传输显示像素；逐段确认保护能力、启用状态和终止位置 |
| Display Output | Cockpit Display | 屏幕 | 显示获准输出的画面，按产品规则限制屏幕、车辆状态和并发 |

TEE 是 SoC 的安全执行环境。VPU、DPU 和受保护内存属于硬件能力，单独放在硬件区域。

图中的跨域线分别表示安全调用、显示控制及 Buffer 引用。受保护媒体数据在硬件允许的路径中流动，不能用一条普通 IPC 连线推导其安全性。

### 3.2 Widevine 代码与动态库

图中黄色的 Widevine HAL／CDM 是 Google/Widevine 的授权代码。当前源码的 AIDL 构建将两个 Plugin 和 CDM Core 链接为一个 `libwvaidl.so`；图内子块表示同一共享库中的逻辑职责，箭头表示关键调用关系。

| 来源 | 交付／构建产物 | 说明 |
| :--- | :--- | :--- |
| Google／Widevine | `libwvaidl.so` | 本地 AIDL 构建的 HAL／CDM 实现库，包含两个 Plugin、CDM Core 及相关支持代码 |
| Google／Widevine | `libwvhidl.so`、`libwvhidl@1.3.so` | 前者有 HIDL 共享库构建定义，后者有预编译文件与构建定义；与 AIDL 版本是不同方案，按目标镜像核对 |
| Google／Widevine | `libcdm.a` | CDM Core 静态库，链接进入 HAL 实现库；此配置不单独安装 `libcdm.so` |
| Google／Widevine | `android.hardware.drm-service.widevine` | 本地 AIDL 构建定义的服务可执行文件，链接依赖 `libwvaidl.so`；注册 `IDrmFactory/widevine`，由同一 Factory 创建 DRM／Crypto Plugin；不是 `.so` |
| 高通 | `liboemcrypto.so` | 提供 L1 OEMCrypto 的平台实现，CDM 动态加载并调用，衔接 TEE 中的安全实现 |
| 高通 | `libtrustedapploader.so`、`libops.so` | 安全应用加载及输出保护相关平台库；按 HQX／LA 交付版本核验实际依赖 |

`libwvdrmengine` 是本地源码目录名，不能直接据此认定镜像中存在同名 `libwvdrmengine.so`。上述 AIDL 关系来自源码构建配置，量产设备实际加载的库仍需结合镜像和进程映射确认。Widevine 官方也区分设备侧授权代码与芯片方提供的 L1 OEMCrypto 库。[Widevine 代码访问说明](https://developers.google.com/widevine/access)

### 3.3 关键调用关系

本图展示会话、许可证与媒体解密主路径，并补出 DRM Plugin 的通用加密分支。它不是所有 API、错误返回及回调的完整调用图。

| 操作 | 源码调用关系 |
| :--- | :--- |
| 会话与许可证 | DRM Plugin → 共享 WvContentDecryptionModule → CdmEngine／CdmSession → OEMCrypto API／Adapter；只有需要相应底层能力的操作继续调用 OEMCrypto |
| 媒体 Sample 解密 | Crypto Plugin → DecryptV16 → CdmEngine → CdmSession 的密钥／策略检查 → CryptoSession → ContentKeySession → OEMCrypto_DecryptCENC |
| 通用加密与 RSA | DRM Plugin → WVGenericCryptoInterface → OEMCrypto API／Adapter；该操作不经过上述 CDM Core 入口 |
| 后端选择 | OEMCrypto Adapter 按会话选择 L1／L3 函数表；图中 L1 selected 连线仅表示选中 L1 后端后的调用，未展开 L3 后端 |

两个 Plugin 通过 `getCDM()` 复用同一 `WvContentDecryptionModule` 入口对象，不代表共用同一个播放会话。参数、会话、密钥或策略检查失败时可以提前返回；不能把每次 API 调用都理解为进入 TEE。

### 3.4 当前证据与待确认边界

| 路径 | 可确认的内容 | 尚需验证 |
| :--- | :--- | :--- |
| CDM／通用加密接口 → OEMCrypto Adapter | 主链与通用分支均有源码调用依据，Adapter 按会话分派，L1 初始化动态加载平台 OEMCrypto | 实际会话的 L1／L3 选择、库与 TA 版本及运行状态 |
| Crypto HAL → Secure Buffer | 本地实现接受 `NATIVE_HANDLE` 安全目标缓冲区 | 整条解密、解码、合成路径是否持续保留保护属性 |
| Android → QNX Display Backend | QNX 显示 BE 源码包含 HAB Buffer 导入及 WFD 调用转发 | 实际 FE／BE 构建选型、端口映射和安全 Buffer 支持 |
| TEE → QNX OPS Listener | 预编译组件注册 QSEECom listener，接收保护命令并返回处理结果 | 安全侧策略来源、可信 HDCP 状态获取和异常恢复 |
| QNX OPS Listener → OpenWFD | 源码允许 OPS 更新 `WFD_DEVICE_OEM_SECURE` 及 `WFD_DEVICE_HDCP_MIN_ENC_LEVEL` | 逐屏配置、更新时序和实际保护效果 |
| OpenWFD Secure Source Gate | `wfdBindSourceToPipeline()` 检查安全源和端口安全属性 | 每块目标屏幕的实际运行结果 |

`bOEMSecure=false` 可以导致安全源被阻断，但这条日志本身不能证明 HDCP 握手失败。端口映射、状态转发和创建时序也需要核对。

`Protection commands / result` 表示安全侧下发命令、QNX 返回处理结果。执行成功不等于 HDCP 认证成功；当前可见 OPS 分派未包含逐屏 HDCP 状态查询。绿色媒体线表示目标受保护数据路径，物理显示链路是否加密仍需逐段验证。

## 4. 播放与授权流程

### 4.1 内容准备

内容方的密钥后端生成或取得 Content Key，并分配 KID。Packager 使用该密钥加密媒体 Sample，输出清单和媒体分片；许可证后端保留与 KID 对应的密钥和授权策略。

| 加密方案 | 算法含义 | 项目核验项 |
| :--- | :--- | :--- |
| `cenc` | AES-128 CTR | 客户端、容器、Codec 和目标平台的组合支持 |
| `cbcs` | AES-128 CBC Pattern Encryption | Android、播放器及安全解码路径的版本支持 |

IV、KID 和 PSSH 是播放所需元数据，不能代替 Content Key。媒体加密与 TLS 传输加密分别处理。[Shaka Packager 加密选项](https://shaka-project.github.io/shaka-packager/html/documentation.html)

### 4.2 设备凭据配置

1. 量产阶段按已选定的设备凭据方案建立设备信任根。
2. 运行时 DRM 操作若报告尚未配置，客户端取得 Provisioning Request。
3. 客户端通过 HTTPS 转发请求，将响应交回 DRM 实现，成功后重试原操作。

Provisioning 用于建立或更新设备凭据，不是向内容服务申请某部影片的播放权。Keybox、OEM Certificate 等方案按芯片交付与 Widevine 要求选定，不把 Android KeyMint RKP 自动等同于 Widevine Provisioning。

### 4.3 获取许可证

1. 客户端完成账户与订阅鉴权，获取清单及 DRM 初始化数据。
2. 通过 MediaDrm／EME 创建会话，取得不透明的 License Challenge。
3. 客户端将 Challenge 和必要的业务令牌提交给内容方的许可证入口。
4. License Proxy 校验业务权限，许可证服务生成与请求关联的响应。
5. 客户端将响应交给 CDM；CDM 与安全实现验证响应、加载密钥及使用策略。

许可证是包含受保护密钥材料、使用策略及认证数据的协议消息。Widevine 采用其二进制协议；客户端通过 API 处理不透明响应，不将许可证当作可自行解析、修改的配置文件。[Widevine 许可证服务](https://developers.google.com/widevine/drm/overview#issuing-widevine-licenses)

### 4.4 解密、解码与显示

1. MediaCrypto 关联 DRM 会话，MediaCodec 配置满足许可证要求的解码器。
2. 客户端提交加密 Sample 及 KID、IV 等解密元数据。
3. Crypto HAL／CDM 调用 OEMCrypto；安全实现执行解密，使用受保护缓冲区。
4. 安全解码硬件输出受保护像素，显示服务处理 Buffer 引用和图层控制。
5. 输出策略允许时，显示硬件向目标屏幕输出；条件不满足时阻断受保护内容。

解码硬件不等于 TEE CPU，解密完成也不等于输出保护完成。原生 API 的会话与数据提交流程以 [MediaDrm](https://developer.android.com/reference/android/media/MediaDrm) 和 [MediaCodec](https://developer.android.com/reference/android/media/MediaCodec) 为准。

续期、密钥轮换、离线恢复和会话关闭分别测试。保护不足时能否降画质、切换到 L3 或保留音频，由内容方策略决定。

## 5. 密钥、证书与许可证

### 5.1 对象与保管责任

| 对象 | 用途 | 生成／交付方 | 保存与使用边界 |
| :--- | :--- | :--- | :--- |
| Content Key | 加密、解密媒体 Sample | 内容方密钥后端／许可证服务 | 服务端受控密钥系统；L1 端侧由安全实现管理，App 不取得明文密钥 |
| Keybox Device Key | Keybox 方案中的设备根凭据之一，参与认证与密钥派生 | Widevine 设备凭据流程；项目交付方待确认 | 设备绑定的受保护存储；安全实现使用，不作为普通应用文件读取 |
| 设备证书与对应私钥 | 证明设备身份，按选定协议签名或恢复会话材料 | 凭据流程与 OEMCrypto 实现 | 私钥受保护；证书按协议提供给验证方 |
| Session Key | 在采用该机制的许可证流程中建立会话保护材料 | RSA 路径由许可证端生成并封装；ECC 路径按协议派生 | 安全实现恢复或派生，按会话使用 |
| 派生加密／MAC Key | 解包内容密钥、验证消息及生成认证数据 | OEMCrypto 根据协议上下文派生 | 安全会话内使用；生命周期由协议管理 |
| Service Privacy Certificate | 隐私模式下保护请求中的设备身份信息 | DRM 服务方 | 客户端可持有公开证书；对应私钥保留在服务端 |
| HDCP 凭据／会话密钥 | 验证显示链路参与方并加密链路 | 设备凭据由合规器件流程部署；会话材料由握手建立 | SoC、桥接器和接收端各自的保护实现 |
| PGP 组织密钥 | 保护 Keybox 等交付资料 | 接收组织生成密钥对，并向 Widevine 提供公钥 | 组织侧受控保存私钥；不用于视频 Sample 解密 |
| TLS 凭据／会话密钥 | 保护设备与服务之间的网络通信 | 服务部署及 TLS 握手 | 各连接端点；不替代 DRM 内容密钥 |

**Device Key、设备 RSA 私钥、Session Key 和 Content Key 是不同对象。** Keybox 是设备凭据容器，TA 是安全程序，许可证是播放授权消息，KID 是密钥标识。

本地 OEMCrypto 接口定义了不同凭据路径：Keybox Device Key 可作为派生根；RSA 凭据路径可先恢复被封装的 Session Key，再派生内容密钥解包与 MAC 所需密钥。具体采用哪条路径，以设备配置和会话行为为准，不能将二者拼成所有设备必经的流程。

### 5.2 生命周期

| 阶段 | 处理要求 | 责任方 |
| :--- | :--- | :--- |
| 内容发布 | 建立 KID 与 Content Key 对应关系，定义轨道、清晰度及轮换策略 | 内容平台 |
| 设备生产 | 选择凭据模式，完成设备绑定、唯一性检查和测试／量产隔离 | Tier1、芯片方、工厂及凭据提供方 |
| 首次使用 | 完成必要的 Provisioning，验证联网失败和重试行为 | 平台、客户端 |
| 播放会话 | 按许可证加载密钥、执行期限与输出限制；关闭会话时释放资源 | CDM／OEMCrypto、客户端 |
| 离线播放 | 保存受保护许可状态，校验期限、用户与设备绑定 | DRM 实现、客户端、内容方 |
| OTA／维修 | 验证安全版本、凭据可用性和离线许可；换板按新设备处理 | Tier1、芯片方、售后 |
| 撤销／泄露 | 区分账户、设备、证书和密钥事件，执行各自的撤销及恢复流程 | 对应服务与凭据责任方 |

Keybox 交付文件使用组织 PGP 公钥加密。文件如何安全导入设备，由项目产线方案确定。[Widevine PGP/GPG](https://developers.google.com/widevine/pgp)

## 6. 显示链路与保护要求

### 6.1 逐屏核对

| 输出 | 实际链路与器件 | 内容方认可的边界 | HDCP 最低版本 | 已启用／已认证 | 验证结果 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 中控 | 待硬件图与 BOM 确认 | 待确认 | 待内容方确认 | 待确认 | 未验证 |
| 副驾 | 待硬件图与 BOM 确认 | 待确认 | 待内容方确认 | 待确认 | 未验证 |
| 后排 | 按每条链路分别填写 | 待确认 | 待内容方确认 | 待确认 | 未验证 |
| 用户可接入的外部显示 | 接口、转接器、接收端待确认 | 待确认 | 按适用规则及内容策略确认 | 待确认 | 未验证 |

HDCP 保护源端到接收端之间的链路。器件标称支持、系统实际启用、接收端认证成功，是三个不同状态。桥接器若终止保护，需要确认后续链路是否仍处于认可的保护范围。

Android CDD 对安全显示的要求明确涉及用户可访问有线端口的外接显示。内容方可提出进一步限制，不能用 CDD 的最低要求代替商用服务要求。[Android 16 Secure Media](https://source.android.com/docs/compatibility/16/android-16-cdd#58_secure_media)

### 6.2 固定内屏与物理边界

手机内屏常用 MIPI DSI，eDP 也用于内置显示。固定连接可在满足规则的设计中纳入整机可信边界，但接口名称本身不是安全证明。DSI 支持可选内容保护功能，实际是否启用需要核对。[MIPI DSI](https://www.mipi.org/specifications/dsi)、[MIPI DCS](https://www.mipi.org/specifications/display-command-set)

受保护内存、防截图和防录屏限制的是软件访问。如果某段物理链路传输未加密且可解析的像素，成功截取后原则上可能重建画面；这不等于取得 Content Key。DSC 是显示压缩，不是加密。

车载 GMSL／FPD-Link 链路按具体串行器、解串器、面板和配置检查。把屏幕标为内置屏、把端口标为 secure，均不能单独证明完整物理链路满足要求。物理攻击防护范围按适用 DRM 鲁棒性要求和内容方条件评估。

## 7. 合作方与职责

| 合作方 | 主要职责 | 交付依据 |
| :--- | :--- | :--- |
| OEM 产品／FO | 冻结服务、客户端、市场、屏幕、画质和车辆状态要求，协调准入与验收 | 产品支持矩阵、决策记录 |
| Tier1／系统集成方 | 集成客户端、Android、QNX 与安全路径，定位跨域问题，准备量产 | 软件基线、链路图、测试报告 |
| SoC／BSP／TEE 供应商 | 提供匹配的 OEMCrypto、TA、驱动、安全内存及输出保护方案 | 版本配套表、集成指南、问题结论 |
| Google／Widevine | 提供适用的许可、设备集成规范、组件与流程要求 | 正式资料、适用流程确认 |
| OTT／内容平台 | 确认客户端与车型支持、内容授权、画质、并发、HDCP 和失败策略 | 书面支持条件、验收用例 |
| 内容／许可证后端 | 管理内容密钥、业务授权、许可证与续期 | 服务接口、策略配置、运维责任 |
| 浏览器／App 供应商 | 维护客户端版本、EME／DRM 对接、车载交互与内容兼容性 | 版本支持范围、升级机制 |
| 显示／SerDes 供应商 | 确认保护能力、认证与保护终止位置 | 器件资料、配置和链路验证报告 |
| 工厂／测试评估合作方 | 按项目方案部署凭据、验证唯一性，执行适用的测试或评估 | 产线记录、评估范围与结果 |

Widevine 资料访问与 L1 OEMCrypto 获取有各自要求。适用的许可、第三方测试、提交材料及准入流程，由 Widevine 与芯片方确认。[Widevine Partner Access](https://developers.google.com/widevine/access)

## 8. 集成与量产

### 8.1 平台集成

高通 HQX／LA 交付资料列出普通侧 `liboemcrypto.so`、`libtrustedapploader.so`、`libops.so` 和安全侧 Widevine TA。动态库与进程 ABI 匹配，TA 与芯片、BSP、安全固件匹配；实际目录及加载方式按当前交付版本核对。

三个动态库是平台依赖，不能仅凭清单认定其调用顺序。也不能直接把旧版资料中的 Android Q／R 与 TZ 分支对应关系用于新版本。文件权限、SELinux、签名和加载策略按集成规范配置。

显示集成重点核验安全 Buffer 属性、跨域导入、输出端口映射、OPS 状态更新和保护不足时的阻断。HAB 显示通路在本地源码中可见，不代表 OEMCrypto 到 TA 也使用 HAB。

### 8.2 量产与维护

- 开发、测试、量产凭据隔离；量产软件不得残留测试凭据。
- 产线执行设备唯一性、凭据状态和目标显示链路验证，记录软件与固件版本。
- OTA 验证 OEMCrypto／TA 配套、回滚约束、凭据及离线许可的可用性。
- 恢复出厂、用户退出和车辆转售分别定义账户、下载与许可清理规则。
- 日志记录错误码、会话关联、输出状态和版本，不记录密钥、凭据明文、业务令牌或完整授权响应。
- 安全事件按账户、客户端、设备凭据、固件或内容密钥分别定位并处理。

## 9. 验证与验收

| 验证项 | 通过条件 | 证据 |
| :--- | :--- | :--- |
| 平台安全能力 | 目标版本的 DRM 会话、安全解密与解码成功 | 库／TA 版本、会话状态、解码器及运行记录 |
| 商用服务 | 支持矩阵中的每个组合获得服务商确认并实际播放通过 | 服务商条件、客户端版本、实测结果 |
| 实际画质 | 获得的媒体轨道符合约定分辨率、Codec、HDR、音频 | 轨道与解码输出信息；不只看 UI 标签 |
| 安全显示 | 每块目标屏幕满足许可策略；保护不足时不泄露受保护画面 | 端口映射、状态、故障注入与恢复结果 |
| 截图／录屏／投屏 | 各入口按产品和内容策略执行 | 原生、浏览器及系统入口的测试记录 |
| 多屏与并发 | 复制、迁移、独立播放及会话额度符合要求 | 屏幕组合与并发结果 |
| 授权异常 | 过期、撤销、续期失败、离线无效等按策略处理 | 客户端行为与错误记录 |
| 整车状态 | 行驶、倒车、电话、休眠唤醒及状态未知时行为符合需求 | 整车场景测试 |
| 量产与升级 | 凭据、唯一性、OTA、恢复出厂和换板流程通过 | 产线与生命周期报告 |
| 性能 | 达到冻结的首帧、卡顿、同步、恢复和功耗指标 | 指标数值、测试条件、测试报告 |

“设备报告 L1”“参考内容能播放”“Netflix 可按目标画质播放”分别记录，不互相替代。HDCP 查询 API 可用于诊断，策略强制执行由可信 DRM／平台实现负责。[MediaDrm HDCP 查询](https://developer.android.com/reference/android/media/MediaDrm#getConnectedHdcpLevel())

## 10. 实施阶段与待确认事项

| 阶段 | 主要产出 | 进入下一阶段的条件 |
| :--- | :--- | :--- |
| 需求与合作确认 | 产品矩阵、候选客户端、供应商职责、适用准入流程 | 目标组合与关键外部依赖明确 |
| 单屏原型 | 授权测试内容的完整播放链路、版本及问题记录 | 授权、解密、解码、显示和阻断验证通过 |
| 目标服务与多屏 | 指定服务、客户端、画质、屏幕及整车状态结果 | 商用支持条件和集成测试通过 |
| 量产准备 | 凭据流程、生命周期回归、适用评估及售后方案 | 产品、平台、内容方分别完成验收 |

当前需要确认：

1. 目标 OTT、市场、车型和客户端，是否有正式车载支持。
2. 各屏的画质、音频、HDCP 版本及保护失败策略。
3. OEMCrypto、TA、BSP 的交付版本，设备凭据与产线方案。
4. Android／QNX 显示 FE／BE 选型、端口映射和受保护 Buffer 通路。
5. 本项目适用的许可、测试、第三方评估和商用准入要求。
6. 并发、离线、车辆状态、性能指标及对应责任人。

## 附录：依据

公开资料核对日期：2026-10-08。正式要求以项目适用版本和合作方确认文件为准。

- [Android DRM Framework](https://source.android.com/docs/core/media/drm)：框架与 HAL。
- [MediaDrm API](https://developer.android.com/reference/android/media/MediaDrm)：会话、Provisioning、许可证与 HDCP 查询。
- [Android 受保护视频通路](https://source.android.com/docs/core/graphics/arch-st#secure_texture_video_playback)：受保护缓冲区和图形处理。
- [Widevine Overview](https://developers.google.com/widevine/drm/overview)：平台、许可证服务和 Proxy。
- [Widevine Partner Access](https://developers.google.com/widevine/access)、[PGP/GPG](https://developers.google.com/widevine/pgp)：集成资料与凭据交付。
- [Chromium 与 Android DRM](../chromium-drm/)：浏览器调用路径；具体行为按内核版本核对。
- [QNX OpenWFD 安全端口分析](../qnx-openwfd-oem-secure-port-analysis/)：端口安全属性及阻断逻辑。

本地源码核验点：

| 源码 | 核验内容 |
| :--- | :--- |
| `widevine/service.mk`、`libwvdrmengine/Android.bp`、`libwvdrmengine/cdm/Android.bp` | AIDL 服务选型、`libwvaidl.so`／`libwvhidl.so` 构建及 CDM／Plugin 静态链接关系 |
| `libwvdrmengine/aidl_src/WVDrmFactory.cpp`、`src/WVCDMSingleton.cpp` | 两种 Plugin 共享 CDM 入口对象 |
| `mediadrm/aidl_src/WVDrmPlugin.cpp`、`mediadrm/aidl_include/WVGenericCryptoInterface.h` | DRM 会话／许可证主链与通用加密分支 |
| `mediacrypto/aidl_src/WVCryptoPlugin.cpp`、`cdm/core/src/content_key_session.cpp` | DecryptV16 入口与 OEMCrypto_DecryptCENC 调用 |
| `libwvdrmengine/cdm/core/src/oemcrypto_adapter_dynamic.cpp` | 动态加载 OEMCrypto、按会话分派及 L1／L3 初始化 |
| `libwvdrmengine/mediacrypto/src_hidl/WVCryptoPlugin.cpp` | 安全目标 Buffer Handle |
| `libwvdrmengine/cdm/core/src/content_key_session.cpp` | `OEMCrypto_DecryptCENC` 调用 |
| `libwvdrmengine/cdm/core/src/license.cpp`、`oemcrypto/include/OEMCryptoCENC.h` | 会话材料、派生密钥、许可证验证与内容密钥加载 |
| `hardware/qcom/display/sdm/libs/hwc2/hwc_display.cpp` | protected／secure Buffer 识别 |
| `openwfd/src/device.c`、`wfd_clientmgr.c`、`pipeline.c` | OPS 属性更新、安全端口状态与 Source 绑定检查 |
| `QSEEComAPI.h`、`qseecom_daemon` 预编译组件 | Listener 接口、OPS 命令分派及处理结果返回 |
| `wfd_be_qnx/src/host_hab_utils.c`、`wire_host.c` | HAB Buffer 导入和 WFD 请求转发 |

源码路径表示本次参考的平台快照。量产结论需要绑定实际构建版本、目标硬件和运行结果。
