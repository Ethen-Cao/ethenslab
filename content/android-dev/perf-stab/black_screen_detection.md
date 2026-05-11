+++
date = '2026-05-11T10:00:00+08:00'
draft = false
title = '智能座舱黑屏检测：PVM 后端链路 + GVM 图形栈综合探测'
+++

智能座舱（以 Qualcomm SA8397 为例）的显示链路跨两个虚拟机：

- **PVM（Linux Host）**：持有真实 DPU / DSI / 背光控制器、跑 DRM/KMS、负责最终把帧打到面板。`adb shell` 进入后是一台标准 aarch64 Linux（`uname -r` → `6.6.110-rt61-debug`）。
- **GVM（Android Guest）**：跑 SurfaceFlinger / HWC / WMS / 应用，把合成结果通过 vendor 私有的跨 VM 显示通道（virtio-gpu / Qualcomm 私有 IPC）交给 PVM。

"黑屏"并不发生在一个点。它可以发生在 Android 应用层、SurfaceFlinger 合成层、HWC HAL、跨 VM 通道、PVM 内核 DRM、DPU、DSI 链路、面板电源、背光任意一段。**任何只看一侧的方案都有结构性盲区**。本文给一套双侧、可执行、字段级的检测方案：PVM 侧测后端硬链路是否在出帧，GVM 侧用 Display / SurfaceFlinger / WMS / Choreographer 公开接口做综合判定，再交叉定位。

---

## 1. 显示链路解剖与黑屏可能位置

```
[GVM Android]                                      [PVM Linux]                       [Hardware]
 App → View tree                                                                       
 ↓ (RenderThread, GPU)                                                                 
 SurfaceFlinger ── HWC HAL ── vendor display IPC ──► DRM atomic commit ── DPU ── DSI ──► Panel
                                                       │                       │           │
                                                       └ vblank IRQ ◄──────────┘           └ Backlight PWM
```

可能黑屏的环节（从上到下）：

| # | 环节 | 表现 | 主测点 |
|---|---|---|---|
| ① | App 层主动绘黑 / 全屏黑 Window | 像素全黑、帧率正常 | WMS focus + gfxinfo |
| ② | UI 线程卡死 | 帧节拍停 | Choreographer |
| ③ | SurfaceFlinger commit 停 | present fence 不推进 | dumpsys SurfaceFlinger |
| ④ | HWC HAL 异常 | composition strategy 异常、commit timeout | SurfaceFlinger + dmesg |
| ⑤ | 跨 VM 显示通道阻塞 | GVM 出帧但 PVM 收不到 buffer | PVM virtio-gpu / vendor 节点 |
| ⑥ | PVM DRM atomic commit 失败 | drm_atomic error、CRTC 不 active | `/sys/kernel/debug/dri/0/state` |
| ⑦ | DPU underrun / timeout | sde_evtlog 报错 | sde_evtlog |
| ⑧ | DSI 链路 LP/HS 异常 | DSI error IRQ、PHY reset | dmesg + msm_dsi |
| ⑨ | 背光关 / 面板电源关 | DRM 在出帧但屏不亮 | `bl_power`、panel reset GPIO |
| ⑩ | 物理面板坏 | 同上但 panel-side 报错 | 面板自检 / EDID |

PVM 测点覆盖 ⑤–⑩，GVM 测点覆盖 ①–④。两侧交叉才能定位。

---

## 2. PVM 侧后端链路监测

### 2.1 DRM 卡 / Connector / CRTC 静态状态

进入 PVM：

```bash
adb -s e66b06ea shell
```

```bash
# 列出 DRM 资源
ls /sys/class/drm/
# 期望看到: card0 card0-DSI-1 card0-DSI-2 card0-Writeback-1 ...

# Connector 是否连接、是否启用
for c in /sys/class/drm/card0-*; do
  printf '%-40s status=%s enabled=%s\n' \
    "$(basename "$c")" \
    "$(cat "$c/status" 2>/dev/null)" \
    "$(cat "$c/enabled" 2>/dev/null)"
done
```

**判定**：

- 主屏对应的 connector（一般是 `card0-DSI-1` 或 `card0-LVDS-1`）必须 `status=connected` **且** `enabled=enabled`。
- 任何一项变成 `disconnected` / `disabled` 即说明显示控制器层面已断链。

### 2.2 Atomic state 完整快照（最有信息量的单个节点）

