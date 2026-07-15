# H47A_8397 STR (Suspend-to-RAM) Process Analysis

> **Document**: H47A_8397_STR_PROCESS_ANALYSIS
> **Platform**: Qualcomm SA8797 (IVI8397)
> **Architecture**: PVM (Linux Host) + GVM (Android Guest VM) via Gunyah Hypervisor
> **Source Root**: `apps_proc/`
> **Date**: 2026-06-24

---

## 1. System Architecture Overview

```
+====================================================================+
|                          MCU (CAN Bus)                              |
|            CAN ID=0x8005  -->  STR Enter / Shutdown                 |
+==================================+=================================+
                                   |
                                   v
+====================================================================+
|                         PVM (Linux Host)                            |
|                                                                     |
|  +--------------------------------------------------------------+  |
|  | Layer 1: Application (powermgr)                              |  |
|  |   CClient_str  -- STR state machine (message-driven)         |  |
|  |   CStmPower    -- Power state broadcast & transition         |  |
|  |   powmgr_convMsg -- CAN frame -> event conversion            |  |
|  +--------------------------------------------------------------+  |
|                              |                                      |
|  +--------------------------------------------------------------+  |
|  | Layer 2: BSP Abstraction (voyahpm_bsp)                       |  |
|  |   pm_pvm_enter_suspend()  -- PVM s2idle + systemd suspend    |  |
|  |   pm_gvm_enter_suspend()  -- GVM virtual power key suspend   |  |
|  |   pm_gvm_resume()         -- GVM virtual power key resume    |  |
|  |   pm_monitor_power_key()  -- Physical power key detection    |  |
|  +--------------------------------------------------------------+  |
|                              |                                      |
|  +--------------------------------------------------------------+  |
|  | Layer 3: Vendor PM (qc-pm)                                   |  |
|  |   qc_pm_trigger_dsqb() -- Full DSQB sequence (legacy)        |  |
|  +--------------------------------------------------------------+  |
|                              |                                      |
|  +--------------------------------------------------------------+  |
|  | Layer 4: systemd Infrastructure                              |  |
|  |   systemd-logind  -- D-Bus SuspendWithFlags                  |  |
|  |   sleep-notify@   -- Per-service sleep notification          |  |
|  |   pm-server        -- UNIX socket PM event dispatcher        |  |
|  +--------------------------------------------------------------+  |
|                              |                                      |
|  +--------------------------------------------------------------+  |
|  | Layer 5: Linux Kernel                                       |  |
|  |   kernel/power/suspend.c  -- s2idle_loop / enter_state       |  |
|  |   drivers/base/power/main.c -- dpm_suspend/resume callbacks  |  |
|  +--------------------------------------------------------------+  |
|                              |                                      |
|  +--------------------------------------------------------------+  |
|  | Layer 6: VMM / Hypervisor                                   |  |
|  |   vmm-service       -- Guest lifecycle event dispatch        |  |
|  |   vmm-pwr-key       -- Virtual power key via uinput          |  |
|  |   crosvm (ACPIPM)   -- GVM ACPI PM1/GPE register emulation   |  |
|  |   Gunyah hypervisor -- VM state transitions                  |  |
|  +--------------------------------------------------------------+  |
+====================================================================+
                                   |
                          Gunyah Hypervisor
                                   |
                                   v
+====================================================================+
|                     GVM (Android Guest VM)                          |
+====================================================================+
```

---

## 2. STR Entry (Suspend) Process

### 2.1 Trigger Sources

There are two entry paths into the STR flow:

#### 2.1.1 Path A: MCU CAN Command (Primary)

The MCU sends a CAN frame to command STR entry.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_convMsg.cpp:502-518`

```cpp
// CAN frame ID 0x8005, frame_bytes[0] == 1 -> enter STR
// CAN frame ID 0x8005, frame_bytes[0] == 0 -> shutdown
else if(msg.frame_id == 0x8005)
{
    if(msg.frame_bytes[0] == 1)
    {
        // ... rpcd notification ...
        get_powerAppIns()->get_clientMgrIns()->get_clientStr_objPtr()->post_enter_str();
    }
    else if(msg.frame_bytes[0] == 0)
    {
        // ... rpcd notification ...
        get_powerAppIns()->get_clientMgrIns()->get_clientStr_objPtr()->post_shutdown();
    }
}
```

| CAN ID | byte[0] | Action |
|--------|---------|--------|
| `0x8005` | `1` | `post_enter_str()` → STR entry |
| `0x8005` | `0` | `post_shutdown()` → System shutdown |

#### 2.1.2 Path B: State Machine Transition (KL15 Off)

When the ignition (KL15) is turned off and no wakeup sources are active, the power state machine transitions from STANDBY to STR.

**Evidence**: `voyah-cluster/powermgr/tool/auto_gen_src.c:278-300` (state transition table)

```
Transition: STANDBY --[EVT_STR_E=1 && KL15=0 && WAKEUP=0]--> STR
Transition: STR     --[WAKEUP=1 || KL15=1]----------------> STANDBY
```

**Event definitions**: `voyah-cluster/powermgr/tool/auto_gen_header.h`
```c
typedef enum stm_evt_tag {
    EVT_SLEEP_STANDBY_E,   // 0
    EVT_STR_STANDBY_E,     // 1
    EVT_WAKEUP_E,          // 2
    EVT_KL15_E,            // 4
    EVT_STR_E,             // 10
    // ...
} stm_evt_t;
```

### 2.2 STR Entry Flow — Step by Step

#### Step 0: State Machine Broadcast

When the STR state is entered, `CStmPower::CStmPower_strOpen()` broadcasts the power state to all subscribers via VIPC shared memory IPC.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_stmPower.cpp:372-378`

```cpp
int32_t CStmPower::CStmPower_strOpen()
{
    VLOGI("CStmPower_strOpen");
    broadcast_powerstate(POWMGR_STATE_STR);   // broadcast "STR" via VIPC
    return 0;
}
```

**State value**: `voyah-cluster/powermgr/inc/powmgr_common.h:39-57`
```c
typedef enum {
    POWMGR_STATE_SLEEP,          // 0
    POWMGR_STATE_STANDBY,        // 1
    POWMGR_STATE_STANDBY_ALARM,  // 2
    POWMGR_STATE_ANIMATION,      // 3
    POWMGR_STATE_GUARDMODE,      // 4
    POWMGR_STATE_STR,            // 5  <-- STR state
    POWMGR_STATE_OTAMODE,        // 6
    POWMGR_STATE_NORMALMODE,     // 7
    POWMGR_STATE_MAX,
} powmgr_state_t;
```

**VIPC topic**: `voyah-cluster/powermgr/inc/powmgr_clientVipc.h:39-48` — published on topic `"Power/EFSM/mode"` with value `"STR"`.

#### Step 1: Enqueue ENTER_STR Message

`CClient_str::post_enter_str()` pushes an `ENTER_STR` message into the worker thread's message queue.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:550-561`

```cpp
int32_t CClient_str::post_enter_str()
{
    if (!m_worker_running.load()) {
        (void)start_thread();
    }
    {
        std::lock_guard<std::mutex> lk(m_q_mtx);
        m_q.push({MsgType::ENTER_STR, PM_OK});
    }
    m_q_cv.notify_one();
    return 0;
}
```

**Message types**: `voyah-cluster/powermgr/inc/powmgr_clientStr.h:101-111`
```cpp
enum class MsgType : uint8_t {
    ENTER_STR = 0,
    ABORT,
    CANCEL_STR,
    GVM_DONE,
    PVM_DONE,
    RESUME,
    RESUME_DONE,
    STOP,
    SHUT_DOWN,
};
```

