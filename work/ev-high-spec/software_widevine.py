"""H56EZ/nurburgring Widevine control, handle and protected-media paths.

Names come from the HBEZ source tree, packaged binaries and supplied logs.
Hardware roles are explicit where a particular crypto IP was not identified.
"""
from html import escape
from software_widevine_graph import render_graph
from software_widevine_sequence import render_sequence


def module(mid, name, domain, short, duty, source, status=""):
    return dict(id=mid, name=name, domain=domain, short=short, duty=duty, source=source, status=status)


MODULES = [
    module('wv-license', 'License Proxy / Service', 'cloud', 'Site endpoint · challenge / response',
           '接收播放器转发的许可证请求，校验账户、设备准入和内容权限，并返回 Widevine 许可证。站点代理对接后端 License Service 或 License Server SDK。', 'MediaDrm / EME API；Google Widevine Overview：license proxy、Cloud License Service / License Server SDK。', 'Prime Video 的服务端部署待确认。'),
    module('wv-cdn', 'Media CDN', 'cloud', 'Manifest · CENC samples',
           '提供播放清单和加密媒体分片。播放器解析媒体样本及 key ID、IV、subsamples 等参数，提交至媒体框架。', 'EME / MediaCodec API；媒体下载端点。'),
    module('wv-app', 'Prime Video App', 'aaos', 'Native player · license HTTP',
           '组织原生播放器的 DRM 会话、许可证网络请求、MediaCrypto、MediaCodec 和 Surface，完成授权内容的播放。', '用户确认 App 播放；前次 App 日志及最新 Chrome 日志分别取证。', 'App 与 Chrome 的播放日志分别记录。'),
    module('wv-web', 'Web Player (JS)', 'aaos', 'EME configuration · message / update',
           '通过 EME 选择 DRM 配置，创建 MediaKeys 和 MediaKeySession。监听 message 事件，将许可证响应通过 update 交回浏览器。', 'W3C EME：requestMediaKeySystemAccess、getConfiguration。', '候选配置、最终配置及实际安全会话待完整采集。'),
    module('wv-eme', 'Chrome / MediaDrmBridge', 'aaos', 'Android CDM · browser media pipeline',
           '实现网页 EME，并通过 MediaDrmBridge 调用 Android MediaDrm。浏览器媒体管线负责解析媒体和向 MediaCodec 提交加密样本。', 'logcat .014:26192、26966、27871；Chromium Android EME / CDM 桥接职责。', 'Chrome 日志已记录 AIDL Widevine 对象和安全 AVC 解码器。'),
    module('wv-mediadrm', 'MediaDrm', 'aaos', 'openSession · getKeyRequest · response',
           '管理 DRM 会话、许可证请求与响应及密钥状态通知。JNI 经 DrmHal 调用厂商实现，播放器负责许可证网络传输。', 'frameworks/base/media/jni/android_media_MediaDrm.cpp:484；frameworks/av/drm/libmediadrm/DrmUtils.cpp:194。'),
    module('wv-mediacrypto', 'MediaCrypto', 'aaos', 'sessionId → ICrypto reference',
           '将 DRM session ID 关联到 crypto 上下文，为 MediaCodec 提供 ICrypto 接口引用和安全解码要求。', 'frameworks/base/media/jni/android_media_MediaCrypto.cpp；MediaCrypto / MediaCodec configure API。'),
    module('wv-mediacodec', 'MediaCodec', 'aaos', 'queueSecureInputBuffer · Surface',
           '接收加密样本及 key ID、IV、subsamples，调度安全解密和解码。渲染输出时，将 graphic block、fence 和时间戳提交至 Surface。', 'frameworks/av/media/libstagefright/MediaCodec.cpp:2682、5281；CCodecBufferChannel.cpp:748、966。'),
    module('wv-drmhal', 'DrmHalAidl', 'aaos', 'IDrmPlugin · Binder IPC',
           '将 MediaDrm 的会话、许可证和密钥状态操作转换为 AIDL IDrmPlugin 调用。', 'frameworks/av/drm/libmediadrm/DrmHal.cpp:48；logcat .014:26192。', '当前日志记录 AIDL WVDrmFactory。'),
    module('wv-cryptohal', 'CryptoHalAidl', 'aaos', 'ICryptoPlugin · decrypt()',
           '通过 AIDL ICryptoPlugin 提交样本解密请求，包含加密源描述、IV、subsamples 和安全目标 native_handle。', 'frameworks/av/drm/libmediadrm/CryptoHal.cpp:80；CryptoHalAidl.cpp；logcat .014:14577。', '当前日志记录 AIDL crypto factory。'),
    module('wv-bufferchannel', 'CCodecBufferChannel', 'aaos', 'NATIVE_HANDLE · queue / render',
           '管理 Codec2 输入、输出缓冲。安全解密以受保护 C2 block 的 native_handle 为目标，完成后将 block 交给 codec，并将输出 graphic block 和 fence 提交至 Surface。', 'frameworks/av/media/codec2/sfplugin/CCodecBufferChannel.cpp:619、630、636、700、966；Codec2Buffer.cpp:959、996。'),
    module('wv-plugin', 'WVDrmPlugin / WVCdm', 'aaos', 'Widevine AIDL service implementation',
           '实现 Widevine DRM 会话、许可证处理及 CDM 状态管理，通过 OEMCrypto 调用 L1 可信能力。', 'logcat .014:26192 WVDrmFactory::createDrmPlugin；26958–27192 会话与内容密钥状态。'),
    module('wv-cryptoplugin', 'WVCryptoPlugin', 'aaos', 'ICryptoPlugin · secure decrypt output',
           '接收 ICryptoPlugin 样本解密请求，将密文输入和安全目标 native_handle 交给 CDM/OEMCrypto 处理，返回操作结果。', 'logcat .014:14577 AIDL createCryptoPlugin；CCodecBufferChannel.cpp:619–636。'),
    module('wv-oemcrypto', 'liboemcrypto.so', 'aaos', 'Session · key load · decrypt commands',
           '提供 OEMCrypto 会话、密钥加载和安全解密接口。通过 QSEECom 或 TA Loader/Mink 的调用链，经 Android 内核和 QNX QCPE 接入 TEE。', 'securemsm/config/cpz_vendor_proprietary_board.mk:234、243；prebuilt_HY11/.../liboemcrypto.so NEEDED/UND；logcat .012:68729。', '源码默认采用 QSEECom。实际会话分支及设备库版本待确认。'),
    module('wv-qseeapi', 'libQSEEComAPI.so', 'aaos', 'Source default · /dev/qseecom',
           '封装可信应用加载和命令调用，通过 /dev/qseecom 的 ioctl 将请求交给 Android guest 驱动。', 'prebuilt_HY11/target/product/msmnile_gvmq/vendor/lib64/liboemcrypto.so、libQSEEComAPI.so 的依赖、符号和设备路径。', '产品源码的默认分支。运行选择待确认。'),
    module('wv-loader', 'TA Loader / Mink', 'aaos', 'Available branch · /dev/smcinvoke',
           '提供可信应用加载和 Mink object 调用。经 libminkdescriptor 打开 /dev/smcinvoke，将请求交给 smcinvoke 驱动。', 'libtrustedapploader.so SMCInvokeInit 反汇编；securemsm/smcinvoke/TZCom/src/TZCom.cpp:78、97；MinkDescriptor.cpp:804、855。', '预编译库包含此分支。运行选择待确认。'),
    module('wv-qseecom', 'qseecom driver', 'guest-kernel', 'QSEECOM_IOCTL_SEND_CMD_REQ',
           '处理 /dev/qseecom 的应用加载和命令 ioctl，通过 qcom_scm_qseecom_call 发起安全调用。', 'vendor/qcom/opensource/securemsm-kernel/qseecom/qseecom.c:530、7877、8060。'),
    module('wv-smcinvoke', 'smcinvoke driver', 'guest-kernel', 'SMCINVOKE_IOCTL_INVOKE_REQ',
           '处理 Mink object invoke 请求，通过 qcom_scm_invoke_smc 或 legacy 接口调用 SCM。', 'vendor/qcom/opensource/securemsm-kernel/smcinvoke/smcinvoke.c:1432、1439；qcom_scm.c:2780、2798。'),
    module('wv-scm', 'qcom_scm / qcom_scm_hab', 'guest-kernel', 'scm_call_qcpe · MM_QCPE_VM1',
           '通过 HAB 的 MM_QCPE_VM1 通道向 QNX QCPE 发送安全调用参数，并接收调用结果。', 'kernel_platform/msm-kernel/drivers/firmware/qcom_scm-smc.c:44、306；qcom_scm_hab.c:37、77、87；autogvm.config:127–128。'),
    module('wv-qcpe', 'qcpe_service', 'qnx', 'HAB dispatch → secure monitor call',
           '接收 Android guest 的 HAB 安全调用请求，执行请求分派和安全监控调用，并向 guest 返回结果。', 'bsp/.../out_8540/mifs_hyp_la_qcc6.build:190、658；qcpe_service-qvmhost-8540 的导出符号及 SMC 调用反汇编。', '本地镜像配置启动 qcpe_service -H。'),
    module('wv-tee-entry', 'Secure monitor / TEE entry', 'tee', 'SMC dispatch · trusted-world entry',
           '接收 QNX 发起的安全监控调用，进入可信执行环境并分派至对应可信服务或 TA。', 'qcpe_service 二进制中的 qcpe_send_smc 及 SMC 指令反汇编；kernel_platform/msm-kernel/drivers/firmware/qcom_scm_hab.c:37、77、87。'),
    module('wv-ta', 'Widevine TA', 'tee', 'Trusted software · keys / crypto policy',
           '在 Qualcomm TEE 中管理 L1 密钥及安全操作，执行内容解密，并向 OPS 提交输出保护要求。', '高通 80-34627-1 Rev. AB §2.2.1；logcat .012:68729 TA_Version；.014:26953 OEMCrypto session。', '具体解密硬件 IP 待确认。'),
    module('wv-ops', 'OPS (TZ service)', 'tee', 'Content requirement ↔ output state',
           '协调内容保护要求与显示端状态，通过 QNX OPS Listener 配置输出保护。链路能力、认证状态或拓扑变化时重新评估受保护输出。', '高通手册 §2.4；QNX qseecom_daemon 的 OPS_SERVICE、min_enc_level、clock_vote 符号。'),
    module('wv-opslistener', 'qseecom_daemon (OPS)', 'qnx', 'OPS Listener · /dev/qsee_listener',
           '处理 TEE 的 OPS 请求，通过 OpenWFD/MDSS 枚举显示端口、配置保护等级并返回输出状态。', 'bsp/apps/qnx_ap/install/aarch64le/bin/qseecom_daemon 二进制；Hoya/qdidriver/.../HDCP/HDCP2p2.c:419。', 'QNX 二进制已包含 OPS Service 和 OpenWFD 接口。'),
    module('wv-codec', 'libqcodec2_v4l2codec', 'aaos', 'c2.qti.avc.decoder.secure',
           '实现 Codec2 安全 AVC 解码组件，通过 libhyp_video_intercept 接入 QNX 视频后端，处理视频输入队列和解码输出。', 'logcat .014:27871、28119、28148；prebuilt_HY11/target/product/msmnile_gvmq/Android.mk:2737–2739。', 'Chrome 日志已记录 c2.qti.avc.decoder.secure。实际 buffer heap 待确认。'),
    module('wv-videofe', 'libhyp_video_intercept / FE', 'aaos', 'video_fe_open / ioctl · HAB',
           '拦截视频调用并加载 libhyp_video_fe。经 HAB 向 QNX 视频后端提交控制命令和已有缓冲的 export ID。', 'vendor/qcom/proprietary/hyp-video/hyp-video-intercept/hyp_video_intercept.cpp:207、215、220；common/src/hyp_buffer_manager.cpp:1227、1236。'),
    module('wv-videobe', 'hyp_video_be', 'qnx', 'MM_VID · commands / buffer IDs',
           '在 QNX host 处理 MM_VID 通道的视频请求，将 guest 控制命令和缓冲引用交给 videoCore。', 'bsp/.../video/source/hypervisor/be/common/src/hyp_video_be.cpp:804、808、877；out_8540/platform_variables.sh:104、108。'),
    module('wv-vidc', 'videoCore / VIDC', 'qnx', 'PMEM handle → secure SMMU mapping',
           '为压缩码流和解码像素分别配置 CP_B_VIDEO、CP_P_VIDEO 安全上下文。将 PMEM handle 映射为视频硬件可访问的设备地址。', 'bsp/.../vidc_hwdrv/src/video_smem.c:546、552、845、878、906。'),
    module('wv-gralloc', 'gralloc / DMA-BUF', 'aaos', 'qcom,secure-pixel · usage policy',
           '按图像 usage 分配 DMA-BUF，并设置安全标志。常规受保护像素使用 qcom,secure-pixel 分配路径，为合成和显示提供 buffer handle。', 'hardware/qcom/display/gralloc/gr_dma_mgr.cpp:209、236、238；qcom_sg_ops.c:400；mem_buf_dma_buf.c:364。'),
    module('wv-cpion', 'libcpion.so', 'aaos', 'cp_ion / cp_qce · buffer support',
           '为 OEMCrypto 提供受保护内存分配和映射辅助接口，包括 cp_ion、cp_qce、DMA-BUF 和 VMMEM 支持。', 'liboemcrypto.so NEEDED/UND；libcpion.so 的 libdmabufheap/libvmmem 依赖和 /dev/qce；cpz_vendor_proprietary_board.mk:244。', '源码配置 WIDEVINE_USES_CE_SMMU=false。实际映射后端待确认。'),
    module('wv-composer', 'SurfaceFlinger / HWC', 'aaos', 'GraphicBuffer · fence · secure layer',
           '接收 Surface 输出的 graphic block 和 fence，根据安全标志配置受保护图层。按合成需求选择硬件图层或受保护 client composition。', 'CCodecBufferChannel.cpp:966；hardware/qcom/display/sdm/libs/hwc2/hwc_layers.cpp:298、307；日志 requiresClient / needProtCtx。', '日志已出现受保护 client composition 状态。'),
    module('wv-kms', 'msm-hyp / wfd_kms', 'guest-kernel', 'dma_buf export · secured WFD source',
           '从 framebuffer 获取 dma_buf，经 HAB 导出缓冲 ID。将 SDE_DRM_FB_SEC 转换为 WFD_SOURCE_TRANSLATION_SECURED，并提交至 QNX 显示后端。', 'display-drivers/msm-hyp/wfd/wfd_kms.c:1089、1122、1932；user_hab_utils.c:639–658；autogvm.config:148；gvmdisp.conf:3。'),
    module('wv-wfdbe', 'wfd_be', 'qnx', 'HAB export ID → same PMEM handle',
           '导入 guest 的 HAB buffer ID，使用对应 PMEM handle 创建 OpenWFD image，交由 host 显示管线处理。', 'bsp/.../Hoya/wfd_be_qnx/src/host_hab_utils.c:168、191；wire_host.c:1558、1580、1607。'),
    module('wv-mdss', 'OpenWFD / MDSS', 'qnx', 'Secure source · SMMU · scanout',
           '管理安全图像源、显示管线和扫描输出。根据安全标志选择 context bank，并将 PMEM handle 映射至显示 SMMU。', 'bsp/.../Hoya/openwfd/src/source.c:746；qdidriver/.../mdss_platform_memmgr.c:424、428、1202、1204。'),
    module('wv-encrypted', 'Encrypted input', 'buffer', 'CENC samples · ordinary input',
           '保存播放器提交的 CENC 密文样本。EncryptedLinearBlockBuffer 管理输入 IMemory，并关联用于安全解密的受保护 C2 block。', 'frameworks/av/media/codec2/sfplugin/CCodecBuffers.cpp:891；Codec2Buffer.cpp:944。'),
    module('wv-bitstream', 'Secure compressed buffer', 'buffer', 'SMMU: CP_B_VIDEO',
           '保存安全解密后的压缩视频码流，以 native_handle 交给视频驱动。驱动通过 CP_B_VIDEO 安全上下文映射缓冲，供 VPU 读取。', 'CCodecBufferChannel.cpp:619、630；bsp/.../vidc_hwdrv/src/video_smem.c:546、878、906。'),
    module('wv-pixels', 'Secure decoded frames', 'buffer', 'SMMU: CP_P_VIDEO',
           '保存 VPU 输出的受保护解码像素，通过 graphic block、FD 和 fence 交给合成及显示管线。视频访问使用 CP_P_VIDEO 安全上下文。', 'bsp/.../vidc_hwdrv/src/video_smem.c:552；CCodecBufferChannel.cpp:966；hwc_layers.cpp:298。'),
    module('wv-crypto-hw', 'Crypto HW', 'hardware', 'Decryption role · IP not verified',
           '执行安全解密，将加密媒体样本写入受保护压缩码流缓冲。', 'OEMCrypto/CDM 安全输出契约。', '硬件职责已标示，具体 crypto IP 待确认。'),
    module('wv-video', 'Video HW / VPU', 'hardware', 'Read bitstream · write protected pixels',
           '读取受保护压缩码流，完成视频解码，并写入受保护像素缓冲。输入与输出分别使用视频驱动配置的安全访问上下文。', 'VIDC video_smem.c secure bitstream/pixel 映射；日志 c2.qti.avc.decoder.secure。'),
    module('wv-dpu', 'Display HW / MDSS', 'hardware', 'Protected scanout via display SMMU',
           '通过显示 SMMU 读取扫描缓冲并输出画面。扫描源由合成路径选择，可来自解码输出或受保护合成结果。', 'Hoya/qdidriver/.../mdss_platform_memmgr.c:424、1202；OpenWFD source.c:746。'),
    module('wv-plain-dp', 'SoC DP Output (Without HDCP)', 'display', 'DisplayPort output',
           '输出 DisplayPort 视频，连接串行器。', 'static/diagrams/cockpit-drm-playback-architecture.html · Display Output。'),
    module('wv-plain-serializer', 'Serializer (Without HDCP)', 'display', 'DP RX · GMSL TX',
           '接收 DP 视频并转换为 GMSL，发送到屏端解串器。', 'static/diagrams/cockpit-drm-playback-architecture.html · Display Output。'),
    module('wv-plain-deserializer', 'Deserializer (Without HDCP)', 'display', 'GMSL RX · panel output',
           '接收 GMSL 视频，还原为屏幕所需的面板接口信号。', 'static/diagrams/cockpit-drm-playback-architecture.html · Display Output。'),
    module('wv-plain-panel', 'Display Panel (Without HDCP)', 'display', 'Panel interface',
           '接收面板接口视频并显示画面。', 'static/diagrams/cockpit-drm-playback-architecture.html · Display Output。'),
    module('wv-hdcp-dp', 'SoC DP Output (HDCP)', 'display', 'HDCP TX',
           '作为 DP 链路的 HDCP 发送端，执行认证并加密视频输出。', 'static/diagrams/cockpit-drm-playback-architecture.html · Display Output。'),
    module('wv-hdcp-serializer', 'Serializer (HDCP)', 'display', 'DP HDCP RX · GMSL HDCP TX',
           '接收 DP 链路的受保护视频，转换为 GMSL，并作为下游 HDCP 发送端输出。', 'static/diagrams/cockpit-drm-playback-architecture.html · Display Output。'),
    module('wv-hdcp-deserializer', 'Deserializer (HDCP)', 'display', 'GMSL HDCP RX',
           '作为 GMSL 链路的 HDCP 接收端，完成认证和视频解密，再通过面板接口送往屏幕。', 'static/diagrams/cockpit-drm-playback-architecture.html · Display Output。'),
    module('wv-hdcp-panel', 'Display Panel (HDCP path)', 'display', 'Panel interface',
           '接收解串器输出的面板接口视频并显示画面。', 'static/diagrams/cockpit-drm-playback-architecture.html · Display Output。'),
]

