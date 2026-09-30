"""Render the logical cockpit software view into the offline architecture page.

The blocks deliberately describe responsibilities, not project process names.  The
QNX side is grounded in the inspected HBEZ image and staged services; AAOS and MCU
blocks remain reference-level unless a module records more specific evidence.
"""

from html import escape


MODULES = [
    # QNX / Cluster
    dict(id="cluster-hmi", name="Cluster HMI", domain="qnx", short="Driver-facing views", duty="呈现仪表、抬头显示等驾驶员界面；消费经过规范化的车辆状态和告警，不负责底层显示设备控制。", evidence="HBEZ staged ClusterApp"),
    dict(id="animation-management", name="Animation Management", domain="qnx", short="Scenes & transitions", duty="统一管理动画播放请求与场景切换策略，协调 Animation Player 与 Display System 的时序；不直接承担具体画面播放。", evidence="HBEZ staged animmgr"),
    dict(id="animation-player", name="Animation Player", domain="qnx", short="Boot · screen-off playback", duty="播放仪表开机、息屏等具体动画，控制播放进度并向动画管理模块回报状态；画面通过 Display System 呈现。", evidence="Functional block; project executable mapping to validate"),
    dict(id="vehicle-state", name="Vehicle State & Alerts", domain="qnx", short="Signals · alerts", duty="接入并规范化车辆信号，形成供仪表、告警和其他消费者使用的车辆状态与事件语义。", evidence="HBEZ staged coreservice; generic boundary"),
    dict(id="ota-update", name="OTA & Update Management", domain="qnx", short="Packages · activation", duty="组织软件包校验、分发、安装、激活与失败恢复，并协调跨控制器固件更新。", evidence="QNX updater in image/startup"),
    dict(id="ambient-lighting", name="Ambient Lighting", domain="qnx", short="Scenes · zones", duty="根据车辆状态和用户选择协调座舱氛围灯场景、区域与效果；具体控制器通信在子系统图中定义。", evidence="HBEZ staged amblightserver"),
    dict(id="audio-system", name="Audio System", domain="qnx", short="Devices · routes · policy", duty="管理音频设备、播放与采集通路以及音频策略；通过底层接口连接编解码器、A2B 和 ADSP。提示音只是其使用方之一。", evidence="QNX ifs_audio; HBEZ staged audiomgr"),
    dict(id="display-system", name="Display System", domain="qnx", short="Screens · composition", duty="管理显示会话、屏幕与画面合成路径；对应已核实的 Screen、OpenWFD 及 MDP/MDSS 集成。", evidence="QNX ifs_display; ifs_graphics"),
    dict(id="camera-video-services", name="Camera & Video Services", domain="qnx", short="Capture · processing", duty="提供摄像头采集、视频处理和流生命周期能力，供监测与显示体验使用。", evidence="QNX ifs_camera; ifs_video"),
    dict(id="communication-services", name="Communication Services", domain="qnx", short="Intra / cross-domain", duty="提供域内消息、网络通信和跨虚拟机通道，并适配经 MCU 网关送来的车辆网络数据；每条业务接口需单独标注实际传输方式。", evidence="QNX HAB/io-pkt/io-vsock; staged someipd"),
    dict(id="power-management", name="Power Management", domain="qnx", short="Power · sleep · wake", duty="协调电源状态、休眠与唤醒流程，向应用及设备服务分发电源状态变化。", evidence="QNX power components; HBEZ staged powermgr"),
    dict(id="time-management", name="Time Management", domain="qnx", short="Clock · synchronization", duty="维护系统时间并协调跨域时钟同步，向需要统一时间基准的服务提供时间能力。", evidence="HBEZ staged systime; QNX HAB time synchronization"),
    dict(id="diagnostics", name="Diagnostics & Observability", domain="qnx", short="DTC · logs · health", duty="采集故障码、运行日志和健康状态，为定位问题及运维提供统一观测入口。", evidence="QNX diagnostics; staged dtcagent/vlogmanager"),
    dict(id="security", name="Security Services", domain="qnx", short="Keys · trusted access", duty="管理安全能力的调用边界、密钥相关接口与受保护资源访问；具体信任根由芯片和安全固件提供。", evidence="QNX image QSEE/keymaster components"),
    dict(id="bsp-audio", name="Audio Device & DSP I/O", domain="qnx", short="audio_service · A2B · ADSP", duty="提供音频设备、A2B 总线和 ADSP 的底层接入与流 I/O，供上层 Audio System 实施设备管理、通路和策略。", evidence="QNX ifs_audio: audio_service, a2b-app, ADSP images"),
    dict(id="bsp-display", name="Display & GPU Drivers", domain="qnx", short="MDSS · KGSL · WFD HAL", duty="提供显示控制器、GPU 与输出设备的硬件适配，支撑上层 Screen、OpenWFD 等显示能力。", evidence="QNX ifs_display/graphics: halmdss, kgsl, OpenWFD"),
    dict(id="bsp-camera", name="Camera Capture I/O", domain="qnx", short="AIS · sensor links", duty="封装摄像头传感器、输入链路和采集设备接口，为上层视频服务提供图像输入。", evidence="QNX ifs_camera: ais_server, camera libraries"),
    dict(id="bsp-video", name="Video Codec & Processing I/O", domain="qnx", short="videoCore · VPP", duty="接入视频编解码与处理硬件，提供编码、解码及图像处理所需的底层接口。", evidence="QNX ifs_video: videoCore, vppService"),
    dict(id="bsp-network", name="Ethernet & Network I/O", domain="qnx", short="io-pkt · EMAC · virtual NIC", duty="提供 QNX 网络协议栈、以太网控制器及虚拟网卡接口；车辆 CAN/LIN 驱动属于 MCU 域。", evidence="QNX ifs_coreservices io-pkt/devnp-virtio; startup EMAC"),
    dict(id="bsp-peripherals", name="Peripheral Bus I/O", domain="qnx", short="SPI · I²C · UART · GPIO", duty="提供 SPI、I²C、UART 和 GPIO 的设备访问能力，承接与 MCU 及板级外设相连的物理接口。", evidence="QNX ifs_coreservices spi_service/i2c_service/qcgpio; startup devc-quipv3"),
    dict(id="bsp-intervm", name="Inter-VM Transport I/O", domain="qnx", short="HAB · VSOCK", duty="提供 QNX 侧 HAB 与 VSOCK 端点的底层接入；业务消息、协议和路由由上层服务决定。", evidence="QNX HAB in ifs_coreservices; io-vsock in system image/startup"),
    dict(id="bsp-storage", name="Storage & Filesystem I/O", domain="qnx", short="UFS · eMMC · io-blk", duty="提供持久存储控制器和块设备接口，支撑文件系统、日志及升级包访问。", evidence="QNX ifs_disk devb-ufs/io-blk; startup storage mounts"),
    dict(id="bsp-power-thermal", name="Power & Thermal Devices", domain="qnx", short="Sleep · DCVS · ADC", duty="接入低功耗、动态电压频率和传感采样等硬件能力，供上层电源与热管理服务使用。", evidence="QNX image sleep_service/dcvs_service/adc_service/vsense_service"),
    dict(id="bsp-trusted", name="Trusted Hardware Interface", domain="qnx", short="QSEECom · Keymaster", duty="提供访问安全执行环境和密钥硬件能力的底层接口；授权策略由上层 Security Services 管理。", evidence="QNX ifs_disk/system image QSEECom and Keymaster libraries"),
    dict(id="qnx-rtos", name="QNX Neutrino RTOS", domain="qnx", short="Kernel · IPC · isolation", duty="提供实时调度、内存隔离与消息传递；设备资源管理器可运行在用户空间，不等同于单体内核驱动层。", evidence="QNX 7.1 platform architecture"),
    # AAOS / IVI reference view
    dict(id="ivi-applications", name="IVI Applications", domain="aaos", short="Media · navigation · UX", duty="承载媒体、导航、设置等面向乘员的应用体验；具体 APK 与产品功能需按 Android 镜像核对。", evidence="AAOS reference-level grouping"),
    dict(id="android-framework", name="Android Framework", domain="aaos", short="system_server · APIs", duty="提供通用 Android 应用框架 API 和系统服务，例如由 system_server 承载的进程、窗口及包管理服务。", evidence="AAOS reference-level grouping"),
    dict(id="car-framework", name="Car Framework", domain="aaos", short="CarService · Car APIs", duty="提供汽车专用 API 与服务边界，向应用开放车辆属性及座舱功能。", evidence="AAOS reference-level grouping"),
    dict(id="android-native-hal", name="Android Native Services & HAL", domain="aaos", short="Vehicle · audio · graphics", duty="通过原生服务与硬件抽象层连接车辆、音频和图形设备；实际 HAL 清单需按项目镜像核对。", evidence="AAOS reference-level grouping"),
    dict(id="widevine-drm", name="Widevine DRM", domain="aaos", short="License · secure playback", duty="协调 DRM 会话、许可证与受保护媒体播放，连接 Android MediaDrm、Widevine CDM / OEMCrypto、安全解码和输出保护；子视图依据高通集成文档与播放日志区分已确认行为和待核实部署。", evidence="Qualcomm Automotive Widevine Integration Guide + observed MediaDrm / secure decoder logs"),
    dict(id="android-os", name="Android OS & Runtime", domain="aaos", short="Runtime · kernel", duty="提供 Android 应用运行时、系统服务基础、进程隔离和内核能力。", evidence="AAOS reference-level grouping"),
    # MCU functional view from the supplied architecture reference. Supplier and chip names are generalized.
    dict(id="mcu-debug-shell", name="Debug Shell", domain="mcu", short="Commands", duty="提供 MCU 调试命令交互，辅助状态查询与问题定位。"),
    dict(id="mcu-can-app", name="CAN Application", domain="mcu", short="Signal handling", duty="处理 CAN 报文及解析后的车辆信号，并执行 MCU 侧应用逻辑。"),
    dict(id="mcu-spi-ivi", name="IVI SPI Service", domain="mcu", short="IVI messages", duty="接收、解析并分发来自 IVI 的 SPI 消息。"),
    dict(id="mcu-spi-cluster", name="Cluster SPI Service", domain="mcu", short="Cluster messages", duty="处理与仪表侧的 SPI 通信及消息分发。"),
    dict(id="mcu-system-monitor", name="System Monitor", domain="mcu", short="Health checks", duty="监测 CPU、任务和栈等运行状态，并处理异常监测结果。"),
    dict(id="mcu-power", name="Power Management", domain="mcu", short="Power states", duty="管理 MCU 供电状态及睡眠、唤醒相关流程。"),
    dict(id="mcu-mfg-diag", name="Manufacturing Diagnostics", domain="mcu", short="Factory tests", duty="提供生产制造阶段所需的诊断和测试入口。"),
    dict(id="mcu-periodic", name="Periodic Services", domain="mcu", short="Scheduled work", duty="调度周期性工作，例如网络管理和通信管理相关处理。"),
    dict(id="mcu-ota", name="OTA Service", domain="mcu", short="Firmware updates", duty="配合 SoC 完成 MCU 固件升级流程和状态管理。"),
    dict(id="mcu-logging", name="Logging", domain="mcu", short="Log export", duty="采集 MCU 日志，并向 SoC 侧输出日志信息。"),
    dict(id="mcu-freertos", name="FreeRTOS", domain="mcu", short="Scheduling", duty="提供 MCU 任务调度、同步和基础实时运行环境。"),
    dict(id="mcu-com", name="Com", domain="mcu", short="Signals", duty="负责通信信号与 I-PDU 的打包、解包和传递。"),
    dict(id="mcu-dcm", name="Dcm", domain="mcu", short="Diagnostics", duty="处理诊断请求、会话和诊断服务。"),
    dict(id="mcu-comm", name="ComM", domain="mcu", short="Channel modes", duty="协调通信通道的启用、休眠和模式切换。"),
    dict(id="mcu-dem", name="Dem", domain="mcu", short="DTC events", duty="管理诊断事件和故障码状态。"),
    dict(id="mcu-canif", name="CanIf", domain="mcu", short="CAN abstraction", duty="为上层提供 CAN 控制器和报文收发的统一接口。"),
    dict(id="mcu-cantp", name="CanTp", domain="mcu", short="ISO 15765-2", duty="实现 CAN 上的分段与重组传输，对接诊断数据传输。"),
    dict(id="mcu-cannm", name="CanNm", domain="mcu", short="Network state", duty="管理 CAN 网络节点的唤醒、保持和休眠协同。"),
    dict(id="mcu-nvm", name="NvM", domain="mcu", short="Persistent data", duty="向上层提供非易失性数据的读写与管理接口。"),
    dict(id="mcu-config", name="BSW Configuration", domain="mcu", short="Generated config", duty="集中提供 BSW 的通信、诊断等配置数据；它通常是配置代码，而非独立运行任务。"),
    dict(id="mcu-cdd", name="CDD", domain="mcu", short="Device services", duty="封装标准驱动接口之外的器件控制与集成逻辑。"),
    dict(id="mcu-pmic", name="Safety PMIC", domain="mcu", short="Power IC", duty="封装安全电源管理芯片的控制和状态访问；具体型号已脱敏。"),
    dict(id="mcu-rtc", name="RTC", domain="mcu", short="Timekeeping", duty="提供实时时钟器件的时间读取与设置接口。"),
    dict(id="mcu-eeprom", name="EEPROM", domain="mcu", short="Storage IC", duty="封装外部 EEPROM 的读写接口。"),
    dict(id="mcu-hsm", name="HSM", domain="mcu", short="Planned", duty="预留安全模块接口；是否启用及具体能力需以 MCU 实现为准。", optional=True),
    dict(id="mcu-canfd-driver", name="CAN FD Driver", domain="mcu", short="CAN FD", duty="控制 CAN FD 硬件及报文收发。"),
    dict(id="mcu-spi-driver", name="SPI Driver", domain="mcu", short="SPI", duty="控制与 IVI、仪表等设备相连的 SPI 总线。"),
    dict(id="mcu-port-driver", name="Port Driver", domain="mcu", short="Pins", duty="配置 MCU 引脚与端口复用，为相关外设提供基础引脚能力。"),
    dict(id="mcu-wdg-driver", name="Watchdog Driver", domain="mcu", short="Supervision", duty="控制看门狗硬件，用于软件运行监督。"),
    dict(id="mcu-core-driver", name="MCU Driver", domain="mcu", short="Clock · reset", duty="提供 MCU 时钟、复位和基础运行模式控制。"),
    dict(id="mcu-flash-driver", name="Flash Driver", domain="mcu", short="Flash access", duty="访问片内 Flash 和配置的程序存储区。"),
    dict(id="mcu-lin-driver", name="LIN Driver", domain="mcu", short="Planned", duty="预留 LIN 总线收发驱动；当前参考图标记为预留。", optional=True),
    dict(id="mcu-uart-driver", name="UART Driver", domain="mcu", short="Serial", duty="提供 UART 串口收发能力。"),
    dict(id="mcu-gpt-driver", name="GPT Driver", domain="mcu", short="Planned", duty="预留通用定时器驱动；当前参考图标记为预留。", optional=True),
    dict(id="mcu-i2c-driver", name="I²C Driver", domain="mcu", short="I²C", duty="提供 I²C 总线控制和器件访问能力。"),
    dict(id="mcu-adc-driver", name="ADC Driver", domain="mcu", short="Analog input", duty="采集并转换 MCU 模拟输入信号。"),
    dict(id="mcu-bootloader", name="Bootloader", domain="mcu", short="Start · update", duty="启动 MCU 应用并承接固件升级切换；校验及回滚策略需按实现核对。"),
    dict(id="mcu-hardware", name="Automotive MCU", domain="mcu", short="Compute · peripherals", duty="提供处理器、片内存储器和外设硬件资源；具体供应商与型号已脱敏。"),
    dict(id="hypervisor", name="VM Management", domain="platform", short="VM lifecycle · qvm", duty="创建、启动、配置与停止来宾虚拟机。当前平台由 QNX 主机承载 Android 来宾，qvm 配置定义 VM 的资源边界。", evidence="QVM configuration and runtime qvm process"),
    dict(id="hv-vcpu", name="vCPU Scheduling", domain="platform", short="Priority · CPU affinity", duty="管理来宾 vCPU 的调度优先级及物理 CPU 亲和性；配置中使用 cpu sched 与 runmask。"),
    dict(id="hv-memory", name="Memory Isolation & Mapping", domain="platform", short="Guest mappings · access control", duty="建立来宾内存映射并实施访问边界；内存范围与访问权限由 VM 配置定义。"),
    dict(id="hv-devices", name="Virtual Devices (VirtIO)", domain="platform", short="Network · block · console", duty="提供虚拟设备后端与来宾设备接口。当前配置包含 virtio-net、virtio-blk、virtio-console；各域中的前端驱动和主机网络栈保留在所属域。"),
    dict(id="hv-shmem", name="Shared Memory", domain="platform", short="Shared regions · peer access", duty="建立受控共享内存区域供域间交换数据。项目配置中 vdev-shmem 的 allow vm2-hab_* 约束 HAB 共享区；不将所有共享内存实现统称为 VirtIO。"),
    dict(id="hv-events", name="Interrupt & Event Notification", domain="platform", short="Virtual IRQ · notifications", duty="向来宾投递设备事件和共享内存通知。Doorbell 可作为该能力的实现机制；当前配置已确认 intr gic 虚拟中断，尚未确认独立 Doorbell 设备，不能将它标为已启用模块。"),
]

