+++
date = '2025-09-29T10:22:54+08:00'
draft = false
title = 'Android SurfaceFlinger 深度解析'
+++

SurfaceFlinger 是 Android 图形栈的核心系统服务，负责全系统的图形合成与显示管理。本文基于 Android 源码，深入剖析其从 Display 创建、Layer 状态管理、合成策略决策到 RenderEngine 渲染执行及 HWC 提交的完整技术链路。

## 1. Display 创建过程

在 SurfaceFlinger 中，`Display` 是物理屏幕（由 HWC 管理）或虚拟屏幕（由系统服务请求创建）的抽象实体。Display 的创建是一个异步且多阶段的过程，涉及内核事件响应、状态机更新及渲染资源的初始化。

### 1.1 核心流程时序解析

下图展示了从触发源（硬件热插拔或服务请求）到 SurfaceFlinger 内部对象初始化的完整调用时序。

```mermaid
sequenceDiagram
    autonumber
    
    %% 定义参与者
    participant HWC as HWC/Kernel
    participant DisplayManagerService as DisplayManagerService
    participant SF as SurfaceFlinger(MainThread)
    participant CE as CompositionEngine
    participant BQ as BufferQueue
    participant VDS as VirtualDisplaySurface
    participant FBS as FramebufferSurface
    participant DD as DisplayDevice
    participant Scheduler as Scheduler

    box "触发源 (Triggers)" #f9f9f9
        participant HWC
        participant DisplayManagerService
    end

    box "SurfaceFlinger" #e1f5fe
        participant SF
        participant Scheduler
        participant DD



        participant CE
        participant BQ
        participant VDS
        participant FBS
    end

    %% === 第一阶段：触发 ===
    rect rgb(255, 240, 240)
    note right of SF: 阶段 1: 触发创建 (物理 vs 虚拟)
    
    alt 物理屏幕插入 (Hotplug)
        HWC ->> SF: onHotplugReceived(displayId, connected=true)
        SF ->> SF: update mCurrentState (add Display)
        SF ->> SF: setTransactionFlags(eDisplayTransactionNeeded)
    else 虚拟屏幕请求 (Virtual)
        DisplayManagerService ->> SF: createDisplay(name, secure)
        SF ->> SF: update mCurrentState (add Display)
        SF ->> SF: setTransactionFlags(eDisplayTransactionNeeded)
    end
    end

    %% === 第二阶段：主循环处理 ===
    SF ->> SF: onMessageInvalidate() -> handleMessageTransaction()
    SF ->> SF: processDisplayChangesLocked()
    note right of SF: 发现 mCurrentState 有新 token<br/>而 mDrawingState 没有

    %% === 第三阶段：核心工厂方法 ===
    rect rgb(255, 250, 230)
    note right of SF: 阶段 2: 核心工厂 (processDisplayAdded)
    SF ->> SF: processDisplayAdded(token, state)

    %% 1. 创建 CE Display
    SF ->> CE: createDisplay(args)
    activate CE
    CE -->> SF: return compositionDisplay
    deactivate CE

    %% 2. 创建 Buffer 管道
    SF ->> BQ: createBufferQueue()
    BQ -->> SF: return (producer, consumer)

    %% 3. 创建 Surface (分叉逻辑)
    note right of SF: 阶段 3: 注册与激活
    
    alt 物理屏幕
        SF ->> Scheduler: registerDisplay(physicalId, refreshRateSelector)
    end

    SF ->> SF: mDisplays.add(token, displayDevice)
    
    opt 如果是物理屏幕
        SF ->> HWC: setPowerMode(ON)
        SF ->> SF: onActiveDisplayChangedLocked (如果是主屏)
    end
    end

```

**技术实现细节：**

1. **事件触发与状态标记**：
* **物理屏幕**：`HWComposer` 收到内核的 Hotplug 事件，回调 `onHotplugReceived`。SF 将新的 Display 信息添加到 `mCurrentState.displays` 中，并调用 `setTransactionFlags(eDisplayTransactionNeeded)`，请求在主线程下一次遍历时处理。
* **虚拟屏幕**：`DisplayManagerService` 通过 Binder 调用 `createDisplay`，同样更新 `mCurrentState` 并设置标志位。


2. **状态提交与差异比对**：
* SF 主线程在 `handleMessageTransaction` 中调用 `processDisplayChangesLocked`。
* 逻辑核心在于比对 `mCurrentState`（最新状态）与 `mDrawingState`（上一帧绘制状态）。若发现 `mCurrentState` 中存在新的 Display Token，则判定为新增屏幕，调用 `processDisplayAdded`。


3. **核心对象构建 (`processDisplayAdded`)**：
* **CompositionEngine::Display**：调用 `getCompositionEngine().createDisplay` 创建合成引擎侧的 Display 抽象，用于管理 OutputLayer 和合成状态。
* **BufferQueue**：创建图形缓冲区队列，用于 SF 的 GPU 合成结果输出。
* **DisplayDevice**：根据屏幕类型创建具体的设备抽象。
* **物理屏幕**：创建 `FramebufferSurface` 作为 BufferQueue 的消费者，直接对接 HWC。
* **虚拟屏幕**：创建 `VirtualDisplaySurface`，通常对接媒体编解码器或 WiFi Display。


* **Scheduler 注册**：如果是物理屏幕，将其注册到 Scheduler，以便该屏幕能接收 VSYNC 信号并参与刷新率策略决策。



---

## 2. Layer 管理与渲染架构

Layer 是 SurfaceFlinger 进行图形管理和合成的基本单元。现代 Android 架构中，Layer 的设计强调了状态的隔离与流水线处理。

### 2.1 Layer 核心架构类图

下图展示了 SurfaceFlinger 核心对象、CompositionEngine 以及硬件层之间的静态关系，明确了 Layer 在不同模块中的形态。

