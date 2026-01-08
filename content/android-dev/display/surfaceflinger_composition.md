+++
date = '2025-09-29T10:22:54+08:00'
draft = false
title = 'SurfaceFlinger详解'
+++


## Display创建过程

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

## Layer管理与渲染

### Layer 核心架构类图

这张图展示了 **SurfaceFlinger**（管理状态）、**LayerFE**（数据快照/接口）和 **CompositionEngine**（合成逻辑）之间的静态关系。

**核心设计点：**

* **Layer**: 是 SurfaceFlinger 的核心实体，管理 Buffer队列、DrawingState 等。
* **LayerFE (Front End)**: 是 Layer 暴露给 CompositionEngine 的“代理”。它持有 Layer 的快照 (`mSnapshot`)，实现了**数据隔离**（SF 主线程修改 Layer，CE 线程读取 LayerFE）。
* **OutputLayer**: 是 CompositionEngine 中 Layer 的容器。因为它属于某个具体的 `Output` (Display)，所以它负责计算该 Layer 在该屏幕上的具体属性（如投影、裁剪）。

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






## Display图像合成流程

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

总结数据流向
```txt
[RenderEngine] 
      | (绘制 GPU 合成部分)
      v
[IGraphicBufferProducer] --> [BufferQueue] --> [IGraphicBufferConsumer]
                                                      |
                                                      v
                                             [FramebufferSurface]
                                                      | (setClientTarget)
                                                      v
                                                [HWComposer] --> [物理屏幕]
```


### 数据流与合成架构解析

这张架构图宏观地展示了 Android 图形系统从应用层生产到硬件层显示的完整流水线。核心逻辑可以概括为 **“一个源头，两次决策，殊途同归”**。

#### 1. 生产端：数据的源头 (App Layer System)

一切始于左上角的 **App Layer System**。

* **生产 (Produce)**：应用程序作为生产者，通过 `AppIGBP` 将绘制好的 GraphicBuffer 填充到 **App BufferQueue** 中。
* **消费 (Consume)**：SurfaceFlinger 端的 `Layer` 作为消费者 (`AppIGBC`)，通过 `latchBuffer()` 锁定应用最新提交的 Buffer。此时，SF 拥有了图层的原始数据。

#### 2. 决策层：CompositionEngine 的分流

中间的 **CompositionEngine** 是“大脑”，负责决定每一帧如何合成。`Output`（代表屏幕）管理着多个 `OutputLayer`。在这里，系统面临关键的**路径选择**：

* **路径 A：GPU 合成 (Client Composition)** —— *图中紫色箭头*
  * **场景**：当图层有复杂特效（如圆角、模糊）、不支持的格式或超出 HWC 处理能力时。
  * **流程**：`Output` 指挥 **`RenderEngine`** 工作。`RenderEngine` 将 `Layer` 中的 Buffer 作为**纹理 (Texture)** 读取，利用 GPU 将其绘制到 `RenderSurface` 申请的目标 Buffer 上。
  * **流向**：图层数据被“画”到了新的 Buffer 中，进入下方的 Display BufferQueue。


* **路径 B：HWC 合成 (Device Composition)** —— *图中红色箭头*
  * **场景**：标准图层，硬件直接支持，效率最高。
  * **流程**：`OutputLayer` 直接将 `Layer` 中的原始 Buffer 句柄传递给 **`HWComposer`** (`setLayerBuffer`)。
  * **流向**：数据**透传**。Buffer 不经过 GPU 读写，直接由 Display Controller 读取并显示。


#### 3. 实现层与基础设施 (Display Hardware)

这一层负责管理合成后的结果（主要是 GPU 合成的结果）：

* **RenderSurface 的双重角色**：它是连接逻辑与物理的枢纽。
* **向上**：对接 `RenderEngine`，作为绘图目标。
* **向下**：对接 **Display BufferQueue** (`SFNativeWindow`)，将 GPU 画好的帧推入队列。


