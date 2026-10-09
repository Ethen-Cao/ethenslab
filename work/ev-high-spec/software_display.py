"""Display interfaces in the current QNX host and Android guest source tree."""
from html import escape

from software_display_graph import render_graph


QNX_DISPLAY = 'QNX/HQX-4-5-5-0_HLOS_DEV_QNX/apps/qnx_ap/AMSS/multimedia/display/Hoya/'
ANDROID = 'android/android/'
QNX_HAB = 'QNX/HQX-4-5-5-0_HLOS_DEV_QNX/apps/qnx_ap/AMSS/multimedia/hab/driver/hypervisor/qvm/qnx/'
GRAPHICS_CONFIG = 'bsp/apps/qnx_ap/boards/display/adp_star_sda8295/config/graphics_HBEZ.conf'


def module(mid, name, domain, short, duty, source, status='', kind='component'):
    return dict(id=mid, name=name, domain=domain, short=short, duty=duty,
                source=source, status=status, kind=kind)


MODULES = [
    module('display-cluster', 'Cluster HMI / Kanzi', 'qnx', 'Driver views · Screen windows',
           '生成仪表界面，通过 Screen、EGL 和 GLES 接口提交窗口画面。',
           'cluster_source_code/apps/clusterkanzi/ClusterHMI/CMakeLists.txt:119、188–190。',
           'QNX 构建链接已核实；窗口和屏幕分配以运行配置为准。'),
    module('display-qnx-render', 'EGL / OpenGL ES', 'qnx', 'QNX rendering libraries',
           '提供图形上下文与绘制接口，将渲染结果写入窗口缓冲。',
           'bsp/apps/qnx_ap/target/filesets/qc.gfx.umd.build:7–9；'+GRAPHICS_CONFIG+':3–5。'),
    module('display-screen', 'QNX Screen', 'qnx', 'Windows · composition · display',
           '管理窗口、图像缓冲和合成路径，按 graphics 配置使用 OpenWFD 显示驱动。',
           GRAPHICS_CONFIG+':3–5、10–15；cluster_source_code/apps/clusterkanzi/ClusterHMI/CMakeLists.txt:119、188–190。'),
    module('display-wfd-client', 'libopenwfd_qnx', 'qnx', 'Native OpenWFD client',
           '封装 OpenWFD 客户端调用，通过本地 read/write IPC 向显示服务提交请求并读取应答。',
           QNX_DISPLAY+'wfd_client_qnx/src/user_qnx_utils.c:50、715–718；'+GRAPHICS_CONFIG+':10–15。'),
    module('display-wfd-be', 'wfd_be', 'qnx', 'HAB backend · buffer imports',
           '接收来宾 OpenWFD wire 请求，导入 HAB 缓冲 ID，并用对应 PMEM handle 创建图像源。',
           QNX_DISPLAY+'wfd_be_qnx/src/host_hab_utils.c:168、191；wfd_be_qnx/src/wire_host.c:1558、1580、1607。',
           '源码接口已核实；运行实例和通道配置需结合启动配置确认。'),
    module('display-wfd-server', 'OpenWFD Server', 'qnx', 'Request dispatch · display runtime',
           '承载本地 OpenWFD 请求处理和显示运行时；核心库、QDI/HAL 与面板库属于其实现组件。',
           QNX_DISPLAY+'wfd_server_qnx/src/wfd_server.c；openwfd/src/wfd_clientmgr.c。',
           '服务实例、设备和输出映射以板级配置为准。'),
    module('display-wfd-core', 'OpenWFD Core', 'qnx', 'Sources · pipelines · commits',
           '管理图像源、显示端口、管线绑定与提交，调用底层显示接口执行配置。',
           QNX_DISPLAY+'openwfd/src/source.c；pipeline.c；port.c；wfd_commitmgr.c。'),
    module('display-mdss', 'QDI / MDP / MDSS', 'qnx', 'Memory mapping · scanout control',
           '将 PMEM 缓冲映射为显示硬件地址，配置图层、扫描管线和提交，通过面板回调配置所选输出接口。',
           QNX_DISPLAY+'qdidriver/source/platform/memmgr/mdss_platform_memmgr.c；platform/mdss/mdss_drv.c；coredriver/mdp/mdp_dc.c:599–607。'),
    module('display-interface-driver', 'DSI / DP Driver & HAL', 'qnx', 'Output modes · link · PHY control',
           '在 OpenWFD 服务内配置 DSI/DP 输出模式、链路时序、时钟和 PHY，通过 HAL 访问接口硬件。',
           QNX_DISPLAY+'qdidriver/source/coredriver/dsi/dsi_host.c；dp/dp_host.c；wfd_server_qnx/common.mk:120–139；bsp/apps/qnx_ap/boards/display/common/panels/DSI_COMMON_QC_0/src/DSI_COMMON_QC_0.c:1017、1136、1431–1440；DP0_COMMON_QC/src/DP0_COMMON_QC.c:676–801、954。',
           '驱动与 HAL 为服务内部组件；启用的接口以板级配置为准。'),
    module('display-config', 'Display Configuration', 'qnx', 'Screen · WFD · panel settings',
           '提供 Screen 驱动、OpenWFD 设备和面板参数，决定具体产品的显示路由。',
           GRAPHICS_CONFIG+'；'+'bsp/apps/qnx_ap/boards/display/adp_star_sda8295/config/qcdisplaycfg_HBEZ.xml:83–102。',
           '配置文件属于静态输入；屏幕拓扑需按选用配置核对。', kind='config'),
    module('display-panel-driver', 'Panel / Bridge Drivers', 'qnx', 'Modes · link · power',
           '在显示服务内适配面板和桥接器，处理模式、链路、电源及面板状态。',
           QNX_DISPLAY+'qdidriver/source/coredriver/oemcfg/mdss_oemcfg.c:477–508；bsp/apps/qnx_ap/boards/display/adp_star_sda8295/config/qcdisplaycfg_HBEZ.xml:332–350。',
           '具体面板库、桥接器和物理连接以板级配置为准。'),
    module('display-qnx-gpu', 'QNX KGSL Graphics', 'qnx', 'Adreno EGL / GLES · kgsl',
           '为 QNX 图形库提供 GPU 设备接入，执行绘制命令并访问渲染缓冲。',
           'bsp/apps/qnx_ap/target/filesets/qc.gfx.build:6；qc.gfx.umd.build:7–9；'+GRAPHICS_CONFIG+':3–5。',
           '镜像清单包含 kgsl 与 EGL/GLES 库。'),
    module('display-apps', 'IVI Application Clients', 'aaos', 'Surfaces · rendered frames',
           '创建界面与 Surface，通过图形接口绘制并提交应用帧。',
           ANDROID+'frameworks/base/core/java/android/view/ViewRootImpl.java:2231、8319。',
           '调用方集合；具体应用和显示分配以产品配置为准。'),
    module('display-wms', 'WindowManagerService', 'aaos', 'Window state · layer transactions',
           '管理窗口状态、层级和可见性，通过 SurfaceControl 事务更新合成场景。',
           ANDROID+'frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java:2986；com/android/server/wm/DisplayContent.java:4879。'),
    module('display-dms', 'DisplayManagerService', 'aaos', 'Logical displays · display policy',
           '管理逻辑显示、显示属性和策略，协调框架中的显示状态。',
           ANDROID+'frameworks/base/services/core/java/com/android/server/display/DisplayManagerService.java:1487；LocalDisplayAdapter.java:823、1011。'),
    module('display-bufferqueue', 'BufferQueue / BLAST', 'aaos', 'Buffer handles · local fences',
           '在帧生产者与消费者之间交换缓冲句柄、队列状态和本域同步 fence。',
           ANDROID+'frameworks/native/libs/gui/BLASTBufferQueue.cpp:143、570；BufferQueueProducer.cpp；BufferQueueConsumer.cpp。'),
    module('display-flinger', 'SurfaceFlinger', 'aaos', 'Layer state · composition',
           '消费图层缓冲，选择合成方式，将图层或 client target 交给 Composer。',
           ANDROID+'frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp。'),
    module('display-gralloc', 'gralloc', 'aaos', 'Allocate · import · buffer handles',
           '按尺寸、格式与 usage 分配或导入图像缓冲，提供供 GPU 和显示路径使用的句柄。',
           ANDROID+'hardware/qcom/display/gralloc/gr_buf_mgr.cpp:1011；gr_dma_mgr.cpp。'),
    module('display-composer', 'HWC Composer', 'aaos', 'Validate · present · layer policy',
           '接收图层与 client target，执行 validate/present，并调用 SDM 完成显示提交。',
           ANDROID+'hardware/qcom/display/sdm/libs/hwc2/hwc_session.cpp；hwc_display.cpp；composer-aidl。',
           '源码包含 HWC2 与 AIDL 实现；部署接口版本需按运行配置确认。'),
    module('display-sdm', 'SDM', 'aaos', 'Composition plan · display commit',
           '规划图层与硬件资源，组织显示提交，并经 DRM 适配层访问来宾显示驱动。',
           ANDROID+'hardware/qcom/display/sdm/libs/core/display_base.cpp；core/drm/hw_device_drm.cpp。'),
    module('display-drm-adapter', 'DRM Adapter', 'aaos', 'DRM objects · atomic submission',
           '将 SDM 的显示配置转换为 DRM 对象、属性与提交请求。',
           ANDROID+'hardware/qcom/display/libdrmutils/drm_master.cpp:166、183；vendor/qcom/proprietary/display/sde-drm/drm_atomic_req.cpp:153。'),
    module('display-renderengine', 'RenderEngine', 'aaos', 'GPU client composition',
           '按 SurfaceFlinger 请求执行 GPU 合成，将结果写入 client target 缓冲。',
           ANDROID+'frameworks/native/libs/renderengine；services/surfaceflinger。'),
    module('display-wfd-fe', 'msm-hyp / wfd_kms', 'aaos', 'WFD wire frontend · HAB',
           '实现来宾 DRM 显示端点，经 HAB 发送 OpenWFD 请求与缓冲 ID，并接收提交、垂直同步和热插拔事件。',
           ANDROID+'vendor/qcom/opensource/display-drivers/msm-hyp/wfd/wfd_kms.c:1089、1122、1932、2379–2394；wire_user.c；user_hab_utils.c。'),
    module('display-android-gpu', 'HGSL Guest GPU Frontend', 'aaos', 'GSL RPC · shared command queues',
           '向主机 GPU 后端请求图形资源与命令提交，使用 HAB RPC 和共享命令队列。',
           ANDROID+'kernel_platform/msm-kernel/drivers/soc/qcom/hgsl/hgsl_hyp_socket.c:19、50；hgsl_hyp.c:1400；hgsl.c:1099、1116；arch/arm64/configs/vendor/autogvm.config:110。'),
    module('display-gsl-be', 'GSL Guest Backend', 'qnx', 'gsl_hab_server · host GPU endpoint',
           '承接来宾图形请求，接入主机 HAB 与 KGSL 资源。',
           'QNX/HQX-4-5-5-0_HLOS_DEV_QNX/apps/qnx_ap/target/filesets/qc.gfx.be.build:9；launcher_scripts/vgfx.c:8；secpol/gsl_be_child.txt:7–14。',
           '后端为预编译组件，内部调度实现未展开。'),
    module('display-vm-memory', 'QVM Shared Communication Pipes', 'platform', 'HAB transport · shared regions',
           '建立 QVM 共享通信管道，供 HAB 消息收发使用；图像内存由缓冲导入与映射接口管理。',
           QNX_HAB+'hab_qvm_qnx.c:140–175；qvm_comm_qnx.c:21、60。'),
    module('display-vm-notify', 'VM Event Notification', 'platform', 'QVM shared-memory notifications',
           '通过 QVM 共享内存通知接口唤醒对端处理 HAB 数据。',
           QNX_HAB+'hab_qvm_qnx.c:140–175；qvm_comm_qnx.c:21、60。',
           'hyp_shm_* / hyp_shm_poke 为源码接口；具体 VM 配置另行定义。'),
    module('display-gpu', 'GPU', 'hardware', 'Render · compose · write frames',
           '执行图形绘制与 GPU 合成，将结果写入图像缓冲。',
           'QNX qc.gfx.build 与 qc.gfx.umd.build；Android kgsl.c 与 gr_buf_mgr.cpp。',
           '硬件职责抽象；图中不指定芯片型号。'),
    module('display-buffers', 'Frame Buffers', 'hardware', 'Pixel storage · shared references',
           '保存应用帧和合成结果；GPU 写入像素，显示引擎读取选定扫描源。',
           ANDROID+'hardware/qcom/display/gralloc/gr_buf_mgr.cpp；'+QNX_DISPLAY+'wfd_be_qnx/src/host_hab_utils.c；qdidriver/source/platform/memmgr/mdss_platform_memmgr.c。',
           kind='memory'),
    module('display-dpu', 'Display Engine / DPU', 'hardware', 'Read scanout · compose · output',
           '按驱动配置读取扫描缓冲，执行硬件图层处理并向输出接口发送像素。',
           QNX_DISPLAY+'qdidriver/source/coredriver/mdp；source/platform/memmgr/mdss_platform_memmgr.c。',
           '显示硬件抽象；DPU 实例与屏幕对应关系以配置为准。'),
    module('display-output', 'DSI / DP Controller & PHY', 'hardware', 'Output controller · physical interface',
           '接收显示引擎的扫描像素，由 DSI/DP 控制器组织链路传输，PHY 输出电气信号。',
           '硬件职责由接口驱动与 HAL 的寄存器操作体现：'+QNX_DISPLAY+'qdidriver/source/coredriver/dsi；dp；wfd_server_qnx/common.mk:118–128。',
           '硬件组件；接口实例与物理连接以板级配置为准。'),
    module('display-link', 'Panel Link / Bridge', 'output', 'Configured link adaptation',
           '按板级设计适配显示输出与面板之间的物理链路。',
           '板级显示配置与面板/桥接驱动接口；'+QNX_DISPLAY+'qdidriver/source/coredriver/mdp/mdp_dc.c。',
           '逻辑链路抽象；具体桥接器及连接拓扑待按产品配置核对。'),
    module('display-panel', 'Display Panels', 'output', 'Configured displays',
           '接收所分配显示链路的像素并呈现画面。',
           'bsp/apps/qnx_ap/boards/display/adp_star_sda8295/config/qcdisplaycfg_HBEZ.xml。',
           '端口、分辨率和显示硬件分配以产品配置为准。'),
]