#### Step 2: Worker Thread — ENTER_STR Handler

The worker thread `thread_main()` receives the `ENTER_STR` message and begins the orchestrated suspend sequence. The flow has three stages: `IDLE → WAIT_GVM → WAIT_PVM → IDLE`.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:303-350`

```cpp
if (msg.type == MsgType::ENTER_STR) {
    // (a) Reset sleep-cycle state
    m_bsp_event_notified = false;

    // (b) Stop MCU heartbeat monitor (MCU will stop expecting periodic heartbeats)
    CClientHeartbeat* heartbeat_client = ...;
    if (heartbeat_client != nullptr) {
        heartbeat_client->stop_mcu_heartbeat_monitor();
    }

    // (c) Guard: only start from IDLE
    if (m_stage != FlowStage::IDLE) { continue; }

    // (d) Reset flow state
    m_need_cancel_str.store(false);
    m_flow_gen++;
    m_retry_left = 3;   // Shared GVM+PVM retry budget

    // (e) GPIO: pull heartbeat pins LOW (signal MCU that VMs are going to sleep)
    (void)pm_bsp_gpio_set(PM_PIN_PVM_HEARTBEAT, PM_PIN_LOW);  // GPIO 66
    (void)pm_bsp_gpio_set(PM_PIN_GVM_HEARTBEAT, PM_PIN_LOW);  // GPIO 67

    // (f) Stage transition: IDLE -> WAIT_GVM
    m_stage = FlowStage::WAIT_GVM;

    // (g) Spawn detached thread for blocking GVM suspend
    m_gvm_thread = std::thread([this, gen]() {
        const pm_status_t st = this->run_gvm_enter_suspend_with_retry(1);
        this->m_gvm_running.store(false);
        const pm_status_t packed = (pm_status_t)((((uint32_t)gen) << 16) | ...);
        this->enqueue_msg(MsgType::GVM_DONE, packed);
    });
    m_gvm_thread.detach();
}
```

**Flow stage definitions**: `voyah-cluster/powermgr/inc/powmgr_clientStr.h:139-143`
```cpp
enum class FlowStage : uint8_t {
    IDLE = 0,
    WAIT_GVM,
    WAIT_PVM,
};
```

**GPIO pin definitions**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:104-108`
```c
#define VOYAHPM_GPIO_LINE_SLEEP_RDY       68   // Notify MCU SoC ready to sleep
#define VOYAHPM_GPIO_LINE_SLEEP_DONE      -1   // SA8397: controlled by PMIC
#define VOYAHPM_GPIO_LINE_PVM_HEARTBEAT   66   // PVM alive indicator
#define VOYAHPM_GPIO_LINE_GVM_HEARTBEAT   67   // GVM alive indicator
#define VOYAHPM_GPIO_LINE_WAKEUP_SRC_REQ  -1   // SA8397: controlled by MCU
```

#### Step 3: GVM Suspend — `pm_gvm_enter_suspend()`

This is a **blocking call** that runs in a dedicated thread. It connects to the VMM service, sends a virtual power key to each GVM, and waits for the GVM to acknowledge suspend completion.

**Evidence**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:1113-1262`

```
Call Sequence:
  pm_gvm_enter_suspend()
    |
    +--[1] vmm_client_connect("gvm_susp_service", VMM_SERVICE_SERVER, &vmm_handle)
    |       Connect to VMM event service (Unix domain socket)
    |
    +--[2] vmm_subscribe_event_notification(vmm_handle, pm_num_gvms, pm_gvmids, &s_attr)
    |       Subscribe to GVM lifecycle events:
    |         GVM_UP_AND_RUNNING | GVM_SHUTDOWN_LEVEL_1 | GVM_SHUTDOWN_LEVEL_2
    |         | GVM_EVENT_LPM_SUSPEND_SUCCESS | GVM_EVENT_LPM_RESUME_SUCCESS
    |       Callback: pm_gvm_event_cb()
    |
    +--[3] vmm_client_connect("gvm_susp_manager", VMM_POWER_MANAGER_SERVER, &vmm_pwr_key_handle)
    |       Connect to virtual power key manager (socket: /tmp/vmm_pwr_mgr_server)
    |
    +--[4] Set termination flags (before iterating GVMs):
    |       a. atomic_store(&pm_gvm_suspend_can_be_terminated, true)
    |       b. atomic_store(&pm_gvm_suspend_terminate_completed, false)
    |
    +--[5] For each GVM (iterating pm_gvmids[]):
    |       a. vmm_request_gvm_pwr_key(vmid, GVM_KEY_POWER, vmm_pwr_key_handle)
    |          -> Inject virtual KEY_POWER into GVM's uinput device
    |       b. pthread_cond_timedwait(timeout = PM_TIMEOUT_270S)
    |          Wait for GVM_EVENT_LPM_SUSPEND_SUCCESS callback
    |       c. Check pm_gvm_suspend_terminate_completed flag (power-key interrupt)
    |       d. If timeout (270s) or error -> return PM_ERR_TIMEOUT / PM_ERR_GENERIC
    |
    +--[6] cleanup: vmm_client_disconnect handles, reset atomic flags
```

**GVM event callback**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:1074-1100`
```c
static int pm_gvm_event_cb(uint32_t vmid, vmm_event_t event, void *sync)
{
    pm_resp_sync_struct *priv_data = (pm_resp_sync_struct *)sync;
    pthread_mutex_lock(&priv_data->lock);
    if (event == GVM_EVENT_LPM_SUSPEND_SUCCESS) {
        priv_data->gvm_suspend_success = true;
    } else if (event == GVM_EVENT_LPM_RESUME_SUCCESS) {
        priv_data->gvm_resume_success = true;
    } else if (event & GVM_SHUTDOWN_LEVEL_1) {
        priv_data->gvm_shutdown_success = true;
    }
    pthread_cond_signal(&priv_data->cond);
    pthread_mutex_unlock(&priv_data->lock);
    return PM_OK;
}
```

**VMM event definitions**: `vendor/qcom/proprietary/vmm-service-noship/vmm-lib/include/vmm_events.h:26-27`
```c
GVM_EVENT_LPM_SUSPEND_SUCCESS = (BIT_POS << 8),   // BIT_POS = 0x01U
GVM_EVENT_LPM_RESUME_SUCCESS  = (BIT_POS << 9),
```

**VMM-side virtual power key injection**: `vendor/qcom/proprietary/virtual-power-key/src/vmm-pwr-key-main.c:180-197`
```c
// Injects KEY_POWER (KEY_DOWN + SYN + KEY_UP + SYN) into the GVM's uinput device
inject_pwr_key_event(fd, KEY_POWER);
```

#### Step 4: GVM_DONE Message Handling

When the GVM suspend thread finishes, it posts `GVM_DONE` to the worker queue.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:353-428`

```
thread_main() receives GVM_DONE:
  |
  +-- Validate: stage == WAIT_GVM, generation matches
  +-- Check m_need_cancel_str (was wakeup requested during GVM suspend?)
  +-- If st != PM_OK and m_retry_left > 0:
  |     Retry GVM suspend (consume 1 budget)
  |     m_retry_left is SHARED between GVM and PVM (initial = 3)
  +-- If retries exhausted:
  |     Fail STR entry, m_stage = IDLE
  +-- If GVM suspend OK:
        |
        +-- add_event(EVT_STR_E, 1)        // notify state machine
        +-- pm_bsp_gpio_set(PM_PIN_SLEEP_RDY, PM_PIN_LOW)  // GPIO 68 LOW
        |     Signal to MCU: "SoC is about to enter sleep"
        +-- m_stage = WAIT_PVM
        +-- Spawn m_pvm_thread -> run_pvm_enter_suspend_with_retry(1)
