"""H56EZ/nurburgring Widevine control, handle and protected-media paths.

Names come from the HBEZ source tree, packaged binaries and supplied logs.
Hardware roles are explicit where a particular crypto IP was not identified.
"""
from html import escape
from software_widevine_graph import render_graph
from software_widevine_sequence import render_sequence


def module(mid, name, domain, short, duty, source):
    return dict(id=mid, name=name, domain=domain, short=short, duty=duty, source=source)


MODULES = [
    module('wv-license', 'License Proxy / Service', 'cloud', 'Site endpoint · challenge / response',
           '播放器向站点许可证端点转发 CDM 产生的 challenge，再把响应交还 CDM。站点代理验证账户、设备准入及业务规则，并由后端 Widevine License Service 或 License Server SDK 签发许可证。图中合并表示站点端点和许可证后端，不代表已确认 Prime Video 的具体部署；设备 provisioning 使用另一类请求/响应。', 'MediaDrm / EME API；Google Widevine Overview：license proxy、Cloud License Service / License Server SDK。'),
    module('wv-cdn', 'Media CDN', 'cloud', 'Manifest · CENC samples',
           '提供播放清单和加密媒体分片。媒体样本下载与许可证请求是两条独立网络链路，播放器解析后把密文和 IV、key ID、subsamples 等信息送入媒体框架。', 'EME / MediaCodec API；媒体下载端点。'),
    module('wv-app', 'Prime Video App', 'aaos', 'Native player · license HTTP',
           '原生播放器组织 DRM 会话、许可证网络交互、MediaCrypto、MediaCodec 和 Surface。前次 App 播放与最新 Chrome 播放为两个不同入口，不能把一方的会话结果归到另一方。', '用户确认 App 播放；前次 App 日志及最新 Chrome 日志分别取证。'),
    module('wv-web', 'Web Player (JS)', 'aaos', 'EME configuration · message / update',
           '网页提交 EME 候选配置，取得 MediaKeys、MediaKeySession，再转发 message 和 update。完整候选数组、最终 getConfiguration 及浏览器实际安全会话需分别观测。', 'W3C EME；配置选择不由网页外观或未填 robustness 单独决定。'),
    module('wv-eme', 'Chrome / MediaDrmBridge', 'aaos', 'Android CDM · browser media pipeline',
           'Chrome 实现网页 EME 并桥接 Android MediaDrm；浏览器媒体管线向 MediaCodec 提交加密样本。本次日志中的 com.android.chrome 创建了 AIDL Widevine 对象和安全 AVC 解码器。', 'logcat .014:26192、26966、27871；Chromium Android EME / CDM 桥接职责。'),
    module('wv-mediadrm', 'MediaDrm', 'aaos', 'openSession · getKeyRequest · response',
           '创建会话并处理 getKeyRequest/provideKeyResponse、密钥状态等控制操作。JDrm 通过 DrmUtils 构建 native DrmHal；应用负责网络请求。它不是所有视频字节通过的数据通道。', 'frameworks/base/media/jni/android_media_MediaDrm.cpp:484；frameworks/av/drm/libmediadrm/DrmUtils.cpp:194。'),
    module('wv-mediacrypto', 'MediaCrypto', 'aaos', 'sessionId → ICrypto reference',
           '用 DRM session ID 创建/关联 crypto 上下文，并交给 MediaCodec 配置。传递的是会话与 ICrypto 对象引用，不是把内容密钥放进播放器或普通内存。', 'frameworks/base/media/jni/android_media_MediaCrypto.cpp；MediaCrypto / MediaCodec configure API。'),
    module('wv-mediacodec', 'MediaCodec', 'aaos', 'queueSecureInputBuffer · Surface',
           '接收密文样本、key ID、IV、subsamples 等参数，在安全组件上排队。输出 render 时提交 graphic block、fence 和时间戳至 Surface，不能把这条提交画成 CPU 拷贝解码像素。', 'frameworks/av/media/libstagefright/MediaCodec.cpp:2682、5281；CCodecBufferChannel.cpp:748、966。'),
    module('wv-drmhal', 'DrmHalAidl', 'aaos', 'IDrmPlugin · Binder IPC',
           'DRM native 适配层通过 AIDL 调用 vendor Widevine 会话接口。项目框架仍有 HIDL 兼容后端，但不是 AIDL 后再串行经过 HIDL。本次日志明确出现 AIDL WVDrmFactory。', 'frameworks/av/drm/libmediadrm/DrmHal.cpp:48；logcat .014:26192。'),
    module('wv-cryptohal', 'CryptoHalAidl', 'aaos', 'ICryptoPlugin · decrypt()',
           '将加密源描述、secure destination native_handle 以及加密参数传给 Widevine ICryptoPlugin。本次已见 AIDL crypto factory；框架存在 HIDL 兼容实现，图展示当前观察对应的 AIDL 路径。', 'frameworks/av/drm/libmediadrm/CryptoHal.cpp:80；CryptoHalAidl.cpp；logcat .014:14577。'),
    module('wv-bufferchannel', 'CCodecBufferChannel', 'aaos', 'NATIVE_HANDLE · queue / render',
           '安全分支将解密 destination.type 设为 NATIVE_HANDLE，使用 EncryptedLinearBlockBuffer::handle()；mCrypto->decrypt 完成后把对应 C2 block 交给 codec。仅普通 SHARED_MEMORY 分支复制解密内容。输出侧 queueToOutputSurface 传 graphic block 和 fence。', 'frameworks/av/media/codec2/sfplugin/CCodecBufferChannel.cpp:619、630、636、700、966；Codec2Buffer.cpp:959、996。'),
    module('wv-plugin', 'WVDrmPlugin / WVCdm', 'aaos', 'Widevine AIDL service implementation',
           'Widevine vendor 实现负责会话、许可证和 CDM 状态，并通过 OEMCrypto 接入 L1 可信能力。WVDrmPlugin 与 WVCryptoPlugin 是同一 Widevine 集成内的职责边界，不能据框图假定它们一定是两个独立进程。', 'logcat .014:26192 WVDrmFactory::createDrmPlugin；26958–27192 会话与内容密钥状态。'),
    module('wv-cryptoplugin', 'WVCryptoPlugin', 'aaos', 'ICryptoPlugin · secure decrypt output',
           '接收样本解密调用和 native_handle 安全输出描述，委托 CDM/OEMCrypto 安全实现处理。应用可填入的是密文输入缓冲，解密结果进入另一个受保护的 C2 buffer。', 'logcat .014:14577 AIDL createCryptoPlugin；CCodecBufferChannel.cpp:619–636。'),
    module('wv-oemcrypto', 'liboemcrypto.so', 'aaos', 'Session · key load · decrypt commands',
           '普通操作系统侧的 OEMCrypto 库。产品源码默认配置 WIDEVINE_USES_SMCINVOKE=false；预编译库同时包含 Qseecom 和 SMCInvoke 实现，必须经相应用户库、内核、SCM/HAB 和 QNX QCPE 后进入 TEE，不能直接连 TA。日志尚未逐跳确认该会话选择的分支或库 hash。', 'securemsm/config/cpz_vendor_proprietary_board.mk:234、243；prebuilt_HY11/.../liboemcrypto.so NEEDED/UND；logcat .012:68729。'),
    module('wv-qseeapi', 'libQSEEComAPI.so', 'aaos', 'Source default · /dev/qseecom',
           'OEMCrypto 库依赖并调用 QSEECom_start_app / send_cmd / send_modified_cmd。QSEECom API 打开 /dev/qseecom 并通过 ioctl 交给 guest 驱动。这里的“默认”来自产品源码配置，不替代运行时选支证据。', 'prebuilt_HY11/target/product/msmnile_gvmq/vendor/lib64/liboemcrypto.so、libQSEEComAPI.so 的依赖、符号和设备路径。'),
    module('wv-loader', 'TA Loader / Mink', 'aaos', 'Available branch · /dev/smcinvoke',
           'libtrustedapploader 的 SMCInvokeInit 调 TZCom_getClientEnvObject；libminkdescriptor 的 MinkDescriptor 打开 /dev/smcinvoke 并发 invoke ioctl。它是库中可用的替代分支，不与 QSEECom driver 串联，也不能根据库存在就断言本次播放选择了它。', 'libtrustedapploader.so SMCInvokeInit 反汇编；securemsm/smcinvoke/TZCom/src/TZCom.cpp:78、97；MinkDescriptor.cpp:804、855。'),
    module('wv-qseecom', 'qseecom driver', 'guest-kernel', 'QSEECOM_IOCTL_SEND_CMD_REQ',
           '处理 /dev/qseecom 的 load-app、send-command ioctl，再调用 qcom_scm_qseecom_call。qseecom_proxy.c 仅为 kernel trampoline，不是图中的 HAB 前端。', 'vendor/qcom/opensource/securemsm-kernel/qseecom/qseecom.c:530、7877、8060。'),
    module('wv-smcinvoke', 'smcinvoke driver', 'guest-kernel', 'SMCINVOKE_IOCTL_INVOKE_REQ',
           '接收 Mink object invoke，并调用 qcom_scm_invoke_smc 或 legacy 入口。它与 QSEECom 驱动是可选调用分支，在 SCM 层汇合，不是先后执行的两层。', 'vendor/qcom/opensource/securemsm-kernel/smcinvoke/smcinvoke.c:1432、1439；qcom_scm.c:2780、2798。'),
    module('wv-scm', 'qcom_scm / qcom_scm_hab', 'guest-kernel', 'scm_call_qcpe · MM_QCPE_VM1',
           '产品启用 QCOM_SCM_HAB。SCM 的 HAB calling convention 通过 scm_call_qcpe，将安全调用参数经 MM_QCPE_VM1 发给 QNX QCPE 并接收返回值；这里传安全调用消息，不是视频像素流。', 'kernel_platform/msm-kernel/drivers/firmware/qcom_scm-smc.c:44、306；qcom_scm_hab.c:37、77、87；autogvm.config:127–128。'),
    module('wv-qcpe', 'qcpe_service', 'qnx', 'HAB dispatch → secure monitor call',
           'QNX host 上的 guest 安全调用代理。二进制包含 HAB 收发、qcpe_dispatch_request 和 qcpe_send_smc；本地镜像启动 qcpe_service -H。其安全监控调用继续进入 TEE，不能在其前强行串上 QNX smcinvoke_service、qseecom_service。', 'bsp/.../out_8540/mifs_hyp_la_qcc6.build:190、658；qcpe_service-qvmhost-8540 的导出符号及 SMC 调用反汇编。'),
    module('wv-tee-entry', 'Secure monitor / TEE entry', 'tee', 'SMC dispatch · trusted-world entry',
           '表示 QNX qcpe_service 发出安全监控调用后进入 TEE 平台的入口职责，再分派到相应可信服务或 TA。该节点不把 Widevine TA 当作硬件或 QNX 服务，也不表示普通世界能够直接读取内容密钥。', 'qcpe_service 二进制中的 qcpe_send_smc 及 SMC 指令反汇编；kernel_platform/msm-kernel/drivers/firmware/qcom_scm_hab.c:37、77、87。'),
    module('wv-ta', 'Widevine TA', 'tee', 'Trusted software · keys / crypto policy',
           '运行在 Qualcomm TEE 内的可信应用软件，管理 L1 密钥与安全操作，并向 OPS 提交内容保护要求。TA 不是硬件模块；普通侧请求需经过图中的安全调用链。底层具体 crypto IP 未由本次日志证明。', '高通 80-34627-1 Rev. AB §2.2.1；logcat .012:68729 TA_Version；.014:26953 OEMCrypto session。'),
    module('wv-ops', 'OPS (TZ service)', 'tee', 'Content requirement ↔ output state',
           'TEE/TZ 的 Output Protection Service 汇总内容所需保护和显示端状态。与 host OPS listener/显示软件协同限制输出；能力不足、认证失效或拓扑变化时重新评估，不满足要求的受保护画面不得继续输出。', '高通手册 §2.4；QNX qseecom_daemon 的 OPS_SERVICE、min_enc_level、clock_vote 符号。'),
    module('wv-opslistener', 'qseecom_daemon (OPS)', 'qnx', 'OPS Listener · /dev/qsee_listener',
           'QNX 二进制包含 ops_service、OPS_SERVICE Dispatch、ops_wfd_enumerate_device，并访问 libopenwfd 和 mdss_0_ops/mdss_1_ops。HDCP 驱动等待其 /dev/qsee_listener。ENABLE_HYP 的 Android 通用 daemon 排除了虚拟化 listener，不能把两侧 listener 都画为必经。', 'bsp/apps/qnx_ap/install/aarch64le/bin/qseecom_daemon 二进制；Hoya/qdidriver/.../HDCP/HDCP2p2.c:419。'),
    module('wv-codec', 'libqcodec2_v4l2codec', 'aaos', 'c2.qti.avc.decoder.secure',
           '最新 Chrome 日志中的高通安全 AVC codec。预编译 codec 库依赖 libhyp_video_intercept，经虚拟视频控制链使用 QNX 视频后端。日志中的 allocator ID 本身不能证明每个 buffer 的实际 heap。', 'logcat .014:27871、28119、28148；prebuilt_HY11/target/product/msmnile_gvmq/Android.mk:2737–2739。'),
    module('wv-videofe', 'libhyp_video_intercept / FE', 'aaos', 'video_fe_open / ioctl · HAB',
           'intercept 库动态加载 libhyp_video_fe，并调用 video_fe_open/ioctl；buffer 管理代码将已有 buffer FD 导出为 HAB export ID。控制命令和 buffer 引用走 HAB，不等于把整帧像素复制到消息体。', 'vendor/qcom/proprietary/hyp-video/hyp-video-intercept/hyp_video_intercept.cpp:207、215、220；common/src/hyp_buffer_manager.cpp:1227、1236。'),
    module('wv-videobe', 'hyp_video_be', 'qnx', 'MM_VID · commands / buffer IDs',
           'QNX 视频后端加载 HAB 接口，打开 MM_VID 通道处理 guest 视频请求。它和 videoCore 是本地生成平台配置中的实际程序名，不用参考图片中的泛称 Video HAL 代替。', 'bsp/.../video/source/hypervisor/be/common/src/hyp_video_be.cpp:804、808、877；out_8540/platform_variables.sh:104、108。'),
    module('wv-vidc', 'videoCore / VIDC', 'qnx', 'PMEM handle → secure SMMU mapping',
           '视频驱动按 bitstream/pixel 安全类型选择 CP_B_VIDEO/CP_P_VIDEO context。vidc_smmu_map 接受 PMEM handle，并用 smmu_map_pt_v2 获取设备地址供视频硬件访问；这不是普通 CPU 获得明文读取权限。', 'bsp/.../vidc_hwdrv/src/video_smem.c:546、552、845、878、906。'),
    module('wv-gralloc', 'gralloc / DMA-BUF', 'aaos', 'qcom,secure-pixel · usage policy',
           '按 usage 分配图像缓冲并设置 secure 标志。常规 GRALLOC_USAGE_PROTECTED 像素分支选择 qcom,secure-pixel；secure display/camera 另有分支。拥有 FD/native handle 不表示 CPU 可以 mmap 读取。', 'hardware/qcom/display/gralloc/gr_dma_mgr.cpp:209、236、238；qcom_sg_ops.c:400；mem_buf_dma_buf.c:364。'),
    module('wv-cpion', 'libcpion.so', 'aaos', 'cp_ion / cp_qce · buffer support',
           'OEMCrypto 的受保护内存辅助库依赖，含 cp_ion_open、cp_qce_open/map/unmap、DMA-BUF 和 VMMEM 支持。产品源码 WIDEVINE_USES_CE_SMMU=false，因此库内具备某种映射能力不能直接证明本次会话使用 /dev/qce 或某个 Crypto FE/BE。', 'liboemcrypto.so NEEDED/UND；libcpion.so 的 libdmabufheap/libvmmem 依赖和 /dev/qce；cpz_vendor_proprietary_board.mk:244。'),
    module('wv-composer', 'SurfaceFlinger / HWC', 'aaos', 'GraphicBuffer · fence · secure layer',
           '接收输出 Surface 的 graphic block/fence，依据 buffer secure 标志提交显示。日志中也有需要受保护 client composition 的状态，不能把所有帧都断言为纯 overlay；实际扫描帧可能是受保护合成结果。', 'CCodecBufferChannel.cpp:966；hardware/qcom/display/sdm/libs/hwc2/hwc_layers.cpp:298、307；日志 requiresClient / needProtCtx。'),
    module('wv-kms', 'msm-hyp / wfd_kms', 'guest-kernel', 'dma_buf export · secured WFD source',
           '本平台 WFD/HAB display 分支从 framebuffer 取得已有 dma_buf，通过 HAB 导出 ID。SDE_DRM_FB_SEC 转为 WFD_SOURCE_TRANSLATION_SECURED 后提交给 host，不是 VirtIO display。', 'display-drivers/msm-hyp/wfd/wfd_kms.c:1089、1122、1932；user_hab_utils.c:639–658；autogvm.config:148；gvmdisp.conf:3。'),
    module('wv-wfdbe', 'wfd_be', 'qnx', 'HAB export ID → same PMEM handle',
           'QNX wfd_be 导入 HAB export ID，使用导入 handle 创建 OpenWFD image。wire_host 明确创建使用同一 PMEM handle 的 shadow image，传输的是引用，不是用 HAB 消息搬运明文像素。', 'bsp/.../Hoya/wfd_be_qnx/src/host_hab_utils.c:168、191；wire_host.c:1558、1580、1607。'),
    module('wv-mdss', 'OpenWFD / MDSS', 'qnx', 'Secure source · SMMU · scanout',
           'OpenWFD 从 secure source 设置 bSecure，MDSS 按 secure flag 选择 context bank，使用 PMEM handle 建立显示 SMMU 映射。显示控制器据设备地址读取扫描缓冲；OPS/HDCP 另负责输出保护状态。', 'bsp/.../Hoya/openwfd/src/source.c:746；qdidriver/.../mdss_platform_memmgr.c:424、428、1202、1204。'),
    module('wv-encrypted', 'Encrypted input', 'buffer', 'CENC samples · ordinary input',
           '播放器可写的密文输入区域，与安全解密目标分离。EncryptedLinearBlockBuffer 保留供加密样本输入的 IMemory，以及另一个受保护 C2 block；不要把二者画成同一块普通明文内存。', 'frameworks/av/media/codec2/sfplugin/CCodecBuffers.cpp:891；Codec2Buffer.cpp:944。'),
    module('wv-bitstream', 'Secure compressed buffer', 'buffer', 'SMMU: CP_B_VIDEO',
           '解密后的压缩视频码流仍位于受保护缓冲。ICrypto 的 destination 是 native_handle，视频驱动映射到 secure bitstream context 后由 VPU 读取；CP_B_VIDEO 是访问上下文，不是独立 DDR 芯片或固定 heap 名。', 'CCodecBufferChannel.cpp:619、630；bsp/.../vidc_hwdrv/src/video_smem.c:546、878、906。'),
    module('wv-pixels', 'Secure decoded frames', 'buffer', 'SMMU: CP_P_VIDEO',
           'VPU 输出的受保护像素缓冲，后续通过 graphic block/FD/fence 和映射引用进入受保护合成及显示。CP_P_VIDEO 是像素安全 context；合成需要时可能另产生受保护扫描缓冲，不能断言所有画面只有一份 buffer。', 'bsp/.../vidc_hwdrv/src/video_smem.c:552；CCodecBufferChannel.cpp:966；hwc_layers.cpp:298。'),
    module('wv-crypto-hw', 'Crypto HW', 'hardware', 'Decryption role · IP not verified',
           '表示把加密样本转换成受保护压缩码流的硬件安全解密职责。源码/二进制可证 OEMCrypto 和缓冲接口，尚未证实本次实际使用哪个 crypto IP，所以不从参考图直接抄为 GPCE/QCE 或假造 Crypto FE/BE 部署。', 'OEMCrypto/CDM 安全输出契约；具体硬件 IP 未由本次源码与会话日志绑定。'),
    module('wv-video', 'Video HW / VPU', 'hardware', 'Read bitstream · write protected pixels',
           '在视频驱动建立的访问权限下读取受保护压缩输入并写出受保护像素。输入/输出 SMMU context 不同，控制命令、buffer handle 和硬件真实读写需区分。', 'VIDC video_smem.c secure bitstream/pixel 映射；日志 c2.qti.avc.decoder.secure。'),
    module('wv-dpu', 'Display HW / MDSS', 'hardware', 'Protected scanout via display SMMU',
           '显示引擎经显示 SMMU 读取实际扫描缓冲并输出画面。扫描缓冲可直接引用解码输出，也可能来自受保护合成，不表示 QNX CPU 读取或复制明文帧。', 'Hoya/qdidriver/.../mdss_platform_memmgr.c:424、1202；OpenWFD source.c:746。'),
    module('wv-output', 'HDCP / Display', 'hardware', 'Output policy · authenticated link',
           '许可证要求链路保护时，实际输出需要满足相应 HDCP 认证和加密状态。串解器支持能力、link lock、L1 会话和 secure decoder 都不能单独证明本次输出已合规受保护。', '高通 OPS/HDCP 手册；HDCP2p2.c；本次日志未确认实际 HDCP 版本与认证状态。'),
]