* **FramebufferSurface**：它是 Display BufferQueue 的消费者。它从队列中取出 GPU 合成好的 Buffer，通过 `setClientTarget()` 提交给 HWC。

#### 4. 最终汇聚：HWComposer

在图的最底部，**`HWComposer`** 完成最后的汇聚：

1. 接收来自 **路径 B** 的独立图层 Buffer (`setLayerBuffer`)。
2. 接收来自 **路径 A** 的 GPU 合成结果 Buffer (`setClientTarget`)。
3. 硬件将这两部分内容叠加，最终输出到物理屏幕。


---

### 完整的合成过程


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


这是为您整理的 **Android SurfaceFlinger 合成流水线技术说明书**。这份文档基于之前的代码分析、架构图和时序图，旨在从系统架构角度详细阐述渲染合成的完整生命周期。

---


SurfaceFlinger 的核心职责是充当系统的“合成器”。在每一次 VSYNC 信号的驱动下，它负责收集来自各个应用程序（App）生产的图形缓冲区（GraphicBuffer），决定合成策略（GPU 绘制或 HWC 叠加），并将最终结果提交给显示硬件。

整个流程是一个 **"调度 (Schedule) -> 锁定 (Latch) -> 决策 (Decide) -> 执行 (Execute) -> 上屏 (Present)"** 的闭环系统。



在深入流程之前，需明确以下关键组件的角色：

* **Layer (图层)**: SurfaceFlinger 端对应 App Surface 的实体，管理 BufferQueue 的消费者接口，维护当前帧的绘制状态 (`mDrawingState`)。
* **LayerFE (Front End)**: Layer 的快照/代理接口。它将 Layer 的数据（如 Buffer 句柄、几何变换）固化，供合成线程安全读取，隔离主线程的修改。
* **Output / Display**: 代表一个物理或虚拟屏幕，负责管理该屏幕上的图层集合 (`OutputLayer`) 和合成策略。
* **RenderEngine (RE)**: 基于 GPU (OpenGL ES/Skia/Vulkan) 的绘图引擎，负责执行“客户端合成”。
* **HWComposer (HWC)**: 硬件合成器抽象层，直接对接显示硬件（Display Controller/DPU），负责执行“设备合成”。
* **RenderSurface & FramebufferSurface**: 连接 GPU 输出与 HWC 输入的管道。


整个合成周期由硬件 VSYNC 信号触发，分为四个核心阶段。

**阶段一：调度与数据锁定 (Scheduling & Latching)**

此阶段的目标是**冻结世界**。SurfaceFlinger 必须确定这一帧要显示什么，并在合成期间保持数据不变。

1. **VSYNC 触发**: `MessageQueue` 收到 VSYNC 信号，调用 `onMessageInvalidate()` 唤醒 SurfaceFlinger 主线程。
2. **处理事务**: 处理 WindowManager 发来的层级变更、属性修改等事务。
3. **锁定 Buffer (Latch Buffer)**:
* SF 遍历所有 Layer。如果 App 已经通过 BufferQueue 提交了新 Buffer，SF 调用 `Layer::latchBuffer()`。
* **关键动作**: Buffer 句柄从 `Layer` 的 `mDrawingState` 转移到 `mBufferInfo`。
* **快照更新**: 调用 `LayerFE::updateSnapshot()`，将最新的 Buffer 引用和几何状态复制到 `LayerFE` 中。后续的合成操作只读取 `LayerFE`，此时 App 即使提交新帧也不会影响正在进行的合成。


**阶段二：策略协商与决策 (Strategy Negotiation)**

此阶段的目标是**性能最优化**。系统倾向于让 HWC 硬件处理尽可能多的图层（功耗低、效率高），只有 HWC 处理不了的才交给 GPU。