```plantuml
@startuml
!theme plain
hide empty members
skinparam linetype ortho
skinparam nodesep 60
skinparam ranksep 60

' ==========================================
' SurfaceFlinger 域
' ==========================================
package "SurfaceFlinger Core" {
    class SurfaceFlinger {
        - mLayers : List<sp<Layer>>
        + createBufferStateLayer()
    }

    class Layer {
        - mDrawingState : State
        - mBufferInfo : BufferInfo
        - mLayerFEs : vector<pair<TraversalPath, sp<LayerFE>>>
        + setBuffer()
        + latchBufferImpl()
        + getCompositionEngineLayerFE()
    }

    class "Layer::State" as LayerState {
        + buffer : shared_ptr<ExternalTexture>
        + geometry : Rect/FloatRect
        + dataspace : Dataspace
    }
}

' ==========================================
' CompositionEngine 域
' ==========================================
package "CompositionEngine" {
    
    ' 接口定义
    interface LayerFE {
        + prepareClientComposition()
        + onPreComposition()
        + getCompositionState()
    }

    ' 具体实现 (通常是 Layer 的内部类或者独立类，这里根据提供的 LayerFE.cpp 是独立类)
    class "LayerFE (Impl)" as LayerFEImpl {
        - mSnapshot : LayerFECompositionState
        - mExternalTexture : shared_ptr<ExternalTexture>
        + prepareBufferStateClientComposition()
        + prepareShadowClientComposition()
    }

    class Output {
        - mOutputLayers : List<OutputLayer>
        + collectVisibleLayers()
        + updateCompositionState()
    }

    class OutputLayer {
        - mLayerFE : sp<LayerFE>
        - mState : OutputLayerCompositionState
        - mHwc : optional<HWC2::Layer>
        + updateCompositionState()
        + writeStateToHWC()
        + getOutput()
    }

    struct LayerSettings {
        + source : PixelSource
        + geometry : Geometry
        + alpha : float
        + bufferId : uint64_t
    }
}

package "RenderEngine Layer" {
    struct "LayerSettings" as RELayerSettings
    class RenderEngine {
        + drawLayers(std::vector<const LayerSettings*>& layers)
    }

    RenderEngine --> RELayerSettings:use
}

package "Hardware" {
    class "HWC2::Layer" as HwcLayer
}

' ==========================================
' 关系连线
' ==========================================

' SF 管理 Layer
SurfaceFlinger "1" o-- "*" Layer : 管理

' Layer 组合 State
Layer *-- LayerState

' Layer 创建并持有 LayerFE
Layer *-- LayerFE : 创建 & 持有\n(1:N, 对应不同遍历路径)
LayerFE <|-- LayerFEImpl : 实现

' Output 管理 OutputLayer
Output "1" *-- "*" OutputLayer : 拥有 (按显示屏)

' OutputLayer 关联 LayerFE
OutputLayer --> LayerFE : 引用 (获取数据)

' OutputLayer 关联 HWC Layer
OutputLayer --> HwcLayer : 包装硬件层

' LayerFE 生成 LayerSettings
LayerFEImpl ..> LayerSettings : 生成 (prepareClientComposition)
LayerSettings --|> RELayerSettings : 继承/兼容

@enduml

```

**组件职责与实现：**

1. **`Layer` (SurfaceFlinger)**：
* **BufferState 管理**：实现了 BufferStateLayer 模式。通过 `setBuffer` 接收应用提交的 BufferData，更新 `mDrawingState`。
* **Latch 机制**：在 VSYNC 到达时，`latchBufferImpl` 将 `mDrawingState` 中的 Buffer 和属性移动到 `mBufferInfo`，确立当前帧的显示内容。
* **LayerFE 工厂**：负责创建并持有 `LayerFE` 实例，建立与 CompositionEngine 的连接。


2. **`LayerFE` (Front End)**：
* **快照隔离**：LayerFE 充当 Layer 的快照代理。当 `latchBuffer` 发生时，Layer 的状态被复制到 LayerFE 的 `LayerFECompositionState` (`mSnapshot`) 中。
* **并发安全**：CompositionEngine 在合成过程中只读取 LayerFE 的快照数据，从而允许 SF 主线程在不阻塞合成的情况下处理下一帧的 Layer 属性更新。


3. **`OutputLayer` (CompositionEngine)**：
* **Output 关联**：一个 Layer 可能显示在多个屏幕上（如镜像）。`OutputLayer` 将 `LayerFE` 的数据映射到具体的 `Display` 坐标系中，计算裁剪、投影和 Z-Order。
* **HWC 桥接**：持有 `HWC2::Layer` 指针，负责将图层属性写入硬件合成器。



---

## 3. Display 图像合成流程

图像合成是将所有 OutputLayer 的内容按照 Z-Order 叠加并输出到显示缓冲区的过程。该过程是一个由 VSYNC 驱动的闭环。

### 3.1 数据流与合成路径选择

下图展示了 Buffer 从 App 生产到最终显示的物理流转路径，以及基于 RenderEngine 和 HWC 的分流机制。

