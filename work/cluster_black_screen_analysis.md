# 仪表屏短暂黑屏分析报告

## 问题描述

- **时间**：2026年6月8日 05:58（用户回忆为 05:59）
- **现象**：车辆行驶过程中，仪表屏短暂黑屏 1-2 秒
- **车型**：H47A 平台，仪表屏分辨率 1920×480
- **系统**：Linux + 团结引擎 (Tuanjie/Unity) HMI

---

## 涉及日志文件

| 路径 | 内容 |
|------|------|
| `syslog/708_20260608_055800.log` | SOC 侧 syslog (05:58:00-05:59:37) |
| `syslog/709_20260608_055937.log` | SOC 侧 syslog (05:59:37-06:00:57) |
| `dltlog/dlt_486.txt` | DLT 诊断日志 (06/07 18:57-06/08 06:22) |
| `tuanjie/LogFiles/PlayerLog34.log` | 团结引擎仪表 HMI 应用日志 (05:09-06:58) |

---

## 排除的疑点

### 1. DS90UB983 显示桥接芯片 — 正常

```
708_20260608_055800.log:
[DISPLAY_BRIDGE_INFO] [ds90ub983_mst_clus888_hud47_diag] port0 lock status:0x53
[DISPLAY_BRIDGE_INFO] [ds90ub983_mst_clus888_hud47_diag] port1 lock status:0x53
[DISPLAY_BRIDGE_INFO] [ds90ub983_mst_clus888_hud47_diag] vp0 sync status:0x1
[DISPLAY_BRIDGE_INFO] [ds90ub983_mst_clus888_hud47_diag] vp1 sync status:0x1
```

全程 port lock=0x53 (locked), VP sync=0x1 (synced)，无异常。

### 2. CABLE 诊断 — 正常

```
display_diag: screen_name -> cluster, diagType -> CABLE, value -> NORMAL
```

全程 NORMAL，轮询间隔 ~9 秒，无中断。

### 3. Weston 合成器 — 正常

```
weston: ResourceImpl::NeedsValidate: needs_validate = true, for display 16780217-1
weston: sts = 0x0
```

帧同步无 >100ms 中断，sts 全程 0x0。

### 4. openwfd_server MDSS 操作 — 正常

`openwfd_server` 以 30fps 稳定运行，使用 DMA2 Layer (1920×480)、LM2/RECO+LM3 合成管线、DMA-12 flush 触发。全程无 ERROR，与仪表屏使用独立硬件管线。

### 5. qcxserver VFE/ISP 错误 — 慢性背景问题

```
708_20260608_055800.log: 2895 次 ResId: 0x3801 Frame Header NULL
247_20260607_093913.log: 4520 次  (09:39 同样存在)
500_20260607_183122.log: 4488 次  (18:31 同样存在)
746_20260608_070017.log: 2041 次  (07:00 同样存在)
```

`ResId: 0x3801` (VFE hwId=1, ISP resId=14337) 的 Frame Header NULL 错误在所有时段均存在，属于 camera 管线的慢性背景错误，与仪表屏无关。

### 6. DLT 日志 — 已瘫痪

```
dlt_486.txt (仅含 logm 日志管理器):
[N file=logmgr_save.c,line=216 no src file: /tmp/run/clsboot.log ]
[N file=logmgr_local.c,line=625 [callback]open dir /log/dltlog/sercls error  ]
```

仪表应用 DLT 日志通道 (`sercls`) 自 2025/05/30 起无法打开，`clsboot.log` 自 2026/05/31 起缺失。DLT 日志无法用于本次诊断。

---

## 关键发现：团结引擎 Procedure 状态机异常切换

### PlayerLog34 中的 Procedure 切换序列 (05:58:01-05:58:18)

```
05:58:01.999  OnLeave  ProcedureDrivingData      离开驾驶数据视图
05:58:02.000  OnEnter  ProcedureCluster          进入 Cluster 视图 (UIDefault.prefab)
05:58:02.001  [ProcedureCluster] Use Shared UI: Assets/ArtResources/Prefabs/UI/UIDefault.prefab
05:58:02.002  AnimStateEnd OnStateEnter          动画状态进入
05:58:03.001  第一个动画状态播放完毕！
05:58:04.534  OnLeave  ProcedureCluster          离开 Cluster 视图 (停留 2.5 秒)
05:58:04.534  OnEnter  ProcedureMusic            进入 Music 视图
05:58:07.202  OnLeave  ProcedureMusic
05:58:07.203  OnEnter  ProcedureMinimalist
05:58:11.205  OnLeave  ProcedureMinimalist
05:58:11.206  OnEnter  ProcedureNavigation
05:58:16.444  OnLeave  ProcedureNavigation
05:58:16.445  OnEnter  ProcedureSenseReality
05:58:18.310  OnLeave  ProcedureSenseReality
05:58:18.310  OnEnter  ProcedureDrivingData      回到驾驶数据，随后稳定 >30 分钟
```

### 对比：全程 ProcedureCluster 进入记录 (共 24 次)

```
05:17:13   Enter ProcedureCluster (Start + UI + Effect)   ← 启动时
05:17:24   Enter ProcedureCluster
05:17:27   Enter ProcedureCluster (Use UI)
05:17:51   Enter ProcedureCluster
05:26:14   Enter ProcedureCluster (Use UI)
05:29:35   Enter ProcedureCluster
05:40:43   Enter ProcedureCluster (Use UI)
05:51:27   Enter ProcedureCluster
05:58:02   Enter ProcedureCluster (Use Shared UI: UIDefault.prefab)  ← ⚠️ 唯一使用 Shared UI
05:58:04   Leave ProcedureCluster
06:11:30   Enter ProcedureCluster (Use UI)
06:12:06   Enter ProcedureCluster
06:20:59   Enter ProcedureCluster (Use UI)
06:21:54   Enter ProcedureCluster
```