1. **可见性计算**: `Output` 遍历图层树，计算每个 `OutputLayer` 在当前屏幕上的可见区域、裁剪（Crop）和 Z-Order。不可见图层被剔除。
2. **验证请求 (Validate Display)**:
* `Output` 先假设所有图层都走 **Device Composition (HWC)**。
* 调用 `HWC::validateDisplay()` 将图层列表提交给硬件驱动。


3. **策略回退**:
* HWC 驱动检查每个图层的属性（格式、缩放比例、混合模式等）。
* 如果硬件不支持某个图层，HWC 会在返回结果中标记该图层为 `CLIENT` (需要客户端合成)。
* SF 根据反馈，更新每个 `OutputLayer` 的合成类型：
* **`DEVICE`**: 硬件直接合成。
* **`CLIENT`**: 回退到 GPU 合成。

**阶段三：执行与分流 (Execution & Dispatch)**

根据协商结果，Buffer 数据流向两条截然不同的路径。**注意：此处传递的均为 Buffer 的句柄 (Handle)，而非像素拷贝。**

路径 A：设备合成 (Device Composition / Overlay)

* **适用对象**: 标记为 `DEVICE` 的图层。
* **数据流转**: `LayerFE` -> `OutputLayer` -> `HWComposer`。
* **动作**: `OutputLayer` 调用 `setLayerBuffer(slot, bufferHandle, fence)`。
* **本质**: **透传 (Pass-through)**。SF 直接将 App 生产的 Buffer 句柄交给 HWC。显示控制器在扫描屏幕时，通过 DMA 直接读取这块内存。

路径 B：客户端合成 (Client Composition / GPU)

* **适用对象**: 标记为 `CLIENT` 的图层。
* **数据流转**: `LayerFE` -> `LayerSettings` -> `RenderEngine` -> `TargetBuffer`。
* **动作**:
1. `Output` 收集所有 CLIENT 图层，调用 `LayerFE::prepareClientComposition()` 生成 `LayerSettings` 列表。
2. `RenderSurface` 申请一块新的 Buffer 作为**渲染目标 (Render Target)**。
3. 调用 `RenderEngine::drawLayers()`。


* **GPU 逻辑**:
* **纹理化**: App 的 Buffer 被绑定为 OpenGL/Vulkan **纹理 (Texture)**。
* **着色器 (Shader)**: GPU 运行 Shader，对纹理进行采样、色彩空间转换、Alpha 混合、圆角裁切等计算。
* **光栅化**: 计算结果写入到“渲染目标” Buffer 中。


* **提交**: 绘制完成后，`RenderSurface` 将渲染目标 Buffer 入队。`FramebufferSurface` 将其取出，作为特殊的 **ClientTarget** 图层提交给 HWC。

**阶段四：最终上屏 (Final Presentation)**

1. **汇聚**: 此时 HWC 拥有了构建完整画面所需的所有原料：
* 若干个独立的 App Buffer (Device Layers)。
* 一个包含所有 GPU 合成结果的 Buffer (ClientTarget)。


2. **上屏**: SF 调用 `HWC::presentDisplay()`。
3. **显示**: 硬件显示控制器从上述所有 Buffer 的物理内存地址中读取数据，按顺序叠加，输出到显示面板。
4. **同步**: HWC 返回 `PresentFence`。SF 根据 Fence 信号通知 App 释放旧 Buffer（`onFrameCommitted`），并准备下一帧。


**核心机制总结**

| 关注点 | 说明 |
| --- | --- |
| **数据本质** | 数据始终静止在共享内存（Shared Memory/DMA Buf）中。跨进程和跨模块传递的仅仅是**文件描述符 (fd/Handle)**。 |
| **GPU 角色** | GPU 仅作为“画师”。它把 App 的 Buffer 当作**颜料（纹理）**，把 FramebufferSurface 的 Buffer 当作**画布**。 |
| **HWC 角色** | HWC 是最终的“装裱师”。它负责将 GPU 画好的画布和那些可以独立展示的 App 图层拼装在一起。 |
| **性能关键** | 这里的核心优化在于**Zero-Copy**。除了 GPU 必须的读写外，CPU 绝不触碰像素数据。 |

