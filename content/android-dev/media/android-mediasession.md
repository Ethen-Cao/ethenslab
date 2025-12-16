+++
date = '2025-08-08T11:36:11+08:00'
draft = false
title = 'Android DRM 框架'
+++

```plantuml
@startuml
title Android MediaSession 管理与交互架构图 (优化版)
top to bottom direction

' --- 样式定义 ---
!define C4_COLOR(color) #color
!define C4_BG_COLOR(color) C4_COLOR(color)
!define C4_BORDER_COLOR(color) #Black

skinparam component {
    ArrowColor #666666
    BorderColor #444444
    BackgroundColor<<System>> C4_BG_COLOR(D4E157)
    BackgroundColor<<Service>> C4_BG_COLOR(2B4353)
    BackgroundColor<<Helper>> C4_BG_COLOR(7E57C2)
    BackgroundColor<<Data>> C4_BG_COLOR(FFC107)
    FontColor #0b0b0bff
}

skinparam rectangle {
    StereotypeFontColor #FFFFFF
    BackgroundColor<<App>> C4_BG_COLOR(4385F4)
    BorderColor C4_BORDER_COLOR(4385F4)
}

' --- 组件定义 ---

rectangle "应用程序 (Client Process)" <<App>> {
    component "MediaSession" as AppSession
    component "AudioTrack / MediaPlayer" as AppPlayer
    component "AudioManager" as AM_Client
}

package "System Server Process" {
    
    component "AudioService" as AudioService <<System>> {
        note bottom
            管理音频焦点
            和物理播放状态
        end note
    }

    rectangle "MediaSessionService (MSS)" as MSS_Rect <<Service>> {
        component "ISessionManager (Binder)" as BinderInterface
        component "MediaSessionService" as MSS_Core
        
        rectangle "组件协作区" #EEEEEE {
            component "AudioPlayerStateMonitor" as Monitor <<Helper>> {
                component "mSortedAudioPlaybackClientUids\n(List<Integer>)" as HistoryQueue <<Data>>
            }
            
            component "MediaSessionStack" as Stack <<Data>> {
                component "mMediaButtonSession\n(Reference)" as MBS <<Data>>
                component "mSessions\n(List<Record>)" as SessionList <<Data>>
            }
        }
    }
}

' --- 关系与交互流程 ---

' 1. App 初始化
AppSession -down-> BinderInterface : 1. createSession() / setActive()
AppSession .right.> AppPlayer : 控制逻辑

' 2. App 播放音频
AppPlayer -down-> AM_Client : 播放请求
AM_Client -down-> AudioService : 2. start/pause/stop (Binder)

' 3. AudioService 通知 Monitor
AudioService -right-> Monitor : 3. onPlaybackConfigChanged()\n(Via AudioManager Callback)

' 4. Monitor 更新历史队列并通知 MSS
Monitor -> HistoryQueue : 更新 [uid_B, uid_A...]
Monitor -down-> MSS_Core : 4. onAudioPlayerActiveStateChanged()

' 5. MSS 触发 Stack 更新
MSS_Core -right-> Stack : 5. updateMediaButtonSessionIfNeeded()

' 6. Stack 核心决策循环
Stack .up.> HistoryQueue : 6. getSortedAudioPlaybackClientUids()\n(获取音频历史)
Stack -left-> Stack : 7. findMediaButtonSession(uid)\n(匹配 Session)

' 8. 清理与确立
Stack .up.> Monitor : 8. cleanUpAudioPlaybackUids(uid)\n(清理旧的不活跃 UID)
Stack -down-> MBS : 9. updateMediaButtonSession()\n(更新 mMediaButtonSession)

' 9. 最终事件分发
User -right-> MSS_Core : 媒体按键 (Media Key)
MSS_Core -down-> MBS : 查找目标
MBS .up.> AppSession : 10. dispatchMediaKeyEvent()

' --- 注释 ---

note right of HistoryQueue
  **关键数据结构**
  维护"最后播放"的 UID 列表。
  即使 App 暂停，UID 也会保留在首位
  直到被 cleanUp。
end note

note right of Stack
  **决策大脑**
  双轨制策略：
  1. 优先查 Monitor 历史队列 (Audio Driven)
  2. 队列为空查 Stack 活跃记录 (Priority Driven)
end note

note left of BinderInterface
  SystemApi 入口
end note

@enduml
```

### 优化的主要改动解释：

1.  **AudioService 的加入**：

      * **原图**：App 直接调 `AudioManager`，然后直接连到 Monitor，掩盖了跨进程通信细节。
      * **新图**：App -\> `AudioManager` (Client) -\> `AudioService` (System)。`AudioService` 才是所有音频状态的源头，它通过回调通知 `Monitor`。

2.  **Monitor 内部的 `HistoryQueue`**：

      * 代码中 `mSortedAudioPlaybackClientUids` 是核心。我在图中将其显式画出。这解释了为什么 App B 暂停后，Stack 依然能从 Monitor 拿到 `[uid_B]` 而不是空列表。

3.  **Step 8: `cleanUpAudioPlaybackUids`**：

      * 这是一个非常关键的**回环调用**。Stack 决定了谁是 MediaButtonSession 后，反过来命令 Monitor 清理掉排在这个 Session 之后的“垃圾”UID。这在原图中是缺失的。

4.  **组件归属调整**：

      * 将 `AudioPlayerStateMonitor` 和 `MediaSessionStack` 放入 `MediaSessionService` 的矩形框内，并用“组件协作区”包裹，强调它们是在同一服务内部紧密协作的对象。

这个新图更准确地反映了代码逻辑：**AudioService 驱动状态变化 -\> Monitor 记录历史 -\> Stack 基于历史做决策 -\> Stack 反向清理 Monitor 历史 -\> 确立 MediaButtonSession。**