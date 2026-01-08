+++
date = '2025-09-29T10:22:54+08:00'
draft = false
title = ' Android 窗口焦点抢占与输入法连接断开技术时序分析'
+++

### 1. 概述

```plantuml
@startuml
!theme plain
autonumber

skinparam backgroundColor white
skinparam participantBackgroundColor white
skinparam boxPadding 10
skinparam noteBackgroundColor #FFFFA0
skinparam noteBorderColor #808080

actor "User" as User

box "应用进程 A (Overlay - 当前焦点持有者)" #MistyRose
    participant "ViewRootImpl" as Overlay_VRI
    participant "ImeFocusController" as Overlay_Ctrl
    participant "InputMethodManager\n(IMM)" as Overlay_IMM
end box

box "系统服务 (System Server)" #LightBlue
    participant "InputDispatcher" as InputDispatcher
    participant "WindowManagerService\n(WMS)" as WMS
    participant "DisplayContent\n(DC)" as DC
    participant "InputMethodManagerService\n(IMMS)" as IMMS
end box

box "应用进程 B (Browser - 触摸事件接收者)" #Honeydew
    participant "ViewRootImpl" as Browser_VRI
    participant "Browser\nActivity" as Browser
    participant "InputMethodManager\n(IMM)" as Browser_IMM
end box

== 第一阶段：Overlay 窗口添加与焦点计算 ==

Overlay_VRI -> WMS: <color:red>**addWindow**(TYPE_APPLICATION_OVERLAY)Flags 中**未包含** FLAG_NOT_FOCUSABLE
activate WMS

    WMS -> WMS: **addWindowInner**() -> **updateFocusedWindowLocked**()

    group WMS 焦点更新逻辑
        WMS -> DC: **findFocusedWindowIfNeeded**()
        activate DC
            DC -> DC: 遍历窗口列表 (Z-Order Top-Down)
            DC -> DC: 检查 Overlay WindowState
            DC -> DC: **mayUseInputMethod**(flags)
            note right of DC
                **判定逻辑：**
                return (flags & FLAG_NOT_FOCUSABLE) == 0;
                **结果：TRUE**
                (系统判定该窗口具备处理 IME 输入的能力)
            end note
        DC --> WMS: 返回 **newFocus = Overlay**
        deactivate DC
    end

    WMS -> WMS: **mCurrentFocus = Overlay**
    
    par 并发通知焦点变更
        WMS -> Overlay_VRI: **windowFocusChanged**(hasWindowFocus=true)
        WMS -> Browser_VRI: **windowFocusChanged**(hasWindowFocus=false)
    end
    
deactivate WMS

== 第二阶段：Overlay 建立输入法连接 ==

activate Overlay_VRI
    note right of Overlay_VRI
        触发条件：
        1. 收到 windowFocusChanged 回调
        2. 或执行 performTraversals 布局遍历
    end note

    Overlay_VRI -> Overlay_Ctrl: **onPostWindowFocus**() / **onTraversal**()
    activate Overlay_Ctrl
    
        Overlay_Ctrl -> Overlay_Ctrl: check **mayUseInputMethod**() == true
        
        Overlay_Ctrl -> Overlay_IMM: **onPostWindowGainedFocus**()
        activate Overlay_IMM
            
            note right of Overlay_IMM
                **IPC 请求：**
                请求建立输入连接
            end note
            
            Overlay_IMM -> IMMS: **startInputOrWindowGainedFocus**(\n  reason=WINDOW_FOCUS_GAIN,\n  client=Overlay,\n  windowToken=OverlayToken)
            activate IMMS

== 第三阶段：IMMS 执行客户端切换与解绑 ==

                group IMMS 服务端处理
                    IMMS -> IMMS: **startInputOrWindowGainedFocusInternalLocked**()
                    
                    IMMS -> IMMS: check **mCurClient (Browser) != newClient (Overlay)**
                    
                    IMMS -> IMMS: **prepareClientSwitchLocked**()
                    IMMS -> IMMS: **unbindCurrentClientLocked**(SWITCH_CLIENT)
                    
                    activate IMMS #FFBBBB
                        note right of IMMS
                            **状态清理：**
                            1. userData.mCurClient.mClient.setActive(false)
                               -> 通知 Browser 停止输入活动
                            2. finishSessionLocked(session)
                               -> 销毁 Browser 的 InputChannel
                            3. **mCurClient = null**
                        end note
                    deactivate IMMS
                    
                    IMMS -> IMMS: **mCurClient = Overlay**
                    note right of IMMS
                        **当前状态：**
                        IMMS 服务端记录的 Client 已变更为 Overlay
                    end note
                end
                
            IMMS --> Overlay_IMM: return InputBindResult (SUCCESS)
            deactivate IMMS
            
        deactivate Overlay_IMM
    deactivate Overlay_Ctrl
deactivate Overlay_VRI

== 第四阶段：触摸事件派发 (Touch Dispatch) ==

User -> InputDispatcher: 点击屏幕 (Touch Down)
activate InputDispatcher

    note right of InputDispatcher
        **事件派发逻辑：**
        虽然 Overlay Z-Order 最高，但设置了 
        FLAG_NOT_TOUCH_MODAL (或点击区域在 Overlay 范围外)
        事件向下穿透
    end note

    InputDispatcher -> Browser_VRI: **InputEvent (ACTION_DOWN)**
deactivate InputDispatcher

activate Browser_VRI
    Browser_VRI -> Browser: **dispatchTouchEvent**()
    Browser -> Browser: View.onTouchEvent() -> performClick()
    
    note right of Browser
        Browser 能够接收点击事件
        但此时 Window 焦点已丢失 (HasFocus=false)
    end note

== 第五阶段：请求输入法失败 ==

    Browser -> Browser_IMM: **showSoftInput**(view)
    activate Browser_IMM
    
        group IMM 客户端自检
            Browser_IMM -> Browser_IMM: **checkFocus**()
            Browser_IMM -> Browser_IMM: **hasServedByInputMethodLocked**()
            note left
                **失败点 A (客户端拦截)：**
                由于之前收到 windowFocusChanged(false)
                ViewRootImpl 判定当前窗口无焦点
                mServedView 可能为 null 或不匹配
                **Result: return false** (Log: "Ignoring... is not served")
            end note
        end

        alt 假设绕过客户端检查 (强制请求服务端)
            Browser_IMM -> IMMS: **showSoftInput**(client=Browser)
            activate IMMS
            
            IMMS -> IMMS: check **mCurClient (Overlay) == client (Browser)**
            
            note left of IMMS #FFAAAA
                **失败点 B (服务端拒绝)：**
                Validation Failed.
                请求者 Browser 与当前记录的 mCurClient (Overlay) 不一致。
            end note
            
            IMMS -->> Browser_IMM: return false
            deactivate IMMS
        end

    Browser_IMM -->> Browser: return false
    deactivate Browser_IMM

deactivate Browser_VRI

@enduml
```