此架构确保了 Android 图形系统在处理复杂 UI（如圆角、模糊）时能利用 GPU 的算力，而在处理视频、游戏等全屏应用时能利用 HWC 的高能效，实现性能与功耗的平衡。


## Scheduler

**Scheduler** 是 SurfaceFlinger 的核心组件，充当图形渲染系统的**“指挥家”**和**“节拍器”**。它的主要职责是管理系统的时间基准（Timing）和刷新率策略。

它负责解决两个核心问题：

1. **When to draw (时机)**：生成和分发 VSYNC 信号，驱动 App 渲染和 SF 合成。
2. **How fast to draw (频率)**：根据内容、交互和热状态，动态调整显示屏的刷新率（60Hz, 90Hz, 120Hz 等），以平衡流畅度与功耗。

### 核心架构图 (Architecture)

Scheduler 处于 HWC（硬件层）与 App/SF（逻辑层）的中间，负责协调上下游。

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



    IGraphicBufferProducer --o BufferQueue : "写入"
    BufferQueue o-- IGraphicBufferConsumer : "读取"
    

    FramebufferSurface <-- IGraphicBufferConsumer : "消费"
    
    class HWComposer {
        + setClientTarget()
    }
    FramebufferSurface ..> HWComposer : "提交"
### 核心机制详解

#### VSYNC 信号分发

Scheduler 并不直接把硬件 VSYNC 发送给所有人，而是通过 **`EventThread`** 进行解耦和分发。

* **硬件同步 (`resyncToHardwareVsync`)**: Scheduler 监听 HWC 的硬件 VSYNC，并利用内部模型计算出精确的“软件 VSYNC”时间点。这允许系统在必要时关闭硬件 VSYNC 以省电（由软件定时器模拟）。
* **双路分发**:
  * **`Cycle::Render` (App VSYNC)**: 发送给 App 的 `Choreographer`。包含一定的**相位偏移 (Phase Offset)**，让 App 在屏幕刷新之前的一段时间开始画图。
  * **`Cycle::LastComposite` (SF VSYNC)**: 发送给 SurfaceFlinger 主线程。通常晚于 App VSYNC，用于收集 App 画好的 Buffer 进行合成。



#### 智能刷新率决策 (Refresh Rate Selection)

Scheduler 维护了一套复杂的策略状态机，决定当前最佳的 Display Mode。

| 触发源 | 机制类 | 行为逻辑 |
| --- | --- | --- |
| **内容侦测** | `LayerHistory` | 记录每个 Layer 的提交时间戳，计算 FPS。<br>例如：检测到视频播放 (24/30fps)，可能调整屏幕为 60Hz 或 120Hz 以匹配倍数；检测到游戏 (High FPS)，推高刷新率。 |
| **用户交互** | `TouchTimer` | 当检测到触摸事件时，**强制 Boost** 到最高刷新率（如 120Hz），保证跟手性。触摸停止一段时间后回落。 |
| **屏幕空闲** | `IdleTimer` | 当屏幕一段时间没有 Layer 更新时，降低刷新率（如 60Hz 或更低）以省电。 |
| **系统限制** | `Thermal/Power` | 当系统过热或开启省电模式时，强制限制最高刷新率。 |

#### 多屏领跑机制 (Pacesetter)

在多屏设备中，为了防止不同刷新率的屏幕导致 VSYNC 混乱，Scheduler 引入了 **Pacesetter (领跑者)** 概念。

* **Pacesetter**: 选定一个主屏幕（通常是获焦的屏幕）。Scheduler 的主 VSYNC 节拍由该屏幕决定。
* **Followers**: 其他屏幕作为跟随者。它们的合成时机是根据 Pacesetter 的时间轴计算出来的偏移量。
* **代码体现**: `promotePacesetterDisplay`, `registerDisplayInternal`.

#### 驱动合成循环 (Frame Orchestration)