FLOWS = [
    ('1 · Player ↔ License Proxy / Service', '控制流：许可证请求/响应', 'HTTPS + MediaDrm / EME', 'getKeyRequest / message → 站点端点与许可证后端 → provideKeyResponse / update；provisioning 使用 getProvisionRequest / provideProvisionResponse，不能混用。'),
    ('2 · MediaDrm → DrmHalAidl → WVDrmPlugin', '控制流：会话和密钥状态', 'JNI / AIDL Binder', '本次 factory 日志为 AIDL；不把 mediadrmserver 固定为所有操作的必经进程。'),
    ('3 · MediaCrypto → MediaCodec', '引用流：session / ICrypto', 'sessionId · ICrypto object', '将 DRM 会话关联到 codec，传引用而非把明文密钥交给应用。'),
    ('4 · MediaCodec → CCodecBufferChannel → CryptoHalAidl → WVCryptoPlugin', '控制流：decrypt；引用流：加密源和安全目标', 'queueSecureInputBuffer · NATIVE_HANDLE', 'source 包含密文；destination 为受保护 C2 block 的 native_handle。解密完成后交 codec，安全分支不 copyDecryptedContent。'),
    ('5A · OEMCrypto → QSEEComAPI → qseecom driver', '控制流：源码默认分支', 'QSEECom_send_cmd · ioctl', 'nurburgring 导入 msmnile 配置，WIDEVINE_USES_SMCINVOKE=false；仍需运行时证明设备库和分支选择。'),
    ('5B · OEMCrypto → TA Loader / Mink → smcinvoke', '控制流：库内可用分支', 'Mink object invoke · ioctl', '可用替代实现，不与 QSEECom 驱动串联，不声称本次播放实际选择了它。'),
    ('6 · qcom_scm → qcom_scm_hab → qcpe_service → TEE', '控制流：安全调用与返回', 'MM_QCPE_VM1 · HAB · secure monitor', 'HAB 传安全调用消息；QCPE 处理后进入安全监控/TEE。QNX 代理服务不是 Widevine TA，也不是密码硬件。'),
    ('7 · OEMCrypto ↔ libcpion', '引用流：受保护内存支持', 'cp_ion / cp_qce / DMA-BUF / VMMEM', '库依赖和映射接口存在；WIDEVINE_USES_CE_SMMU=false，不能断言本次使用特定 crypto IP 或 FE/BE。'),
    ('8 · Encrypted input → Crypto HW → Secure compressed buffer', '数据流：密文 → 受保护的压缩码流', 'Secure decrypt output', 'CPU 可填密文输入；安全目标与输入不是同一个可任意读取的普通 buffer。'),
    ('9 · Codec2 → video FE → hyp_video_be → videoCore / VIDC', '控制流与引用流：视频队列、buffer ID', 'video_fe_ioctl · HAB / MM_VID', 'libqcodec2_v4l2codec 依赖 intercept，后者加载 libhyp_video_fe；HAB 传已有 FD 的 export ID。'),
    ('10 · Secure compressed buffer → VPU → Secure decoded frames', '数据流：受保护压缩输入 → 受保护像素输出', 'CP_B_VIDEO / CP_P_VIDEO contexts', 'context 名表示 SMMU 访问权限；不是内存池名，不是 CPU 地址，也不代表帧经 guest/host 消息复制。'),
    ('11 · CCodecBufferChannel → SurfaceFlinger / HWC → msm-hyp / wfd_kms', '引用流：graphic block / fence / dma_buf', 'queueToOutputSurface · secure layer', 'HWC 读取 secure flag。需要时可走 protected client composition；不把路径固定为纯 overlay。'),
    ('12 · wfd_kms → HAB → wfd_be → OpenWFD / MDSS', '引用流：export ID → PMEM handle', 'HAB export / import · WFD secured source', '导入已有内存，创建引用同一 PMEM handle 的 OpenWFD image；不通过 HAB memcpy 明文像素。'),
    ('13 · Scanout buffer → Display SMMU / MDSS → output', '数据流：读取实际扫描缓冲', 'Secure context bank · device address', '扫描源由合成路径决定；普通进程拥有 handle 并不意味着拥有 mmap/CPU 读权限。'),
    ('14 · Widevine TA ↔ OPS ↔ QNX OPS Listener ↔ MDSS / HDCP', '输出策略流：最低保护要求、拓扑与状态', 'qseecom_daemon · OpenWFD OPS interface', '保护不足时限制输出；本次安全解码日志不能替代 HDCP 认证、版本或加密状态验证。'),
]

