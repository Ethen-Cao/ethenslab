+++
date = '2025-08-27T17:17:50+08:00'
draft = false
title = 'QNN HTP (ONNX Runtime) 架构与调用流程详解'
+++

## 1. 概述

本架构图展示了从 Android 应用层（CPU）到高通 Hexagon DSP（NPU）层的完整调用链路。核心机制是利用 **FastRPC** 跨越处理器边界，将存储在 CPU 文件系统中的 NPU 驱动代码（Skel）动态加载到 DSP 中运行，从而实现模型的高性能推理。


```plantuml
@startuml
!theme plain
skinparam backgroundColor white
skinparam defaultFontName Arial
skinparam defaultFontSize 14
skinparam defaultFontColor black
skinparam arrowColor black
skinparam nodesep 60
skinparam ranksep 50
skinparam rectangle {
    BackgroundColor #ECEFF1
    BorderColor #607D8B
    RoundCorner 8
}
skinparam package {
    BackgroundColor #E3F2FD
    BorderColor #1E88E5
    FontStyle bold
}
skinparam component {
    BackgroundColor #E8F5E9
    BorderColor #2E7D32
}

title QNN HTP (ONNX Runtime) Architecture Flow

node "Qualcomm SoC (System on Chip)" {

    ' --- CPU Subsystem (Android) ---
    rectangle "CPU Subsystem (Application Processor)" as CPU_DOMAIN {

        rectangle "1. Android User Space (APK Process)" as LAYER_APP {
            component "Business Logic\n(Kotlin/Java/C++)" as AppCode
            note right of AppCode
               <b>关键配置:</b>
               setenv("ADSP_LIBRARY_PATH", 
               nativeLibraryDir, 1);
            end note

            package "Native Libraries (jniLibs / lib/arm64)" {
                component "libonnxruntime.so" as ORT
                component "libonnxruntime_providers_qnn.so" as QNN_EP
                
                package "QNN SDK CPU Libs" {
                    component "libQnnHtp.so\n(Backend Manager)" as QnnHtp
                    component "libQnnHtpV[xx]Stub.so\n(CPU Proxy)" as QnnStub
                }
                
                component "libQnnHtpV[xx]Skel.so\n(DSP Executable)" as SkelFile
                note bottom of SkelFile
                   <b>Skel 文件</b>
                   虽然打包在 CPU 文件系统
                   但必须由 FastRPC 读取并
                   加载到 DSP 运行
                end note
            }

            component "Assets (model.onnx)" as Model
            note top of Model
               由 ORT 在 CPU 端
               直接读取并解析
            end note
        }

        rectangle "2. Android System / Vendor Libs" as LAYER_SYS {
            component "libadsprpc.so (FastRPC Framework)" as FastRPC
        }

        rectangle "3. Linux Kernel Space" as LAYER_KERNEL {
            component "adsprpc.ko (FastRPC Driver)" as Driver
            component "ION / SMMU\n(Shared Memory)" as Mem
        }
    }

    ' --- DSP Subsystem ---
    rectangle "DSP Subsystem (Hexagon cDSP/HTP)" as DSP_DOMAIN {
        component "QuRT OS (Real-time Kernel)" as QuRT

        package "Signed PD (Protection Domain)" {
            component "Skel Instance (Running Code)" as SkelRun
            component "HTP Hardware (Tensor Cores)" as HTP_HW
        }
    }
}

' --- 详细调用关系 ---
AppCode -down-> ORT : 1. Run()
ORT .left.> Model: Read & Parse
ORT -down-> QNN_EP : 2. Get EP
QNN_EP -down-> QnnHtp : 3. Create Backend
QnnHtp -down-> QnnStub : 4. Load specific Stub

QnnStub -down-> FastRPC : 5. remote_handle_open()
FastRPC -down-> Driver : 6. ioctl (FASTRPC_IOCTL_INVOKE)
Driver <-> QuRT : 7. Context Switch / Wake up

QuRT .up.> Driver : 8. Request Skel
Driver .up.> FastRPC : 9. Callback
FastRPC .left.> SkelFile : 10. Read from ADSP_LIBRARY_PATH
FastRPC .down.> Mem : 11. Map to ION
Mem .down.> SkelRun : 12. Load into PD

QuRT -down-> SkelRun : 13. Execute Graph
SkelRun -down-> HTP_HW : 14. Compute
@enduml


```

## 2. 核心组件分层

### 2.1 Android User Space (应用层)

这是应用程序运行的进程空间，包含了业务代码和所有的第三方依赖库。