Scheduler 不仅负责发信号，还通过回调驱动每一帧的实际工作流程。

**核心函数**: `onFrameSignal(ICompositor& compositor, ...)`

```cpp
void Scheduler::onFrameSignal(...) {
    // 1. 准备阶段：计算预期时间
    beginFrameArgs = ...;
    
    // 2. 通知各 Display 的 Targeter 准备 (Layer 更新)
    pacesetter->targeterPtr->beginFrame(...);
    
    // 3. 提交事务 (Commit)
    // 处理 WindowManager 的事务，Layer 属性变化等
    compositor.commit(...);

    // 4. 执行合成 (Composite)
    // 通知 RenderEngine 进行绘图，或者通知 HWC 准备 Flip
    compositor.composite(...);
    
    // 5. 收尾
    targeter->endFrame(...);
}

```


### 关键类说明 (Glossary)

* **`Scheduler`**: 门面类，统筹全局。
* **`VsyncSchedule`**: 管理特定显示屏的 VSYNC 时间表和分发器 (`Dispatch`)。
* **`VsyncModulator`**: 动态调节 VSYNC 的相位偏移 (Phase Offsets)。例如在 App 频繁掉帧时，可能会调整偏移量给 App 更多的时间。
* **`LayerHistory`**: 历史记录器。它知道哪些 Layer 是“活跃”的，以及它们的平均帧率。
* **`EventThread`**: 一个独立的线程，通过 `BitTube` (Socket) 将 VSYNC 信号发送给跨进程的客户端 (App)。
* **`FrameTargeter`**: 负责计算每一帧的目标渲染时间点。


### 工作流时序 (Sequence Diagrams)

#### 5.1 触摸升频流程 (Touch Boost)

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

#### 帧率检测与切换 (Content Detection)

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

### 常见调试命令

在终端中可以使用 dumpsys 查看 Scheduler 的内部状态：

```bash
# 查看 SurfaceFlinger 完整信息 (包含 Scheduler)
adb shell dumpsys SurfaceFlinger

# 仅查看 Scheduler 部分 (依赖实现)
adb shell dumpsys SurfaceFlinger --section Scheduler

# 关键输出解读:
# Pacesetter Display: 当前领跑的屏幕 ID
# LayerHistory: 各个 Layer 的检测帧率
# VsyncSchedule: 当前 Vsync 的周期和偏移量

```

## HWComposer

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



### 架构解析

1. **HWComposer (顶层)**:
* 这是 SurfaceFlinger 进程中的单例（或主入口）。
* 它通过 `mDisplayData` 维护所有物理屏幕的状态。

2. **DisplayData & HWC2::Display**:
* `DisplayData` 是一个封装结构，持有一个 `HWC2::Display` 的指针。
* `HWC2::Display` 是一个抽象基类，定义了屏幕操作的标准接口。
* `HWC2::impl::Display` 是具体实现，它负责将屏幕操作转发给更底层的 `Composer`。


3. **Hwc2::AidlComposer (AIDL 实现层)**:
* 这是 Android 13/14 引入的基于 AIDL 的 Composer 实现（替代了旧的 HIDL）。
* 它持有一个 `AidlComposerClient`，通过 Binder 通信直接与硬件服务的 `IComposerClient` 对话。


4. **命令批处理 (Writer/Reader)**:
* 这是图中最关键的性能优化部分。
* **`ComposerClientWriter`**: SF 不会每做一个操作（比如设置 Layer 位置）就发一次 Binder 请求。相反，它把这些操作写入 `mCommands` 缓冲区（Command Buffer）。
* **`ComposerClientReader`**: 用于解析硬件返回的结果。
* 当调用 `executeCommands()` 或 `presentOrValidateDisplay()` 时，`AidlComposer` 会把 Writer 中积攒的一大包命令一次性发给硬件。




### AidlComposer 读写机制架构图

