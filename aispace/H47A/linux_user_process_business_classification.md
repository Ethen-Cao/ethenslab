# Linux用户态进程业务分类

来源：[linux_process_inventory.md](linux_process_inventory.md)。本表只覆盖`空间类型=user`的稳定进程行，不包含内核线程。

## 分类口径

- 操作系统基础设施与通用运维：Linux通用能力，和车业务弱相关，例如启动、登录、ADB、日志、ramdump、NFS/RPC、基础网络、升级和配置。
- 车业务中间件（诊断/通信/数据）：直接承载车辆诊断、SOME/IP、车载以太网/PTP、ECU信息、车辆策略、车辆安全/IDPS等。
- 座舱多媒体与人机交互：专业垂直业务，包括Audio、Camera/Video、Display/GPU、HMI、Touch、DMS/OMS等。
- 虚拟化/GVM与跨域通道：qcrosvm、GVM生命周期、vhost/virtio后端、vsock和跨域设备通道。
- 芯片硬件平台与安全资源：SoC资源管理、功耗/热管理、DSP/RPC/GLINK/SCMI、VFIO/IOMMU、安全执行环境、FuSa和子系统生命周期。

## 汇总

| 业务分类 | 车相关性 | 稳定进程行数 | 说明 |
| --- | --- | --- | --- |
| 操作系统基础设施与通用运维 | 弱/否 | 41 | Linux通用能力、调试接入、日志、文件/网络基础服务、登录会话、升级与基础配置。 |
| 车业务中间件（诊断/通信/数据） | 强 | 21 | 直接承载车端诊断、SOME/IP/以太网、ECU信息、车辆策略、车载安全/IDPS、车辆数据适配。 |
| 座舱多媒体与人机交互 | 强 | 40 | 音频、显示、HMI、触摸、背光、相机/视频、DMS/OMS、座舱感知等专业垂直业务。 |
| 虚拟化/GVM与跨域通道 | 间接/平台 | 25 | qcrosvm、GVM生命周期、vhost/virtio后端、vsock和GVM跨域设备通道。 |
| 芯片硬件平台与安全资源 | 间接/平台 | 25 | SoC硬件资源、功耗/热管理、DSP/RPC/GLINK/SCMI、VFIO/IOMMU、安全执行环境和子系统生命周期。 |

## 子领域分布

| 业务分类 | 子领域 | 进程行数/实例数近似 |
| --- | --- | --- |
| 操作系统基础设施与通用运维 | 启动/服务管理 | 9 |
| 操作系统基础设施与通用运维 | 日志/文件/故障转储 | 9 |
| 操作系统基础设施与通用运维 | 调试接入/登录/远程访问 | 9 |
| 操作系统基础设施与通用运维 | 配置/存储/升级 | 6 |
| 操作系统基础设施与通用运维 | 通用网络/NFS | 5 |
| 操作系统基础设施与通用运维 | 其他OS支撑 | 4 |
| 操作系统基础设施与通用运维 | 安全/审计 | 1 |
| 车业务中间件（诊断/通信/数据） | 车辆策略/事件/数据适配 | 6 |
| 车业务中间件（诊断/通信/数据） | SOME/IP服务 | 6 |
| 车业务中间件（诊断/通信/数据） | 诊断/DTC/ECU信息 | 4 |
| 车业务中间件（诊断/通信/数据） | 车载以太网/时间同步/链路控制 | 3 |
| 车业务中间件（诊断/通信/数据） | 车载安全/IDPS | 2 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 33 |
| 座舱多媒体与人机交互 | Audio | 11 |
| 座舱多媒体与人机交互 | Camera/Video/DMS/OMS | 8 |
| 座舱多媒体与人机交互 | Touch/Input | 2 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 13 |
| 虚拟化/GVM与跨域通道 | GVM垂直设备后端 | 6 |
| 虚拟化/GVM与跨域通道 | GVM生命周期/电源/ramdump | 4 |
| 虚拟化/GVM与跨域通道 | GVM承载 | 1 |
| 虚拟化/GVM与跨域通道 | VSOCK通道 | 1 |
| 芯片硬件平台与安全资源 | 安全/VFIO/IOMMU/FuSa | 7 |
| 芯片硬件平台与安全资源 | DSP/RPC/GLINK/SCMI/子系统 | 6 |
| 芯片硬件平台与安全资源 | 计算/缓存/资源调度 | 6 |
| 芯片硬件平台与安全资源 | 电源/CPU频率 | 4 |
| 芯片硬件平台与安全资源 | 热管理 | 2 |

## 详细分类