FLOWS = [
    ('1 · Cluster HMI / Kanzi → EGL / OpenGL ES → QNX Screen',
     'Control / buffer references', 'Screen · EGL · GLES',
     'QNX 构建已链接 Screen、EGL 和 GLES；应用生成窗口帧并提交缓冲。'),
    ('2 · QNX Screen → libopenwfd_qnx ↔ OpenWFD Server',
     'Control / replies', 'Local QNX read/write IPC',
     '客户端向 /dev/openwfd_server_<id> 写入 wire 请求并读取应答；像素保留在图像缓冲中。'),
    ('3 · WindowManagerService / DisplayManagerService → SurfaceFlinger',
     'Control', 'Framework APIs · SurfaceControl transactions',
     '框架管理窗口和逻辑显示状态，SurfaceFlinger 接收图层与显示事务。'),
    ('4 · Apps → BufferQueue / Surface → SurfaceFlinger',
     'Buffer references / synchronization', 'GraphicBuffer handles · local fences',
     '提交缓冲句柄、帧信息及同步对象；BufferQueue 管理生产者与消费者之间的队列。'),
    ('5 · SurfaceFlinger → HWC Composer → SDM → DRM Adapter',
     'Control / buffer references', 'Validate · present · DRM atomic API',
     '选择硬件图层或 client composition，提交图层配置与所选扫描缓冲引用。'),
    ('6 · SurfaceFlinger → RenderEngine → HGSL → GSL Guest Backend → QNX KGSL; QNX EGL / GLES → QNX KGSL',
     'Control / pixel writes', 'Rendering APIs · HAB GSL RPC / shared queues · host GPU API',
     '来宾图形请求由 GSL 主机后端接入 KGSL；GPU 将绘制或合成结果写入目标缓冲。'),
    ('7 · gralloc ↔ Frame Buffers',
     'Buffer references', 'Allocation / import · native handles · DMA-BUF',
     '按格式与 usage 分配或导入缓冲；句柄供图形与显示组件引用。'),
    ('8 · DRM Adapter → msm-hyp / wfd_kms ↔ wfd_be',
     'Control / replies', 'DRM submit · OpenWFD wire requests · HAB',
     '来宾在提交前等待本域 acquire fence，再发送显示请求；fence FD 保留在来宾域。'),
    ('9 · msm-hyp / wfd_kms → wfd_be → OpenWFD Core',
     'Buffer references', 'HAB export ID / import · PMEM handle',
     '后端导入 HAB ID，用对应 PMEM handle 创建 OpenWFD image；跨域消息携带缓冲引用。'),
    ('10 · Display Configuration → OpenWFD Core → QDI / MDP / MDSS → Panel / Bridge Drivers → DSI / DP Driver & HAL',
     'Configuration / control', 'OpenWFD commit · QDI · panel / output interface APIs',
     '服务内的核心库与 QDI 配置图层、管线和内存映射；面板库通过 DSI/DP 接口驱动配置输出模式、链路和电源。'),
    ('11 · GPU → Frame Buffers → Display Engine / DPU → DSI / DP Controller & PHY → Panel Link → Display Panels',
     'Pixel data', 'Memory writes / scanout reads · configured physical link',
     'GPU 写入图像，显示引擎读取选定扫描缓冲并输出像素；物理路由按板级配置选择。'),
    ('12 · DSI / DP Driver & HAL → DSI / DP Controller & PHY',
     'Hardware configuration', 'Driver calls · HAL register access',
     '接口驱动通过 HAL 配置控制器、PHY、时钟与链路；该配置路径独立于硬件像素传输路径。'),
    ('13 · OpenWFD / MDSS → wfd_be → msm-hyp / wfd_kms → HWC / SurfaceFlinger',
     'Events / feedback', 'COMMIT_COMPLETE · VSYNC · HPD · local guest fences',
     '完成与显示事件经 HAB 返回，来宾处理事件并更新本域同步状态。QVM 的 hyp_shm_* / hyp_shm_poke 支撑 HAB 共享内存通知。'),
]