本时序图展示了一个配置为 `TYPE_APPLICATION_OVERLAY` 但缺失 `FLAG_NOT_FOCUSABLE` 属性的悬浮窗口（Overlay），如何在系统层（WMS）和输入法服务层（IMMS）通过标准生命周期回调，强制剥夺底层应用（Browser）的输入法连接权（Input Connection），导致底层应用虽然能响应点击但无法弹出软键盘的异常流程。

### 2. 详细流程阶段解析

#### 第一阶段：WMS 焦点仲裁（Focus Arbitration）

此阶段发生在 Overlay 窗口被添加到系统窗口管理器（WMS）的时刻。

* **触发动作**：Overlay 应用调用 `WindowManager.addView`，参数中未包含 `FLAG_NOT_FOCUSABLE`。
* **WMS 内部逻辑**：
  * `addWindowInner` 触发层级更新，Overlay 被置于 Z-Order 顶层。
  * 随后调用 `updateFocusedWindowLocked` -> `findFocusedWindowIfNeeded` 重新计算全局焦点。
  * **关键判定**：`DisplayContent` 从顶层向下遍历窗口。对于 Overlay 窗口，系统调用 `mayUseInputMethod(flags)` 进行判定。由于 **Missing Flag**，该方法返回 `true`。
* **结果**：WMS 将全局焦点变量 `mCurrentFocus` 锁定为 Overlay，并向各应用进程分发 `windowFocusChanged` 回调（Overlay 为 true，Browser 为 false）。

