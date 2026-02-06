@startuml
!theme plain
skinparam componentStyle rectangle
skinparam linetype ortho

' --- 定义区域边界 ---

package "Android User Space" {
    
    ' 1. 上层业务与生态
    package "Clients" {
        [PolarisAgent\n(Java App)] as Agent
        
        frame "Native Ecosystem" {
            [Audio HAL] as Audio
            [Camera HAL] as Camera
            component "libpolaris_client\n(Static Lib)" as Lib #lightgrey
        }
    }

    ' 2. 核心守护进程
    node "polarisd (System Daemon)" #White {
        
        ' 2.1 接入层 (Ingress)
        frame "Ingress Layer" {
            port "socket: polaris_bridge\n(STREAM, 0660)" as P_Bridge
            port "socket: polaris_report\n(DGRAM, 0666)" as P_Report
            
            [AppBridge] as Bridge <<Thread A>>
            [EventIngestor] as Ingestor <<Thread B>>
        }

        ' 2.2 核心逻辑层 (Core)
        component "PolarisManager\n(Router & State Machine)" as Manager <<Main Thread>>
        component "EventCache\n(Ring Buffer)" as Cache

        ' 2.3 输出与执行层 (Egress)
        frame "Egress Layer" {
            [CommandExecutor] as Exec <<Process>>
            [HostTransport] as Transport <<Thread C>>
        }
        
        ' 2.4 监控层
        component "ResourceMonitor" as Monitor
    }
}

package "Linux Host Space" {
    [polaris_hostd] as Host
}

' --- 定义连接关系 ---

' Flow 1: App 控制与全域事件接收 (全双工)
Agent <--> P_Bridge : Cmd / Event
P_Bridge <--> Bridge

' Flow 2: Native 埋点上报 (单向, 非阻塞)
Audio ..> Lib
Camera ..> Lib
Lib --> P_Report : Native Event
P_Report --> Ingestor

' 内部路由逻辑
Bridge <--> Manager : Bi-dir
Ingestor --> Manager : One-way
Monitor --> Manager : System Event

' 缓存逻辑
Manager <--> Cache : Backup / Restore

' 执行逻辑
Manager --> Exec : Local Cmd (Perfetto/Logcat)
Exec --> Manager : Result / File Path

' 跨域逻辑 (全双工)
Manager <--> Transport : PLP Protocol
Transport <--> Host : VSOCK (CID:2 Port:10240)

@enduml