LAYERS = [
    ("Product Experience", ["cluster-hmi", "animation-player"]),
    ("Vehicle Domain Services", ["vehicle-state", "ota-update", "ambient-lighting"]),
    ("Platform Services", ["audio-system", "display-system", "animation-management", "camera-video-services", "communication-services", "power-management", "time-management", "diagnostics", "security"]),
    ("Device Integration & BSP", ["bsp-audio", "bsp-display", "bsp-camera", "bsp-video", "bsp-network", "bsp-peripherals", "bsp-intervm", "bsp-storage", "bsp-power-thermal", "bsp-trusted"]),
    ("QNX Neutrino Core", ["qnx-rtos"]),
]

AAOS_LAYERS = [
    ("Applications", ["ivi-applications"]),
    ("Framework", ["android-framework", "car-framework"]),
    ("Native / HAL", ["android-native-hal", "widevine-drm"]),
    ("Android OS", ["android-os"]),
]

MCU_BSW_SERVICES = ["mcu-com", "mcu-dcm", "mcu-comm", "mcu-dem", "mcu-canif", "mcu-cantp", "mcu-cannm", "mcu-nvm", "mcu-config"]
MCU_CDD_DEVICES = ["mcu-pmic", "mcu-rtc", "mcu-eeprom", "mcu-hsm"]
MCU_LAYERS = [
    ("Applications", ["mcu-debug-shell", "mcu-can-app", "mcu-spi-ivi", "mcu-spi-cluster", "mcu-system-monitor", "mcu-power", "mcu-mfg-diag", "mcu-periodic", "mcu-ota", "mcu-logging"]),
    ("BSW & RTOS", ["mcu-freertos", *MCU_BSW_SERVICES, "mcu-cdd", *MCU_CDD_DEVICES]),
    ("Drivers", ["mcu-canfd-driver", "mcu-spi-driver", "mcu-port-driver", "mcu-wdg-driver", "mcu-core-driver", "mcu-flash-driver", "mcu-lin-driver", "mcu-uart-driver", "mcu-gpt-driver", "mcu-i2c-driver", "mcu-adc-driver"]),
    ("Bootloader", ["mcu-bootloader"]),
    ("Hardware", ["mcu-hardware"]),
]

