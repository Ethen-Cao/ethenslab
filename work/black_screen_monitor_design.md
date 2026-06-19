# 仪表屏黑屏监测方案设计

## 目标

实现 500ms~1000ms 精度的仪表屏黑屏检测，覆盖本次事件暴露出的两类黑屏场景：

| 场景 | 硬件信号 | 显示内容 | 现有检测能力 |
|------|:---:|:---:|------|
| A. 物理链路断开 (CABLE/LINK 异常) | ❌ 异常 | 黑屏 | ✅ CABLE diag (3s) |
| B. 链路正常但显示空白内容 | ✅ 正常 | 黑屏 | ❌ 无 |

本次事件属于场景 B——DS90UB983 桥接芯片正常输出视频信号，但 Unity HMI 加载了空白 `UIDefault.prefab`。

---

## 现有架构分析

### display_diag 轮询机制

源码：`layers/meta-voyah-bsp/recipes-products/owfds-misc/files/diag/display_diag/src/display_diag.c`

```
main() 循环:
  for displayId in [central, cluster, hud, ...]:
    for diagType in [CABLE, LINK]:
      if (使能):
        value = diag_detect_status()   // 动态加载 bridge so → I2C 读寄存器
        display_diag_send_sync()       // vsock 上报到 host
        sleepMs(sleepTimes)            // 间隔 = 3000ms / 使能总数
```

当前使能配置（`diag_info_case[]`）：
```c
{"central",   diag_enable=0,  diag_type={CABLE=1, LINK=1}}   // 关闭
{"cluster",   diag_enable=0,  diag_type={CABLE=1, LINK=0}}   // 关闭，且 LINK 未使能
{"hud",       diag_enable=0,  diag_type={CABLE=0, LINK=0}}   // 全关
```

**注意**：`diag_enable` 默认为 `DIAG_DISABLE`，由 XML 配置 `Diag_display_<screen_name>` 动态开启。从日志来看实际运行时是 enable 的。

如果运行时 central(CABLE+LINK)=2 + cluster(CABLE)=1，则 `total_enabled=3`，`sleepTimes=3000/3=1000ms`。cluster CABLE 每 3 秒检查一次。

### DS90UB983 桥接芯片诊断

源码：`layers/meta-voyah-bsp/.../display/bridge/DS90UB983_MST_CLUS888_HUD47/src/DS90UB983_MST_CLUS888_HUD47.c`

```c
// ds90ub983_mst_clus888_hud47_diag() — 每次 I2C 读取以下寄存器：
port0 lock status:  reg 0x0C via port 0x01      // FPD-Link 端口锁定状态
port1 lock status:  reg 0x0C via port 0x12      // FPD-Link 端口锁定状态
vp0 sync status:    reg 0x42 via page 0x31/0x30  // Video Processor 0 同步状态
vp1 sync status:    reg 0x42 via page 0x31/0x70  // Video Processor 1 同步状态

// CABLE diag:
SAR ADC LINE_FAULT0_FINAL (reg 0x1D): 0x22~0x3D=正常, 0x00~0x0A=对地短路, 0x49~0x6A=开路, >0xA9=对电源短路

// LINK diag (cluster 未使能):
port 0 reg 0xC4 bit5: 1=链路有效, 0=链路无效
```

**关键限制**：所有检查都是物理层信号完整性验证。当视频时序正常但显示内容为黑色时，全部返回 NORMAL。

---

## 分层监测方案

```
┌─────────────────────────────────────────────────────┐
│                   Layer 3: MCU 侧                     │
│   MCU 通过独立通道采样 FPD-Link 信号或 SOC 心跳       │
│   精度: 100ms, 检测: 物理断链 + SOC 死机              │
├─────────────────────────────────────────────────────┤
│                   Layer 2: HMI 应用层                 │
│   Unity HMI 上报 Procedure 状态 + 渲染帧计数           │
│   精度: ~100ms, 检测: UI 空白/异常切换                 │
├─────────────────────────────────────────────────────┤
│                   Layer 1: 硬件链路层                 │
│   增强 display_diag 轮询频率到 500ms                   │
│   精度: 500ms, 检测: CABLE/LINK 物理断链              │
└─────────────────────────────────────────────────────┘
```