FLOWS = [('1 · Player ↔ License Proxy / Service',
  '控制流：许可证请求/响应',
  'HTTPS + MediaDrm / EME',
  '播放器转发 getKeyRequest/message 产生的 challenge，并通过 provideKeyResponse/update 提交许可证响应。设备 provisioning 使用独立的请求与响应接口。'),
 ('2 · MediaDrm → DrmHalAidl → WVDrmPlugin', '控制流：会话和密钥状态', 'JNI / AIDL Binder', '通过 JNI 和 AIDL Binder 传递会话、许可证和密钥状态操作。'),
 ('3 · MediaCrypto → MediaCodec',
  '引用流：session / ICrypto',
  'sessionId · ICrypto object',
  '将 DRM session ID 关联到 crypto 上下文，并将 ICrypto 引用交给 MediaCodec。'),
 ('4 · MediaCodec → CCodecBufferChannel → CryptoHalAidl → WVCryptoPlugin',
  '控制流：decrypt；引用流：加密源和安全目标',
  'queueSecureInputBuffer · NATIVE_HANDLE',
  '以密文缓冲为 source，以受保护 C2 block 的 native_handle 为 destination。安全解密完成后将对应 block 交给 codec。'),
 ('5A · OEMCrypto → QSEEComAPI → qseecom driver',
  '控制流：源码默认分支',
  'QSEECom_send_cmd · ioctl',
  '产品源码配置 WIDEVINE_USES_SMCINVOKE=false，经 QSEECom API 和 /dev/qseecom 提交命令。'),
 ('5B · OEMCrypto → TA Loader / Mink → smcinvoke',
  '控制流：库内可用分支',
  'Mink object invoke · ioctl',
  '预编译库提供 TA Loader/Mink 调用，经 /dev/smcinvoke 提交 object invoke。'),
 ('6 · qcom_scm → qcom_scm_hab → qcpe_service → TEE',
  '控制流：安全调用与返回',
  'MM_QCPE_VM1 · HAB · secure monitor',
  'SCM 通过 HAB 发送安全调用消息，QNX QCPE 处理后执行安全监控调用，进入 TEE 并返回结果。'),
 ('7 · OEMCrypto ↔ libcpion', '引用流：受保护内存支持', 'cp_ion / cp_qce / DMA-BUF / VMMEM', 'OEMCrypto 使用受保护内存辅助接口进行分配和映射。'),
 ('8 · Encrypted input → Crypto HW → Secure compressed buffer',
  '数据流：密文 → 受保护的压缩码流',
  'Secure decrypt output',
  '播放器填入密文样本，安全解密实现将压缩码流写入独立的受保护目标缓冲。'),
 ('9 · Codec2 → video FE → hyp_video_be → videoCore / VIDC',
  '控制流与引用流：视频队列、buffer ID',
  'video_fe_ioctl · HAB / MM_VID',
  'Codec 库经 intercept 加载 video FE，通过 MM_VID 通道传递视频控制命令和已有缓冲的 export ID。'),
 ('10 · Secure compressed buffer → VPU → Secure decoded frames',
  '数据流：受保护压缩输入 → 受保护像素输出',
  'CP_B_VIDEO / CP_P_VIDEO contexts',
  'VPU 使用 CP_B_VIDEO 上下文读取压缩码流，使用 CP_P_VIDEO 上下文写入解码像素。'),
 ('11 · CCodecBufferChannel → SurfaceFlinger / HWC → msm-hyp / wfd_kms',
  '引用流：graphic block / fence / dma_buf',
  'queueToOutputSurface · secure layer',
  '通过 graphic block、fence 和 dma_buf 提交图层。HWC 根据安全标志和合成需求配置受保护显示路径。'),
 ('12 · wfd_kms → HAB → wfd_be → OpenWFD / MDSS',
  '引用流：export ID → PMEM handle',
  'HAB export / import · WFD secured source',
  'QNX 后端导入 HAB buffer ID，创建引用对应 PMEM handle 的 OpenWFD image。'),
 ('13 · Scanout buffer → Display SMMU / MDSS → SoC DP Output',
  '数据流：读取实际扫描缓冲',
  'Secure context bank · device address',
  'MDSS 将扫描缓冲映射至安全 context bank，显示引擎按设备地址读取，并向 DP 接口输出视频像素。'),
 ('14 · Widevine TA ↔ OPS ↔ QNX OPS Listener ↔ MDSS / HDCP',
  '输出策略流：最低保护要求、拓扑与状态',
  'qseecom_daemon · OpenWFD OPS interface',
  'OPS 向 QNX 显示服务提交保护要求并获取拓扑、认证和加密状态。保护条件不足时限制受保护输出。'),
 ('15 · SoC DP Output → Serializer → Deserializer → Display Panel',
  '数据流：无 HDCP 显示链路',
  'DP · GMSL · Panel interface',
  'DP 视频经串行器转换为 GMSL，在屏端解串后通过面板接口显示。'),
 ('16 · SoC DP Output → Serializer → Deserializer → Display Panel',
  '数据流：HDCP 显示链路',
  'DP + HDCP · GMSL + HDCP · Panel interface',
  'SoC 为 DP HDCP 发送端。串行器接收受保护 DP，并发送受保护 GMSL；屏端解串器完成 GMSL HDCP 接收和解密，再输出面板接口视频。')]