FLOWS = [
    ("QNX Cluster ↔ AAOS IVI", "ECU configuration read", "HAB", "HAB 业务示例：ecuconfig 接收 Android 读取请求并返回 vehicle_config；这不代表 HAB 的全部用途，写入路径尚未实现。"),
    ("QNX Cluster ↔ AAOS IVI", "RPC / service data", "TCP/IP over virtual LAN", "已在项目跨域服务源码中核实；不能仅凭类名认定为 Vsock。"),
    ("QNX Cluster → AAOS IVI", "CPU thermal status", "VSOCK", "powermgr 通过 VSOCK.POWERMGR 向 Android 发布 CPU 温度；VirtIO 虚拟设备归于 Virtualization 层。"),
    ("SoC ↔ MCU", "Control / status", "SPI / UART hardware links", "硬件图标注物理链路；业务消息到链路的映射仍待核实。"),
    ("MCU ↔ Vehicle Networks", "Vehicle signals", "CAN FD / CAN / LIN", "硬件图列出接口能力；实际网络配置以 MCU 固件为准。"),
]


def _module_button(module, context="board"):
    name = escape(module["name"])
    module_id = escape(module["id"])
    if context == "board":
        optional_class = " sw-module-planned" if module.get("optional") else ""
        return (
            f'<button class="sw-module{optional_class}" type="button" data-sw-module="{module_id}" '
            f'aria-pressed="false" aria-label="{name}">'
            f'<span class="sw-module-name">{name}</span>'
            f'<span class="sw-module-short">{escape(module["short"])}</span>'
            '</button>'
        )
    return (
        f'<li><button class="sw-index-entry" type="button" data-sw-module="{module_id}" '
        f'aria-pressed="false" id="sw-index-{module_id}">'
        f'<span class="sw-index-name">{name}</span>'
        f'<span class="sw-index-duty" lang="zh-CN">{escape(module["duty"])}</span>'
        '</button></li>'
    )