```

#### Step 5: PVM Suspend — `pm_pvm_enter_suspend()`

This is a **blocking call** that configures s2idle mode, starts the resume listener, and triggers systemd suspend.

**Evidence**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:1001-1025`

```c
pm_status_t pm_pvm_enter_suspend(void)
{
    pm_status_t st = pm_bsp_check_init(__FUNCTION__);
    if (st != PM_OK) { return st; }

    // (a) Configure suspend mode: write "s2idle" to /sys/power/mem_sleep
    st = pm_set_pvm_str_mode();
    if (st != PM_OK) { return st; }

    // (b) Start the resume listener BEFORE triggering suspend
    //     to ensure we don't miss the PrepareForSleep(false) signal
    st = pm_pvm_start_resume_listener();
    if (st != PM_OK) { return st; }

    // (c) Trigger systemd suspend (BLOCKING — returns only after resume)
    st = pm_pvm_systemd_suspend();
    if (st != PM_OK) { return st; }

    return PM_OK;
}
```

##### 5a. Set s2idle Mode

**Evidence**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:408-443`

```c
static pm_status_t pm_set_pvm_str_mode(void)
{
    // Read current mem_sleep
    fp = fopen(PM_SYS_POWER_MEM_SLEEP_PATH, "r");  // "/sys/power/mem_sleep"
    // ...
    // Write "s2idle" to /sys/power/mem_sleep
    if (fprintf(fp, "s2idle\n") < 0) { ... }
    voyahpm_info("%s set to s2idle", PM_SYS_POWER_MEM_SLEEP_PATH);
    return PM_OK;
}
```

This configures the kernel to use **Suspend-to-Idle** (s2idle) rather than deep suspend (STR in the traditional sense). In s2idle, the CPUs enter idle states but the system is not fully powered down — wakeup latency is minimal.

##### 5b. Start Resume Listener (D-Bus PrepareForSleep)

A detached thread is created to listen for the systemd `PrepareForSleep` D-Bus signal. When the signal arrives with `start=false`, it means the system has resumed and the BSP notifies the upper layer.

**Evidence**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:523-634`

```c
static pm_status_t pm_pvm_start_resume_listener(void)
{
    // Open system D-Bus connection
    sd_bus_open_system(&listen_bus);

    // Match: org.freedesktop.login1.Manager.PrepareForSleep
    sd_bus_match_signal(listen_bus, &listen_slot, NULL,
                        "/org/freedesktop/login1",       // object path
                        "org.freedesktop.login1.Manager", // interface
                        "PrepareForSleep",                // signal name
                        pm_pvm_prepforsleep_handler, NULL);

    // Create detached thread with 256KB custom stack
    pthread_create(&tid, &attr, pm_pvm_wait_for_device_resume_thread, ctx);
}
```

**Resume listener thread**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:475-517`

```c
static void *pm_pvm_wait_for_device_resume_thread(void *arg)
{
    while (!pm_pvm_resumed) {
        ret = sd_bus_process(ctx->bus, NULL);  // Process incoming D-Bus messages
        if (ret > 0) continue;                  // Message was processed
        ret = sd_bus_wait(ctx->bus, (uint64_t)-1); // Block until next message
    }
    // Resume detected: notify upper layer via callback
    if (pm_pvm_resumed && pm_event_cb_func) {
        pm_event_cb_func(PM_EVT_WAKEUP_IRQ, NULL, 0);
    }
    // Cleanup bus/slot
    return NULL;
}
```

**PrepareForSleep handler**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:448-473`

```c
static int32_t pm_pvm_prepforsleep_handler(sd_bus_message *m, ...)
{
    int32_t current_state;
    sd_bus_message_read(m, "b", &current_state);

    if (current_state == false) {
        // current_state = false -> system has RESUMED
        voyahpm_info("system resumed from suspend!!");
        pm_pvm_resumed = true;
        atomic_store(&pm_pvm_suspend_can_be_terminated, false);
    }
    return 0;
}
```

##### 5c. Trigger systemd Suspend

**Evidence**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:636-674`

```c
static pm_status_t pm_pvm_systemd_suspend(void)
{
    sync();  // Best-effort filesystem flush

    sd_bus_default_system(&bus);

    atomic_store(&pm_pvm_suspend_can_be_terminated, true);

    // D-Bus call: org.freedesktop.login1.Manager.SuspendWithFlags(flags)
    // This call BLOCKS until the system resumes from suspend
    ret = sd_bus_call_method(bus,
                             "org.freedesktop.login1",           // service
                             "/org/freedesktop/login1",          // object path
                             "org.freedesktop.login1.Manager",   // interface
                             "SuspendWithFlags",                 // method
                             &error,
                             NULL,                               // no reply needed
                             "t",                                // input signature: uint64
                             flags);                             // SD_LOGIND_ROOT_CHECK_INHIBITORS
    // ...
    return PM_OK;  // Returns only AFTER system has resumed
}
```

#### Step 6: Kernel Suspend Sequence

When systemd receives the `SuspendWithFlags` call, it triggers the kernel's power management subsystem.

**Evidence**: `kernel/kernel_platform/kernel/kernel/power/suspend.c`

```
pm_suspend(state)                          [suspend.c:618]
  |
  +-- enter_state(state)                   [suspend.c:560-635]
        |
        +-- s2idle_begin()                 [suspend.c]
        +-- sys_sync()                     [suspend.c:572]
        +-- suspend_prepare()              [suspend.c:575]
        |     Freeze user-space processes
        |     Call PM_SUSPEND_PREPARE notifiers
        |
        +-- suspend_devices_and_enter()    [suspend.c:489-537]
        |     |
        |     +-- platform_suspend_begin(state)
        |     +-- suspend_console()
        |     +-- dpm_suspend_start(PMSG_SUSPEND)
        |     |     Iterate dpm_list, call ->suspend() on each device
        |     |     See: drivers/base/power/main.c
        |     |
        |     +-- suspend_enter(state)     [suspend.c:404-483]
        |     |     |
        |     |     +-- dpm_suspend_late(PMSG_SUSPEND)
        |     |     +-- dpm_suspend_noirq(PMSG_SUSPEND)
        |     |     +-- s2idle_loop()      [suspend.c:434]
        |     |     |     CPU enters idle, waiting for wakeup IRQ
        |     |     |     Loop continues until wakeup detected
        |     |     |
        |     |     |   *** SYSTEM IS ASLEEP ***
        |     |     |   *** WAKEUP EVENT OCCURS ***
        |     |     |
        |     |     +-- syscore_resume()
        |     |     +-- dpm_resume_noirq(PMSG_RESUME)
        |     |     +-- dpm_resume_early(PMSG_RESUME)
        |     |     +-- dpm_resume(PMSG_RESUME)          [main.c:997-1036]
        |     |
        |     +-- dpm_resume_end(PMSG_RESUME)
        |     +-- resume_console()
        |
        +-- suspend_finish()              [suspend.c:545]
              Thaw user-space processes
              Call PM_POST_SUSPEND notifiers