#### 第二阶段：Overlay 建立连接（Active Connection Establishment）

此阶段发生在 Overlay 应用的主线程（UI Thread）中。

* **触发动作**：Overlay 的 `ViewRootImpl` 收到获焦通知或执行布局遍历（`performTraversals`）。
* **客户端自检**：
  * `ImeFocusController` 执行 `onTraversal` 或 `onPostWindowFocus`。
  * 再次执行本地检查 `WindowManager.LayoutParams.mayUseInputMethod`，结果为 `true`。

* **发起请求**：Overlay 进程通过 `InputMethodManager` 向系统服务发起 IPC 调用 `startInputOrWindowGainedFocus`，理由为 `WINDOW_FOCUS_GAIN`。**这标志着 Overlay 主动向系统宣誓了输入法的主权。**

#### 第三阶段：IMMS 服务端会话切换（Session Switch）

此阶段发生在系统服务进程（System_Server）的 `InputMethodManagerService` 中。

* **状态校验**：IMMS 接收到 Overlay 的请求，对比当前绑定的客户端 `mCurClient`（此时仍指向 Browser）与请求者（Overlay）。
* **强制解绑（Critical Step）**：
  * 发现客户端不一致，IMMS 调用 `prepareClientSwitchLocked`。
  * 执行 `unbindCurrentClientLocked(SWITCH_CLIENT)`。
* **后果**：系统销毁了 Browser 的 `InputMethodSession`，并将 Browser 对应的 `ClientState` 标记为非激活。
* **新绑定**：`mCurClient` 更新为 Overlay。至此，输入法的数据通道已物理切换至 Overlay，Browser 与输入法的连接被彻底切断。

#### 第四阶段：触摸事件与输入焦点的逻辑分离（Touch vs Focus Discrepancy）

此阶段揭示了问题的隐蔽性：用户感知与系统状态的割裂。

* **触摸派发（Touch Dispatch）**：用户点击屏幕。`InputDispatcher` 进行命中测试。由于 Overlay 设置了 `FLAG_NOT_TOUCH_MODAL`（或点击区域位于 Overlay 之外），点击事件（ACTION_DOWN/UP）穿透 Overlay，正常派发给了底层的 Browser。
* **逻辑冲突**：Browser 能够响应 `onClick`，产生一种“我还在前台”的错觉。但根据 WMS 的状态（第一阶段），它实际上处于“可见但无焦点”的状态。

#### 第五阶段：请求被拒（Request Rejection）

此阶段是用户看到的最终故障现象。

* **Browser 发起请求**：Browser 的 EditText 响应点击，调用 `showSoftInput`。
* **拦截点 A（客户端本地拦截）**：`InputMethodManager` 检查本地状态 `checkFocus()`。由于之前收到了 `windowFocusChanged(false)`，`hasServedByInputMethodLocked()` 返回 `false`，请求可能直接在应用进程内被丢弃。
* **拦截点 B（服务端拦截）**：即使请求通过某种方式发出，到达 IMMS 后，服务端的鉴权逻辑会发现 `mCurClient` (Overlay) 与请求者 (Browser) 不匹配，直接返回 `false`。

### 3. 根本原因总结

问题的根源在于 Android 窗口系统中 **Z-Order（显示层级）** 与 **Input Focus（输入焦点）** 的默认关联机制。

* **机制**：默认情况下，可获焦（Focusable）的最高层级窗口自动获得输入焦点。
* **缺陷**：Overlay 窗口作为高层级窗口，若不显式声明放弃焦点（`FLAG_NOT_FOCUSABLE`），系统会依据标准流程将其认定为输入法目标，从而切断其他应用的输入连接。

### 4. 解决方案技术原理

在 Overlay 窗口的 LayoutParams 中添加 `FLAG_NOT_FOCUSABLE`：

1. **阻断第一阶段**：WMS 的 `mayUseInputMethod` 返回 `false`，焦点计算跳过 Overlay，保留在 Browser。
2. **阻断第二阶段**：Overlay 应用内的 `ImeFocusController` 判定不需要输入法，不再发送 `startInputOrWindowGainedFocus` IPC 请求。
3. **保护第三阶段**：IMMS 不会收到切换请求，Browser 的 Session 保持活跃。