def render_widevine():
    groups = [('Content Services', 'cloud'), ('Android Guest · User Space', 'aaos'),
              ('Android Guest · Kernel', 'guest-kernel'), ('QNX Host', 'qnx'),
              ('Qualcomm TEE · Trusted Software', 'tee'), ('Memory / Secure Buffers', 'buffer'),
              ('Hardware', 'hardware')]
    index = ''.join('<section class="sw-index-group"><h4>'+title+'</h4><ul class="sw-index-list">'+''.join(
        '<li><button class="sw-index-entry" id="sw-index-'+m['id']+'" type="button" data-sw-module="'+m['id']+'" aria-pressed="false"><span class="sw-index-name">'+escape(m['name'])+'</span><span class="sw-index-duty" lang="zh-CN">'+escape(m['duty'])+'<span class="wv-source">证据：'+escape(m['source'])+'</span></span></button></li>'
        for m in MODULES if m['domain']==domain)+'</ul></section>' for title,domain in groups)
    rows = ''.join('<tr>'+''.join('<td>'+escape(cell)+'</td>' for cell in row)+'</tr>' for row in FLOWS)
    controls = ''.join('<button type="button" data-widevine-focus="'+key+'" aria-pressed="'+str(key=='all').lower()+'">'+title+'</button>'
        for key,title in [('all','All'), ('control','Control calls'), ('data','Media data'), ('buffer','Buffer / handles'), ('output','Output policy')])
    return f'''
<div class="sw-page sw-widevine-page" id="sw-widevine-view" hidden>
  <div class="sw-ota-nav"><button class="sw-back" id="sw-widevine-back" type="button">← High-Level software architecture</button><span>Widevine DRM software architecture</span></div>
  <div class="sw-ota-controls" role="group" aria-label="Highlight Widevine flow type"><span>Interaction paths</span>{controls}</div>
  <div class="sw-board-scroll sw-ota-scroll" aria-label="Widevine integrated software layers, secure buffers, hardware and display architecture">{render_graph(MODULES)}</div>
  <div class="sw-ota-inspector" id="sw-widevine-inspector" role="status" aria-live="polite">Select a component to highlight its connections. Right-click to clear selection.</div>
  <section class="wv-process" aria-labelledby="wv-process-title" lang="zh-CN"><h3 id="wv-process-title">播放过程与模块交互</h3>{render_sequence()}</section>
  <section class="sw-index" aria-labelledby="sw-widevine-index-title"><div class="sw-section-heading"><h3 id="sw-widevine-index-title">Module responsibilities &amp; source evidence</h3></div>{index}</section>
  <section class="sw-interfaces" aria-labelledby="sw-widevine-flows-title"><div class="sw-section-heading"><h3 id="sw-widevine-flows-title">Interface &amp; data-flow register</h3></div><div class="sw-flow-table-wrap"><table class="sw-flow-table"><thead><tr><th>Interaction</th><th>Flow type</th><th>API / transport</th><th>Behavior</th></tr></thead><tbody>{rows}</tbody></table></div></section>
  <div class="sw-provenance" lang="zh-CN">项目依据 H56EZ/nurburgring 对应的 HBEZ 工作树：<code>/home/ethen/workspace/HBEZ</code>。Android 路径以 <code>android/android/</code> 为根；标记 <code>bsp/...</code> 的目录位于 <code>bsp/apps/qnx_ap/</code>。运行观察来自用户提供的 android(1) Chrome 日志。图中 Crypto HW 仅表示安全解密职责，本次未确认具体 GPCE/QCE IP；参考图片只用于布局，不作为已部署模块证据。接口规范参考 <a href="https://developer.android.com/reference/android/media/MediaDrm">MediaDrm</a>、<a href="https://developers.google.com/widevine/drm/overview">Widevine Overview</a>、<a href="https://source.android.com/docs/core/media/drm">AOSP DRM</a>、<a href="https://developer.android.com/reference/android/media/MediaCodec">MediaCodec</a>、<a href="https://www.w3.org/TR/encrypted-media/">W3C EME</a>；OPS 参考 Qualcomm 80-34627-1 Rev. AB。模块源码与运行观察各自标注。</div>
</div>''', {'modules': MODULES, 'flows': FLOWS}