```plantuml
@startuml
!theme cerulean
hide empty members
skinparam linetype ortho
skinparam nodesep 60
skinparam ranksep 50

' ==========================================
' 1. App Layer System (新增部分：生产端)
' ==========================================
package "App Layer System" {
    package "App BufferQueue" <<Rectangle>> {
        interface "IGBP (App)" as AppIGBP
        class "BufferQueue (App)" as AppBQ
        interface "IGBC (Layer)" as AppIGBC
    }

    ' App 生产流程
    AppIGBP -down-o AppBQ: App 写入
    AppBQ o-down- AppIGBC: Layer 读取

}

' ==========================================
' 2. SurfaceFlinger (总管)
' ==========================================
package "SurfaceFlinger Core" {
    class SurfaceFlinger {
        - mLayers : List<sp<Layer>>
        - mDisplays : Map
        + handleMessageInvalidate()
    }

    class DisplayDevice {
        - mCompositionDisplay
        - mDisplaySurface
    }

    class Layer {
        - mDrawingState : State
        - mBufferInfo : BufferInfo
        + setBuffer() : "接收 Buffer (BufferState 模式)"
        + latchBufferImpl() : "锁定最新 Buffer"
        + getBuffer() : "获取 GraphicBuffer"
    }    
}

AppIGBC -right-> Layer : 消费
' SF 管理 Layer 和 Display
SurfaceFlinger -down-> Layer : 遍历 Layer
SurfaceFlinger -down-> DisplayDevice : 管理 Display

' ==========================================
' 3. CompositionEngine (逻辑核心 & 决策)
' ==========================================
package "CompositionEngine" {
    abstract class Output {
        - mRenderSurface
        - mOutputLayers : List<OutputLayer>
        + composeSurfaces()
    }

    class "\tOutputLayer\t\t\t\t\t" as OutputLayer {
        - mLayerFE : LayerFE
        + writeStateToHWC()
    }

    class Display {
        ' 逻辑对象
    }

    class RenderSurface {
        - mNativeWindow
        - mDisplaySurface
        + queueBuffer()
    }
    
    class RenderEngine {
        + drawLayers()
    }

    interface DisplaySurface {
        + advanceFrame()
    }
}

' CE 内部关系
DisplayDevice -down-> Display : 持有
Display -down-|> Output
Output "1" *-down- "*" OutputLayer : 包含
Output "1" *-down- "1" RenderSurface : 拥有

' OutputLayer 关联具体的 Layer 数据
OutputLayer .left.> Layer : 引用 Layer 数据

' ==========================================
' 4. 关键分支：渲染路径选择
' ==========================================

' 路径 A: GPU 合成 (RenderEngine 读取 Layer Buffer)
RenderEngine .up.> Layer : Path A: 读取 Layer Buffer (纹理)
Output .right.> RenderEngine #purple : 指挥绘图
RenderEngine .down.> RenderSurface#purple : 绘制结果 (Target)


' ==========================================
' 5. 实现层 & 基础设施
' ==========================================
package "Display Hardware" {
    class "\t\t\tFramebufferSurface\t\t" as FramebufferSurface{
        + advanceFrame()
        + setClientTarget()
    }
    
    interface "\t\tANativeWindow\t\t" as SFNativeWindow {
        + queueBuffer()
        + queueBuffer()
    }

    ' ==========================================
    ' 6. SF BufferQueue (输出端)
    ' ==========================================
    package "Display BufferQueue" <<Rectangle>> {
        interface "IGBP" as SFIGBP
        class "BufferQueue" as SFBQ
        interface "IGBC" as SFIGBC
    }

}

package "HWC Abstraction" {
    class "\t\t\t\tHWComposer\t\t\t\t\t\t" as HWComposer{
        + setLayerBuffer()
        + setClientTarget()
    }
}

' RenderSurface 的分发
DisplayDevice -right-> DisplaySurface : 持有管道
RenderSurface -right-> DisplaySurface : 控制流
RenderSurface -down-> SFNativeWindow#purple : 数据流

' FramebufferSurface 实现
FramebufferSurface .up.|> DisplaySurface
FramebufferSurface -down-> HWComposer#purple : 提交合成后的ClientTarget
' 路径 B: HWC 合成 (直接透传 Layer Buffer)
OutputLayer ..> HWComposer #red : Path B: setLayerBuffer(直接送给硬件)


SFNativeWindow -down-> SFIGBP
SFIGBP --o SFBQ
SFBQ o-- SFIGBC
SFIGBC --> FramebufferSurface

@enduml

```

**技术路径详解：**

1. **路径 A：GPU 合成 (Client Composition)**（紫色路径）
* **触发条件**：HWC 无法处理的 Layer（如超出图层数量限制、不支持的混合模式、复杂的圆角/模糊特效）。
* **输入**：`Output` 将这些 Layer 标记为 `Client`，提取其 Buffer 句柄作为**纹理**。
* **处理**：`RenderEngine` 使用 OpenGL/Skia 对纹理进行采样和片段着色。
* **输出**：渲染结果写入 `RenderSurface` 申请的 `GraphicBuffer`。该 Buffer 入队后，由 `FramebufferSurface` 消费，并作为 **ClientTarget** 提交给 HWC。


2. **路径 B：HWC 合成 (Device Composition)**（红色路径）
* **触发条件**：标准的 Overlay 图层，硬件直接支持。
* **处理**：`OutputLayer` 通过 `writeStateToHWC`，将 Layer 的 Buffer 句柄、屏幕坐标、裁切区域直接配置给 `HWComposer`。
* **输出**：无中间 Buffer 生成。显示控制器（Display Controller）在扫描输出时，利用 DMA 直接读取 App 的 Buffer 内存进行叠加。



### 3.2 完整的合成时序

整个合成周期分为调度、锁定、策略决策、执行与上屏四个阶段。