---

## Layer 1: 硬件链路层（基于现有 display_diag 增强）

### 方案：cluster-only 独立快速诊断线程

**不改 `DEFAULT_DIAG_INTERVAL_MS`，不改变 central/hud 等其他屏的轮询节奏。** 仅对 cluster 新增独立线程。

```c
// display_diag.c 修改点

// 启动时缓存 bridge .so 和函数指针，避免每次 dlopen/dlclose
static void *bridge_handle = NULL;
static diag_func_type cached_cluster_diag_func = NULL;
static diag_func_type cached_cluster_diag_sub_func = NULL;

// cluster 专用快速诊断线程
static void *cluster_fast_diag_thread(void *arg)
{
    char *xml_name = (char *)arg;
    uint32_t interval_ms = 500;
    uint8_t  cable_fail_count = 0;
    uint8_t  link_fail_count  = 0;
    uint8_t  status_log_throttle = 0;       // 日志节流计数器
    uint64_t last_check_ms = 0;
    uint64_t lock_wait_count = 0;
    uint64_t i2c_retry_count  = 0;

    while (TRUE) {
        if (diag_suspend_flag) {
            sleep(1);
            continue;
        }
        if (get_dp_power_mode("/run/display-voyah/TRG_DP3S1/dppwr") != ON ||
            get_dp_trigger_inactive("/run/display-voyah/TRG_DP3S1/active") != INACTIVE) {
            sleep(1);
            continue;
        }

        // 基于绝对时间戳控制间隔，避免 I2C 重试导致的间隔漂移
        uint64_t now = get_time_ms();
        if (now - last_check_ms < interval_ms) {
            sleepMs(10);
            continue;
        }
        last_check_ms = now;

        uint64_t t0 = get_time_us();

        int cable_ret = cached_cluster_diag_func(DISPLAY_DIAG_TYPE_CABLE);
        int link_ret  = cached_cluster_diag_func(DISPLAY_DIAG_TYPE_LINK);

        uint64_t elapsed_us = get_time_us() - t0;

        // --- Cable 判断 ---
        if (cable_ret == DISPLAY_DIAG_STATUS_ABNORMAL) {
            if (++cable_fail_count >= 3) {       // 连续 3 次 → 1.5s 确认窗口
                LOGE("CLUSTER BLACK SCREEN: CABLE abnormal (fail_count=%u)", cable_fail_count);
                report_black_screen_event(BLACK_SCREEN_TYPE_HARDWARE_CABLE);
                cable_fail_count = 0;            // 上报后重置，避免重复上报
            }
        } else {
            cable_fail_count = 0;
        }

        // --- Link 判断 ---
        if (link_ret == DISPLAY_DIAG_STATUS_ABNORMAL) {
            if (++link_fail_count >= 3) {
                LOGE("CLUSTER BLACK SCREEN: LINK abnormal (fail_count=%u)", link_fail_count);
                report_black_screen_event(BLACK_SCREEN_TYPE_HARDWARE_LINK);
                link_fail_count = 0;
            }
        } else {
            link_fail_count = 0;
        }

        // --- 可观测性：记录诊断耗时、重试、锁等待 ---
        if (elapsed_us > 50000) {   // >50ms 异常慢
            LOGW("cluster diag slow: %llu us, i2c_retries=%llu, lock_waits=%llu",
                 elapsed_us, i2c_retry_count, lock_wait_count);
        }

        // --- 状态日志节流：每 30 次 (~15s) 或状态变化才打印 ---
        if (++status_log_throttle >= 30 ||
            cable_ret != last_cable_status ||
            link_ret  != last_link_status) {
            status_log_throttle = 0;
            last_cable_status = cable_ret;
            last_link_status  = link_ret;
            LOGI("cluster diag: cable=%s link=%s elapsed=%llu us",
                 cable_ret == 0 ? "NORMAL" : "ABNORMAL",
                 link_ret  == 0 ? "NORMAL" : "ABNORMAL",
                 elapsed_us);
        }

        sleepMs(interval_ms);
    }
    return NULL;
}
```

### 风险控制措施