```bash
cat /sys/kernel/debug/dri/0/state
```

关注字段：

```
crtc[36]: crtc-0
        enable=1          # CRTC 启用
        active=1          # CRTC 通电运行
        mode_changed=0    # 没在切换模式
        active_changed=0
        connectors_changed=0
        mode: "1920x720": ... 60 1920 ... vrefresh 60 ...
connector[80]: DSI-1
        crtc=crtc-0
        self_refresh_aware=0
plane[31]: plane-0
        crtc=crtc-0
        fb=148
        crtc-pos=1920x720+0+0
        src-pos=1920.000000x720.000000+0.000000+0.000000
```

**判定**：

- `active=0` 或 `enable=0`：CRTC 已被关。Android 侧多半看到 `Display.STATE_OFF`，但 DPU 实际未在出帧。
- `fb=0` / 无 plane 绑定：合成层没向 DRM 提交 framebuffer。
- `mode_changed=1` 持续：在反复重协商模式（常见于 EDID 异常 / 跨 VM 通道抖动）。

### 2.3 vblank 计数 —— 是否真的在出帧

```bash
# 间隔 1 秒读两次
c1=$(cat /sys/kernel/debug/dri/0/crtc-0/vblank_count)
sleep 1
c2=$(cat /sys/kernel/debug/dri/0/crtc-0/vblank_count)
echo "delta=$((c2-c1))"
```

**判定**：

- `delta ≈ refresh_rate`（60Hz 屏应当 ≈ 60）—— 硬件 vblank 正常。
- `delta == 0` —— **DPU 已经停止出帧**，最强的"PVM 侧硬黑屏"信号。
- `delta` 远低于 refresh rate —— underrun，可在 `sde_evtlog` 看到对应记录。

### 2.4 SDE / DPU vendor 事件日志（Qualcomm 专用）

```bash
# 高通 Snapdragon Display Engine 事件环
cat /sys/kernel/debug/dri/0/debug/dump/evtlog/sde_evtlog

# 寄存器 / 中断 dump
cat /sys/kernel/debug/dri/0/debug/dump/INTR_STATUS
cat /sys/kernel/debug/dri/0/debug/dump/regs/DPU_INTR

# DSI controller 状态
cat /sys/kernel/debug/dri/0/debug/dump/dsi_ctrl_0
```

**重点关键字**：

- `commit_done timeout` —— DPU commit 超时（强异常）
- `underrun` —— 数据通路供帧不及，常伴 DSI underrun IRQ
- `panel_dead` / `esd_check fail` —— ESD 自检失败，面板未响应
- `dsi_err_intr` —— DSI link error，PHY/CK 链路异常

### 2.5 背光与面板电源

```bash
ls /sys/class/backlight/
# 一般有 panel0-backlight 之类

bl=/sys/class/backlight/panel0-backlight
cat $bl/bl_power     # 0 = FB_BLANK_UNBLANK 亮屏，4 = FB_BLANK_POWERDOWN 关
cat $bl/brightness
cat $bl/max_brightness

# 面板 reset / power GPIO（路径需按 dts 配置查找）
cat /sys/kernel/debug/gpio | grep -iE "panel|disp|lcd|bl_en"
```

**判定**：

- `bl_power=4` 或 `brightness=0`：DRM 在出帧但屏暗——典型"软件正常 / 用户感知黑屏"。
- panel reset GPIO 为低且 `enable` 设置错误：面板未上电。

### 2.6 跨 VM 显示共享通道

Qualcomm 多 VM 平台上 GVM 与 PVM 之间的 buffer 共享路径在 vendor 私有节点。常见可观测点：

```bash
# Gunyah / qcrosvm 相关
ls /sys/devices/virtual/misc/ | grep -iE "gunyah|gh_"
ls /sys/kernel/debug/gunyah/ 2>/dev/null

# dma-heap 暴露的 inter-VM 显示堆
ls /dev/dma_heap/ | grep -iE "qcom|system-uncached|display"

# vendor 通道统计（路径与具体 BSP 相关，需结合 dts/lk2nd 文档）
find /sys/kernel/debug -name "*display*" 2>/dev/null
find /sys/kernel/debug -name "*virtio*gpu*" 2>/dev/null
```

**判定**：

- buffer queue 深度长期撑满 / fence 长期 unsignaled —— 跨 VM 显示通道堵塞。
- GVM 侧 SurfaceFlinger 报 `present fence timeout` 同时 PVM vblank 仍递增 —— 通道断开。