```plantuml
@startuml
!theme plain
hide footbox
skinparam linetype ortho
skinparam sequenceMessageAlign center
autonumber

' ==========================================
' 参与者定义
' ==========================================

box "Scheduling & Logic" #f9f9f9
    participant "MessageQueue\n(VSYNC)" as MQ
    participant "SurfaceFlinger" as SF
    participant "Layer" as Layer
end box

box "Composition Engine" #e1f5fe
    participant "Output\n(Display)" as Output
    participant "LayerFE\n(Snapshot)" as LayerFE
    participant "OutputLayer" as OutLayer
    participant "RenderSurface" as RS
end box

box "Render Hardware" #e8f5e9
    participant "RenderEngine\n(GPU)" as RE
    participant "FramebufferSurface" as FBS
end box

box "Hardware Composer" #fff3e0
    participant "HWComposer\n(HAL)" as HWC
end box

' ==========================================
' Phase 1: 调度与锁定 (Heartbeat & Latch)
' ==========================================
== Phase 1: VSYNC Trigger & Data Latching ==

MQ ->> SF: onMessageInvalidate() \n(VSYNC Arrives)
activate SF

SF ->> SF: handleMessageTransaction()\n处理 Layer 属性变化
SF ->> SF: handleMessageInvalidate()

loop 遍历所有 Layer
    SF ->> Layer: latchBuffer()
    activate Layer
    note right of Layer: 锁定当前帧的 Buffer\n更新 mBufferInfo
    
    Layer ->> LayerFE: updateSnapshot()
    activate LayerFE
    note right of LayerFE: 固化 Buffer 句柄\n隔离主线程
    deactivate LayerFE
    deactivate Layer
end

' ==========================================
' Phase 2: 收集与策略协商 (Strategy)
' ==========================================
== Phase 2: Visibility & Strategy Choice ==

SF ->> Output: composeSurfaces()
activate Output

' 1. 收集可见层
Output ->> Output: collectVisibleLayers()
note right of Output: 计算可见性、裁剪、Z-Order\n创建 OutputLayer 列表

' 2. 更新合成状态
Output ->> OutLayer: updateCompositionState()
activate OutLayer
OutLayer ->> LayerFE: getCompositionState()
LayerFE -->> OutLayer: return Snapshot (Geometry, Buffer)
deactivate OutLayer

' 3. 询问 HWC (Validate)
Output ->> Output: prepareFrame() (策略协商)
Output ->> HWC: validateDisplay()
note right of HWC
    HWC 检查每个 Layer 的属性。
    返回它<b>不能</b>处理的 Layer 列表。
end note
HWC -->> Output: ChangedCompositionTypes (Fallback to GPU)

Output ->> OutLayer: applyCompositionType()
note right of OutLayer
    根据 HWC 的反馈，标记每个 Layer 是
    <color:red><b>DEVICE (HWC)</b></color> 还是 <color:blue><b>CLIENT (GPU)</b></color>
end note

' ==========================================
' Phase 3: 执行合成 (Execution)
' ==========================================
== Phase 3: Composition Execution ==

' --- 分支 B: GPU 合成 (Client Composition) ---
group Client Composition (GPU Rendering)
    Output ->> Output: generateClientCompositionRequests()
    
    loop 遍历标记为 CLIENT 的 OutputLayer
        Output ->> LayerFE: prepareClientComposition()
        activate LayerFE
        note right of LayerFE: 封装 LayerSettings\n包含 ExternalTexture(Buffer)
        LayerFE -->> Output: LayerSettings
        deactivate LayerFE
    end

    Output ->> RS: dequeueBuffer()
    RS -->> Output: 目标 Buffer (Render Target)

    Output ->> RE: drawLayers(LayerSettings[], TargetBuffer)
    activate RE
    note right of RE
        GPU Shader 运行：
        采样 Layer Buffer (纹理)
        混合写入 Target Buffer
    end note
    RE -->> Output: 绘制完成 (Fence)
    deactivate RE

    Output ->> RS: queueBuffer(TargetBuffer)
    activate RS
    
    ' 关键连接点：RenderSurface 通知 FramebufferSurface
    RS ->> FBS: advanceFrame()
    activate FBS
    note right of FBS: 从 BufferQueue 获取\nGPU 画好的 Buffer
    
    FBS ->> HWC: setClientTarget(TargetBuffer)
    note right of HWC
        HWC 接收 GPU 合成结果
        作为背景层或混合层
    end note
    deactivate FBS
    deactivate RS
end

' --- 分支 A: HWC 合成 (Device Composition) ---
group Device Composition (Overlay)
    loop 遍历标记为 DEVICE 的 OutputLayer
        Output ->> OutLayer: writeStateToHWC()
        activate OutLayer
        OutLayer ->> LayerFE: getBuffer()
        OutLayer ->> HWC: setLayerBuffer(Slot, BufferHandle, Fence)
        note right of HWC
            <color:red><b>透传模式</b></color>
            HWC 直接持有 Layer 的 Buffer 句柄
        end note
        deactivate OutLayer
    end
end

' ==========================================
' Phase 4: 最终上屏 (Present)
' ==========================================
== Phase 4: Final Present ==

Output ->> HWC: presentDisplay()
activate HWC
note right of HWC
    硬件刷新屏幕：
    读取 ClientTarget (GPU结果)
    + 读取 Overlay Layers (透传结果)
end note
HWC -->> Output: PresentFence
deactivate HWC

Output ->> Output: onFrameCommitted()
deactivate Output
deactivate SF

@enduml

```

---

## 4. 深入 RenderEngine：GPU 合成详解

RenderEngine 是 SurfaceFlinger 的渲染后端，负责执行所有 Client Composition 任务。它屏蔽了底层 OpenGL ES / Vulkan 的 API 差异，提供面向图层的绘制接口。

### 4.1 RenderEngine 架构概览

RenderEngine 采用了分层与装饰器模式设计，包含接口定义、线程模型、逻辑实现与后端驱动。