这张图重点展示了 `AidlComposer` 如何管理多显示器的 Writer 和 Reader，以及数据结构（Command vs Result）是如何在这些组件之间流转的。

**核心机制说明：**

1. **Buffered Writing (缓冲写入)**：`ComposerClientWriter` 不直接发 Binder 请求，而是将操作（如 `setLayerBuffer`）序列化为 AIDL 定义的结构体 (`DisplayCommand`, `LayerCommand`) 并缓存在内存 (`mCommands`) 中。
2. **Batch Execution (批量执行)**：`AidlComposer` 负责从 Writer 取出积攒的所有命令，通过 Binder 接口 `executeCommands` 一次性发送给HWC HAL。
3. **Result Parsing (结果解析)**：硬件服务返回 `CommandResultPayload` 列表。`AidlComposer` 将其交给 `ComposerClientReader` 进行解析，Reader 将原始数据分类存储到哈希表 (`mReturnData`) 中，供上层按需读取（如获取 Fence）。

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

---

### 图二：AidlComposer 命令执行时序图

这张图展示了从 `HWComposer` 调用 `setLayerBuffer` 设置图层属性，到最终调用 `execute` 提交命令并获取返回值的完整流程。

**流程关键点：**

* **Phase 1 (Buffering)**: 调用 `writer->setLayerBuffer` 仅仅是在内存中操作，非常快，无 IPC。
* **Phase 2 (Extraction)**: `takePendingCommands()` 将 Writer 中的命令所有权转移出来，清空 Writer。
* **Phase 3 (IPC)**: `mAidlComposerClient->executeCommands` 是真正的跨进程调用。
* **Phase 4 (Parsing)**: `reader->parse` 将扁平的返回列表转换为结构化数据。
* **Phase 5 (Retrieval)**: `AidlComposer` 从 Reader 中取出特定的结果（如 PresentFence）。