def render_display():
    groups = [('QNX Cluster', 'qnx'), ('AAOS IVI', 'aaos'),
              ('Virtualization', 'platform'), ('SoC Hardware / Memory', 'hardware'),
              ('Display Output', 'output')]
    index = ''.join(
        '<section class="sw-index-group"><h4>'+title+'</h4><ul class="sw-index-list">'
        + ''.join(
            '<li><button class="sw-index-entry" id="sw-index-'+m['id']
            +'" type="button" data-sw-module="'+m['id']+'" aria-pressed="false">'
            +'<span class="sw-index-name">'+escape(m['name'])+'</span>'
            +'<span class="sw-index-duty" lang="zh-CN">'+escape(m['duty'])
            +'</span></button></li>'
            for m in MODULES if m['domain'] == domain)
        +'</ul></section>' for title, domain in groups)
    rows = ''.join('<tr>'+''.join('<td>'+escape(cell)+'</td>' for cell in row)
                   +'</tr>' for row in FLOWS)
    controls = ''.join(
        '<button type="button" data-display-focus="'+key+'" aria-pressed="'
        +str(key == 'all').lower()+'">'+title+'</button>'
        for key, title in [('all', 'All'), ('control', 'Control calls'),
                           ('buffers', 'Buffer references'), ('pixels', 'Pixel data'),
                           ('events', 'Events / feedback')])
    return f'''
<div class="sw-page sw-display-page" id="sw-display-view" hidden>
  <div class="sw-ota-nav"><button class="sw-back" id="sw-display-back" type="button">← High-Level software architecture</button><span>Display software architecture</span></div>
  <div class="sw-ota-controls" role="group" aria-label="Highlight display interaction type"><span>Interaction paths</span>{controls}</div>
  <div class="sw-board-scroll sw-ota-scroll" aria-label="Display execution domains, software layers, shared buffers and physical output">{render_graph(MODULES)}</div>
  <div class="sw-ota-inspector" id="sw-display-inspector" role="status" aria-live="polite">Select a component to highlight its connections. Right-click to clear selection.</div>
  <section class="sw-index" aria-labelledby="sw-display-index-title"><div class="sw-section-heading"><h3 id="sw-display-index-title">Module responsibilities</h3><p lang="zh-CN">职责和源码来源列于下方；点击模块可查看源码来源；屏幕映射按产品配置核对。</p></div>{index}</section>
  <section class="sw-interfaces" aria-labelledby="sw-display-flows-title"><div class="sw-section-heading"><h3 id="sw-display-flows-title">Interfaces &amp; data flow</h3></div><div class="sw-flow-table-wrap"><table class="sw-flow-table"><thead><tr><th>Components</th><th>Flow type</th><th>API / transport</th><th>Behavior</th></tr></thead><tbody>{rows}</tbody></table></div></section>
  <div class="sw-provenance" lang="zh-CN">依据当前 QNX Hoya、Android 图形源码、HBEZ 图形配置与镜像清单整理。OpenWFD 核心、QDI/HAL 和面板库为服务内部组件。跨域传递 OpenWFD 请求、缓冲 ID 与事件，像素保存在帧缓冲中。屏幕端口、分辨率及物理链路以板级配置为准。</div>
</div>''', {'modules': MODULES, 'flows': FLOWS}