```plantuml
@startuml
!theme plain
hide empty members
skinparam linetype ortho
skinparam nodesep 80
skinparam ranksep 150

' ==========================================
' 接口与基类
' ==========================================
package "Interface Layer" {
    abstract class RenderEngine {
        + {static} create() : unique_ptr<RenderEngine>
        + {abstract} drawLayers()
        + {abstract} mapExternalTextureBuffer()
    }

    class RenderEngineThreaded {
        - mRenderEngine : unique_ptr<RenderEngine>
        - mThread : thread
        + drawLayers() : "推入任务队列"
    }
}

' ==========================================
' 核心实现层 (Skia Base)
' ==========================================
package "Skia Implementation Layer" {
    abstract class "SkiaRenderEngine\t\t\t\t\t\t\t\t\t\t\t\t\t" as SkiaRenderEngine {
        # mTextureCache : TextureCache
        # mCaptureCache : CaptureCache
        + drawLayers() : "通用 Skia 绘制逻辑"
        # drawLayersInternal()
    }
}

' ==========================================
' 后端具体实现 (Backends)
' ==========================================
package "Backend Layer" {
    class SkiaGLRenderEngine {
        - mEGLDisplay : EGLDisplay
        - mEGLContext : EGLContext
        + create()
        --
        (Ganesh GL Backend)
    }

    class GaneshVkRenderEngine {
        - mInstance : VkInstance
        - mDevice : VkDevice
        + create()
        --
        (Ganesh Vulkan Backend)
    }

    class GraphiteVkRenderEngine {
        + create()
        --
        (Graphite Vulkan Backend)
    }
}

' ==========================================
' 数据对象
' ==========================================
package "Data Objects" {
    class ExternalTexture {
        - mBuffer : sp<GraphicBuffer>
        + getBuffer()
    }
    
    struct LayerSettings {
        + geometry
        + source
        + alpha
    }
}

' ==========================================
' 关系连线
' ==========================================

' 继承关系
RenderEngine <|-- RenderEngineThreaded
RenderEngine <|-- SkiaRenderEngine
SkiaRenderEngine <|-- SkiaGLRenderEngine
SkiaRenderEngine <|-- GaneshVkRenderEngine
SkiaRenderEngine <|-- GraphiteVkRenderEngine

' 组合关系 (Decorator Pattern)
RenderEngineThreaded o-- RenderEngine : 包装实际引擎

' 依赖关系
RenderEngine ..> ExternalTexture : 管理
RenderEngine ..> LayerSettings : 消费


@enduml

```

**关键组件实现原理：**

* **RenderEngineThreaded (Threading)**：这是一个装饰器类，用于实现**单线程异步渲染**。它内部维护一个命令队列（`mFunctionCalls`）和一个后台工作线程（`mThread`）。当外部调用 `drawLayers` 时，它将调用参数封装为 Lambda 表达式推入队列，并立即返回 `std::future`。这确保了 SurfaceFlinger 主线程不会被耗时的 GPU 提交（`flush/submit`）操作阻塞。
* **SkiaRenderEngine (Core Logic)**：这是业务逻辑的核心。它负责将 SurfaceFlinger 的 `LayerSettings`（包含几何、特效、Buffer）翻译成 Skia 的 `SkCanvas` 绘图指令。例如，它将 `LayerSettings.geometry.positionTransform` 转换为 `canvas->concat(matrix)`，将圆角参数转换为 `canvas->drawRRect()`。
* **SkiaGLRenderEngine (GL Backend)**：负责管理 EGL 上下文。在初始化时，它创建 EGLDisplay 和 EGLContext，并将原生的 GL 环境封装成 Skia 的 `GrDirectContext`，注入到 `SkiaRenderEngine` 中，使其具备操作 GPU 的能力。

### 4.2 物理数据流与内存视图

在 RenderEngine 的合成过程中，数据并未发生拷贝，而是以句柄（Handle）形式在进程间和模块间流转。

```plantuml
@startuml
!theme plain
hide empty members
skinparam linetype ortho
skinparam nodesep 100
skinparam ranksep 120

package "Physical RAM (Shared Memory)" {
    class "App Buffer Memory\t\t\t\t\t\t" as SharedMemApp {
        <color:red><b>[ 像素数据 R,G,B,A... ]</b></color>
        (由 App GPU 写入)
    }
    
    class "\tSF Output Memory\t\t\t\t" as SharedMemSF {
        <color:blue><b>[ 合成后的像素数据 ]</b></color>
        (由 SF GPU 写入)
    }
}

package "App Process" {
    class "App BufferQueue" as AppBQ
    AppBQ -down-> SharedMemApp : 1. 持有句柄\n(Producer)
}

package "SurfaceFlinger Process" {
    class "\t\tLayer\t\t" as Layer
    class "RenderEngine" as RE
    class "FramebufferSurface" as FBS
    
    Layer -down-> SharedMemApp : 2. 接收句柄\n(Consumer/Wrapper)
    
    RE -down-> SharedMemApp : 3. 绑定为<b>纹理(Texture)</b>\n(Input Source)
    RE -down-> SharedMemSF : 4. 绑定为<b>渲染目标(Target)</b>\n(Output Destination)
    
    FBS -down-> SharedMemSF : 5. 持有句柄\n(Consumer)
}

package "HWC / Display Hardware" {
    class "Display Controller" as HWC
    HWC -up-> SharedMemSF : 6. 读取显示\n(Scanout)
}

note left of SharedMemApp
    <b>核心真相：</b>
    数据一直躺在 RAM 里。
    跨进程传递的只是指向
    这块 RAM 的文件描述符 (fd)。
end note

@enduml

```

### 4.3 逻辑工作流：Draw Call 视图

RenderEngine 将物理 Buffer 抽象为纹理，将合成过程转化为一次标准的 GPU 渲染流程。