| 风险 | 措施 |
|------|------|
| I2C 竞争（外部进程不守 flock） | 仅 cluster 提速，不改全局；连续 3 次异常才上报 |
| 日志压力（port/vp status 裸奔 `LOGI`） | status log throttle 每 30 次 (~15s) 或状态变化才打 |
| I2C 瞬态误报 | 连续 3 次 ABNORMAL (1.5s 窗口) 才触发 DTC |
| dlopen/dlclose 重复开销 | 启动时缓存函数指针 |
| 间隔漂移（I2C 重试导致） | 绝对时间戳控制 |
| 诊断退化不可见 | 记录单次耗时、retry 计数、lock wait 计数 |

### 改动量

| 文件 | 改动 |
|------|------|
| `display_diag.c` | 新增 cluster 快速诊断线程 (~70 行) + 启动缓存 |
| `display_diag.h` | 新增函数声明 |
| `display_def_type.h` 或配置 | 新增 `BLACK_SCREEN_EVENT` DTC 码 ×2 (CABLE / LINK) |
| xml 配置 | 开启 `Diag_display_cluster` 的 LINK 诊断使能 |
| `DS90UB983_MST_CLUS888_HUD47.c` | port/vp status 日志加节流 |

### 检测精度

- CABLE 断线 / LINK 失效：**500ms 采样 + 1.5s 确认 = 2s 内告警**
- I2C 总线占用率：~3.6%（500ms 间隔，单次 ~18ms）
- 日志量：~0.07 行/秒（节流后，相比节流前降低 ~99%）

---

## Layer 2: HMI 应用层（Unity 侧新增）

### 问题分析

本次黑屏的根因是 Unity HMI 在 `ProcedureCluster` 状态下加载了空白 `UIDefault.prefab`。硬件链路完全正常，Layer 1 无法检测。

### 方案 A：渲染帧心跳 + Procedure 状态上报

在 Unity HMI 侧新增一个 Monitor 脚本，每 200ms 通过 IPC 上报心跳：

```csharp
// Unity C# 侧新增：BlackScreenMonitor.cs
public class BlackScreenMonitor : MonoBehaviour
{
    private int _frameCount = 0;
    private string _currentProcedure = "";
    private string _currentPrefab = "";
    private float _lastReportTime = 0f;
    
    void Update()
    {
        _frameCount++;
        
        if (Time.time - _lastReportTime > 0.2f)  // 200ms 上报一次
        {
            _lastReportTime = Time.time;
            
            // 通过 IPC 上报到 clusterservice
            IpcPublisher.Publish("icdiag/RenderHeartbeat", JsonUtility.ToJson(new {
                frameCount = _frameCount,
                procedure = _currentProcedure,
                prefab = _currentPrefab,
                timestamp = DateTime.Now
            }));
        }
    }
    
    public void OnProcedureChanged(string procedure, string prefab)
    {
        _currentProcedure = procedure;
        _currentPrefab = prefab;
        
        // 检测到 UIDefault.prefab 时立即上报 Warning
        if (prefab.Contains("UIDefault"))
        {
            IpcPublisher.Publish("icdiag/RenderHeartbeat", JsonUtility.ToJson(new {
                frameCount = _frameCount,
                procedure = procedure,
                prefab = prefab,
                warning = "DEFAULT_PREFAB_LOADED",
                timestamp = DateTime.Now
            }));
        }
    }
}
```

### 方案 B：GPU 合成帧计数器（Weston/DRM 层）

在 SOC 侧新增一个 daemon，通过 DRM 事件监控 cluster 输出：

```c
// 新增: black_screen_monitor.c
// 通过 DRM_IOCTL_WAIT_VBLANK 或监听 page_flip 事件检测 cluster CRTC 的帧输出

#include <xf86drm.h>
#include <xf86drmMode.h>

static int monitor_cluster_vblank(int drm_fd, int crtc_id)
{
    drmVBlank vbl = {
        .request = {
            .type = DRM_VBLANK_RELATIVE,
            .sequence = 1,
        },
    };
    
    uint64_t last_vblank_time = 0;
    uint32_t black_screen_ms = 0;
    
    while (1) {
        // 等待下一个 vblank
        drmWaitVBlank(drm_fd, &vbl);
        
        uint64_t now = get_current_time_ms();
        if (last_vblank_time > 0) {
            uint64_t interval = now - last_vblank_time;
            if (interval > 500) {  // 超过 500ms 无 vblank
                LOGE("CLUSTER VBLANK TIMEOUT: %llu ms", interval);
                black_screen_ms += interval;
                if (black_screen_ms >= 1000) {
                    report_black_screen_event(BLACK_SCREEN_TYPE_VBLANK_LOST);
                }
            } else {
                black_screen_ms = 0;
            }
        }
        last_vblank_time = now;
    }
}
```