* **Business Logic**: 你的业务代码（Kotlin/Java/C++）。
* **关键配置**: 必须在初始化时设置环境变量 `setenv("ADSP_LIBRARY_PATH", nativeLibraryDir, 1)`，否则 FastRPC 将无法找到 Skel 文件。


* **ONNX Runtime (ORT)**: 微软提供的统一推理引擎 (`libonnxruntime.so`)。
* **QNN Execution Provider (EP)**: ORT 与 QNN 之间的适配层 (`libonnxruntime_providers_qnn.so`)。
* **QNN CPU Libraries**:
* `libQnnHtp.so`: **Backend Manager**，负责管理 HTP 后端的生命周期。
* `libQnnHtpV[xx]Stub.so`: **CPU Proxy (桩)**，负责在 CPU 端打包数据和指令，并通过 RPC 发送给 DSP。


* **Skel File (关键)**:
* `libQnnHtpV[xx]Skel.so`: **DSP Executable (骨架)**。这是真正运行在 NPU 上的“服务端”代码。
* **注意**: 尽管它物理上存储在 APK 的 `lib/arm64` 目录下（CPU 文件系统），但它**不**在 CPU 上执行，而是被传输到 DSP 内存中运行。



### 2.2 Android System & Kernel (系统与内核层)

负责 CPU 与 DSP 之间的通信桥梁。

* **libadsprpc.so (FastRPC Framework)**: Android 系统提供的用户空间库，用于发起 RPC 调用。
* **adsprpc.ko (FastRPC Driver)**: Linux 内核驱动，负责处理内存映射、中断和跨核通信。
* **ION / SMMU**: 共享内存管理器。允许 CPU 和 DSP 访问同一块物理内存（零拷贝），显著提高大数据传输效率。

### 2.3 DSP Subsystem (硬件层)

高通 Hexagon 处理器的运行环境。

* **QuRT OS**: 高通的实时微内核 (Real-time Kernel)，管理 DSP 资源。
* **Signed PD (Protection Domain)**: 受保护的进程域。为了安全，未签名的代码无法在此运行。
* **Skel Instance**: 加载进内存并正在运行的 `Skel.so` 实例。
* **HTP Hardware**: 实际执行张量计算的硬件核心。

---

## 3. 详细调用流程 (Step-by-Step)

流程分为五个主要阶段，对应图中的编号 **1-14**。

### 第一阶段：应用发起 (App Invocation)

1. **Run()**: 业务代码调用 ONNX Runtime 的推理接口。
2. **Get EP**: ORT 识别到配置了 QNN，将任务分发给 QNN EP。
3. **Create Backend**: EP 调用 `libQnnHtp.so` 初始化 HTP 后端。
4. **Load Stub**: 后端管理器根据当前芯片型号，加载对应的桩文件（如 `libQnnHtpV81Stub.so`）。

### 第二阶段：RPC 桥接 (RPC Bridging)

5. **remote_handle_open()**: Stub 库调用系统的 `libadsprpc.so`，请求连接 DSP。
6. **ioctl (INVOKE)**: 用户空间库通过 `ioctl` 系统调用进入内核驱动 `adsprpc.ko`。

### 第三阶段：DSP 唤醒 (Wake up)

7. **Context Switch**: 内核驱动发送硬件中断，唤醒沉睡中的 DSP 子系统 (QuRT OS)。

### 第四阶段：Skel 加载回环 (The Side-load Loop) —— **最关键步骤**

这是最容易出错的环节。DSP 自身没有文件系统，它需要“反向”请求 CPU 提供代码文件。
8.  **Request Skel**: QuRT 发现需要运行 V81 版本的代码，向内核驱动请求 `libQnnHtpV81Skel.so`。
9.  **Callback**: 驱动无法直接读文件，于是**回调** (Callback) 到用户空间的 `libadsprpc.so`。
10. **Read file (Red Arrow)**: `libadsprpc.so` 根据之前设置的 `ADSP_LIBRARY_PATH` 环境变量，在 APK 的安装目录下找到并读取 Skel 文件。
11. **Map to ION**: 将读取的文件内容写入 ION 共享内存。
12. **Load into PD**: DSP 从共享内存中读取代码，通过签名验证后，加载到保护域 (PD) 中成为可执行实例。

### 第五阶段：硬件执行 (Execution)

13. **Execute Graph**: QuRT 调度 `Skel Instance` 开始工作。
14. **Compute**: Skel 驱动底层的 HTP 硬件进行矩阵运算，并将结果原路返回。

---

## 模型加载运行过程