```

**mem_sleep states**: `kernel/kernel_platform/kernel/kernel/power/suspend.c:42-46`
```c
// Default: mem_sleep_current = PM_SUSPEND_TO_IDLE  (line 49)
static const char * const mem_sleep_states[] = {
    [PM_SUSPEND_TO_IDLE] = "s2idle",
    [PM_SUSPEND_STANDBY] = "shallow",
    [PM_SUSPEND_MEM]     = "deep",
};
```

**Device PM callbacks** are executed in order defined by Linux PM core at `kernel/kernel_platform/kernel/drivers/base/power/main.c`:
- `__device_suspend()` (line 561): calls `.suspend` from `dev->pm_domain->ops`, `dev->type->pm`, `dev->class->pm`, `dev->bus->pm`, `dev->driver->pm`
- `device_resume()` (line 884): calls `.resume` in reverse priority order

#### Step 7: PVM_DONE Message Handling

After the system resumes and `pm_pvm_systemd_suspend()` returns, the PVM thread posts `PVM_DONE` to the worker.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:431-489`

```cpp
if (msg.type == MsgType::PVM_DONE) {
    // Validate stage == WAIT_PVM and generation matches
    // Check m_need_cancel_str
    // If st != PM_OK and m_retry_left > 0: retry PVM suspend
    // If success: STR entry complete
    //     m_stage = IDLE
    //     (Resume will be handled in a separate RESUME message)
}
```

**Important note**: When PVM_DONE arrives with `PM_OK`, it means the system went to sleep AND woke up successfully. The STR entry flow is now complete. The wakeup signal (`PM_EVT_WAKEUP_IRQ`) was already delivered to `handle_bsp_event()` via the BSP resume listener thread. If `m_stage != IDLE` at that point, the cancel flow handles it. If already IDLE, the resume flow is triggered.

### 2.3 STR Entry Sequence Diagram

```
   MCU          powermgr          voyahpm_bsp          VMM/Hypervisor       Kernel
    |               |                   |                    |                 |
    |--CAN 0x8005-->|                   |                    |                 |
    |               |--ENTER_STR        |                    |                 |
    |               |--GPIO66/67 LOW--->|                    |                 |
    |               |                   |                    |                 |
    |               |--WAIT_GVM-------->|                    |                 |
    |               |                   |--connect---------->|                 |
    |               |                   |--subscribe events->|                 |
    |               |                   |--GVM_KEY_POWER---->|                 |
    |               |                   |                    |--uinput-->GVM   |
    |               |                   |                    |                 |
    |               |                   |<--LPM_SUSPEND_OK---|                 |
    |               |<--GVM_DONE--------|                    |                 |
    |               |                   |                    |                 |
    |               |--GPIO68 LOW------>| (MCU: SoC sleep ready)              |
    |               |--WAIT_PVM-------->|                    |                 |
    |               |                   |--write s2idle----->|                 |
    |               |                   |--start resume      |                 |
    |               |                   |  listener thread   |                 |
    |               |                   |--SuspendWithFlags->|                 |
    |               |                   |                    |--enter_state--->|
    |               |                   |                    |  s2idle_loop    |
    |               |                   |                    |  ............   |
    |               |                   |                    |  *** ASLEEP *** |
    |               |                   |                    |  *** WAKEUP *** |
    |               |                   |                    |<-dpm_resume-----|
    |               |                   |<--PrepareForSleep--|                 |
    |               |                   |  (false)           |                 |
    |               |<--PM_EVT_WAKEUP---|                    |                 |
    |               |                   |                    |                 |
    |               |<--PVM_DONE--------|                    |                 |
    |               |                   |                    |                 |
    |               |--RESUME flow------|                    |                 |
```

---

## 3. STR Resume (Wakeup) Process

### 3.1 Wakeup Sources

Wakeup can be triggered by any of:

| Source | Detection | File |
|--------|-----------|------|
| **Physical power key** | `pm_monitor_power_key_thread()` reads `/dev/input/by-path/platform-soc@0:gpio-keys-event` for `KEY_POWER` | `voyahpm_bsp.c:778-836` |
| **MCU GPIO interrupt** | Wakeup IRQ routed through PMIC | Hardware-level |
| **CAN bus activity** | MCU sends CAN wakeup frame | `powmgr_convMsg.cpp:458-471` |

### 3.2 Resume Flow — Step by Step

#### Step 0: Kernel-Level Resume

The kernel's `s2idle_loop()` detects a wakeup interrupt. The CPU exits idle and the kernel begins the device resume sequence in reverse order of suspend.

**Evidence**: `kernel/kernel_platform/kernel/kernel/power/suspend.c:459-483`

```c
// Inside suspend_enter(), after wakeup from s2idle_loop():
syscore_resume();                          // line 459
platform_resume_noirq(state);              // line 470
dpm_resume_noirq(PMSG_RESUME);             // line 472 — devices resume with IRQs disabled
platform_resume_early(state);              // line 475
dpm_resume_early(PMSG_RESUME);             // line 478 — devices early resume
platform_resume_finish(state);             // line 481
// Then back in suspend_devices_and_enter():
dpm_resume_end(PMSG_RESUME);               // line 525 — full device resume
resume_console();                          // line 526
```

**Device resume callback dispatch**: `kernel/kernel_platform/kernel/drivers/base/power/main.c:997-1036`
```c
// dpm_resume() iterates dpm_suspended_list in LIFO order
// device_resume() calls .resume from the PM ops chain:
//   dev->pm_domain->ops, dev->type->pm, dev->class->pm, dev->bus->pm, dev->driver->pm
```

#### Step 1: systemd Sends PrepareForSleep(false)

After the kernel resume completes, systemd-logind broadcasts the `PrepareForSleep` D-Bus signal with `start=false`. The BSP's resume listener thread receives this.

**Evidence**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:448-517`

```
PrepareForSleep(false) arrives on system D-Bus
  |
  +-- pm_pvm_prepforsleep_handler()  [line 448]
  |     current_state == false -> pm_pvm_resumed = true
  |
  +-- pm_pvm_wait_for_device_resume_thread() exits wait loop  [line 486]
  |
  +-- pm_event_cb_func(PM_EVT_WAKEUP_IRQ, NULL, 0)  [line 510]
        Notifies the business layer (CClient_str)
```

#### Step 2: Power Key Detection (Alternate Path)

In parallel, the physical power key monitor thread also detects key presses.

**Evidence**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:778-836`

```c
static void *pm_monitor_power_key_thread(void *arg)
{
    while (1) {
        // Open /dev/input/by-path/platform-soc@0:gpio-keys-event
        fd = open(PVM_POWER_KEY_DEV_PATH, O_RDONLY);
        // Read input_event structs
        bytes_read = read(fd, &ev, sizeof(ev));
        if (ev.type == EV_KEY && ev.code == KEY_POWER) {
            if (ev.value == 1) {  // PRESSED
                // Only process if GVM suspend is in a terminable state
                if (!atomic_load(&pm_gvm_suspend_can_be_terminated)) {
                    continue;  // Ignore — PVM already resumed normally
                }
                // Notify upper layer: wakeup IRQ
                pm_event_cb_func(PM_EVT_WAKEUP_IRQ, NULL, 0);
            }
        }
    }
}
```

#### Step 3: BSP Event Handled by CClient_str

The BSP callback `CClient_str::bsp_event_cb()` forwards the event to the main thread via `m_onNotice`.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:21-67`

```cpp
static void CClient_str::bsp_event_cb(pm_event_type_t event_type, void *data, uint32_t len)
{
    // Forward to main thread context
    g_str_client->m_onNotice([=]() {
        g_str_client->handle_bsp_event(event_type);
    });
}