### 2.7 dmesg 错误模式

```bash
dmesg -T | grep -iE "drm|sde|msm_drm|dsi|dpu|panel|backlight" | tail -100
```

关注：

- `drm_atomic: ... failed -EBUSY`
- `sde_crtc_atomic_check: ... failed`
- `msm_dsi_host: cmd dma tx err`
- `panel_reset: reset failed`
- `Display Lockup`、`gpu hang`

### 2.8 PVM 侧"硬链路是否健康"判定脚本

```bash
#!/bin/sh
# pvm_display_check.sh —— 在 PVM 上跑
CRTC=/sys/kernel/debug/dri/0/crtc-0
CONN=/sys/class/drm/card0-DSI-1
BL=/sys/class/backlight/panel0-backlight

v1=$(cat $CRTC/vblank_count); sleep 1; v2=$(cat $CRTC/vblank_count)
delta=$((v2 - v1))

st=$(cat $CONN/status)
en=$(cat $CONN/enabled)
bl=$(cat $BL/bl_power 2>/dev/null || echo NA)
br=$(cat $BL/brightness 2>/dev/null || echo NA)

active=$(grep -A1 '^crtc' /sys/kernel/debug/dri/0/state | head -2 | tail -1 \
         | tr -d '\t ' | sed -n 's/.*active=\([01]\).*/\1/p')

echo "connector=$st/$en active=$active vblank/s=$delta bl_power=$bl brightness=$br"

# 判定
if [ "$st" != "connected" ] || [ "$en" != "enabled" ]; then echo "FAIL: connector lost"; fi
if [ "$active" != "1" ]; then echo "FAIL: crtc inactive"; fi
if [ "$delta" -lt 30 ]; then echo "FAIL: vblank stalled ($delta/s)"; fi
if [ "$bl" = "4" ] || [ "$br" = "0" ]; then echo "FAIL: backlight off"; fi
```

PVM 侧只要这四个条件齐绿，**就可以断言"屏在出帧、面板有光"**。其余黑屏必然在 GVM 软件栈。

---

## 3. GVM 侧 Android 综合探测

下面命令在 GVM 上执行（`adb -s d7df5883 shell` 或 PVM 上 `ssh android`）。所有信号都来自 Android 公开 / 半公开接口，**不依赖 SurfaceControl 反射截屏**。

### 3.1 DisplayManager —— 系统是否认为"屏开着"

shell 侧：

```bash
dumpsys display | sed -n '/^Display Manager State/,/^$/p'
```

关键字段：

```
Display Manager State:
  mGlobalDisplayState=ON                # 全局电源状态
  mPendingTraversal=false
  Display Device: ...
    mState=ON                           # 设备状态
    mDisplayId=0
    DisplayDeviceInfo{ ...
      state ON,                         # 与上面一致才对
      committedState ON,
      FLAG_DEFAULT_DISPLAY|FLAG_ROTATES_WITH_CONTENT ...}
    mActiveModeId=1
    mDefaultModeId=1
    DisplayModeRecord{mMode={... 1920x720@60.000000 ...}}
```

应用侧 API：

```java
DisplayManager dm = ctx.getSystemService(DisplayManager.class);
Display d = dm.getDisplay(Display.DEFAULT_DISPLAY);
int state = d.getState();              // STATE_ON / STATE_OFF / STATE_DOZE / STATE_UNKNOWN
float fps = d.getRefreshRate();        // 0 → 链路异常
boolean valid = d.isValid();
```

**判定**：

- `mGlobalDisplayState != ON`：系统层面已认为屏是关的（息屏/DOZE/被电源管理切走）—— 不作为黑屏异常。
- `mState != mCommittedState`：状态切换中，给容忍窗口（500ms）。
- `getRefreshRate() == 0` 或 `isValid() == false`：Display 设备已不可用——这是异常。

### 3.2 SurfaceFlinger —— 合成器是否在出帧

```bash
# 显示设备信息
dumpsys SurfaceFlinger --display-id
dumpsys SurfaceFlinger | sed -n '/^Display \[0\]/,/^$/p'
```

关键字段：