```plantuml
@startuml
!theme plain
skinparam backgroundColor white
skinparam defaultFontName Arial
skinparam defaultFontSize 13
skinparam defaultFontColor black
skinparam arrowColor #333333
skinparam nodesep 50
skinparam ranksep 40
skinparam linetype ortho

' --- 样式定义 ---
skinparam rectangle {
    BackgroundColor #F5F5F5
    BorderColor #9E9E9E
    RoundCorner 6
}
skinparam component {
    BackgroundColor #E3F2FD
    BorderColor #1E88E5
}
skinparam file {
    BackgroundColor #FFF9C4
    BorderColor #FBC02D
}

title QNN HTP Architecture: Full Lifecycle (Fixed Directions)

' --- 图例 (Legend) ---
legend right
    | 颜色 | 阶段 / 含义 |
    | <#FF0000> | <b>Phase 1: 初始化与建图</b> (只运行一次) |
    | <#0000FF> | <b>Side-load 回环</b> (驱动加载 Skel 文件) |
    | <#008000> | <b>Phase 2: 推理执行</b> (每帧运行, 高频) |
endlegend

node "Qualcomm SoC" {

    rectangle "CPU Subsystem (Application Processor)" as CPU_DOMAIN {

        rectangle "1. App Process Space" as LAYER_APP {
            component "App Code" as AppCode
            file "Assets/model.onnx" as Model

            rectangle "Native Libraries" {
                component "ONNX Runtime" as ORT
                component "QNN EP" as QNN_EP
                
                package "QNN SDK" {
                    component "Backend Manager\n(libQnnHtp.so)" as QnnHtp
                    component "Stub(CPU Proxy)\t\t" as QnnStub
                }
                
                file "libQnnHtpVxxSkel.so\n(Disk Artifact)" as SkelFile
            }
        }

        rectangle "2. System / Kernel" as LAYER_SYS {
            component "FastRPC Lib" as FastRPC
            component "FastRPC Driver" as Driver
            database "Shared Memory\n(ION / DMA-BUF)" as Mem
        }
    }

    rectangle "DSP Subsystem" as DSP_DOMAIN {
        component "QuRT OS" as QuRT

        package "Signed PD" {
            component "Skel Instance\n(Running Code)" as SkelRun
            component "HTP Hardware\n(NPU)" as HTP_HW
        }
    }
}

' =======================
' 逻辑连线 (已修复方向问题)
' =======================

' --- Phase 1: Initialization (红色箭头) ---
AppCode -[#FF0000]down-> ORT : 1. CreateSession
ORT .[#FF0000]right.> Model : 2. Parse
ORT -[#FF0000]down-> QNN_EP : 3. Delegate
QNN_EP -[#FF0000]down-> QnnHtp : 4. Init
QnnHtp -[#FF0000]down-> QnnStub : 5. Load Stub

' RPC 建立
QnnStub -[#FF0000]down-> FastRPC : 6. Open Session
FastRPC -[#FF0000]down-> Driver : 7. ioctl

' DSP 唤醒
Driver -[#FF0000]down-> QuRT : 8. WakeUp & Create PD

' --- Side-load Loop (蓝色箭头 - 加载回环) ---
QuRT .[#0000FF]up.> Driver : 9. Request Load
Driver .[#0000FF]up.> FastRPC : 10. Upcall
FastRPC .[#0000FF]left.> SkelFile : 11. READ FILE
FastRPC .[#0000FF]down.> Mem : 12. Map to Shared Mem
Mem .[#0000FF]down.> SkelRun : 13. Load into DSP Mem

' --- Phase 2: Execution (绿色箭头 - 已修复方向) ---
AppCode -[#008000]right-> ORT : Run(Input)

' 修复点：添加了 down 方向
ORT -[#008000]down-> QNN_EP
QNN_EP -[#008000]down-> QnnStub

' 写入共享内存 (使用 dotted 线表示数据流，solid 线表示控制流)
QnnStub .[#008000]right.> Mem : 14. Write Input Tensor\n数据不走 RPC 拷贝而是走共享内存

' RPC 执行链
QnnStub -[#008000]down-> FastRPC : 15. Invoke Execute
FastRPC -[#008000]down-> Driver
Driver -[#008000]down-> SkelRun : 16. Signal
SkelRun -[#008000]down-> HTP_HW : 17. Compute

@enduml
```

这是一段针对该 QNN HTP 架构流程图的详细专业解说。这段解说将图表分为三个逻辑阶段，清晰阐述了模型从加载到硬件执行的完整生命周期。

---

### **QNN HTP 架构全生命周期解说**