void CClient_str::handle_bsp_event(pm_event_type_t event_type)
{
    if (event_type == PM_EVT_WAKEUP_IRQ && (m_bsp_event_notified == false)) {
        m_bsp_event_notified = true;  // dedup for this sleep cycle

        // Special case: if shutting down, reboot SOC directly
        if (m_shutdowning) {
            VLOGI("[STR] BSP event: pm_reboot_soc");
            pm_reboot_soc();
        }

        if (m_stage == FlowStage::IDLE) {
            // Normal resume: system was fully suspended, now waking up
            VLOGI("[STR] BSP event: post_resume");
            (void)this->post_resume();
        }
        else {
            // Interrupt: STR entry is in progress (WAIT_GVM or WAIT_PVM)
            VLOGI("[STR] BSP event: post_cancel_str");
            (void)this->post_cancel_str();
        }
    }
}
```

#### Step 4a: RESUME Message Handling (m_stage == IDLE)

When the system was fully suspended and wakes up normally, the `RESUME` message handler runs.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:280-301`

```cpp
if (msg.type == MsgType::RESUME) {
    // (a) Notify state machine to exit STR state
    get_powStmMgrIns()->add_event(EVT_STR_E, 0, STMPOWMGR_TYPE);

    // (b) Increment generation (stale message protection)
    m_flow_gen++;

    // (c) Restore GPIOs: signal MCU that system is awake
    (void)pm_bsp_gpio_set(PM_PIN_SLEEP_RDY, PM_PIN_HIGH);      // GPIO 68
    (void)pm_bsp_gpio_set(PM_PIN_PVM_HEARTBEAT, PM_PIN_HIGH);   // GPIO 66
    (void)pm_bsp_gpio_set(PM_PIN_GVM_HEARTBEAT, PM_PIN_HIGH);   // GPIO 67

    // (d) Spawn thread to resume GVM (retry up to 3 times)
    m_resume_thread = std::thread([this, gen]() {
        const pm_status_t st = this->run_gvm_resume_with_retry(3);
        const pm_status_t packed = ...;
        this->enqueue_msg(MsgType::RESUME_DONE, packed);
    });
    m_resume_thread.detach();
}
```

#### Step 4b: CANCEL_STR Message Handling (m_stage != IDLE)

When wakeup occurs during an in-progress STR entry (GVM or PVM is still suspending), the cancel flow aborts the suspend and initiates recovery.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:234-278`

```cpp
if (msg.type == MsgType::CANCEL_STR) {
    m_need_cancel_str.store(true);   // Signal in-progress operations to abort

    if (m_stage == FlowStage::WAIT_GVM) {
        // GVM is still suspending:
        //   - Restore heartbeat GPIOs immediately
        //   - Call pm_gvm_terminate_suspend() (blocks for VMM protocol,
        //     sends KEY_POWER to each GVM, signals CV to unblock
        //     pm_gvm_enter_suspend, then returns — does NOT wait for
        //     GVM resume confirmation)
        (void)pm_bsp_gpio_set(PM_PIN_PVM_HEARTBEAT, PM_PIN_HIGH);
        (void)pm_bsp_gpio_set(PM_PIN_GVM_HEARTBEAT, PM_PIN_HIGH);
        m_flow_gen++;
        const pm_status_t st = pm_gvm_terminate_suspend();
        this->enqueue_msg(MsgType::RESUME_DONE, packed);
    }
    else if (m_stage == FlowStage::WAIT_PVM) {
        // PVM is suspending (GVM already suspended):
        //   - Terminate PVM suspend (non-blocking)
        //   - Resume GVM
        (void)pm_pvm_terminate_suspend();
        m_flow_gen++;
        get_powStmMgrIns()->add_event(EVT_STR_E, 0, STMPOWMGR_TYPE);
        (void)pm_bsp_gpio_set(PM_PIN_SLEEP_RDY, PM_PIN_HIGH);
        (void)pm_bsp_gpio_set(PM_PIN_PVM_HEARTBEAT, PM_PIN_HIGH);
        (void)pm_bsp_gpio_set(PM_PIN_GVM_HEARTBEAT, PM_PIN_HIGH);

        m_resume_thread = std::thread([this, gen]() {
            const pm_status_t st = this->run_gvm_resume_with_retry(1);
            this->enqueue_msg(MsgType::RESUME_DONE, packed);
        });
    }
}
```

**GVM terminate suspend**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:1273-1339`

```c
pm_status_t pm_gvm_terminate_suspend(void)
{
    // Guard: only proceed if GVM suspend is in progress
    if (!atomic_load(&pm_gvm_suspend_can_be_terminated)) {
        return PM_OK;  // Not in GVM suspend flow, nothing to do
    }

    // Connect to virtual power key manager
    vmm_client_connect("gvm_terminate_susp_manager", VMM_POWER_MANAGER_SERVER, &vmm_pwr_key_handle);

    // For each GVM: inject KEY_POWER to wake it up / cancel its suspend
    for (gvm_idx = 0; gvm_idx < pm_num_gvms; gvm_idx++) {
        vmm_request_gvm_pwr_key(pm_gvmids[gvm_idx], GVM_KEY_POWER, vmm_pwr_key_handle);
    }

    // Signal the waiting pm_gvm_enter_suspend() to abort
    pthread_mutex_lock(&pm_gvm_suspend_sync_state.lock);
    atomic_store(&pm_gvm_suspend_terminate_completed, true);
    pthread_cond_broadcast(&pm_gvm_suspend_sync_state.cond);
    pthread_mutex_unlock(&pm_gvm_suspend_sync_state.lock);

    vmm_client_disconnect(vmm_pwr_key_handle);
    return PM_OK;
}
```

#### Step 5: GVM Resume — `pm_gvm_resume()`

This is a blocking call that resumes each GVM by injecting a virtual power key and waiting for the resume acknowledgement.