```
Display [0] : ...
  Display p0=0,0 1920x720 ... refresh=60.000004fps
  Display State:
    isVirtual=false
    isSecure=true
    layerStack=0
    transform=ROT_0
    powerMode=2                 # 2=ON 0=OFF 1=DOZE
    isEnabled=true
  VSYNC period 16666666
  HWC layers:
    Layer "com.voyah.cockpit.launcher/...#0"  composition=DEVICE
    Layer "StatusBar#0"                       composition=DEVICE
```

**最有判定力的两个查询**：

```bash
# (a) 全局/单 layer 延迟流水（frameNumber 序列）
dumpsys SurfaceFlinger --latency
# 输出三列时间戳: appDrawn / vsyncCompose / presentFence
# 间隔 1s 取两次，最后一行 frameNumber 应当增长

# (b) 帧事件历史
dumpsys SurfaceFlinger --frame-events | tail -30
```

**判定**：

- `powerMode != 2`：SurfaceFlinger 已收到关屏指令——配合 §3.1 判断。
- `--latency` 输出的 presentFence 时间戳 1 秒内不前进：**合成停摆**（覆盖环节 ③④）。
- HWC layers 列表为空 / 没有可见 layer 覆盖整屏：合成结果就是黑——是 ① / ② 的可能体现。

### 3.3 WindowManager —— 是否有焦点窗口且可见

```bash
dumpsys window | grep -E 'mFocusedWindow|mTopFullOpaqueWindow|mInputMethodTarget|mCurrentFocus'
dumpsys window displays | sed -n '/Display: mDisplayId=0/,/^$/p'
```

关键字段：

```
mCurrentFocus=Window{... u0 com.voyah.cockpit.launcher/.MainActivity}
mFocusedApp=AppWindowToken{... token=Token{... ActivityRecord{...MainActivity}}}
mTopFullOpaqueWindow=Window{... com.voyah.cockpit.launcher/.MainActivity}
```

**判定**：

- `mCurrentFocus=null` 或 `mFocusedApp=null`：焦点丢失——典型 B 类异常（WMS 死锁、栈错乱）。
- `mTopFullOpaqueWindow=null`：没有任何 fullopaque window 覆盖屏幕——一定看到底层（壁纸或黑）。
- focused window 的 frame 不覆盖整屏：露出底色。

### 3.4 ActivityManager —— 顶层 Activity 状态

```bash
dumpsys activity activities | grep -E 'mResumedActivity|topActivity'
dumpsys activity top | head -40
```

**判定**：

- `mResumedActivity=null`：当前没有 RESUMED 的 Activity——异常。
- top Activity 的 process 在 `cached` 或 `not running`：进程被回收后未拉起 stub Activity。

### 3.5 Choreographer —— UI 线程帧节拍

应用侧（注入到 Launcher / SystemUI / 仪表 app）：

```java
public class FramePulse implements Choreographer.FrameCallback {
    private long lastNs = SystemClock.elapsedRealtimeNanos();
    private final Handler watchdog;            // 独立 HandlerThread
    private static final long STALL_NS = 2_000_000_000L;

    public void start() {
        Choreographer.getInstance().postFrameCallback(this);
        watchdog.postDelayed(this::check, 1000);
    }
    @Override public void doFrame(long frameTimeNanos) {
        lastNs = frameTimeNanos;
        Choreographer.getInstance().postFrameCallback(this);
    }
    private void check() {
        long now = SystemClock.elapsedRealtimeNanos();
        if (now - lastNs > STALL_NS) {
            report("ui_thread_frame_stall", (now - lastNs)/1_000_000);
        }
        watchdog.postDelayed(this::check, 1000);
    }
}
```

**判定**：

- 连续 > 2s 没有 `doFrame`：该进程 UI 线程已卡死 / VSYNC 不再下发。
- 不依赖任何 hidden API、单次回调 < 1μs。

### 3.6 gfxinfo —— 应用级渲染统计

```bash
dumpsys gfxinfo com.voyah.cockpit.launcher framestats reset
sleep 2
dumpsys gfxinfo com.voyah.cockpit.launcher framestats
```

关注：

- `Total frames rendered` 在 2 秒间增量 ≈ 期望帧率：进程在画。
- 全 0：进程 UI 线程没在出帧（与 Choreographer 信号互证）。
- `Number Frame deadline missed` 飙高：渲染卡顿，但未必黑屏。

字段解读详见同目录 [`gfxinfo_jank_analysis.md`](gfxinfo_jank_analysis.md)。