def _layer(label, ids, lookup, kind="qnx"):
    modules = "".join(_module_button(lookup[module_id]) for module_id in ids)
    modifier = " sw-layer-framework" if kind == "aaos" and label == "Framework" else ""
    if kind == "mcu" and label == "BSW & RTOS":
        modifier = " sw-mcu-bsw"
        services = "".join(_module_button(lookup[module_id]) for module_id in MCU_BSW_SERVICES)
        devices = "".join(_module_button(lookup[module_id]) for module_id in MCU_CDD_DEVICES)
        modules = (
            '<div class="sw-mcu-bsw-rtos">' + _module_button(lookup["mcu-freertos"]) + '</div>'
            '<div class="sw-mcu-bsw-services">' + services + '</div>'
            '<div class="sw-mcu-bsw-cdd">' + _module_button(lookup["mcu-cdd"])
            + '<div class="sw-mcu-cdd-devices">' + devices + '</div></div>'
        )
    return (
        f'<div class="sw-layer sw-layer-{kind}{modifier}">'
        f'<div class="sw-layer-label">{escape(label)}</div>'
        f'<div class="sw-layer-modules">{modules}</div>'
        '</div>'
    )


def render_software():
    lookup = {module["id"]: module for module in MODULES}
    qnx = "".join(_layer(*layer, lookup) for layer in LAYERS)
    aaos = "".join(_layer(*layer, lookup, kind="aaos") for layer in AAOS_LAYERS)
    mcu = "".join(_layer(*layer, lookup, kind="mcu") for layer in MCU_LAYERS)

    groups = [
        ("QNX Cluster", [m for m in MODULES if m["domain"] == "qnx"]),
        ("AAOS IVI", [m for m in MODULES if m["domain"] == "aaos"]),
        ("MCU", [m for m in MODULES if m["domain"] == "mcu"]),
        ("Virtualization", [m for m in MODULES if m["domain"] == "platform"]),
    ]
    index = "".join(
        f'<section class="sw-index-group"><h4>{escape(title)}</h4><ul class="sw-index-list">'
        + "".join(_module_button(module, "index") for module in items)
        + '</ul></section>'
        for title, items in groups
    )
    virtualization = "".join(_module_button(m) for m in MODULES if m["domain"] == "platform")
    flow_rows = "".join(
        '<tr>' + ''.join(f'<td>{escape(cell)}</td>' for cell in row) + '</tr>'
        for row in FLOWS
    )

    html = f'''
<div class="sw-page" id="sw-high-level-view">
  <div class="sw-board-scroll" aria-label="High-level software architecture diagram; scroll horizontally if needed">
    <div class="sw-board" lang="en" aria-label="High-level cockpit software architecture">
      <div class="sw-soc">
        <div class="sw-system-heading"><div><strong>SoC Platform</strong><small>QNX host + Android guest</small></div></div>
        <div class="sw-soc-domains">
          <section class="sw-domain sw-domain-qnx" aria-label="QNX Cluster domain">
            <div class="sw-domain-heading"><span class="sw-domain-symbol sw-qnx-symbol">Q</span><div><h3>QNX Cluster</h3><p>Real-time host domain</p></div><span class="sw-domain-os">QNX Neutrino</span></div>
            {qnx}
          </section>
          <div class="sw-cross-domain" aria-label="Cross-domain interfaces">
            <div class="sw-link-title">CROSS-DOMAIN<br>DATA FLOW</div>
            <div class="sw-link"><strong>HAB</strong></div>
            <div class="sw-link"><strong>TCP/IP</strong></div>
            <div class="sw-link"><strong>VSOCK</strong></div>
            <p>Transport is selected per interface.</p>
          </div>
          <section class="sw-domain sw-domain-aaos" aria-label="AAOS IVI domain">
            <div class="sw-domain-heading"><span class="sw-domain-symbol sw-aaos-symbol">A</span><div><h3>AAOS IVI</h3><p>Android guest domain</p></div></div>
            {aaos}
          </section>
        </div>
        <div class="sw-platform-bands">
          <div class="sw-hypervisor-band"><div class="sw-band-lead"><span>VIRTUALIZATION</span><small>Hypervisor capabilities</small></div><div class="sw-hv-modules">{virtualization}</div></div>
          <div class="sw-hardware-band"><span>SoC Hardware</span><span>CPU · GPU · ADSP · Memory Controller · Display Controller · Audio Interfaces · Ethernet MAC</span></div>
        </div>
      </div>
      <div class="sw-mcu-bridge"><div class="sw-bridge-line">↔</div><strong>SoC ⇄ MCU</strong><span>SPI / UART</span><small>Service mapping to be verified</small></div>
      <section class="sw-mcu" aria-label="MCU domain">
        <div class="sw-system-heading"><div><strong>MCU</strong><small>FreeRTOS · BSW · drivers</small></div></div>
        <div class="sw-mcu-layers">{mcu}</div>
        <p class="sw-mcu-legend">Dashed outline: planned interface</p>
        <div class="sw-vehicle-flow"><span>↕</span><strong>Vehicle Networks</strong><small>CAN FD · CAN · LIN</small></div>
      </section>
    </div>
  </div>

  <section class="sw-index" id="sw-module-index" aria-labelledby="sw-index-title">
    <div class="sw-section-heading"><div><h3 id="sw-index-title">Module responsibilities</h3></div><p lang="zh-CN">点击架构块可定位对应职责；模块名称保持英文，解释按业务边界编写。</p></div>
    {index}
    <p class="sw-platform-explainer" lang="zh-CN"><strong>Virtualization</strong> 展示 VM 管理、资源隔离、虚拟设备、共享内存与事件通知等基础能力。HAB、TCP/IP、VSOCK 保留在跨域通信层；Doorbell 属于通知机制，其具体实现需由平台配置确认。参考 <a href="https://www.qnx.com/developers/docs/7.1/com.qnx.doc.hypervisor.user/topic/virt/vdevs.html">QNX Virtual devices</a>。</p>
  </section>

  <section class="sw-interfaces" aria-labelledby="sw-interfaces-title">
    <div class="sw-section-heading"><div><h3 id="sw-interfaces-title">Interface & data-flow register</h3></div><p lang="zh-CN">表中业务是已核实的代表性例子，并不穷尽同一方案承载的接口；SoC–MCU 和车载网络行标注物理链路能力。</p></div>
    <div class="sw-flow-table-wrap"><table class="sw-flow-table"><thead><tr><th>Boundary</th><th>Data flow</th><th>Transport</th><th>Scope note</th></tr></thead><tbody>{flow_rows}</tbody></table></div>
  </section>

  <div class="sw-provenance" lang="zh-CN">QNX 域依据已检查的 HBEZ IFS 镜像、启动脚本及预置服务归纳。AAOS 软件块主要为功能级参考边界，Widevine 子视图另依据集成文档与播放日志标注证据；MCU 模块依据用户提供的架构资料绘制，尚未通过 MCU 镜像核实，供应商与芯片型号已脱敏。层级表达职责，不代表进程均运行在同一特权级。</div>
</div>'''
    return html, {"modules": MODULES, "flows": FLOWS}