FLOW_STATUS = {'2': '当前 factory 日志为 AIDL。', '5A': '实际设备库及运行分支待确认。', '5B': '运行选择待确认。', '7': '实际映射后端及 crypto IP 待确认。', '14': '实际 HDCP 版本、认证和加密状态待验证。'}

def render_widevine():
    groups = [('Content Services', 'cloud'), ('Android Guest · User Space', 'aaos'),
              ('Android Guest · Kernel', 'guest-kernel'), ('QNX Host', 'qnx'),
              ('Qualcomm TEE · Trusted Software', 'tee'), ('Memory / Secure Buffers', 'buffer'),
              ('Hardware', 'hardware'), ('Display Output', 'display')]
    index = ''.join('<section class="sw-index-group"><h4>'+title+'</h4>'+('<p class="wv-source" lang="zh-CN">显示输出为两种候选方案。若 OTT 要求 HDCP 保护及相关认证，采用 HDCP 链路；器件能力与量产配置待确认。</p>' if domain=='display' else '')+'<ul class="sw-index-list">'+''.join(
        '<li><button class="sw-index-entry" id="sw-index-'+m['id']+'" type="button" data-sw-module="'+m['id']+'" aria-pressed="false"><span class="sw-index-name">'+escape(m['name'])+'</span><span class="sw-index-duty" lang="zh-CN">'+escape(m['duty'])+('<span class="wv-source wv-status">状态：'+escape(m['status'])+'</span>' if m['status'] else '')+'<span class="wv-source">来源：'+escape(m['source'])+'</span></span></button></li>'
        for m in MODULES if m['domain']==domain)+'</ul></section>' for title,domain in groups)
    rows = ''.join('<tr>'+''.join('<td>'+escape(cell)+(('<span class="wv-source wv-status">状态：'+escape(FLOW_STATUS[row[0].split(' · ', 1)[0]])+'</span>') if j==3 and row[0].split(' · ', 1)[0] in FLOW_STATUS else '')+'</td>' for j,cell in enumerate(row))+'</tr>' for i,row in enumerate(FLOWS))
    controls = ''.join('<button type="button" data-widevine-focus="'+key+'" aria-pressed="'+str(key=='all').lower()+'">'+title+'</button>'
        for key,title in [('all','All'), ('control','Control calls'), ('data','Media data'), ('buffer','Buffer / handles'), ('output','Output policy')])
    return f'''
<div class="sw-page sw-widevine-page" id="sw-widevine-view" hidden>
  <div class="sw-ota-nav"><button class="sw-back" id="sw-widevine-back" type="button">← High-Level software architecture</button><span>Widevine DRM software architecture</span></div>
  <div class="sw-ota-controls" role="group" aria-label="Highlight Widevine flow type"><span>Interaction paths</span>{controls}</div>
  <div class="sw-board-scroll sw-ota-scroll" aria-label="Widevine integrated software layers, secure buffers, hardware and display architecture">{render_graph(MODULES)}</div>
  <div class="sw-ota-inspector" id="sw-widevine-inspector" role="status" aria-live="polite">Select a component to highlight its connections. Right-click to clear selection.</div>
  <section class="wv-process" aria-labelledby="wv-process-title" lang="zh-CN"><h3 id="wv-process-title">播放过程与模块交互</h3>{render_sequence()}</section>
  <section class="sw-index" aria-labelledby="sw-widevine-index-title"><div class="sw-section-heading"><h3 id="sw-widevine-index-title">Module responsibilities</h3></div>{index}</section>
  <section class="sw-interfaces" aria-labelledby="sw-widevine-flows-title"><div class="sw-section-heading"><h3 id="sw-widevine-flows-title">Interfaces &amp; data flow</h3></div><div class="sw-flow-table-wrap"><table class="sw-flow-table"><thead><tr><th>Interaction</th><th>Flow type</th><th>API / transport</th><th>Behavior</th></tr></thead><tbody>{rows}</tbody></table></div></section>

</div>''', {'modules': MODULES, 'flows': FLOWS}