### 3.7 PowerManager / Keyguard / Media —— 真黑场景的前置过滤

在判定"异常黑屏"前必须排除以下"合理黑"场景：

```bash
dumpsys power | grep -E 'mWakefulness|mDisplayPowerRequest'
dumpsys media_session | grep -E 'state=PLAYING|state=BUFFERING'
dumpsys deviceidle | grep mState
```

或在应用侧：

```java
PowerManager pm = ctx.getSystemService(PowerManager.class);
if (!pm.isInteractive()) return;             // 息屏
KeyguardManager km = ctx.getSystemService(KeyguardManager.class);
if (km.isKeyguardLocked()) checkLockscreen();
if (mediaSessionPlaying) skipScreenshot();   // 避开 DRM 帧
```

**这些不是异常**：

| 状态 | 含义 | 处理 |
|---|---|---|
| `mWakefulness=Asleep` | 用户息屏 | 跳过所有黑屏判定 |
| `mWakefulness=Dozing` | DOZE 节能 | 跳过 |
| MediaSession `PLAYING` 且 surface 受保护 | 视频播放、DRM 全黑帧 | 跳过截屏路径 |
| 启动前 2s 内 splash 期 | 应用刚启动 | 给容忍窗口 |

---

## 4. 信号交叉与定位决策表

PVM 与 GVM 信号交叉后可以直接定位异常段：

| PVM vblank | PVM connector | GVM SF presentFence | GVM Choreographer | GVM WMS focus | 定位 |
|---|---|---|---|---|---|
| ✓ 60/s | ✓ connected | ✓ 推进 | ✓ 出帧 | ✓ 有 focus | **正常** |
| ✓ 60/s | ✓ connected | ✓ 推进 | ✓ 出帧 | ✗ focus 丢失 | **① 应用层**：WMS / 焦点应用异常 |
| ✓ 60/s | ✓ connected | ✓ 推进 | ✗ 停摆 | ✓ 有 focus | **② UI 卡死**：该进程 RenderThread/main 阻塞 |
| ✓ 60/s | ✓ connected | ✗ 停摆 | — | — | **③④ 合成层**：SurfaceFlinger / HWC HAL 异常 |
| ✓ 60/s | ✓ connected | GVM 出帧但 PVM 同帧反复 | ✓ | ✓ | **⑤ 跨 VM 通道**：buffer 未送达 PVM |
| ✗ 0/s | ✓ connected | ✓ 出帧 | ✓ | ✓ | **⑥⑦ DRM/DPU**：commit 不再下发硬件 |
| — | ✗ disconnected | — | — | — | **⑧ DSI 链路**：物理链路掉 |
| ✓ 60/s | ✓ connected | ✓ | ✓ | ✓ | 屏暗但软件正常 → 看 `bl_power` / `brightness` → **⑨ 背光** |
| `bl_power=4` | ✓ | ✓ | ✓ | ✓ | **⑨ 背光被关** |

这张表是双 VM 检测的核心价值：单看 GVM 永远分不清 ⑤⑥⑦⑧⑨，单看 PVM 永远分不清 ①②③④。

---

## 5. 端到端线上检测组合方案

```text
┌────────────────────────────────────────────────────────────────┐
│ GVM 监测服务（系统签名 priv-app，无需反射截屏）                │
│                                                                │
│  [前置过滤] PowerManager.isInteractive + DisplayManager.state │
│                  └─ 不满足 → 跳过本周期                        │
│                                                                │
│  [主信号-应用] Choreographer FrameCallback（埋点在 Launcher/   │
│                SystemUI/仪表），UI 线程 > 2s 无 doFrame → 标记 │
│                                                                │
│  [主信号-系统] 周期 5s 解析 dumpsys SurfaceFlinger --latency  │
│                presentFence 不前进 → 标记                      │
│                                                                │
│  [辅助]   dumpsys window  / dumpsys activity top              │
│           focus 丢失或 mResumedActivity 为空 → 标记            │
│                                                                │
│  任一标记触发 → IPC 通知 PVM 协查                              │
└────────────────────────────────────────────────────────────────┘
                            │ AF_VSOCK / vsock-socket
                            ▼
┌────────────────────────────────────────────────────────────────┐
│ PVM 黑屏协查 daemon（C/Rust，跑在 systemd）                    │
│                                                                │
│  收到 GVM 告警 → 立刻采样：                                    │
│    - vblank_count 两次差 (硬件出帧率)                         │
│    - drm state.active / connector status                       │
│    - bl_power / brightness                                     │
│    - sde_evtlog tail（最近 100 行）                            │
│    - dmesg 过滤 (drm|sde|dsi|panel) 最近 5s                    │
│                                                                │
│  本地常驻轻量轮询（30s/次）：                                  │
│    - vblank 突降 / connector 断开 → 主动上报                   │
│                                                                │
│  采样结果 + GVM 信号 → 写 /data/vendor/blackscreen/<ts>.json  │
│                          → 上传车云                            │
└────────────────────────────────────────────────────────────────┘
```