```plantuml
@startuml
!theme plain
hide empty members
skinparam linetype ortho
skinparam nodesep 80
skinparam ranksep 120

package "Inputs: Layers (Textures)" {
    class "Layer A\n(Texture 1)" as TexA
    class "Layer B\n(Texture 2)" as TexB
    class "Layer C\n(Texture 3)" as TexC
}

package "RenderEngine (The GPU Worker)" {
    class "\t\tShader / Pipeline\t\t\t\t\t" as Shader {
        <b>Step 1: Sampling (采样)</b>
        读取纹理坐标 (u,v) 处的颜色
        ====
        <b>Step 2: Math (运算)</b>
        Color = A*alpha + B*(1-alpha)
        处理圆角、阴影、模糊
    }
}

package "Output: FramebufferSurface" {
    class "ClientTarget Buffer\n(Render Target)" as OutBuf {
        <color:blue><b>[ 最终图像 ]</b></color>
        格式: RGBA_8888 / FP16
    }
}

' 流程连线
TexA -down-> Shader : Read (Sample)
TexB -down-> Shader : Read (Sample)
TexC -down-> Shader : Read (Sample)

Shader -down-> OutBuf : Write (Render)

note bottom of Shader
    <b>drawLayers() 的本质：</b>
    1. Bind Textures (Layer Buffers)
    2. Bind Framebuffer (Target Buffer)
    3. DrawCall (运行 Shader 合成像素)
end note

@enduml

```

**实现细节：**

1. **绑定输入**：`SkiaRenderEngine::mapExternalTextureBuffer` 将 Layer 的 Buffer 映射为 `SkiaBackendTexture`。
2. **绑定输出**：将 FramebufferSurface 提供的 Buffer 封装为 `SkSurface`，作为渲染画布。
3. **指令生成**：根据 `LayerSettings`，通过 `SkCanvas` 发出 `drawImageRect` 等指令。
4. **Shader 执行**：`flushAndSubmit` 触发 Skia 将高级指令转换为 GL/VK 命令流，GPU 运行 Shader 执行像素混合和特效计算。

### 4.4 RenderEngine 异步调用时序

下图展示了 `RenderEngineThreaded` 如何通过任务队列实现异步渲染。

```plantuml
@startuml
!theme plain
hide footbox
skinparam sequenceMessageAlign center

participant "SurfaceFlinger\n(Output)" as SF
participant "RenderEngine\n(Threaded)" as Threaded
participant "Task Queue" as Queue
participant "Worker Thread" as Worker
participant "SkiaGLRenderEngine\n(GLES Backend)" as GLImpl
participant "Skia\n(Library)" as Skia

== 1. 提交绘制任务 ==

SF ->> Threaded: drawLayers(layers, buffer, fence)
activate Threaded
note right of Threaded
    非阻塞调用
    仅打包任务
end note

Threaded ->> Queue: push(Task)
Threaded -->> SF: Future<Fence>
deactivate Threaded

== 2. 异步执行 ==

Worker ->> Queue: wait & pop()
activate Worker

Worker ->> GLImpl: drawLayers(layers, buffer)
activate GLImpl

' 准备画布
GLImpl ->> GLImpl: mapBuffer(buffer) -> SkSurface
GLImpl ->> Skia: getCanvas()

' 遍历图层
loop For each Layer
    GLImpl ->> GLImpl: setupMatrix & Clip
    
    alt is Texture Layer
        GLImpl ->> Skia: canvas->drawImageRect(image, paint)
    else is Solid Color
        GLImpl ->> Skia: canvas->drawRect(rect, paint)
    end
    
    opt has Shadow/Blur
        GLImpl ->> Skia: SkShadowUtils::DrawShadow / Paint.setImageFilter
    end
end

' 提交
GLImpl ->> Skia: context->flushAndSubmit()
activate Skia
Skia -->> GLImpl: Submit
deactivate Skia

GLImpl ->> GLImpl: createFence()
GLImpl -->> Worker: DrawFence
deactivate GLImpl

' 完成
Worker ->> SF: Future.set(DrawFence)
deactivate Worker

@enduml

```

---

## 5. Scheduler 与 VSYNC 调度

Scheduler 是 SurfaceFlinger 的时间基准控制中心，负责生成 VSYNC 信号、分发事件以及根据系统状态动态调整刷新率。

### 5.1 Scheduler 核心架构

Scheduler 位于 HWC 硬件信号与上层逻辑之间，起到解耦和策略控制的作用。

```mermaid
graph TD
    %% 外部输入
    subgraph Inputs [输入信号]
        HWC_Vsync[HWC VSYNC 信号]
        Touch[Input 触摸事件]
        Layers[Layer 更新频率]
        Power[电源/热状态]
    end

    %% Scheduler 核心
    subgraph Scheduler_Core [Scheduler]
        direction TB
        
        VsyncModulator[VsyncModulator<br/>相位控制]
        LayerHistory[LayerHistory<br/>FPS检测]
        Policy[RefreshRate Policy<br/>策略决策]
        
        subgraph Timers [状态机定时器]
            IdleTimer[Idle Timer]
            TouchTimer[Touch Timer]
        end
        
        Pacesetter[Pacesetter Logic<br/>多屏领跑机制]
    end

    %% 输出分发
    subgraph EventThreads [VSYNC 分发]
        AppET[EventThread App<br/>Cycle::Render]
        SfET[EventThread SF<br/>Cycle::LastComposite]
    end

    %% 最终输出
    subgraph Outputs [输出动作]
        Choreographer[App Choreographer]
        SF_Main[SF Main Thread]
        HWC_Config[HWC Config/Mode<br/>切帧率]
    end

    %% 连线
    HWC_Vsync --> Scheduler_Core
    Touch --> TouchTimer
    Layers --> LayerHistory
    
    Scheduler_Core --> AppET
    Scheduler_Core --> SfET
    
    AppET --> Choreographer
    SfET --> SF_Main
    
    Policy --> HWC_Config

```

**关键组件机制：**

* **VsyncModulator**：根据系统负载动态调整 App VSYNC 和 SF VSYNC 的相位偏移（Offset）。例如，当系统掉帧时，减小偏移量以给予 CPU/GPU 更多处理时间。
* **LayerHistory**：记录每个 Layer 的提交时间戳，计算其平均帧率。这是内容自适应刷新率（Content Detection）的基础。
* **Pacesetter**：在多屏设备中，选定一个主屏作为时间基准，其他屏幕的 VSYNC 基于主屏时钟进行偏移生成，防止节奏混乱。