### 对比

| 方案 | 精度 | 改动量 | 覆盖场景 |
|------|:---:|------|------|
| A: Unity 心跳 | ~200ms | Unity C# + clusterservice IPC | UI 空白、Procedure 异常 |
| B: DRM vblank | ~16ms | 新增 daemon (~100行C) | GPU 停止输出、compositor 卡死 |

**建议同时实施 A+B**：A 覆盖应用层异常（本次事件），B 覆盖 GPU/compositor 层异常。

---

## Layer 3: MCU 侧独立监测

### 原理

MCU 独立于 SOC 运行，通过硬件通道直接采样显示信号：

```
SOC (Linux) ──FPD-Link──> DS90UB983 ──LVDS──> Panel
                              │
                              ├── I2C ← SOC 自身读取 (Layer 1, 不独立)
                              │
                              └── 独立的 GPIO/ADC ← MCU 读取 (Layer 3, 独立)
```

### 实现方式

**方式 1：MCU 通过独立 I2C 读取 DS90UB983 状态**

```
MCU ──独立 I2C 总线──> DS90UB983 ──读取 VP sync + port lock 寄存器
                      每 100ms 轮询
                      连续 5 次 (500ms) 异常 → 触发告警
```

**方式 2：SOC→MCU 心跳看门狗**

```
SOC clusterservice ──CAN/UART──> MCU 心跳 (每 200ms)
                                  MCU 超时 1s 无心跳 → 判定 SOC 侧异常
```

**方式 3：FPD-Link 信号监控**

```
DS90UB983 FPD-Link 输出 ──GPIO──> MCU 检测 HSYNC/VSYNC 信号
                                  信号丢失 >500ms → 判定链路异常
```

### 建议

Layer 3 作为独立于 SOC 的最后一道防线，建议至少实施方式 2（心跳看门狗），在 SOC 完全死机/重启时也能检测。

---

## 实施优先级

| 优先级 | 方案 | 覆盖场景 | 精度 | 改动量 |
|:---:|------|------|:---:|------|
| **P0** | Layer 1: display_diag 高速轮询 | 物理断链 | 500ms | 小 (~40行 C) |
| **P0** | Layer 2-A: Unity 心跳 + Prefab 检测 | UI 空白 (本次事件) | 200ms | 中 (Unity+IPC) |
| **P1** | Layer 2-B: DRM vblank 监控 | GPU 停输/compositor 卡死 | 16ms | 小 (~100行 C) |
| **P1** | Layer 3: SOC→MCU 心跳看门狗 | SOC 死机/重启 | 1000ms | 中 (MCU+CAN) |

---

## 告警上报

检测到黑屏后，通过现有 `display_diag_send_sync()` 的 vsock 通道上报到 PVM host：

```c
// 新增 DTC 码定义
#define DTC_CLUSTER_BLACK_SCREEN_HARDWARE  0x9F3XXX  // 硬件链路黑屏
#define DTC_CLUSTER_BLACK_SCREEN_CONTENT   0x9F3YYY  // 显示内容空白
#define DTC_CLUSTER_BLACK_SCREEN_VBLANK    0x9F3ZZZ  // vblank 丢失

// 上报函数
void report_black_screen_event(BlackScreenType type) {
    uint8_t msg[DIAG_MSG_SIZE] = {0};
    // 构造 diag 消息并通过 vsock 发送
    msg[STATUS_OFFSET] = DISPLAY_DIAG_STATUS_ABNORMAL;
    // 编码黑屏类型到消息中
    vsock_send(msg, DIAG_MSG_SIZE);
    // 同时写 syslog
    LOGE("BLACK_SCREEN: cluster screen black detected, type=%d", type);
}
```