这张架构图展示了使用 ONNX Runtime (ORT) 配合 QNN SDK 在高通 Hexagon NPU (HTP) 上运行 AI 模型的完整技术链路。流程被清晰地划分为三个阶段：**初始化（红色）**、**Side-load 回环（蓝色）以及推理执行（绿色）**。

#### **第一阶段：初始化与建图 (Phase 1: Initialization)**

> **图例颜色：红色 <font color="red">──></font>**
> *这是“准备工作”，通常在应用启动时执行一次，耗时较长。*

1. **应用发起**：业务代码 (`App Code`) 调用 ORT 的 `CreateSession` 接口。
2. **模型解析 (CPU)**：**关键点！** ORT 在 CPU 侧直接读取并解析 `Assets/model.onnx` 文件。模型文件本身**不会**被发送到 DSP，ORT 负责理解网络结构并进行图分割。
3. **任务委托**：ORT 识别到支持 NPU 加速的节点，将其委托给 `QNN EP`，随后层层传递至 `Backend Manager` 和 `Stub`。
4. **握手与唤醒**：`Stub` (CPU 代理) 通过 `FastRPC` 向底层驱动发起 `open` 请求，驱动负责唤醒沉睡的 DSP 子系统，并在其上创建一个受保护的进程域 (Signed PD)。

#### **第二阶段：Skel 加载回环 (The Side-load Loop)**

> **图例颜色：蓝色 <font color="blue">..></font>**
> *这是 QNN 架构的核心机制，发生在初始化阶段的内部，解决了 DSP 如何获取执行代码的问题。*

1. **反向请求 (Upcall)**：DSP 被唤醒后，其内部的系统（QuRT/Loader）发现需要加载 HTP 硬件驱动逻辑，于是向 CPU 发起一个“请求加载文件”的反向 RPC 调用。
2. **文件读取**：CPU 端的 `FastRPC Lib` 收到请求，根据环境变量（`ADSP_LIBRARY_PATH`）在磁盘的 Native 库路径下找到 `libQnnHtpVxxSkel.so` (Skel 文件)。
3. **共享内存传输**：FastRPC **不**通过慢速的 RPC 协议拷贝文件内容，而是将文件直接映射到 **共享内存 (ION/DMA-BUF)** 中。
4. **DSP 加载**：DSP 直接从共享内存读取 Skel 镜像并完成加载。至此，`Skel Instance` (服务端) 就位，准备好控制 HTP 硬件。

#### **第三阶段：推理执行 (Phase 2: Execution)**

> **图例颜色：绿色 <font color="green">──></font>**
> *这是高频运行的阶段（如相机预览流每秒 30 帧），追求极致性能。*

1. **零拷贝输入**：当应用调用 `Run()` 时，输入数据（如图片张量）被直接写入 **共享内存 (Mem)**。注意图中虚线所示，**大数据不走 RPC 协议拷贝**，这是高性能的关键。
2. **轻量级指令**：`QnnStub` 仅通过 RPC 发送一条轻量级的 `Execute` 指令，告知 DSP 数据在共享内存的哪个位置。
3. **硬件计算**：DSP 端的 `SkelRun` 收到指令，指挥 `HTP Hardware` (Tensor Cores) 全速运转。
4. **结果返回**：计算完成后，结果同样通过共享内存返回给 CPU，完成一次推理。

---

### **核心总结**

* **物理隔离**：模型文件 (`model.onnx`) 由 CPU 解析，Skel 库 (`.so`) 由 DSP 加载，两者物理存储位置和加载时机完全不同。
* **反向加载**：DSP 是“大脑”，但它需要 CPU 这个“管家”帮忙从磁盘拿代码（Skel），这就是 Side-load 机制。
* **性能优化**：控制流走 FastRPC，数据流走共享内存，实现了控制与数据分离，最大化了吞吐量。


## 4. 开发与调试重点

* **Skel 文件必须打包**: 务必确保 `libQnnHtpV[xx]Skel.so` 被正确打包进 APK 的 `jniLibs` 或 `assets` 中。如果 DSP 请求文件时（步骤 8-10）在路径中找不到文件，初始化将直接失败。
* **环境变量设置**: 图中 Note 提到的 `setenv("ADSP_LIBRARY_PATH", ...)` 是必不可少的。因为系统的 FastRPC 库默认不知道你的 App 安装在哪个随机生成的路径下，必须显式告知。
* **版本匹配**: Stub（CPU侧）和 Skel（DSP侧）必须属于同一个 QNN SDK 版本，否则在握手阶段会因协议不一致而崩溃。