### 5.2 智能刷新率决策流程

**场景一：触摸升频 (Touch Boost)**
为了保证交互的跟手性，当 Input 系统检测到触摸时，Scheduler 会强制将屏幕刷新率提升至最高。

```mermaid
sequenceDiagram
    participant Touch as InputSystem
    participant Sched as Scheduler
    participant Timer as TouchTimer
    participant Policy as PolicyLogic
    participant HWC as HWC

    Touch->>Sched: onTouchHint()
    Sched->>Timer: reset()
    Timer-->>Policy: Callback(TimerState::Reset)
    
    rect rgb(230, 240, 255)
    Note right of Policy: 策略判定：进入 Touch 状态
    Policy->>Policy: Current Mode = 120Hz (Max)
    end
    
    Policy->>HWC: setActiveConfig(120Hz)
    HWC-->>Sched: VSYNC (120Hz)

```

**场景二：内容帧率匹配 (Content Detection)**
当播放 30fps 视频时，`LayerHistory` 检测到 Buffer 提交间隔稳定在 33ms，Scheduler 会选择 60Hz 或 30Hz 的显示模式以避免画面抖动（Judder）。

```mermaid
sequenceDiagram
    participant App as VideoApp
    participant LH as LayerHistory
    participant Sched as Scheduler
    participant HWC

    loop 播放视频 (30fps)
        App->>Sched: queueBuffer (T1)
        App->>Sched: queueBuffer (T2)
        Sched->>LH: record(LayerID, PresentTime)
    end

    LH->>LH: 分析: 平均间隔 33ms -> 30fps
    LH-->>Sched: Summary: Vote for 30Hz/60Hz

    Sched->>Sched: chooseDisplayModes()
    Note right of Sched: 最佳匹配: 60Hz (30的倍数)
    
    Sched->>HWC: setActiveConfig(60Hz)

```

---

## 6. HWComposer 硬件抽象与通信

HWComposer (HWC) 是 SurfaceFlinger 与底层显示驱动交互的 AIDL 接口。为了减少 Binder IPC 通信的开销，HWC 引入了复杂的命令缓冲机制。

### 6.1 HWComposer 架构设计

下图展示了 HWComposer 的层级结构，从顶层的单例管理到底层 AIDL 接口的代理。

```mermaid
classDiagram
    direction TD

    %% ==========================================
    %% 1. Top Level: HWComposer
    %% ==========================================
    class HWComposer {
        - mDisplayData : map~HalDisplayId, DisplayData~
        + getDeviceCompositionChanges() : void
    }

    class DisplayData {
        - port : int
        - hwcDisplay : unique_ptr~HWC2::Display~
    }

    %% ==========================================
    %% 2. Abstraction Layer (HWC2)
    %% ==========================================
    %% 使用 ID["Label"] 语法处理特殊字符
    class HWC2_Display["HWC2::Display"] {
        <<Interface>>
    }

    class HWC2_impl_Display["HWC2::impl::Display"] {
        - mComposer : Hwc2::Composer&
        + presentOrValidate() : void
    }

    class Hwc2_Composer["Hwc2::Composer"] {
        <<Interface>>
    }

    %% ==========================================
    %% 3. Implementation Layer (AIDL)
    %% ==========================================
    class AidlComposer["Hwc2::AidlComposer"] {
        - mAidlComposer
        - mAidlComposerClient
        - mAidlComposerCallback
        + executeCommands() : void
        + presentOrValidateDisplay() : void
    }

    %% ==========================================
    %% 4. Command Processing (Writer/Reader)
    %% ==========================================
    class ComposerClientWriter {
        - mDisplayCommand : optional~DisplayCommand~
        - mLayerCommand : optional~LayerCommand~
        - mCommands : vector~DisplayCommand~
        - mDisplay : int
        + presentOrValidateDisplay() : void
        + setDisplayBrightness() : void
    }

    class ComposerClientReader {
        - mErrors : vector~CommandError~
        - mReturnData : map~int64_t, ReturnData~
        + parse(results) : void
    }

    %% ==========================================
    %% 5. AIDL Interfaces (Bottom Leaves)
    %% ==========================================
    class AidlComposerInterface {
        <<AidlInterface>>
    }
    
    class AidlComposerClient {
        <<AidlInterface>>
        + executeCommands() : void
    }

    class AidlComposerCallbackWrapper {
        <<Callback>>
    }

    %% ==========================================
    %% Relationships
    %% ==========================================

    %% 1. HWComposer holds DisplayData
    HWComposer *-- DisplayData

    %% 2. DisplayData holds HWC2::Display
    DisplayData *-- HWC2_Display

    %% 3. HWC2::impl::Display implements HWC2::Display
    HWC2_Display <|-- HWC2_impl_Display

    %% 4. impl::Display uses Composer
    HWC2_impl_Display --> Hwc2_Composer

    %% 5. AidlComposer implements Composer
    Hwc2_Composer <|-- AidlComposer

    %% 6. AidlComposer Aggregates Writer & Reader (Key to command buffer)
    AidlComposer o-- ComposerClientWriter : Map<DisplayId>
    AidlComposer o-- ComposerClientReader : Map<DisplayId>

    %% 7. AidlComposer holds AIDL Proxies
    AidlComposer --> AidlComposerInterface : - mAidlComposer
    AidlComposer --> AidlComposerClient : - mAidlComposerClient
    AidlComposer --> AidlComposerCallbackWrapper : - mAidlComposerCallback

```

### 6.2 命令批处理机制 (Batching)