**Evidence**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:1352-1536`

```c
pm_status_t pm_gvm_resume(void)
{
    // Initialize local synchronization (mutex + condvar with CLOCK_MONOTONIC)
    // ...

    // Connect to VMM event service
    vmm_client_connect("gvm_resume_service", VMM_SERVICE_SERVER, &vmm_handle);

    // Subscribe to events: GVM_EVENT_LPM_SUSPEND_SUCCESS | GVM_EVENT_LPM_RESUME_SUCCESS
    vmm_subscribe_event_notification(vmm_handle, pm_num_gvms, pm_gvmids, &s_attr);

    // Connect to virtual power key manager
    vmm_client_connect("gvm_resume_manager", VMM_POWER_MANAGER_SERVER, &vmm_pwr_key_handle);

    // For each GVM:
    for (gvm_idx = 0; gvm_idx < pm_num_gvms; gvm_idx++) {
        // (a) Inject virtual KEY_POWER
        vmm_request_gvm_pwr_key(pm_gvmids[gvm_idx], GVM_KEY_POWER, vmm_pwr_key_handle);

        // (b) Wait for GVM_EVENT_LPM_RESUME_SUCCESS with 10s timeout
        ts.tv_sec += PM_TIMEOUT_10S;  // 10 seconds
        while (!pm_resp_sync.gvm_suspend_success && !pm_resp_sync.gvm_resume_success) {
            ret = pthread_cond_timedwait(&pm_resp_sync.cond, &pm_resp_sync.lock, &ts);
            if (ret == ETIMEDOUT) {
                status = PM_ERR_TIMEOUT;
                break;
            }
        }
    }

    cleanup:
        // Disconnect all VMM clients, destroy sync objects
        return status;
}
```

**Key difference from GVM suspend**: Resume waits for EITHER `GVM_EVENT_LPM_RESUME_SUCCESS` OR `GVM_EVENT_LPM_SUSPEND_SUCCESS` — this is a workaround for the NordAU platform where the suspend ACK sometimes indicates that the GVM has already resumed.

**Timeout comparison**:

| Operation | Timeout | Rationale |
|-----------|---------|-----------|
| `pm_gvm_enter_suspend()` | 270 seconds | GVM (Android) may take a long time to finish suspend |
| `pm_gvm_resume()` | 10 seconds | Resume is expected to be fast |
| `qc_pm_trigger_gvm_suspend()` (legacy) | 360 seconds | Even more conservative |

#### Step 6: crosvm Resume Handling

When the virtual power key reaches the GVM, the Android guest resumes. The crosvm VMM handles the ACPI-level resume notification.

**ACPI PM1 wake status**: `external/crosvm/devices/src/acpi.rs:851-855`

```rust
impl BusResumeDevice for ACPIPMResource {
    fn resume_imminent(&mut self) {
        // Set BITMASK_PM1CNT_WAKE_STATUS in PM1 status register
        // This notifies the GVM that the wake was from a sleep state
    }
}
```

**VCPU resume**: `external/crosvm/src/linux/mod.rs:1952-1968`

```rust
// When VmRunMode::Running is received:
//   1. For each device: dev.resume_imminent()  — set ACPI wake status
//   2. Send VcpuControl::RunState(VmRunMode::Running) to all VCPUs
```

**ACPI suspend event trigger** (for context — this is how GVM suspend was initiated): `external/crosvm/devices/src/acpi.rs:768-791`

```rust
// When GVM writes SLP_EN + SLEEP_TYPE_S1 to ACPI PM1 register:
//   -> trigger self.suspend_evt.write(1)   — signals crosvm main loop
//   -> main loop sees Token::Suspend
//   -> pauses all VCPUs via VcpuControl::RunState(VmRunMode::Suspending)
```

#### Step 7: RESUME_DONE Handling

When the GVM resume thread finishes, it posts `RESUME_DONE` to the worker.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:491-545`

```cpp
if (msg.type == MsgType::RESUME_DONE) {
    // Validate generation
    // ...

    // Clear cancel state
    if (m_need_cancel_str.load()) {
        m_need_cancel_str.store(false);
        m_gvm_resume_retry_left = 0;
    }

    m_stage = FlowStage::IDLE;

    // Notify MCU heartbeat monitor (system is fully awake)
    if (this->m_onNotice) {
        this->m_onNotice([=]() {
            VLOGI("[STR] resume done");
            CClientHeartbeat* heartbeat_client = ...;
            if (heartbeat_client != nullptr) {
                heartbeat_client->notify_mcu_heartbeat_monitor();
            }
        });
    }
}
```

### 3.3 Resume Sequence Diagram

```
  Wakeup       Kernel        systemd        voyahpm_bsp       powermgr         VMM
  Source          |             |               |                 |              |
    |             |             |               |                 |              |
    |--IRQ------->|             |               |                 |              |
    |             |--dpm_resume |               |                 |              |
    |             |--resume_console             |                 |              |
    |             |             |               |                 |              |
    |             |--suspend_finish (thaw)      |                 |              |
    |             |             |               |                 |              |
    |             |--PrepareForSleep(false)---->|                 |              |
    |             |             |               |--PM_EVT_WAKEUP->|              |
    |             |             |               |                 |              |
    |  (or Physical Power Key)                  |                 |              |
    |--KEY_POWER-------------------------------->                 |              |
    |             |             |               |--PM_EVT_WAKEUP->|              |
    |             |             |               |                 |              |
    |             |             |               |    handle_bsp_event()         |
    |             |             |               |     |                         |
    |             |             |               |     +--[IDLE]-->RESUME        |
    |             |             |               |     +--[!IDLE]->CANCEL_STR    |
    |             |             |               |                 |              |
    |             |             |               |    GPIO restore:|              |
    |             |             |               |    SLEEP_RDY=H  |              |
    |             |             |               |    HEARTBEAT=H  |              |
    |             |             |               |                 |              |
    |             |             |               |    pm_gvm_resume()------------>|
    |             |             |               |                 |  GVM_KEY_PWR |
    |             |             |               |                 |  uinput->GVM |
    |             |             |               |                 |              |
    |             |             |               |                 |<-LPM_RESUME--|
    |             |             |               |<--PM_OK---------|              |
    |             |             |               |                 |              |
    |             |             |               |         RESUME_DONE            |
    |             |             |               |    m_stage=IDLE                |
    |             |             |               |    notify_heartbeat            |
```

---

## 4. State Machine Transitions

### 4.1 STR-Related State Transitions

**Evidence**: `voyah-cluster/powermgr/tool/auto_gen_src.c` (auto-generated transition table)

```
+------------------+----------+-----------+-----------+------------------+
| From State       | Event    | KL15      | WAKEUP    | To State         |
+------------------+----------+-----------+-----------+------------------+
| SLEEP            | WAKEUP=1 | any       | any       | STANDBY          |
| STR              | WAKEUP=1 | any       | any       | STANDBY          |
| STR              | KL15=1   | any       | any       | STANDBY          |
| STANDBY          | STR_E=1  | KL15=0    | WAKEUP=0  | STR              |
| STANDBY_ALARM    | STR_E=1  | any       | any       | STANDBY          |
+------------------+----------+-----------+-----------+------------------+
```

### 4.2 Power State Evolution (STR Cycle)

```
NORMALMODE                    STANDBY
    |                            |
    |  (KL15 off, no wakeup)     |
    +--------------------------->|
                                 |
                                 |  EVT_STR_E=1 && KL15=0 && !WAKEUP
                                 v
                               STR  ← broadcast_powerstate("STR")
                                 |
                                 |  (wakeup: power key / CAN / GPIO)
                                 v
                              STANDBY  ← add_event(EVT_STR_E, 0)
                                 |
                                 |  (KL15 on / system ready)
                                 v
                             NORMALMODE
```

---

## 5. systemd Sleep Chain

The systemd sleep target chain manages orderly suspend/resume notifications to services.

### 5.1 Service Ordering

```
check-inhibitors.service   (Before=sleep-bounds.target)
    |
    v
sleep-bounds.target        (Boundary — active during suspend AND resume)
    |
    v
sleep-notify@<name>.service  (After=sleep-bounds.target, Before=sleep.target)
    |
    v
sleep-apps.target          (After=sleep-bounds.target, Before=sleep-drivers.target)
    |
    v
sleep-drivers.target       (After=sleep-apps.target, Before=sleep.target)
    |
    v
sleep.target               (JobTimeoutSec=20s, OnFailure=failure-resume.service)
    |
    v
systemd-suspend.service    (Executes the actual suspend)
    |
    v
[System suspended]
    |
    v
[System resumes]
    |
    v
trigger-resume.service     (After=systemd-suspend.service, Before=suspend.target)
    Stops sleep-bounds.target
```

**Configuration files**:

| File | Purpose |
|------|---------|
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/sleep-bounds.target` | Sleep boundary target |
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/sleep.target.d/30-qcom-override.conf` | `JobTimeoutSec=20.0s`, `OnFailure=failure-resume.service` |
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/check-inhibitors.service` | Checks for logind inhibitor locks before sleep |
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/trigger-resume.service` | Cleans up sleep-bounds.target after resume |
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/failure-resume.service` | Cleans up on sleep failure |
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/sleep-notify@.service` | Template: notifies registered clients via pm-server UNIX socket |

### 5.2 Sleep Notification Services

Registered services that receive sleep notifications via `pm-notify <name> <cmd>` (which connects to the `pm-server` UNIX socket at `/run/qcom_pm/<name>.sock`). Each service has a systemd drop-in config that adds `Before=sleep-apps.target` and `PartOf=sleep-apps.target` to the `sleep-notify@.service` template:

| Service | Config File |
|---------|-------------|
| `rpcd` | `voyah-cluster/rpcd/systemd/rpcd-sleep-notify.conf` |
| `voyah_oms_server` | `voyah-cluster/dmsserver/systemd/voyah_oms_server-sleep-notify.conf` |
| `audiomgr` | `voyah-cluster/audiomgr/systemd/audiomgr-sleep-notify.conf` |
| `a2b` | `voyah-bsp/a2b/sleep-notify@a2b.service.d/a2b-sleep-notify.conf` |

### 5.3 PM Notification Server

**Evidence**: `vendor/qcom/opensource/safelinux-services/power-utils/src/pm-server.c:76-159`

The `pm-server` sends suspend/resume events to registered client services via UNIX domain sockets at `/run/qcom_pm/<name>.sock`. Each client receives a `pm_event` struct with the current power command and mode.

---

## 6. Key Constants and Configuration

### 6.1 GPIO Pin Map

**Evidence**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:104-108`

```
+------+--------+-----------+---------------------------------------+
| GPIO | Name   | Direction | Purpose                               |
+------+--------+-----------+---------------------------------------+
| 66   | PVM_   | OUT       | PVM heartbeat. LOW during suspend,    |
|      | HEART- |           | HIGH when awake. Monitored by MCU.    |
|      | BEAT   |           |                                       |
+------+--------+-----------+---------------------------------------+
| 67   | GVM_   | OUT       | GVM heartbeat. LOW during suspend,    |
|      | HEART- |           | HIGH when awake. Monitored by MCU.    |
|      | BEAT   |           |                                       |
+------+--------+-----------+---------------------------------------+
| 68   | SLEEP_ | OUT       | Sleep ready signal to MCU. LOW when   |
|      | RDY    |           | SoC is about to enter sleep. HIGH     |
|      |        |           | when awake or resuming.               |
+------+--------+-----------+---------------------------------------+
| -1   | SLEEP_ | N/A       | SA8397: Controlled by PMIC, not Host  |
|      | DONE   |           |                                       |
+------+--------+-----------+---------------------------------------+
| -1   | WAKEUP | N/A       | SA8397: Controlled by MCU, not Host   |
|      | _SRC   |           |                                       |
|      | _REQ   |           |                                       |
+------+--------+-----------+---------------------------------------+
```

All pins are on `/dev/gpiochip0`, accessed via `libgpiod v2.1.2`.

### 6.2 Timeout Values

| Constant | Value | Location | Context |
|----------|-------|----------|---------|
| `PM_TIMEOUT_270S` | 270s | `voyahpm_bsp.c:1194` | GVM suspend ACK wait |
| `PM_TIMEOUT_10S` | 10s | `voyahpm_bsp.c:1468` | GVM resume ACK wait |
| `qc_pm` GVM timeout | 360s | `qc-pm.c` (legacy) | Legacy GVM suspend |
| `sleep.target JobTimeoutSec` | 20s | `sleep.target.d/30-qcom-override.conf` | systemd sleep timeout |
| `m_retry_left` (initial) | 3 | `powmgr_clientStr.cpp:324` | GVM+PVM shared retry budget |
| `kGvmResumeRetryMax` | 3 | `powmgr_clientStr.h:160` | Resume retry count |
| `PVM_RESUME_THREAD_STACK_SIZE` | 256KB | `voyahpm_bsp.c:581` | Resume listener thread stack |

### 6.3 Suspend Mode

The system uses **s2idle** (Suspend-to-Idle) rather than deep suspend:

- **Evidence**: `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:433` — writes `"s2idle"` to `/sys/power/mem_sleep`
- **Evidence**: `voyah-cluster/powermgr/src/powmgr_stmPower.cpp:73` — legacy path also writes `"s2idle"`
- **Evidence**: `kernel/kernel_platform/kernel/kernel/power/suspend.c:49` — default is `PM_SUSPEND_TO_IDLE`

In s2idle, CPUs enter idle states but the platform is not fully powered off. This provides faster wakeup latency compared to deep suspend (STR in the traditional sense).

### 6.4 VMM Client Service Names

| Client Name | Server | Purpose |
|-------------|--------|---------|
| `"gvm_susp_service"` | `VMM_SERVICE_SERVER` | Subscribe to GVM suspend events |
| `"gvm_resume_service"` | `VMM_SERVICE_SERVER` | Subscribe to GVM resume events |
| `"gvm_susp_manager"` | `VMM_POWER_MANAGER_SERVER` | Send virtual power key for suspend |
| `"gvm_resume_manager"` | `VMM_POWER_MANAGER_SERVER` | Send virtual power key for resume |
| `"gvm_terminate_susp_manager"` | `VMM_POWER_MANAGER_SERVER` | Send virtual power key to abort suspend |

---

## 7. Complete File Index

### 7.1 Application Layer (powermgr)

| File | Content |
|------|---------|
| `voyah-cluster/powermgr/src/powmgr_clientStr.cpp` | STR client state machine (647 lines) — message-driven GVM/PVM orchestration, cancel/resume flows |
| `voyah-cluster/powermgr/inc/powmgr_clientStr.h` | STR client header — `FlowStage`, `MsgType`, retry budget constants |
| `voyah-cluster/powermgr/src/powmgr_stmPower.cpp` | Power state machine — `CStmPower_strOpen/Close/Action`, `broadcast_powerstate`, `strtrigger_thread` |
| `voyah-cluster/powermgr/inc/powmgr_stmPower.h` | Power state machine class declaration |
| `voyah-cluster/powermgr/inc/powmgr_common.h` | `powmgr_state_t` enum (POWMGR_STATE_STR = 5) |
| `voyah-cluster/powermgr/src/powmgr_convMsg.cpp` | CAN message to event conversion (0x8005 STR trigger, KL15, WAKEUP) |
| `voyah-cluster/powermgr/inc/powmgr_clientVipc.h` | VIPC SHM topic definitions, power state string map |
| `voyah-cluster/powermgr/tool/auto_gen_src.c` | Auto-generated state transition table and guard functions |
| `voyah-cluster/powermgr/tool/auto_gen_header.h` | Event enum (`EVT_STR_E = 10`, `EVT_WAKEUP_E = 2`, `EVT_KL15_E = 4`) |
| `voyah-cluster/serviceconfig/powermgr.service` | systemd unit: starts powermgr after audiomgr, rpcd, animmgr |

### 7.2 BSP Layer (voyahpm_bsp)

| File | Content |
|------|---------|
| `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c` | BSP implementation (~1929 lines) — GPIO, s2idle, systemd suspend, VMM communication, power key monitor |
| `voyah-bsp/voyahpm-bsp/include/voyahpm_bsp.h` | BSP public API — `pm_pvm_enter_suspend`, `pm_gvm_enter_suspend`, `pm_gvm_resume`, `pm_gvm_terminate_suspend`, `pm_event_type_t` |

### 7.3 Vendor PM Layer

| File | Content |
|------|---------|
| `vendor/qcom/proprietary/platform_utils/qc-pm/qc-pm.c` | QC PM DSQB library — full suspend/resume sequence with GVM/SM coordination |
| `vendor/qcom/proprietary/platform_utils/qc-pm/include/qc-pm.h` | QC PM header — `qc_pm_trigger_dsqb()` |
| `vendor/qcom/proprietary/vmm-service-noship/vmm-lib/include/vmm_events.h` | VMM event definitions — `GVM_EVENT_LPM_SUSPEND_SUCCESS`, `GVM_EVENT_LPM_RESUME_SUCCESS` |
| `vendor/qcom/proprietary/virtual-power-key/src/vmm-pwr-key-main.c` | Virtual power key manager — uinput device per GVM, `inject_pwr_key_event()` |

### 7.4 systemd Configuration

| File | Content |
|------|---------|
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/sleep-bounds.target` | Sleep boundary target |
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/sleep.target.d/30-qcom-override.conf` | JobTimeoutSec=20s, OnFailure |
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/check-inhibitors.service` | Pre-sleep inhibitor check |
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/trigger-resume.service` | Post-resume cleanup |
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/failure-resume.service` | Sleep failure cleanup |
| `vendor/qcom/opensource/safelinux-services/power-utils/conf/sleep-notify@.service` | Per-client sleep notification template |
| `vendor/qcom/opensource/safelinux-services/power-utils/src/pm-server.c` | PM notification server (UNIX socket IPC) |
| `vendor/qcom/opensource/safelinux-services/power-utils/src/pm-common.c` | PM common (socket path, suspend mode detection) |