```mermaid
sequenceDiagram
    autonumber
    participant Caller as HWComposer
    participant Aidl as AidlComposer
    participant Writer as ComposerClientWriter
    participant Binder as IComposerClient (Binder)
    participant Reader as ComposerClientReader

    Note over Caller, Writer: 阶段 1: 命令积攒 (Buffering)<br/>此处不发生 IPC，仅内存操作

    %% 模拟积攒多个命令
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

    %% 阶段 2: 提交执行
    Note over Caller, Reader: 阶段 2: 批量提交与解析 (Execution & Parsing)

    Caller->>Aidl: execute(display) / presentDisplay
    activate Aidl
    
    %% 2.1 取出命令
    Aidl->>Writer: takePendingCommands()
    activate Writer
    Writer->>Writer: flushLayerCommand()
    Writer->>Writer: flushDisplayCommand()
    Writer-->>Aidl: vector<DisplayCommand> cmds
    deactivate Writer
    Note right of Writer: mCommands 被清空<br/>cmds 被移动到 AidlComposer

    %% 2.2 IPC 调用
    Aidl->>Binder: executeCommands(cmds)
    activate Binder
    Note right of Binder: 跨进程传输<br/>Hardware Composer 处理命令
    Binder-->>Aidl: vector<CommandResultPayload> results
    deactivate Binder

    %% 2.3 解析结果
    Aidl->>Reader: parse(results)
    activate Reader
    loop 遍历 results
        Reader->>Reader: 根据 Tag (Fence/Error/etc)<br/>分类存入 mReturnData
    end
    deactivate Reader

    %% 2.4 检查错误与获取结果
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
---

## 从 App 绘制到 RenderEngine 合成

### 核心误区：数据真的在“移动”吗？

很多刚接触 Android 图形系统的开发者容易产生一个误区：认为 App 画好一帧图后，系统通过 Binder 把这张巨大的图片（比如 4K 分辨率的位图）“拷贝”给了 SurfaceFlinger。

**这是完全错误的。** 如果每一帧都拷贝几 MB 的数据，手机发热和耗电将无法想象。

#### 物理本质：不动如山的共享内存

Android 图形流转的核心真相是：**数据不动，句柄（Handle）乱飞**。

请看下图，这是数据在物理内存和进程间的真实视图：

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

#### 流程解析

1. **App 生产**：App 请求一块 Buffer。系统在内核空间（或特定硬件内存区）分配一块**共享内存**（Shared Memory）。App 通过 OpenGL/Vulkan 将红色像素写入这块内存。
2. **句柄传递**：App 绘制完成后，并不把数据发给 SF，而是把这块内存的**文件描述符（fd）/句柄**通过 Binder 扔给 SurfaceFlinger。这就像银行保险柜，App 只是把**钥匙**给了 SF，钱（像素）还在保险柜里。
3. **SF 接收**：SurfaceFlinger 收到钥匙，在自己的进程空间里映射这块内存。
4. **SF 合成**：SurfaceFlinger 的绘图引擎（RenderEngine）读取这块内存，把它画到另一块**新的共享内存**（SF Output Memory）上。
5. **上屏**：最后，SF 把新内存的钥匙交给硬件控制器（HWC），屏幕亮起。

---

### 逻辑视图：RenderEngine 的合成魔法

对于熟悉 OpenGL ES 的说，SurfaceFlinger 的合成过程其实非常容易理解：**它就是一个标准的纹理绘制过程（Draw Call）。**

在 `RenderEngine` 的视角里，没有“图层（Layer）”的概念，只有 **纹理（Texture）** 和 **帧缓冲区（Framebuffer）**。

#### 术语对齐

| SurfaceFlinger 概念 | OpenGL ES 对应概念 | 说明 |
| --- | --- | --- |
| **Layer Buffer** | `GL_TEXTURE_2D` / `GL_TEXTURE_EXTERNAL_OES` | App 生产的画面，对于 SF 来说就是一张张贴图素材。 |
| **FramebufferSurface** | `GL_FRAMEBUFFER` (FBO) / Render Target | SF 的画板。GPU 最终把画好的像素写到这里。 |
| **drawLayers()** | `glDrawArrays()` / `glDrawElements()` | 执行 Shader 程序，把纹理画到 FBO 上。 |

#### 合成流水线图解

请看下图，这是 GPU 内部发生的事情：

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

#### 关键步骤详解

1. **绑定输入 (Bind Textures)**：
RenderEngine 拿到 Layer A, B, C 的 Buffer 句柄，调用 EGL API 将其绑定为 OpenGL 纹理。
> *注意：这里不需要 CPU 读取像素，GPU 直接通过 DMA 从共享内存中采样。*


2. **运行 Shader (The Math)**：
SF 并不只是简单的“叠加”。RenderEngine 会生成一个 Shader 程序，处理复杂的数学运算：
* **Alpha 混合**：根据 Layer 的透明度，计算 `SrcColor * Alpha + DstColor * (1 - Alpha)`。
* **几何变换**：如果 Layer 被缩放或旋转了，Vertex Shader 会修改坐标矩阵。
* **特效处理**：圆角（Rounded Corner）、背景模糊（Blur）、阴影（Shadow）本质上都是 Shader 里的数学计算。


3. **输出结果 (Render Target)**：
Fragment Shader 计算出的最终颜色值，被写入到 **FramebufferSurface** 提供的 Buffer 中。
* 这个 Buffer 本质上也是一块 GraphicBuffer（共享内存）。
* 它是 SurfaceFlinger 这一帧工作的**最终产物**。


### 总结

作为 OpenGL ES 的开发者，只需要记住这一句话：

> **SurfaceFlinger 的 GPU 合成（Client Composition），本质上就是把 App 生产的 GraphicBuffer 当作纹理（Texture），在一个巨大的 FBO 上画了一次 Quad（四边形），最终生成的 Texture 交给了屏幕控制器。**

* **数据**：从未离开过共享内存。
* **传递**：传的是文件句柄。
* **合成**：就是跑了一遍 Shader。