关键设计要点：

1. **不做常态截屏**。SurfaceFlinger 截屏会把 idle 的 HWC 路径拉醒，对车机怠速功耗不友好；改用 SurfaceFlinger frameNumber/presentFence 推进作为同等强度但零唤醒的信号。
2. **GVM 主动告警 + PVM 被动协查**。PVM 平时不轮询 GVM（跨 VM IPC 成本），只在 GVM 报警时按需采样硬链路状态。这样两侧成本都最低。
3. **信号必须双侧合一**才升级故障。单侧信号容易被启动闪屏 / DOZE / DRM 内容触发，双侧交叉去掉绝大部分误报。
4. **截屏只在最后兜底**。当 PVM 报硬链路全绿、GVM 报合成正常、但用户仍上报黑屏时，再做一次截屏 + 多元判据（黑/灰/冻/单色）确认是否是"应用绘黑"。

---

## 6. 真黑场景白名单

无论方案多强，下列状态绝不能误报，必须在 GVM 监测服务里硬过滤：

| 场景 | 识别方式 |
|---|---|
| 用户息屏 / DOZE | `PowerManager.isInteractive() == false` |
| 锁屏全黑墙纸 | `KeyguardManager.isKeyguardLocked()` + 检查 Keyguard window 可见 |
| 应用启动 splash | Activity `onWindowFocusChanged` 后 1.5s 内不判 |
| DRM / Widevine 视频 | `MediaSession.PlaybackState == PLAYING` 且 surface secure |
| 用户调节亮度到 0 | `Settings.System.SCREEN_BRIGHTNESS == 0` |
| OTA / Recovery 启动中 | `getprop sys.boot_completed != 1` |
| 仪表夜间黑底 UI | 业务白名单（Activity 包名/Theme 注册） |

---

## 7. 关键 adb 命令速查

PVM 侧：

```bash
adb -s e66b06ea shell                          # 进 PVM Linux

cat /sys/class/drm/card0-DSI-1/status          # connector
cat /sys/class/drm/card0-DSI-1/enabled
cat /sys/kernel/debug/dri/0/state              # atomic 全量
cat /sys/kernel/debug/dri/0/crtc-0/vblank_count
cat /sys/kernel/debug/dri/0/debug/dump/evtlog/sde_evtlog
cat /sys/class/backlight/panel0-backlight/bl_power
cat /sys/class/backlight/panel0-backlight/brightness
dmesg -T | grep -iE 'drm|sde|dsi|panel|dpu'
```

GVM 侧：

```bash
adb -s d7df5883 shell                          # 进 GVM Android

dumpsys display | grep -E 'mGlobal|mState|RefreshRate'
dumpsys SurfaceFlinger | grep -E 'powerMode|VSYNC period|composition'
dumpsys SurfaceFlinger --latency
dumpsys SurfaceFlinger --frame-events
dumpsys window | grep -E 'mCurrentFocus|mTopFullOpaqueWindow'
dumpsys activity top | head -20
dumpsys gfxinfo com.voyah.cockpit.launcher framestats
dumpsys power | grep -E 'mWakefulness|mDisplayPowerRequest'
```

---

## 一句话总结

> 智能座舱黑屏检测必须**双 VM 并行**：PVM 侧用 DRM/vblank/sde_evtlog/背光判定"屏是否在出帧、面板是否有光"，覆盖跨 VM 通道及以下的环节⑤–⑩；GVM 侧用 DisplayManager / SurfaceFlinger / WMS / ActivityManager / Choreographer 公开接口判定"Android 软件栈是否在按节拍出可见画面"，覆盖环节①–④。**两侧信号必须经过决策表交叉**才能区分 10 个黑屏环节，否则一定有结构性盲区。截屏不是探测主信号，是兜底验证。