### 7.5 Kernel Layer

| File | Content |
|------|---------|
| `kernel/kernel_platform/kernel/kernel/power/suspend.c` | Kernel suspend core — `pm_suspend`, `enter_state`, `s2idle_loop` |
| `kernel/kernel_platform/kernel/drivers/base/power/main.c` | Device PM core — `dpm_suspend/resume` series, `dev_pm_ops` callback dispatch |

### 7.6 VMM / Hypervisor Layer

| File | Content |
|------|---------|
| `external/crosvm/devices/src/acpi.rs` | ACPI PM resource — `suspend_evt`, `resume_imminent()`, PM1 register emulation |
| `external/crosvm/src/linux/mod.rs` | crosvm main loop — `Token::Suspend`, VCPU suspend/resume handling |
| `external/crosvm/devices/src/bus.rs` | `BusResumeDevice` trait — `resume_imminent()` hook |
| `vmm-service-architecture.md` | VMM service architecture documentation (860 lines) |

---

## 8. Error Handling and Edge Cases

### 8.1 Retry Logic

The STR entry flow has a **shared retry budget** of 3 attempts across both GVM and PVM phases.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:324` — `m_retry_left = 3`

Budget is consumed once per attempt start: the ENTER_STR handler consumes 1 before spawning the first GVM attempt (line 337), GVM_DONE failure handler consumes 1 before each retry (line 379), and the transition to PVM consumes 1 before spawning the PVM attempt (line 416).

```
Example: GVM fails once, retries, then succeeds; PVM succeeds
  m_retry_left: 3 -> 2 (first GVM attempt) -> 1 (GVM retry) -> 1 (GVM OK, no consumption)
              -> 0 (PVM attempt) -> 0 (PVM OK, no consumption left)
              Total: 3 budget consumed, STR entry succeeds

  If GVM fails 3 times in total (3 budget exhausted for GVM alone): STR entry fails
  If GVM OK, PVM fails with 0 budget left: STR entry fails (no retry possible)
```

### 8.2 Generation-Based Message Validation

To prevent stale messages from being processed, each STR flow cycle has a unique `m_flow_gen` (generation token).

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:323,345-346,360-366`

```cpp
m_flow_gen++;  // Incremented at start of each ENTER_STR
// Each DONE message carries the generation in the upper 16 bits of status
const pm_status_t packed = (pm_status_t)((((uint32_t)gen) << 16) | ...);
// On receipt: validate generation before processing
if ((uint32_t)(m_flow_gen & 0xFFFF) != msg_gen) {
    VLOGW("[STR] stale GVM_DONE ignored");
    continue;  // Stale message from a previous/aborted cycle
}
```

### 8.3 m_bsp_event_notified Deduplication

The `m_bsp_event_notified` flag ensures that `PM_EVT_WAKEUP_IRQ` is processed at most once per sleep cycle.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:43-44,305`

```cpp
// Reset at ENTER_STR start:
m_bsp_event_notified = false;
// Checked in handle_bsp_event:
if (event_type == PM_EVT_WAKEUP_IRQ && (m_bsp_event_notified == false)) {
    m_bsp_event_notified = true;  // Block subsequent events this cycle
    // ...
}
```

### 8.4 Shutdown Interrupt

If a wakeup occurs while the system is in the shutdown flow (`m_shutdowning == true`), the system directly reboots the SoC rather than trying to resume.

**Evidence**: `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:46-49`

```cpp
if (m_shutdowning) {
    VLOGI("[STR] BSP event: pm_reboot_soc");
    pm_reboot_soc();
}
```

---

## 9. Summary

### STR Entry (Suspend) — End-to-End

```
1. MCU sends CAN 0x8005=1  (or KL15 off triggers state machine)
2. powermgr broadcasts POWMGR_STATE_STR via VIPC
3. CClient_str::ENTER_STR:
   a. Stop MCU heartbeat monitor
   b. Pull HEARTBEAT GPIOs LOW
   c. Stage = WAIT_GVM
4. pm_gvm_enter_suspend():
   a. Connect to VMM service
   b. Inject virtual KEY_POWER to each GVM
   c. Wait for GVM_EVENT_LPM_SUSPEND_SUCCESS (timeout: 270s)
5. On GVM_DONE:
   a. Pull SLEEP_RDY GPIO LOW (notify MCU)
   b. Stage = WAIT_PVM
6. pm_pvm_enter_suspend():
   a. Write "s2idle" to /sys/power/mem_sleep
   b. Start resume listener (D-Bus PrepareForSleep)
   c. Call systemd SuspendWithFlags (BLOCKING)
   d. Kernel enters s2idle_loop — CPUs idle
7. On PVM_DONE: Stage = IDLE (STR entry complete)
```

### STR Resume (Wakeup) — End-to-End

```
1. Wakeup source (power key / CAN / GPIO) triggers IRQ
2. Kernel s2idle_loop exits, dpm_resume series runs
3. systemd sends PrepareForSleep(false) on D-Bus
4. BSP resume listener detects signal → pm_event_cb_func(PM_EVT_WAKEUP_IRQ)
5. CClient_str::handle_bsp_event():
   - If IDLE: post_resume()
   - If WAIT_GVM/WAIT_PVM: post_cancel_str()
6. RESUME / CANCEL_STR handler:
   a. Restore all GPIOs HIGH
   b. Notify state machine: EVT_STR_E = 0
7. pm_gvm_resume():
   a. Connect to VMM service
   b. Inject virtual KEY_POWER to each GVM
   c. Wait for GVM_EVENT_LPM_RESUME_SUCCESS (timeout: 10s)
8. crosvm: resume_imminent() sets ACPI wake status, VCPUs resume
9. RESUME_DONE: Stage = IDLE, restart MCU heartbeat monitor
```