| 业务分类 | 子领域 | 车相关性 | 进程名 | 实例数 | 父进程名 | 启动来源/服务 | 进程职责 | Socket数 | 是否硬件依赖 | 分类依据 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 操作系统基础设施与通用运维 | 其他OS支撑 | 弱/否 | bash | 1 | init | - | 待确认 | 2 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 其他OS支撑 | 弱/否 | qlf-cloud-server | 1 | init | qlf-cloud-server.service | QLF Cloud Service | 2 | 否 | qlf-cloud-server.service; QLF Cloud Service | 自动分类 |
| 操作系统基础设施与通用运维 | 其他OS支撑 | 弱/否 | systemd-journald | 1 | init | systemd-journald.service | Journal Service | 116 | 是 | systemd-journald.service; Journal Service; /dev/kmsg, /sys/fs/cgroup/system.slice/systemd-journald.service/memory.pressure | 自动分类 |
| 操作系统基础设施与通用运维 | 其他OS支撑 | 弱/否 | systemd-udevd | 1 | init | systemd-udevd.service | Rule-based Manager for Device Events and Files | 7 | 是 | systemd-udevd.service; Rule-based Manager for Device Events and Files; /sys/fs/selinux/status, /sys/fs/cgroup/system.slice/systemd-udevd.service/memory.pressure | 自动分类 |
| 操作系统基础设施与通用运维 | 启动/服务管理 | 弱/否 | (sd-pam) | 1 | systemd | - | 待确认 | 3 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 启动/服务管理 | 弱/否 | (sd-pam) | 1 | weston | - | 待确认 | 3 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 启动/服务管理 | 弱/否 | dbus-daemon | 1 | init | - | 待确认 | 17 | 是 | /sys/fs/selinux/status | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 启动/服务管理 | 弱/否 | init | 1 | - | - | 待确认 | 137 | 是 | /sys/fs/selinux/status, /dev/kmsg, /sys/fs/cgroup, /dev/watchdog0, /sys/fs/cgroup/init.scope/memory.pressure, /dev/autofs, /dev/kiumd, /dev/input/event1 | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 启动/服务管理 | 弱/否 | systemd | 1 | init | - | systemd系统/用户管理进程 | 10 | 是 | systemd系统/用户管理进程; /sys/fs/selinux/status, /sys/fs/cgroup/user.slice/user-0.slice/user@0.service, /sys/fs/cgroup/user.slice/user-0.slice/user@0.service/init.scope/memory.pressure | 自动分类 |
| 操作系统基础设施与通用运维 | 启动/服务管理 | 弱/否 | systemd-userdbd | 1 | init | systemd-userdbd.service | User Database Manager | 4 | 是 | systemd-userdbd.service; User Database Manager; /sys/fs/cgroup/system.slice/systemd-userdbd.service/memory.pressure | 自动分类 |
| 操作系统基础设施与通用运维 | 启动/服务管理 | 弱/否 | systemd-userwork: | 3 | systemd-userdbd | - | 待确认 | 4 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 安全/审计 | 弱/否 | auditd | 1 | init | auditd.service | Security Audit Logging Service | 4 | 否 | auditd.service; Security Audit Logging Service | 自动分类 |
| 操作系统基础设施与通用运维 | 日志/文件/故障转储 | 弱/否 | ana-syslog-mgr | 1 | init | ana-syslog-mgr.service | QLF SysLogMgr Service | 3 | 否 | ana-syslog-mgr.service; QLF SysLogMgr Service | 自动分类 |
| 操作系统基础设施与通用运维 | 日志/文件/故障转储 | 弱/否 | analyzer-file-manager | 1 | init | analyzer-file-manager.service | QLF FileMgr Service | 3 | 否 | analyzer-file-manager.service; QLF FileMgr Service | 自动分类 |
| 操作系统基础设施与通用运维 | 日志/文件/故障转储 | 弱/否 | dlt-daemon | 1 | init | - | 日志采集/管理服务 | 4 | 否 | 日志采集/管理服务 | 自动分类 |
| 操作系统基础设施与通用运维 | 日志/文件/故障转储 | 弱/否 | dlt-system | 1 | init | dlt-system.service | COVESA DLT system. Application to forward syslog messages to DLT, transfer system information, logs and files. | 2 | 否 | dlt-system.service; COVESA DLT system. Application to forward syslog messages to DLT, transfer system information, logs and files. | 自动分类 |
| 操作系统基础设施与通用运维 | 日志/文件/故障转储 | 弱/否 | log-collector | 1 | init | log-collector.service | QLF Minidump Extraction | 3 | 否 | log-collector.service; QLF Minidump Extraction | 自动分类 |
| 操作系统基础设施与通用运维 | 日志/文件/故障转储 | 弱/否 | logmgr | 1 | init | logmgr.service | logmgr | 2 | 否 | logmgr.service; logmgr | 自动分类 |
| 操作系统基础设施与通用运维 | 日志/文件/故障转储 | 弱/否 | subsys-ramdump-util | 1 | init | subsys-ramdump-util.service | subsys-ramdump-util Daemon | 3 | 是 | subsys-ramdump-util.service; subsys-ramdump-util Daemon; /sys/firmware/devicetree/base/soc@0/subsystem_ramdump_util@89b00000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/141, vfio | 自动分类 |
| 操作系统基础设施与通用运维 | 日志/文件/故障转储 | 弱/否 | systemd-logind | 1 | init | systemd-logind.service | User Login Management | 8 | 是 | systemd-logind.service; User Login Management; /sys/fs/selinux/status, /sys/fs/cgroup/system.slice/systemd-logind.service/memory.pressure, /sys/devices/virtual/tty/tty0/active, /dev/tty2, /dev/input/event1, /dev/tty6, /dev/input/event0, /dev/input/event2 | 自动分类 |
| 操作系统基础设施与通用运维 | 日志/文件/故障转储 | 弱/否 | vlogmanager | 1 | init | vlogmanager.service | Voyah PVM LogManager App | 3 | 否 | vlogmanager.service; Voyah PVM LogManager App | 自动分类 |
| 操作系统基础设施与通用运维 | 调试接入/登录/远程访问 | 弱/否 | adbd | 1 | init | adbd.service | Adb Daemon Starter | 11 | 是 | adbd.service; Adb Daemon Starter; /dev/usb-ffs/adb/ep0, /dev/usb-ffs/adb/ep1, /dev/usb-ffs/adb/ep2, usb | 自动分类 |
| 操作系统基础设施与通用运维 | 调试接入/登录/远程访问 | 弱/否 | agetty | 1 | init | - | 登录终端 | - | 是 | 登录终端; /dev/hvc0 | 自动分类 |
| 操作系统基础设施与通用运维 | 调试接入/登录/远程访问 | 弱/否 | agetty | 1 | init | - | 登录终端 | - | 是 | 登录终端; /dev/ttyMSM0 | 自动分类 |
| 操作系统基础设施与通用运维 | 调试接入/登录/远程访问 | 弱/否 | agetty | 1 | init | - | 登录终端 | - | 是 | 登录终端; /dev/tty1 | 自动分类 |
| 操作系统基础设施与通用运维 | 调试接入/登录/远程访问 | 弱/否 | agetty | 1 | init | - | 登录终端 | - | 是 | 登录终端; /dev/tty2 | 自动分类 |
| 操作系统基础设施与通用运维 | 调试接入/登录/远程访问 | 弱/否 | busybox | 1 | init | - | 待确认 | 1 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 调试接入/登录/远程访问 | 弱/否 | busybox.nosuid | 1 | init | - | 待确认 | 3 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 调试接入/登录/远程访问 | 弱/否 | charon-systemd | 1 | init | - | 待确认 | 14 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 调试接入/登录/远程访问 | 弱/否 | proftpd: | 1 | init | - | 待确认 | 2 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 通用网络/NFS | 弱/否 | rpc.mountd | 1 | init | - | NFS/RPC服务 | 15 | 否 | NFS/RPC服务 | 自动分类 |
| 操作系统基础设施与通用运维 | 通用网络/NFS | 弱/否 | rpc.statd | 1 | init | - | NFS/RPC服务 | 8 | 否 | NFS/RPC服务 | 自动分类 |
| 操作系统基础设施与通用运维 | 通用网络/NFS | 弱/否 | rpcbind | 1 | init | rpcbind.service | RPC Bind | 8 | 否 | rpcbind.service; RPC Bind | 自动分类 |
| 操作系统基础设施与通用运维 | 通用网络/NFS | 弱/否 | systemd-networkd | 1 | init | systemd-networkd.service | Network Configuration | 12 | 是 | systemd-networkd.service; Network Configuration; /sys/fs/cgroup/system.slice/systemd-networkd.service/memory.pressure | 自动分类 |
| 操作系统基础设施与通用运维 | 通用网络/NFS | 弱/否 | systemd-resolved | 1 | init | systemd-resolved.service | Network Name Resolution | 11 | 是 | systemd-resolved.service; Network Name Resolution; /sys/fs/selinux/status, /sys/fs/cgroup/system.slice/systemd-resolved.service/memory.pressure | 自动分类 |
| 操作系统基础设施与通用运维 | 配置/存储/升级 | 弱/否 | fusermount3 | 1 | ecuconfig | - | 待确认 | 2 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 配置/存储/升级 | 弱/否 | leprop-service | 1 | init | - | 待确认 | 3 | 是 | /dev/socket/leprop-service type=STREAM | 自动分类，需源码/Owner复核 |
| 操作系统基础设施与通用运维 | 配置/存储/升级 | 弱/否 | nvdata-bspconfig | 1 | init | nvdata-bspconfig.service | NVData bspconfig Service | 2 | 是 | nvdata-bspconfig.service; NVData bspconfig Service; /dev/shm/lrmc_rq_4200_1_nvdata-bspconfi | 自动分类 |
| 操作系统基础设施与通用运维 | 配置/存储/升级 | 弱/否 | nvdata_service | 1 | init | nvdata_service.service | NVData Storage Service | 4 | 否 | nvdata_service.service; NVData Storage Service | 自动分类 |
| 操作系统基础设施与通用运维 | 配置/存储/升级 | 弱/否 | tpm | 1 | init | tpm.service | QLF Tool Policy Service | 3 | 是 | tpm.service; QLF Tool Policy Service; tpm | 自动分类 |
| 操作系统基础设施与通用运维 | 配置/存储/升级 | 弱/否 | updatemgr | 1 | init | updatemgr.service | updatemgr | 3 | 否 | updatemgr.service; updatemgr | 自动分类 |
| 车业务中间件（诊断/通信/数据） | SOME/IP服务 | 强 | someipd | 1 | bash | - | SOME/IP网络服务 | 17 | 是 | SOME/IP网络服务; eth | 自动分类 |
| 车业务中间件（诊断/通信/数据） | SOME/IP服务 | 强 | someipd | 1 | bash | - | SOME/IP网络服务 | 26 | 是 | SOME/IP网络服务; eth | 自动分类 |
| 车业务中间件（诊断/通信/数据） | SOME/IP服务 | 强 | someipd | 1 | bash | - | SOME/IP网络服务 | 28 | 是 | SOME/IP网络服务; eth | 自动分类 |
| 车业务中间件（诊断/通信/数据） | SOME/IP服务 | 强 | someipd | 1 | bash | - | SOME/IP网络服务 | 34 | 是 | SOME/IP网络服务; eth | 自动分类 |
| 车业务中间件（诊断/通信/数据） | SOME/IP服务 | 强 | someipd | 1 | bash | - | SOME/IP网络服务 | 28 | 是 | SOME/IP网络服务; eth | 自动分类 |
| 车业务中间件（诊断/通信/数据） | SOME/IP服务 | 强 | someipd | 1 | bash | - | SOME/IP网络服务 | 9 | 是 | SOME/IP网络服务; eth | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 诊断/DTC/ECU信息 | 强 | diag_service | 1 | init | - | 诊断/日志通道服务 | 4 | 是 | 诊断/日志通道服务; /dev/shm/lrmc_rq_3836_2_qdss-service, /dev/shm/lrmc_rq_2160_1_thermal-engine, /dev/shm/lrmc_rq_2564_8_diag_task, /dev/shm/lrmc_rq_2564_4_diag_service, /dev/shm/lrmc_rq_2564_3_diag_service, /dev/shm/lrmc_rq_2564_2_diag_service, /dev/shm/lrmc_rq_2564_1_diag_service, /dev/shm/lrmc_rq_2564_7_diag_service | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 诊断/DTC/ECU信息 | 强 | dtcagent | 1 | init | dtcagent.service | dtcagent | 7 | 否 | dtcagent.service; dtcagent | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 诊断/DTC/ECU信息 | 强 | ecuconfig | 1 | init | ecuconfig.service | ecuconfig | 3 | 是 | ecuconfig.service; ecuconfig; /dev/fuse | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 诊断/DTC/ECU信息 | 强 | ecuinfobe | 1 | init | ecuinfobe.service | ecuinfobe | 27 | 是 | ecuinfobe.service; ecuinfobe; /dev/shm/vcore_env | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 车载以太网/时间同步/链路控制 | 强 | ptp4l | 1 | init | - | 待确认 | 6 | 是 | /dev/ptp1, eth, ptp | 自动分类，需源码/Owner复核 |
| 车业务中间件（诊断/通信/数据） | 车载以太网/时间同步/链路控制 | 强 | rpcd | 1 | init | rpcd.service | rpcd | 11 | 是 | rpcd.service; rpcd; /dev/spidev21.0, spi | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 车载以太网/时间同步/链路控制 | 强 | rtl9071_daemon | 1 | init | rtl9071-daemon.service | RTL9071 Ethernet Controller Daemon | 4 | 是 | rtl9071-daemon.service; RTL9071 Ethernet Controller Daemon; /dev/spidev2.0, spi, eth, rtl9071 | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 车载安全/IDPS | 强 | xdja_idps | 1 | init | xdja_idps.service | XDJA IDPS Service | 4 | 否 | xdja_idps.service; XDJA IDPS Service | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 车载安全/IDPS | 强 | xdja_nidps | 1 | busybox.nosuid | - | 待确认 | 3 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | dmpolicy | 1 | init | dmpolicy.service | 显示策略服务：接收Android/GVM的IVCD topic和MCD屏幕状态，维护多屏背光/开关状态，通过rpcd下发CAN信号控制仪表/主屏/HUD/吸顶屏背光与吸顶屏角度，并向IVCD回传屏幕状态/吸顶屏反馈。 | 28 | 是 | 源码确认：voyah-cluster/dmpolicy；dmpolicy.service After/Wants ivcd/rpcd/mcd；处理TOPIC_BACKLIGHT_*、TOPIC_CEILING_SCREEN_*；通过rpcif_update_clusterstate下发CAN信号 | 源码复核 |
| 车业务中间件（诊断/通信/数据） | 车辆策略/事件/数据适配 | 强 | exd_adapter_linux | 1 | init | exd_adapter_linux.service | EXD Linux Adapter Service for 8397 Platform | 25 | 是 | exd_adapter_linux.service; EXD Linux Adapter Service for 8397 Platform; /dev/shm/fastdds_port7431, /dev/shm/fastdds_port7430, /dev/shm/fastdds_b908146d0f0336ec, /dev/shm/fastdds_port7429, /dev/shm/fastdds_port7428, /dev/shm/fastdds_19a0f3a64139b440, /dev/shm/fastdds_port7425, /dev/shm/fastdds_port7424 | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 车辆策略/事件/数据适配 | 强 | inframan | 1 | init | inframan.service | launch inframan server | 4 | 否 | inframan.service; launch inframan server | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 车辆策略/事件/数据适配 | 强 | ivcd | 1 | init | ivcd.service | ivcd | 16 | 否 | ivcd.service; ivcd | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 车辆策略/事件/数据适配 | 强 | mcd | 1 | init | mcd.service | mcd | 7 | 否 | mcd.service; mcd | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 车辆策略/事件/数据适配 | 强 | polaris-monitor | 1 | init | polaris-monitor.service | Polaris System Monitor Service | 5 | 是 | polaris-monitor.service; Polaris System Monitor Service; /sys/devices/virtual/thermal/thermal_zone36/temp, /sys/devices/virtual/thermal/thermal_zone64/temp, /sys/devices/virtual/thermal/thermal_zone123/temp, /sys/devices/virtual/thermal/thermal_zone92/temp, /sys/devices/virtual/thermal/thermal_zone26/temp, /sys/devices/virtual/thermal/thermal_zone2/temp, /sys/devices/virtual/thermal/thermal_zone54/temp, /sys/devices/virtual/thermal/thermal_zone113/temp | 自动分类 |
| 车业务中间件（诊断/通信/数据） | 车辆策略/事件/数据适配 | 强 | polarisd | 1 | init | polarisd.service | Polaris Core Daemon (Event & Message Broker) | 7 | 否 | polarisd.service; Polaris Core Daemon (Event & Message Broker) | 自动分类 |
| 座舱多媒体与人机交互 | Audio | 强 | a2b | 1 | init | a2b.service | A2B Audio Bus Daemon | 4 | 是 | a2b.service; A2B Audio Bus Daemon; /dev/i2c-18, i2c, audio | 自动分类 |
| 座舱多媒体与人机交互 | Audio | 强 | aud_fastrpcd | 1 | init | aud-fastrpcd.service | Audio Fastrpc Daemon | 3 | 是 | aud-fastrpcd.service; Audio Fastrpc Daemon; /dev/shm/lrmc_rq_3661_2_aud_fastrpcd, /dev/shm/lrmc_rq_3661_1_aud_fastrpcd, audio, fastrpc | 自动分类 |
| 座舱多媒体与人机交互 | Audio | 强 | audiomgr | 1 | init | audiomgr.service | audiomgr | 4 | 是 | audiomgr.service; audiomgr; audio | 自动分类 |
| 座舱多媒体与人机交互 | Audio | 强 | awe_audio_service | 1 | init | - | 待确认 | 20 | 是 | /dev/ipc_shmem, /dev/shm/lrmc_rq_5591_2_HabRecvSendThre, /dev/shm/lrmc_rq_1798_1_awe_audio_servi, /sys/kernel/debug/tracing/trace_marker, /sys/firmware/devicetree/base/soc@0/vfio_audio_adsp0@1/iommus, /dev/scmi_audio, /dev/kiumd, /dev/vfio/vfio | 自动分类，需源码/Owner复核 |
| 座舱多媒体与人机交互 | Audio | 强 | awe_command | 1 | init | awe-command.service | AWE Command Daemon | 4 | 是 | awe-command.service; AWE Command Daemon; /dev/ipc_shmem, /dev/shm/lrmc_rq_1716_1_ssr_event_reg, /sys/firmware/devicetree/base/soc@0/umd_audiolite@9185000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/16, /sys/kernel/debug/tracing/trace_marker, vfio | 自动分类 |
| 座舱多媒体与人机交互 | Audio | 强 | awe_linuxproxy | 1 | init | awe-linuxproxy.service | AWE linuxproxy | 5 | 否 | awe-linuxproxy.service; AWE linuxproxy | 自动分类 |
| 座舱多媒体与人机交互 | Audio | 强 | awe_packet_service | 1 | init | - | 待确认 | 21 | 是 | /dev/ipc_shmem, /sys/firmware/devicetree/base/soc@0/umd_audio_hlos1@9185000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/54, vfio, audio | 自动分类，需源码/Owner复核 |
| 座舱多媒体与人机交互 | Audio | 强 | camcorder_be_server | 1 | init | camcorderbeserver.service | Launch camcorder BE Server for LRH | 28 | 是 | camcorderbeserver.service; Launch camcorder BE Server for LRH; /dev/shm/lrmc_rq_5591_2_HabRecvSendThre, /dev/shm/fastdds_8c4d61ed1364a699, /dev/shm/fastdds_404bf134ee3aa057, /dev/shm/fastdds_16a1a7d344778c31, /dev/shm/fastdds_002e1f969f48e96b, /dev/shm/fastdds_4b80b252e9f3622a, /dev/shm/fastdds_a842883fbd3694ce, /dev/shm/fastdds_ed3c01aa2bc8606d | 自动分类 |
| 座舱多媒体与人机交互 | Audio | 强 | clusterchime | 1 | init | clusterchime.service | clusterchime | 21 | 是 | clusterchime.service; clusterchime; /dev/shm/fastdds_b908146d0f0336ec, /dev/shm/fastdds_4b80b252e9f3622a, /dev/shm/fastdds_404bf134ee3aa057, /dev/shm/fastdds_8c4d61ed1364a699, /dev/shm/fastdds_16a1a7d344778c31, /dev/shm/fastdds_002e1f969f48e96b, /dev/shm/fastdds_port7431, /dev/shm/fastdds_port7430 | 自动分类 |
| 座舱多媒体与人机交互 | Audio | 强 | pcm6360 | 1 | init | pcm6360.service | PCM6360 initializer | 2 | 是 | pcm6360.service; PCM6360 initializer; /dev/i2c-18, i2c | 自动分类 |
| 座舱多媒体与人机交互 | Audio | 强 | voyah_oms_server | 1 | init | voyah_oms_server.service | voyah_oms_server | 23 | 是 | voyah_oms_server.service; voyah_oms_server; /dev/shm/fastdds_port7431, /dev/shm/fastdds_port7430, /dev/shm/fastdds_b908146d0f0336ec, /dev/shm/fastdds_ed3c01aa2bc8606d, /dev/shm/fastdds_4b80b252e9f3622a, /dev/shm/fastdds_0b5ff3e7ee93a96e, /dev/shm/fastdds_a842883fbd3694ce, /dev/shm/fastdds_8c4d61ed1364a699 | 自动分类 |
| 座舱多媒体与人机交互 | Camera/Video/DMS/OMS | 强 | hyp_video_be | 1 | init | hyp-video-be.service | launch hyp-video-be | 3 | 是 | hyp-video-be.service; launch hyp-video-be; /dev/hab | 自动分类 |
| 座舱多媒体与人机交互 | Camera/Video/DMS/OMS | 强 | qcx_be_server | 1 | init | qcx_be_server.service | Launch QCX BE Server for LRH | 3 | 是 | qcx_be_server.service; Launch QCX BE Server for LRH; /dev/shm/sem.dzkatF, /dev/hab | 自动分类 |
| 座舱多媒体与人机交互 | Camera/Video/DMS/OMS | 强 | qcxserver | 1 | init | - | 待确认 | 7 | 是 | /dev/shm/lrmc_rq_1207_2_devcreate_0_1, /dev/shm/lrmc_rq_1207_1_qcxserver, /sys/firmware/devicetree/base/soc@0/vfio_cam_cdm_non_secure_cb/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/79, /sys/firmware/devicetree/base/soc@0/vfio_cam_ipe0_non_secure_cb/iommus, /dev/vfio/81 | 自动分类，需源码/Owner复核 |
| 座舱多媒体与人机交互 | Camera/Video/DMS/OMS | 强 | sv_hyp_server | 1 | init | - | 待确认 | 3 | 是 | /dev/hab | 自动分类，需源码/Owner复核 |
| 座舱多媒体与人机交互 | Camera/Video/DMS/OMS | 强 | sv_server | 1 | init | - | 待确认 | 4 | 是 | /dev/shm/lrmc_rq_2147_1_sv_server, /sys/firmware/devicetree/base/soc@0/vfio_eva@ab00000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/24, /dev/dma_heap/system, /dev/scmi_eva, /sys/kernel/smmu_faults/ab00000.vfio_eva/fsr_iova | 自动分类，需源码/Owner复核 |
| 座舱多媒体与人机交互 | Camera/Video/DMS/OMS | 强 | v4q_be_server | 1 | init | v4qbeserver.service | Launch V4Q BE Server for LRH | 7 | 是 | v4qbeserver.service; Launch V4Q BE Server for LRH; /dev/shm/vcore_env, /dev/hab, camera, cam | 自动分类 |
| 座舱多媒体与人机交互 | Camera/Video/DMS/OMS | 强 | videoCore | 1 | init | - | 待确认 | 4 | 是 | /dev/shm/lrmc_rq_1418_1_videoCore, /sys/firmware/devicetree/base/soc@0/vfio_vidc@aa00000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/61, /sys/firmware/devicetree/base/soc@0/vfio_vidc_non_secure_pixel_cb/iommus, /dev/vfio/69, /sys/firmware/devicetree/base/soc@0/vfio_vidc_non_secure_non_pixel_cb/iommus | 自动分类，需源码/Owner复核 |
| 座舱多媒体与人机交互 | Camera/Video/DMS/OMS | 强 | voyah_dms_server | 1 | init | voyah_dms_server.service | voyah_dms_server | 24 | 是 | voyah_dms_server.service; voyah_dms_server; /dev/shm/fastdds_b908146d0f0336ec, /dev/shm/fastdds_4b80b252e9f3622a, /dev/shm/fastdds_404bf134ee3aa057, /dev/shm/fastdds_8c4d61ed1364a699, /dev/shm/fastdds_16a1a7d344778c31, /dev/shm/fastdds_port7431, /dev/shm/fastdds_port7430, /dev/shm/fastdds_port7429 | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | TuanjieHmi | 1 | init | TuanjieHmi.service | [Graphics] TuanjieHmi | 27 | 是 | TuanjieHmi.service; [Graphics] TuanjieHmi; /dev/shm/fastdds_b908146d0f0336ec, /dev/shm/fastdds_19a0f3a64139b440, /dev/shm/fastdds_404bf134ee3aa057, /dev/shm/fastdds_8c4d61ed1364a699, /dev/shm/fastdds_fa031f2a34f80fdd, /dev/shm/fastdds_002e1f969f48e96b, /dev/shm/fastdds_0b5ff3e7ee93a96e, /dev/shm/fastdds_a842883fbd3694ce | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | VirtIOGPU2DBackendService | 1 | init | - | 待确认 | 3 | 是 | /dev/shm/lrmc_rq_4063_2_VirtIOGPU2DBack, /dev/shm/lrmc_rq_4063_1_VirtIOGPU2DBack, /dev/dma_heap/system, /dev/hab, virtio, gpu | 自动分类，需源码/Owner复核 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | amblightserver | 1 | init | amblightserver.service | amblightserver | 27 | 是 | amblightserver.service; amblightserver; /dev/shm/fastdds_port7431, /dev/shm/fastdds_port7430, /dev/shm/fastdds_b908146d0f0336ec, /dev/shm/fastdds_port7429, /dev/shm/fastdds_port7428, /dev/shm/fastdds_19a0f3a64139b440, /dev/shm/fastdds_port7415, /dev/shm/fastdds_port7414 | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | animmgr | 1 | init | animmgr.service | animmgr | 35 | 是 | animmgr.service; animmgr; /dev/shm/vcore_env | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | backlight_server | 1 | init | backlight_server.service | Launch backlight Server | 3 | 否 | backlight_server.service; Launch backlight Server | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | bridgechip_server | 1 | init | bridgechip_server.service | Launch Bridgechip Server | 3 | 否 | bridgechip_server.service; Launch Bridgechip Server | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | clusterservice | 1 | init | clusterservice.service | clusterservice | 117 | 是 | clusterservice.service; clusterservice; /dev/shm/fastdds_b908146d0f0336ec, /dev/shm/fastdds_4b80b252e9f3622a, /dev/shm/fastdds_404bf134ee3aa057, /dev/shm/fastdds_8c4d61ed1364a699, /dev/shm/fastdds_16a1a7d344778c31, /dev/shm/fastdds_0b5ff3e7ee93a96e, /dev/shm/fastdds_fa031f2a34f80fdd, /dev/shm/fastdds_a842883fbd3694ce | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | display_diag | 1 | init | display_diag.service | Launch display diag Server | 3 | 是 | display_diag.service; Launch display diag Server; display | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | display_monitor | 1 | init | display_monitor.service | Launch display monitor Server | 3 | 是 | display_monitor.service; Launch display monitor Server; display | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | gsl_hab_server | 15 | gsl_hab_server | gsl_hab_server.service | [Graphics] GSL HAB Server | 7-8 | 是 | gsl_hab_server.service; [Graphics] GSL HAB Server; /dev/hab, /dev/ksync, /dev/dma_heap/system, /dev/dma_heap/qcom,secure-pixel, qcom | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | gsl_hab_server | 1 | gsl_hab_server | gsl_hab_server.service | [Graphics] GSL HAB Server | - | 否 | gsl_hab_server.service; [Graphics] GSL HAB Server | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | gsl_hab_server | 1 | init | gsl_hab_server.service | [Graphics] GSL HAB Server | 3 | 是 | gsl_hab_server.service; [Graphics] GSL HAB Server; /dev/hab | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | kgsl | 1 | init | kgsl.service | [Graphics] KGSL | 61 | 是 | kgsl.service; [Graphics] KGSL; /dev/shm/lrmc_rq_1204_3_AdrenoOsLib, /dev/shm/lrmc_rq_1204_2_AdrenoOsLib, /dev/shm/lrmc_rq_1204_1_kgsl, /dev/dma_heap/system, /dev/dma_heap/qcom,secure-pixel, /sys/firmware/devicetree/base/soc@0/vfio_kgsl@1/iommus, /dev/kiumd, /dev/vfio/vfio | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | kgsl | 1 | init | kgsl.service | [Graphics] KGSL | 47 | 是 | kgsl.service; [Graphics] KGSL; /dev/shm/lrmc_rq_1206_3_AdrenoOsLib, /dev/shm/lrmc_rq_1206_2_AdrenoOsLib, /dev/shm/lrmc_rq_1206_1_kgsl, /dev/dma_heap/system, /dev/dma_heap/qcom,secure-pixel, /sys/firmware/devicetree/base/soc@0/vfio_kgsl@2/iommus, /dev/kiumd, /dev/vfio/vfio | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | openwfd_server | 1 | init | - | OpenWFD显示服务 | 4 | 是 | OpenWFD显示服务; /dev/shm/lrmc_rq_4952_1_weston, /dev/shm/lrmc_rq_4063_1_VirtIOGPU2DBack, /dev/shm/lrmc_rq_3368_1_openwfd_server, /sys/firmware/devicetree/base/soc@0/vfio_dpu_00@ae00000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/26, /sys/firmware/devicetree/base/soc@0/vfio_dpu_01_secure/iommus | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | openwfd_server | 1 | init | - | OpenWFD显示服务 | 4 | 是 | OpenWFD显示服务; /dev/shm/lrmc_rq_4952_2_weston, /dev/shm/lrmc_rq_4063_2_VirtIOGPU2DBack, /dev/shm/lrmc_rq_3369_1_openwfd_server, /sys/firmware/devicetree/base/soc@0/vfio_dpu_10@8c00000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/28, /sys/firmware/devicetree/base/soc@0/vfio_dpu_11_secure/iommus | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | systime | 1 | init | systime.service | [Graphics] systime | 28 | 是 | systime.service; [Graphics] systime; /dev/shm/vcore_env, /dev/hab | 自动分类 |
| 座舱多媒体与人机交互 | Display/HMI/GPU | 强 | weston | 1 | init | weston.service | Weston reference Wayland compositor | 25 | 是 | weston.service; Weston reference Wayland compositor; /dev/shm/lrmc_rq_4952_2_weston, /dev/shm/lrmc_rq_4952_1_weston, /dev/dma_heap/system, /dev/input/event1, /dev/input/event0, /dev/input/event2, /dev/ksync, /dev/dma_heap/qcom,secure-pixel | 自动分类 |
| 座舱多媒体与人机交互 | Touch/Input | 强 | touch_central | 1 | init | touch_central.service | Launch touch central Server | 3 | 是 | touch_central.service; Launch touch central Server; /dev/i2c-1, /dev/uinput, /dev/gpiochip0, gpio, i2c, touch | 自动分类 |
| 座舱多媒体与人机交互 | Touch/Input | 强 | touch_cluster | 1 | init | touch_cluster.service | Launch touch cluster Server | 3 | 是 | touch_cluster.service; Launch touch cluster Server; /dev/i2c-8, /dev/gpiochip0, gpio, i2c, touch | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM垂直设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-aud | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM垂直设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-cam, cam | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM垂直设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-disp | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM垂直设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-dprx, dprx | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM垂直设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-ogles | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM垂直设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-vid | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM承载 | 间接/平台 | qcrosvm | 1 | init | qcrosvm.service | Service to start the Android GVM | 96 | 是 | qcrosvm.service; Service to start the Android GVM; /sys/kernel/tracing/trace_marker, /dev/gunyah, /dev/sda32, /dev/sda27, /dev/sdg12, /dev/sda30, /dev/sdg15, /dev/sde25 | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM生命周期/电源/ramdump | 间接/平台 | vmm-boot-lcm | 1 | init | vmm-boot-lcm.service | Gvm Boot Lifecycle Manager | 6 | 否 | vmm-boot-lcm.service; Gvm Boot Lifecycle Manager | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM生命周期/电源/ramdump | 间接/平台 | vmm-pwr-key | 1 | init | vmm-pwr-key.service | virtual pwr key service | 5 | 是 | vmm-pwr-key.service; virtual pwr key service; /dev/uinput | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM生命周期/电源/ramdump | 间接/平台 | vmm-ramdump | 1 | init | vmm-ramdump.service | Guest ramdump service | 6 | 否 | vmm-ramdump.service; Guest ramdump service | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM生命周期/电源/ramdump | 间接/平台 | vmm_service | 1 | init | - | 待确认 | 35 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-device-gpio | 1 | init | vhost-device-gpio.service | launch vhost-device-gpio for pmic gpiochip | 3 | 是 | vhost-device-gpio.service; launch vhost-device-gpio for pmic gpiochip; /dev/gpiochip1, gpio | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-device-i2c | 1 | init | vhost-device-i2c.service | Service to start vhost-device-i2c daemon | 3 | 是 | vhost-device-i2c.service; Service to start vhost-device-i2c daemon; /dev/i2c-9, i2c | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-device-ssr | 1 | init | vhost-device-ssr.service | launch vhost-device-ssr | 4 | 是 | vhost-device-ssr.service; launch vhost-device-ssr; /dev/shm/lrmc_rq_2404_1_vhu-vsock-ssr-" | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-user-eavb | 1 | init | vhost-user-eavb.service | Vhost-User eavb BE driver | 5 | 否 | vhost-user-eavb.service; Vhost-User eavb BE driver | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-user-frpc | 1 | init | vhost-user-frpc.service | Vhost-User fastrpc Passthrough-BE | 5 | 是 | vhost-user-frpc.service; Vhost-User fastrpc Passthrough-BE; /dev/shm/lrmc_rq_3856_1_vhost-user-frpc, /dev/hyp_udmabuf, fastrpc | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-user-glinkpassthrough | 1 | init | vhost-user-glinkpassthrough.service | Vhost-User Glink Passthrough BE | 4 | 是 | vhost-user-glinkpassthrough.service; Vhost-User Glink Passthrough BE; /dev/shm/sem.t6Pv9n, glink | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-eva, eva | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-ext | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-gpce, gpce | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-misc | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-soccp | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-user-qti | 1 | init | - | 为GVM提供vhost/virtio后端设备 | 7 | 是 | 为GVM提供vhost/virtio后端设备; /dev/vhost-vnw | 自动分类 |
| 虚拟化/GVM与跨域通道 | GVM通用/平台设备后端 | 间接/平台 | vhost-user-scmi | 1 | init | vhost-user-scmi.service | Service for vhost-user-scmi | 4 | 是 | vhost-user-scmi.service; Service for vhost-user-scmi; /dev/scmi_usb2, /dev/scmi_usb2_phy2, /dev/scmi_uart17, /dev/scmi_bluetooth, /dev/scmi_pcie2, /dev/scmi_emac1, /dev/scmi_wlan, /dev/scmi_uart16 | 自动分类 |
| 虚拟化/GVM与跨域通道 | VSOCK通道 | 间接/平台 | vsock_misc | 1 | init | vsock_misc.service | VSOCK misc daemon | 3 | 否 | vsock_misc.service; VSOCK misc daemon | 自动分类 |
| 芯片硬件平台与安全资源 | DSP/RPC/GLINK/SCMI/子系统 | 间接/平台 | glink-passthrough-service | 1 | init | glink-passthrough-service.service | Glink Passthrough Service Daemon | 3 | 是 | glink-passthrough-service.service; Glink Passthrough Service Daemon; /dev/shm/lrmc_rq_2657_7_glink-passthrou, /dev/shm/lrmc_rq_2657_6_glink-passthrou, /dev/shm/lrmc_rq_2657_5_glink-passthrou, /dev/shm/lrmc_rq_2657_4_glink-passthrou, /dev/shm/lrmc_rq_2657_3_glink-passthrou, /dev/shm/lrmc_rq_2657_2_glink-passthrou, /dev/shm/lrmc_rq_2657_1_glink-passthrou, /dev/shm/sem.glink_passthrough_sem_2 | 自动分类 |
| 芯片硬件平台与安全资源 | DSP/RPC/GLINK/SCMI/子系统 | 间接/平台 | glink_service_lrm | 1 | init | glink-service-lrm.service | GLINK Service Daemon | 3 | 是 | glink-service-lrm.service; GLINK Service Daemon; /dev/shm/lrmc_rq_3310_7_nspconfig_servi, /dev/shm/lrmc_rq_3310_3_nspconfig_servi, /dev/shm/lrmc_rq_3310_4_nspconfig_servi, /dev/shm/lrmc_rq_3310_6_nspconfig_servi, /dev/shm/lrmc_rq_3310_5_nspconfig_servi, /dev/shm/lrmc_rq_3310_2_nspconfig_servi, /dev/shm/lrmc_rq_3310_1_nspconfig_servi, /dev/shm/lrmc_rq_2657_7_glink-passthrou | 自动分类 |
| 芯片硬件平台与安全资源 | DSP/RPC/GLINK/SCMI/子系统 | 间接/平台 | nsp_drv | 1 | init | nsp-drv.service | NSP Driver Service Daemon | 7 | 是 | nsp-drv.service; NSP Driver Service Daemon; /dev/shm/lrmc_rq_1199_2_nsp_drv, /sys/firmware/devicetree/base/soc@0/umd_nsp_drv@1f012000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/147, vfio, nsp | 自动分类 |
| 芯片硬件平台与安全资源 | DSP/RPC/GLINK/SCMI/子系统 | 间接/平台 | nspconfig_service | 1 | init | - | 待确认 | 7 | 是 | /dev/shm/lrmc_rq_3310_7_nspconfig_servi, /dev/shm/lrmc_rq_3310_6_nspconfig_servi, /dev/shm/lrmc_rq_3310_5_nspconfig_servi, /dev/shm/lrmc_rq_3310_4_nspconfig_servi, /dev/shm/lrmc_rq_3310_3_nspconfig_servi, /dev/shm/lrmc_rq_3310_2_nspconfig_servi, /dev/shm/lrmc_rq_3310_1_nspconfig_servi, nsp | 自动分类，需源码/Owner复核 |
| 芯片硬件平台与安全资源 | DSP/RPC/GLINK/SCMI/子系统 | 间接/平台 | pil-rm | 1 | init | pil-rm.service | PIL Service Daemon | 3 | 是 | pil-rm.service; PIL Service Daemon; /dev/kiumd, /dev/shm/lrmc_rq_2147_1_sv_server, /dev/shm/lrmc_rq_1207_2_devcreate_0_1, /dev/shm/lrmc_rq_1418_1_videoCore, /dev/shm/lrmc_rq_1204_3_AdrenoOsLib, /dev/shm/lrmc_rq_1206_3_AdrenoOsLib, /dev/shm/lrmc_rq_1199_2_nsp_drv, /dev/shm/lrmc_rq_1005_1_pil-rm | 自动分类 |
| 芯片硬件平台与安全资源 | DSP/RPC/GLINK/SCMI/子系统 | 间接/平台 | ssr-rm | 1 | init | ssr-rm.service | SSR RM Service Daemon | 3 | 是 | ssr-rm.service; SSR RM Service Daemon; /dev/shm/lrmc_rq_3661_2_aud_fastrpcd, /dev/shm/lrmc_rq_2588_8_fastrpc-rm, /dev/shm/lrmc_rq_2564_8_diag_task, /dev/shm/lrmc_rq_2404_1_vhu-vsock-ssr-", /dev/shm/lrmc_rq_1798_1_awe_audio_servi, /dev/shm/lrmc_rq_1716_1_ssr_event_reg, /dev/shm/lrmc_rq_1083_1_glink_service_l, /dev/shm/lrmc_rq_1005_1_pil-rm | 自动分类 |
| 芯片硬件平台与安全资源 | 安全/VFIO/IOMMU/FuSa | 间接/平台 | ecc-err-handler | 1 | init | ecc-err-handler.service | ECC and Fusa Error monitor | 3 | 否 | ecc-err-handler.service; ECC and Fusa Error monitor | 自动分类 |
| 芯片硬件平台与安全资源 | 安全/VFIO/IOMMU/FuSa | 间接/平台 | gpce_be | 1 | init | gpce_be.service | gpce be service for handling smmu mapping and decryption requests form host and guest applications | 3 | 是 | gpce_be.service; gpce be service for handling smmu mapping and decryption requests form host and guest applications; /sys/firmware/devicetree/base/soc@0/vfio_gpce_gvm_ns_tzdec_cb/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/144, /sys/firmware/devicetree/base/soc@0/vfio_gpce_gvm_s_tzdec_cb/iommus, /dev/vfio/143, /sys/firmware/devicetree/base/soc@0/vfio_hwkm_gpce_core_0@1dc0000/iommus, /dev/vfio/142 | 自动分类 |
| 芯片硬件平台与安全资源 | 安全/VFIO/IOMMU/FuSa | 间接/平台 | qdss-service | 1 | init | qdss-service.service | qdss-service daemon | 4 | 是 | qdss-service.service; qdss-service daemon; /dev/shm/lrmc_rq_3836_2_qdss-service, /sys/firmware/devicetree/base/soc@0/qdss-service@11A05000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/135, vfio, qdss | 自动分类 |
| 芯片硬件平台与安全资源 | 安全/VFIO/IOMMU/FuSa | 间接/平台 | safetymonitor | 1 | init | safetymonitor.service | Safetymonitor service | 5 | 是 | safetymonitor.service; Safetymonitor service; /sys/firmware/devicetree/base/soc@0/safety-ddr@82010000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/13, vfio | 自动分类 |
| 芯片硬件平台与安全资源 | 安全/VFIO/IOMMU/FuSa | 间接/平台 | sailmb_server | 1 | init | - | 待确认 | 4 | 是 | /sys/firmware/devicetree/base/soc@0/sail-mailbox@82030000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/17, vfio | 自动分类，需源码/Owner复核 |
| 芯片硬件平台与安全资源 | 安全/VFIO/IOMMU/FuSa | 间接/平台 | smcinvoke_service | 1 | init | - | 待确认 | 3 | 是 | /dev/shm/lrmc_rq_4200_1_nvdata-bspconfi, /dev/shm/lrmc_rq_4214_1_ssgtzd, /dev/shm/lrmc_rq_4086_1_qseecomd, /dev/shm/lrmc_rq_3369_1_openwfd_server, /dev/shm/lrmc_rq_3368_1_openwfd_server, /dev/shm/lrmc_rq_910_1_smcinvoke_servi, /dev/scmnode, /dev/scmnode_sec | 自动分类，需源码/Owner复核 |
| 芯片硬件平台与安全资源 | 安全/VFIO/IOMMU/FuSa | 间接/平台 | ssgtzd | 1 | init | - | 待确认 | 3 | 是 | /dev/shm/lrmc_rq_4214_1_ssgtzd | 自动分类，需源码/Owner复核 |
| 芯片硬件平台与安全资源 | 热管理 | 间接/平台 | temp-monitor | 1 | init | temp-monitor.service | Temperature Monitor Service | 2 | 否 | temp-monitor.service; Temperature Monitor Service | 自动分类 |
| 芯片硬件平台与安全资源 | 热管理 | 间接/平台 | thermal-engine | 1 | init | thermal-engine.service | Thermal Engine Service | 9 | 是 | thermal-engine.service; Thermal Engine Service; /dev/shm/lrmc_rq_2160_1_thermal-engine, /sys/devices/virtual/thermal/thermal_zone36/temp, /sys/devices/virtual/thermal/thermal_zone64/temp, /sys/devices/virtual/thermal/thermal_zone123/temp, /sys/devices/virtual/thermal/thermal_zone92/temp, /sys/devices/virtual/thermal/thermal_zone26/temp, /sys/devices/virtual/thermal/thermal_zone2/temp, /sys/devices/virtual/thermal/thermal_zone54/temp | 自动分类 |
| 芯片硬件平台与安全资源 | 电源/CPU频率 | 间接/平台 | powercyclemgr | 1 | init | powercyclemgr.service | launch powercyclemgr server | 4 | 是 | powercyclemgr.service; launch powercyclemgr server; /dev/input/event1 | 自动分类 |
| 芯片硬件平台与安全资源 | 电源/CPU频率 | 间接/平台 | powermgr | 1 | init | powermgr.service | powermgr | 4 | 是 | powermgr.service; powermgr; /dev/gpiochip0, /dev/input/event1, gpio | 自动分类 |
| 芯片硬件平台与安全资源 | 电源/CPU频率 | 间接/平台 | qseecomd | 1 | init | qseecomd.service | Qseecomd for TZ to access HLOS side | 4 | 是 | qseecomd.service; Qseecomd for TZ to access HLOS side; /dev/shm/lrmc_rq_4086_1_qseecomd, /dev/shm/sem.pQjNa7, /sys/power/wake_lock, /sys/power/wake_unlock, qsee | 自动分类 |
| 芯片硬件平台与安全资源 | 电源/CPU频率 | 间接/平台 | set_cpu_freq | 1 | init | - | 待确认 | 24 | 否 | 按进程名/命令初判 | 自动分类，需源码/Owner复核 |
| 芯片硬件平台与安全资源 | 计算/缓存/资源调度 | 间接/平台 | compresmgr_service | 1 | init | - | 待确认 | 3 | 是 | /dev/shm/lrmc_rq_3989_2_compute-cape, /dev/shm/lrmc_rq_1204_1_kgsl, /dev/shm/lrmc_rq_1206_1_kgsl, /sys/firmware/devicetree/base/soc@0/hscnoc@2030000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/134, /dev/shm/lrmc_rq_347149_1_rpc_0_GVM_.vo | 自动分类，需源码/Owner复核 |
| 芯片硬件平台与安全资源 | 计算/缓存/资源调度 | 间接/平台 | compresmon_rm | 1 | init | - | 待确认 | 3 | 是 | /dev/shm/lrmc_rq_3989_1_compute-cape, /dev/shm/lrmc_rq_3931_1_compresmon_rm, /dev/shm/compressched_shm_domain_id-82, /dev/shm/compressched_shm_domain_id-81, /dev/shm/compressched_shm_domain_id-80, /dev/shm/compressched_shm_domain_id-19, /dev/shm/compressched_shm_domain_id-18, /dev/shm/compressched_shm_domain_id-17 | 自动分类，需源码/Owner复核 |
| 芯片硬件平台与安全资源 | 计算/缓存/资源调度 | 间接/平台 | compute-cape | 1 | init | compute-cape.service | launch compute-cape service | 3 | 是 | compute-cape.service; launch compute-cape service; /dev/shm/lrmc_rq_3989_2_compute-cape, /dev/shm/lrmc_rq_3989_1_compute-cape | 自动分类 |
| 芯片硬件平台与安全资源 | 计算/缓存/资源调度 | 间接/平台 | compute-ressched | 1 | init | compute-ressched.service | launch compute-ressched server | 3 | 是 | compute-ressched.service; launch compute-ressched server; /dev/shm/lrmc_rq_3672_1_compute-ressche, /dev/shm/compressched_shm_domain_id-82, /dev/shm/compressched_shm_domain_id-81, /dev/shm/compressched_shm_domain_id-80, /dev/shm/compressched_shm_domain_id-19, /dev/shm/compressched_shm_domain_id-18, /dev/shm/compressched_shm_domain_id-17, /dev/shm/compressched_shm_domain_id-16 | 自动分类 |
| 芯片硬件平台与安全资源 | 计算/缓存/资源调度 | 间接/平台 | fastrpc-rm | 1 | init | fastrpc-rm.service | FastRPC RM Service Daemon | 3 | 是 | fastrpc-rm.service; FastRPC RM Service Daemon; /dev/shm/lrmc_rq_6190_1_main, /dev/shm/lrmc_rq_4618_1_main, /dev/shm/lrmc_rq_3931_1_compresmon_rm, /dev/shm/lrmc_rq_3856_1_vhost-user-frpc, /dev/shm/lrmc_rq_3672_1_compute-ressche, /dev/shm/lrmc_rq_3661_1_aud_fastrpcd, /dev/shm/lrmc_rq_2588_8_fastrpc-rm, /dev/shm/lrmc_rq_2588_7_fastrpc-rm | 自动分类 |
| 芯片硬件平台与安全资源 | 计算/缓存/资源调度 | 间接/平台 | syscache-rm | 1 | init | syscache-rm.service | Syscache server daemon | 3 | 是 | syscache-rm.service; Syscache server daemon; /dev/shm/lrmc_rq_1207_1_qcxserver, /dev/shm/lrmc_rq_1204_2_AdrenoOsLib, /dev/shm/lrmc_rq_1206_2_AdrenoOsLib, /sys/firmware/devicetree/base/soc@0/umd_llcc@20400000/iommus, /dev/kiumd, /dev/vfio/vfio, /dev/vfio/139, vfio | 自动分类 |

## 注意事项

- 本分类按“职责/业务归属”划分，不按进程是否打开硬件节点划分；例如`adbd`打开USB节点，但仍属于OS基础设施。
- `vhost-user-qti`等进程虽然承载Audio/Camera/Display设备通道，但职责是GVM虚拟设备后端，因此归入虚拟化/GVM平台。
- `fastrpc-rm`、`glink*`、`thermal-engine`等是车业务的重要支撑，但更接近芯片/硬件平台能力，不直接归入车业务中间件。
- 标记为“自动分类，需源码/Owner复核”的进程需要结合systemd unit、源码目录和日志进一步确认。