`AidlComposer` 并不直接发起 IPC 调用。它维护了每个 Display 对应的 `ComposerClientWriter`。当 SurfaceFlinger 调用 `setLayerBuffer` 或 `setLayerColor` 等接口时，这些操作被序列化为 AIDL 定义的结构体（`DisplayCommand`）并缓存在 `mCommands` 内存缓冲区中。

```mermaid
classDiagram
    direction TB

    %% ==========================================
    %% 核心控制器
    %% ==========================================
    class AidlComposer {
        - mAidlComposerClient : IComposerClient
        - mWriters : Map~DisplayId, ComposerClientWriter~
        - mReaders : Map~DisplayId, ComposerClientReader~
        + setLayerBuffer()
        + execute()
        + presentDisplay()
    }


    %% ==========================================
    %% 写入侧 (Client -> Service)
    %% ==========================================
    class ComposerClientWriter {
        - mDisplay : int64_t
        - mCommands : vector~DisplayCommand~
        - mDisplayCommand : optional~DisplayCommand~
        - mLayerCommand : optional~LayerCommand~
        + setLayerBuffer()
        + setLayerColor()
        + takePendingCommands() : vector~DisplayCommand~
    }
    note for ComposerClientWriter "<b>职责：命令缓冲</b><br/>将函数调用转换为AIDL结构体<br/>并缓存在 mCommands 中，不发生IPC"

    %% ==========================================
    %% 读取侧 (Service -> Client)
    %% ==========================================
    class ComposerClientReader {
        - mReturnData : Map~DisplayId, ReturnData~
        + parse(vector~CommandResultPayload~)
        + takePresentFence()
        + takeReleaseFences()
    }
    note for ComposerClientReader "<b>职责：结果解析</b><br/>解析 IPC 返回的 Payload<br/>按类型存入 mReturnData 供查询"


    class CommandResultPayload {
        <<AIDL Union>>
        + presentFence
        + releaseFences
        + error
    }

    class ReturnData {
        + presentFence : ScopedFileDescriptor
        + releasedLayers : vector
    }

    class DisplayCommand {
    <<AIDL Struct>>
    + layers : vector~LayerCommand~
    + clientTarget : ClientTarget
    }


    %% ==========================================
    %% IPC 接口
    %% ==========================================
    class IComposerClient {
        <<AIDL Interface>>
        + executeCommands(commands, out results)
    }



    %% ==========================================
    %% 关系连线
    %% ==========================================
    
    %% 组合关系
    AidlComposer "1" *-- "*" ComposerClientWriter : 拥有 (按Display管理)
    AidlComposer "1" *-- "*" ComposerClientReader : 拥有 (按Display管理)
    AidlComposer ..> IComposerClient : 代理调用 (Binder IPC)

    %% 数据流向：写
    ComposerClientWriter ..> DisplayCommand : 生成并缓存
    DisplayCommand ..> IComposerClient : 作为参数发送

    %% 数据流向：读
    IComposerClient ..> CommandResultPayload : 返回结果
    CommandResultPayload ..> ComposerClientReader : 输入解析
    ComposerClientReader *-- ReturnData : 内部存储解析结果


```

### 6.3 HWC 交互时序

只有当调用 `execute()` 或 `presentOrValidateDisplay()` 时，`AidlComposer` 才会将缓冲区中的所有命令打包，通过 `IComposerClient::executeCommands` 发起一次 Binder 调用，并将返回结果交给 `ComposerClientReader` 解析。

```mermaid
sequenceDiagram
    autonumber
    participant Caller as HWComposer
    participant Aidl as AidlComposer
    participant Writer as ComposerClientWriter
    participant Binder as "IComposerClient (Binder)"
    participant Reader as ComposerClientReader

    Note over Caller, Writer: 阶段 1: 命令积攒 (Buffering)<br/>此处不发生 IPC，仅内存操作

    Caller->>Aidl: setLayerBuffer(display, layer, buffer...)
    activate Aidl
    Aidl->>Aidl: getWriter(display)
    Aidl->>Writer: setLayerBuffer(..., buffer)
    activate Writer
    Writer->>Writer: getLayerCommand()
    Writer->>Writer: 填充 Buffer 数据到 mLayerCommand
    deactivate Writer
    deactivate Aidl

    Caller->>Aidl: setLayerColor(display, layer, color...)
    activate Aidl
    Aidl->>Writer: setLayerColor(..., color)
    deactivate Aidl

    Note over Caller, Reader: 阶段 2: 批量提交与解析 (Execution & Parsing)

    Caller->>Aidl: execute(display) / presentDisplay
    activate Aidl

    Aidl->>Writer: takePendingCommands()
    activate Writer
    Writer->>Writer: flushLayerCommand()
    Writer->>Writer: flushDisplayCommand()
    Writer-->>Aidl: `vector<DisplayCommand>` cmds
    deactivate Writer

    Note right of Writer: mCommands 被清空<br/>cmds 被移动到 AidlComposer

    Aidl->>Binder: executeCommands(cmds)
    activate Binder
    Note right of Binder: 跨进程传输<br/>Hardware Composer 处理命令
    Binder-->>Aidl: `vector<CommandResultPayload>` results
    deactivate Binder

    Aidl->>Reader: parse(results)
    activate Reader
    loop 遍历 results
        Reader->>Reader: 根据 Tag (Fence/Error/etc)<br/>分类存入 mReturnData
    end
    deactivate Reader

    Aidl->>Reader: takeErrors()
    activate Reader
    Reader-->>Aidl: errors
    deactivate Reader

    opt 如果 Caller 需要 PresentFence
        Aidl->>Reader: takePresentFence(display)
        activate Reader
        Reader-->>Aidl: ScopedFileDescriptor
        deactivate Reader
    end

    Aidl-->>Caller: Error::NONE
    deactivate Aidl

```