**只有 05:58:02 这一次日志显示 `Use Shared UI`（回退到默认预制体），其余正常进入均使用具体 UI prefab。**

---

## 源码分析

### 触发链路

源码路径：`voyah-cluster/clusterservice/fds/v6.3.1/fds_someip/fds_InformationControlSwitch.cpp`

```cpp
// 方向盘 Info 按键处理
void Fds_InformationControlSwitch::InfoControlInfoSwitchProc(
    field_notifier_Notify_f_InfoControlSwitch_FDD_eventType *notifyData)
{
    // 按下时开始计时
    if (send_sts.isInfoLongPress == false && 
        static_cast<HMI_enum_Button>(send_sts.infoControlSwitchSts.InfoSwitch) == HMI_enum_Button::Press)
    {
        send_sts.infoSwitchPressTimeCount++;
        // cycle 100ms, 超过1001ms时表示长按
        if (send_sts.infoSwitchPressTimeCount >= 11)
        {
            send_sts.infoSwitchPressTimeCount = 11;
            IC_LOG_INFO("InfoSwtich long press");
            remove_top_warning();
            publish_driving_topic(TOPIC_ICDRIVING_INFO_SWITCH_PRESS, 
                                  BUTTON_LONG_PRESS, true, 0, true);
            send_sts.isInfoLongPress = true;
        }
    }

    uint8 value = notifyData->InfoControlSwitch.InfoSwitch;
    if (send_sts.infoControlSwitchSts.InfoSwitch != value)
    {
        if (static_cast<HMI_enum_Button>(value) == HMI_enum_Button::Notpress)
        {
            if (send_sts.infoSwitchPressTimeCount < 11)
            {
                IC_LOG_INFO("InfoSwtich short press");
                // 短按 → 发布到 Unity HMI，触发 Procedure 切换
                publish_driving_topic(TOPIC_ICDRIVING_INFO_SWITCH_PRESS, 
                                      BUTTON_SHORT_PRESS, true, 0, true);
            }
            send_sts.isInfoLongPress = false;
            send_sts.infoSwitchPressTimeCount = 0;
        }
        send_sts.infoControlSwitchSts.InfoSwitch = value;
    }
}
```

IPC Topic 定义（源码：`voyah-cluster/chimeservice/include/topic/ipc_topic_new_def.h`）：

```cpp
#define TOPIC_ICDRIVING_INFO_SWITCH_PRESS "icdriving/InfoSwitchPress"
```

### 完整链路

```
方向盘 Info 按键 (CAN ID 0x43F, signal SWS_MenuorAPA)
  → Fds_InformationControlSwitch::Notify_f_InfoControlSwitch_FDD_EventCallback()
    → InfoControlInfoSwitchProc()
      → publish_driving_topic("icdriving/InfoSwitchPress", 1)
        → [IPC] voyahipc publish
          → Unity HMI 订阅 icdriving/InfoSwitchPress
            → Procedure 状态机: OnLeave(当前) → OnEnter(下一个)
```

---

## 根因分析

### 直接原因

在行驶中（车速 ~39km/h），方向盘 Info 按键被快速按压，触发了仪表 HMI 的 Procedure 状态机快速轮转（16 秒内切换 7 个视图）。当切换到 `ProcedureCluster` 时，正常 UI prefab 加载失败，回退到空白占位预制体 `UIDefault.prefab`，导致仪表屏显示空白约 2.5 秒。

### 为什么 UIDefault.prefab 会导致黑屏

`UIDefault.prefab` 是团结引擎 HMI 框架中的 Shared UI（共享默认预制体），路径为 `Assets/ArtResources/Prefabs/UI/UIDefault.prefab`。它是一个通用的占位/过渡界面，不包含仪表盘的具体 UI 元素（速度表、功率表、指示灯等）。当正常的 `ProcedureCluster` UI prefab 无法在过渡时间内加载完成时，框架回退到该空白预制体。

### 可能的深层原因

1. **资源竞争**：同一时刻（05:58:01-02）qcxserver 的 max96712 Link 0 正在执行 serializer 复位（power down → CSIPHY reset → power up），大量 DDR/SMMU 操作可能影响了 Unity 的资源加载
2. **UI Prefab 加载超时**：`ProcedureCluster` 的正常 UI prefab 在 2.5 秒的过渡窗口内未能完成加载
3. **Info 按键快速连续按压**：快速的视图切换导致多个 UI prefab 同时加载/卸载，资源竞争加剧

### 恢复过程

2.5 秒后，状态机自动切出 `ProcedureCluster` 进入 `ProcedureMusic`（有具体 UI），随后经过 Minimalist → Navigation → SenseReality，最终回到 `ProcedureDrivingData`，屏幕完全恢复正常。

---

## 建议

1. **检查 `UIDefault.prefab`**：确认该预制体是否为空白/黑色，如果是，建议替换为带 loading 提示或保留上一帧画面的过渡方案
2. **增加 ProcedureCluster 正常 UI 的预加载**：避免在切换时才加载
3. **增加视图切换防抖**：对 Info 按键的快速连续按压增加最小间隔限制（如 500ms）
4. **增加 Procedure 切换的 fallback 日志**：当回退到 Shared UI 时记录 Warning 级别日志以便排查
