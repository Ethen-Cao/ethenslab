+++
title = 'PREEMPT_RT 下 AF_UNIX close() 与定时器超时的底层原理'
date = '2026-03-29T18:00:00+08:00'
draft = false
+++

## 一、问题模型

### 1.1 现象

在 PREEMPT_RT 内核 + 密集块设备 I/O 的系统上，可能同时观察到以下症状：

- 多个 watchdog 几乎同一时刻报 timeout
- `select()` / `poll()` / `pthread_cond_timedwait()` 超时不准，偏差达数秒
- 业务主线程、watchdog 管理端本身调度正常，不存在 CPU 饥饿

表面上像是上层 timeout 逻辑有 bug，实际根因在内核锁语义变化。

### 1.2 同一根因的两种表现

这类问题的根因是 **per-CPU BH 锁饥饿**（BH 锁：PREEMPT_RT 下 `local_bh_disable()` 获取的 per-CPU sleeping lock，详见第二节）。它通过两条路径表现为上层 timeout：

| | 路径一：socket close 阻塞 | 路径二：soft hrtimer 延迟 |
|---|---|---|
| 受害者 | 用户线程的 `close()` → `write_lock_bh()` | 内核 softirq 线程（`ktimers/N` 或 `ksoftirqd`） |
| 直接阻塞点 | `sock_orphan()` → `write_lock_bh()` → `local_bh_disable()` → `rt_spin_lock`（BH 锁） | softirq 线程处理定时器时的 `local_bh_disable()` → `rt_spin_lock`（同一把 BH 锁） |
| 上层表现 | 心跳发送线程卡在 `close()` 上，无法发出新心跳 | `futex_wait` / `select` / `poll` 超时不准（偏差达数秒） |
| 线程状态 | D（不可中断睡眠） | softirq 线程 D 状态；用户线程 S 状态（等待 hrtimer 到期） |
| 影响范围 | 所有经过 `write_lock_bh()` / `local_bh_disable()` 的线程 | 所有 SCHED_NORMAL 线程的超时定时器 |
| 共同根因 | IRQ handler 在 `irq_forced_thread_fn()` 中持有 BH 锁，被内层 folio/writeback 锁阻塞，BH 锁长时间不释放 |

两条路径已分别通过 ftrace 验证：路径一确认了用户线程 D 状态的完整等待链和锁持有时序；路径二确认了 softirq 线程（`ktimers/5`）进入 D 状态 1.4 秒，期间无法处理 soft hrtimer，导致 500ms 定时器延迟到 1803ms。

### 1.3 一个典型的脆弱心跳实现

```c
void heartbeat_once(void)
{
    int fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    sendto(fd, &msg, sizeof(msg), 0, ...);
    close(fd);  // ← 每次心跳都走 close() 路径
}
```

每次心跳都新建并关闭一个 AF_UNIX datagram socket。在非 RT 内核上这几乎无感知，但在 PREEMPT_RT 上 `close()` 可能阻塞数秒。

## 二、PREEMPT_RT 如何改变 `local_bh_disable()` 的语义

### 2.1 非 RT 内核：per-CPU 计数器

在普通内核中，`local_bh_disable()` 仅递增 per-CPU 的 preempt_count（`kernel/softirq.c:327-356`）：

```c
// 非 RT 实现
__preempt_count_add(cnt);  // 纯计数器递增，永远不会阻塞
```

它的作用是标记"本 CPU 的 softirq 被禁止"。多个线程各自递增各自的计数器，互不干扰。

### 2.2 RT 内核：per-CPU sleeping lock

在 PREEMPT_RT 内核中，`local_bh_disable()` 被替换为获取 per-CPU 的 `rt_spin_lock`（`kernel/softirq.c:155-192`）：

```c
// RT 实现
local_lock(&softirq_ctrl.lock);  // → rt_spin_lock()，sleeping mutex
```

这意味着：

- **同一 CPU 上只能有一个线程持有 BH 锁**
- 后来者会**睡眠等待**，而非自旋或仅递增计数器
- BH 锁变成了一个**跨子系统的共享阻塞点**

| | 非 RT | RT |
|---|---|---|
| `local_bh_disable()` 实现 | `__preempt_count_add(cnt)`（per-CPU 计数器） | `local_lock(&softirq_ctrl.lock)`（per-CPU rt_spin_lock） |
| 是否可能阻塞 | 永远不会 | 可能睡眠等待 |
| 多线程竞争 | 各自递增计数器，互不干扰 | 串行竞争同一把锁 |
| 持有期间能否被抢占 | 不能（softirq 被禁止） | 能（sleeping lock，可被高优先级线程抢占） |

### 2.3 `irq_forced_thread_fn` 的行为差异

在 PREEMPT_RT 内核中，很多中断处理不再在 hardirq 上下文执行，而是运行在内核线程中（forced-threaded handler）。`irq_forced_thread_fn()`（`kernel/irq/manage.c:1188-1205`）是这类线程的执行入口：

```c
static irqreturn_t irq_forced_thread_fn(struct irq_desc *desc,
                                        struct irqaction *action)
{
    local_bh_disable();                      // RT 和非 RT 都调用
    if (!IS_ENABLED(CONFIG_PREEMPT_RT))
        local_irq_disable();                 // 仅非 RT：关硬中断
    ret = action->thread_fn(action->irq, action->dev_id);
    if (!IS_ENABLED(CONFIG_PREEMPT_RT))
        local_irq_enable();
    local_bh_enable();
    return ret;
}
```

RT 和非 RT 的执行语义完全不同：

| | 非 RT | RT |
|---|---|---|
| `local_bh_disable()` | 递增计数器（不阻塞） | 获取 per-CPU sleeping lock（可能阻塞） |
| `local_irq_disable()` | **调用**：handler 在关硬中断下原子执行 | **不调用**：handler 可被抢占、可睡眠 |
| handler 内的 spinlock | 普通 spinlock（关抢占，不可睡眠） | `rt_spin_lock`（sleeping mutex，可阻塞） |
| handler 能否在持有 BH 锁时睡眠 | 不能：整个 handler 原子完成 | **能：handler 可在内层锁上睡眠，外层 BH 锁仍被持有** |

最后一行是整个问题的关键：**RT 内核中，handler 可以在持有外层 BH 锁的同时，被内层的 sleeping lock 阻塞并睡眠。**

## 三、路径一：BH 锁饥饿导致 socket close 阻塞

### 3.1 AF_UNIX `close()` 的内核路径

```
close()
  → __fput_sync()
    → sock_close()
      → __sock_release()
        → unix_release()
          → unix_release_sock()                        // net/unix/af_unix.c
            → sock_orphan(sk)                          // inline, include/net/sock.h
              → write_lock_bh(&sk->sk_callback_lock)   // include/linux/rwlock_rt.h (RT 路径)
                → local_bh_disable()                   ← 获取 per-CPU BH 锁
                → rt_write_lock(rwlock)
```

`unix_release_sock()` 本身不直接调用 `local_bh_disable()`。BH 锁的获取来自其内部调用的 `sock_orphan()`——这是一个内联函数，通过 `write_lock_bh()` 间接获取 BH 锁。在 ftrace 栈中，由于 `sock_orphan()` 被内联，栈帧显示为 `__local_bh_disable_ip ← unix_release_sock`。

在非 RT 内核中，`write_lock_bh()` 内部的 `local_bh_disable()` 只是递增计数器（`rwlock_api_smp.h:__raw_write_lock_bh`），`close()` 瞬间完成。在 RT 内核中（`rwlock_rt.h:write_lock_bh`），`local_bh_disable()` 变为获取 per-CPU sleeping lock，如果 BH 锁已被其他线程持有（例如一个正在处理 I/O 完成回调的 IRQ 线程），`close()` 会**睡眠等待**直到锁被释放。

### 3.2 嵌套锁的放大效应

单看 BH 锁竞争本身，阻塞时间应该很短（handler 处理完一批 I/O 完成回调就会释放）。问题的核心在于 **RT 下嵌套 sleeping lock 导致的放大效应**。

以存储 I/O 完成回调为例。IRQ handler 的调用链为：

```
irq_forced_thread_fn()
  → local_bh_disable()                         ← 获取外层 BH 锁
  → handler: ufshcd_compl_one_cqe()
    → scsi_done() → bio_endio()
      → folio_end_writeback()
        → __folio_end_writeback()
          → xa_lock(&mapping->i_pages)          ← 内层锁：address_space 的 xarray lock
```

`__folio_end_writeback()` 需要获取 `mapping->i_pages` 的 xarray lock（`xa_lock`）来清除 folio 的 writeback tag。在非 RT 内核中这是一个普通 spinlock，自旋获取，持有时间极短。在 RT 内核中，`xa_lock` 被转换为 `rt_spin_lock`（sleeping mutex）。

此时，如果有另一个线程（例如正在执行 `fsync()` → `write_cache_pages()` 的写入进程）也在操作同一个 `mapping->i_pages` 并持有 xa_lock，IRQ handler 会**睡眠等待**：

```
CPU A（写入进程，提交写回）:         CPU B（IRQ 线程，I/O 完成）:
write_cache_pages()                 irq_forced_thread_fn()
  → 获取 xa_lock                     → local_bh_disable()  [获取 BH 锁]
  → 遍历并设置 folio writeback tag     → handler()
  → 持有 xa_lock ...                    → __folio_end_writeback()
                                          → 尝试获取 xa_lock
                                          → ⚠️ 阻塞！但 BH 锁仍被持有
```

等待链：

```
用户线程 close(AF_UNIX)
  → unix_release_sock() → sock_orphan() → write_lock_bh() → local_bh_disable()
  → 等待 IRQ 线程释放 BH 锁

IRQ 线程
  → 已持有 BH 锁
  → 被内层 xa_lock 阻塞（xa_lock 被写入进程持有）
  → BH 锁长时间不释放

写入进程
  → 持有 xa_lock，正在遍历 address_space 设置 writeback tag
```

**三层嵌套**：用户线程等 BH 锁 → IRQ 线程持有 BH 锁但等 xa_lock → 写入进程持有 xa_lock。在非 RT 内核中，IRQ handler 在 `local_irq_disable()` 下原子执行，xa_lock 是普通 spinlock 且自旋时间极短，这种嵌套不会产生有意义的阻塞。**RT 内核将两层锁都变成了 sleeping lock，使得微秒级的竞争被放大为秒级的阻塞。**

### 3.3 优先级反转加剧饥饿

IRQ 线程通常具有较高的调度优先级（例如 49，属于 SCHED_FIFO）。当它短暂释放 BH 锁后（一次 handler 迭代结束），如果还有 pending 的中断需要处理，它会立即开始新的迭代并重新获取 BH 锁：

```
irq_forced_thread_fn() {
    local_bh_disable();      // 获取 BH 锁
    handler();               // 处理一批 CQE
    local_bh_enable();       // 释放 BH 锁
}
// 如果还有 pending IRQ，立即进入下一次迭代
irq_forced_thread_fn() {
    local_bh_disable();      // 因优先级高，在等待者被调度前就重新获取了
    ...
}
```

由于 IRQ 线程优先级高于等待者（用户态线程通常是 SCHED_NORMAL，优先级 120），等待者在 IRQ 线程的两次迭代间隙根本来不及获取锁。如果 I/O 密集期间有大量 pending CQE，IRQ 线程会反复获取-释放 BH 锁，造成**低优先级线程的长期饥饿**。

实际观察到的典型时间线：

| 事件 | 时间 |
|---|---|
| IRQ 线程第一次获取 BH 锁 | T+0s |
| 第一次释放（持有约 220ms） | T+0.22s |
| 立即重新获取 | T+0.22s |
| 第二次释放（持有约 4.8s） | T+5.03s |
| 等待者开始逐个获取 | T+5.03s |

**总饥饿时间约 5 秒**。在此期间，所有需要 `local_bh_disable()` 的线程全部阻塞。

### 3.4 多线程同时阻塞

如果系统中有多个线程采用"每次新建并关闭 socket"的心跳模式，并且这些线程碰巧在同一个被拖住的 CPU 上执行 `close()`，它们会同时阻塞在同一把 BH 锁上。

更一般地，任何经过 `sock_orphan()` → `write_lock_bh()` 的路径在 RT 下都会竞争 per-CPU BH 锁，不限于 AF_UNIX datagram socket 的 `close()`。

BH 锁释放后，等待者按 `rt_mutex` 的优先级队列顺序依次获取：

1. 内核线程（rcuc、softirq 线程，优先级 98）先获取
2. 用户线程（优先级 120）按 FIFO 顺序依次获取
3. softirq 线程获取后需要处理积压的定时器软中断，持有时间较长（约 1-2ms）
4. 其他等待者各自仅持有几微秒（完成 `sock_orphan()` 的 `write_lock_bh` / `write_unlock_bh` 临界区即释放）

### 3.5 故障时序

```
    心跳线程                  BH 锁               IRQ 线程              watchdog 管理端
       │                       │                     │                       │
       │  socket() + sendto()  │                     │                       │
       │  ──────────────────>  │                     │                       │
       │  最后一个心跳成功送达  │                     │                       │
       │                       │                     │                       │
       │                       │  ◄── 获取 BH 锁     │                       │
       │                       │      处理 I/O 回调   │                       │
       │                       │      被内层锁阻塞    │                       │
       │                       │      但 BH 锁仍持有  │                       │
       │  close()              │                     │                       │
       │  → unix_release_sock  │                     │                       │
       │  → sock_orphan        │                     │                       │
       │  → write_lock_bh      │                     │                       │
       │  → local_bh_disable   │                     │                       │
       │  ──── 阻塞等待 ────>  │                     │                       │
       │                       │                     │                       │
       │  （心跳线程卡住）      │                     │      周期检查：         │
       │                       │                     │      连续 N 秒未收到心跳│
       │                       │                     │      判定 timeout       │
       │                       │                     │                       │
       │                       │  释放 BH 锁 ──────> │                       │
       │  ◄── 获取 BH 锁       │                     │                       │
       │  close() 完成         │                     │                       │
       │  恢复心跳发送         │                     │                       │
```

watchdog timeout 是正确的：管理端在超时窗口内确实没有收到新的心跳。它不是误判，而是对"心跳链路被冻住"的正确反应。

## 四、路径二：BH 锁饥饿导致 soft hrtimer 延迟

### 4.1 PREEMPT_RT 的 hrtimer 分类机制

PREEMPT_RT 内核将 hrtimer 分为 hard 和 soft 两类（`kernel/time/hrtimer.c:2016-2046`）：

```c
static void __hrtimer_init_sleeper(struct hrtimer_sleeper *sl,
                                   clockid_t clock_id, enum hrtimer_mode mode)
{
    if (IS_ENABLED(CONFIG_PREEMPT_RT)) {
        if (task_is_realtime(current) && !(mode & HRTIMER_MODE_SOFT))
            mode |= HRTIMER_MODE_HARD;     // RT 调度类 → hard hrtimer
    }
    // SCHED_NORMAL → 默认 soft hrtimer
}
```

| 任务调度类 | hrtimer 类型 | 处理上下文 | 精度 |
|---|---|---|---|
| `SCHED_FIFO` / `SCHED_RR` | hard hrtimer | 硬中断上下文 | 微秒级，不受 CPU 负载影响 |
| `SCHED_NORMAL` | soft hrtimer | softirq 线程上下文（见下文） | softirq 线程可被 BH 锁阻塞，延迟达数秒 |

soft hrtimer 的执行线程因内核版本而异：v6.12+ 引入了专用的 `ktimers/N` 线程（入口函数 `run_timersd()`）；更早的版本由 `ksoftirqd/%u` 统一处理所有 softirq（包括 `HRTIMER_SOFTIRQ`，入口函数 `hrtimer_run_softirq()`）。部分含 RT backport 的平台内核也可能包含 `ktimers/N`。具体线程名以 ftrace 中实际观察到的为准。

### 4.2 soft hrtimer 为什么会延迟

soft hrtimer 的处理流程：

```
硬件定时器中断
  → hrtimer_interrupt()
    → 标记 HRTIMER_SOFTIRQ pending
    → raise_softirq_irqoff(HRTIMER_SOFTIRQ)
      → 唤醒 softirq 线程（ktimers/N 或 ksoftirqd/%u）
        → ksoftirqd_run_begin()                              ← 获取 per-CPU BH 锁
          → handle_softirqs()
            → hrtimer_run_softirq()
              → __hrtimer_run_queues()
                → 处理到期的 soft hrtimer
        → ksoftirqd_run_end()                                ← 释放 BH 锁
```

hard hrtimer 直接在 `hrtimer_interrupt()` 硬中断上下文中处理，精度接近硬件极限。soft hrtimer 需要等 softirq 线程被调度后才能处理——而在 PREEMPT_RT 下，softirq 线程在进入 `handle_softirqs()` 之前，需要通过 `ksoftirqd_run_begin()` → `__local_bh_disable_ip()` → `local_lock(&softirq_ctrl.lock)` 获取 per-CPU BH 锁（`softirq.c:270-273`，仅 RT 路径）。

**这意味着 soft hrtimer 延迟的根因与路径一完全相同：BH 锁饥饿。**

softirq 线程（例如 `ktimers/5`，SCHED_FIFO 优先级 98）在尝试获取 BH 锁时，如果锁被 IRQ handler 持有，会直接进入 **D 状态**（不可中断睡眠）——这不是调度优先级不够的问题，而是被锁直接阻塞。

复现测试中观察到的典型时间线：

```
3984.815890  ktimers/5 进入 D 状态（尝试获取 BH 锁，被 UFS IRQ handler 持有）
             ... 420ms 完全阻塞 ...
3985.235613  ktimers/5 短暂恢复，但再次进入 D 状态
             ... 1011ms 完全阻塞 ...
3986.245715  ktimers/5 恢复正常，处理积压的 soft hrtimer
3986.245721  updatemgr(5561) 终于被唤醒（500ms 定时器实际延迟了 1803ms）
```

同一时间段，UFS IRQ handler（`irq/302-qcom-mc`，prio 49）也在同一 CPU 上反复进入 D 状态——它持有 BH 锁但被内层 folio writeback 锁阻塞，每次只运行约 10-15μs 就再次 D 状态。**它和 softirq 线程被同一套嵌套锁链阻塞**：

```
UFS IRQ handler
  → irq_forced_thread_fn() 持有 BH 锁
  → writeback 路径等待 folio 锁 → D 状态（BH 锁不释放）

softirq 线程（ktimers/N）
  → 需要 local_bh_disable() 获取 BH 锁
  → BH 锁被 IRQ handler 持有 → D 状态（无法处理 soft hrtimer）
```

这与第三节路径一的等待链结构完全一致——只是受害者从用户线程的 `close()` 换成了内核的 softirq 线程。

### 4.3 受影响的系统调用

所有带超时的阻塞系统调用在 PREEMPT_RT 下对 SCHED_NORMAL 线程都使用 soft hrtimer，最终都经过 `__hrtimer_init_sleeper()`：

| 系统调用 | 超时路径 |
|---|---|
| `pthread_cond_timedwait` | `futex_wait` → `futex_setup_timer` → `__hrtimer_init_sleeper()` |
| `select` | `do_select` → `poll_schedule_timeout` → `schedule_hrtimeout_range` → `__hrtimer_init_sleeper()` |
| `poll` | `do_poll` → `poll_schedule_timeout` → `schedule_hrtimeout_range` → `__hrtimer_init_sleeper()` |
| `epoll_wait` | `ep_poll` → `schedule_hrtimeout_range` → `__hrtimer_init_sleeper()` |
| `nanosleep` | `hrtimer_nanosleep` → `__hrtimer_init_sleeper()` |
| `clock_nanosleep` | `hrtimer_nanosleep` → `__hrtimer_init_sleeper()` |

**在 PREEMPT_RT 内核 + I/O 密集的系统上，所有 SCHED_NORMAL 线程的超时精度都无法保证。**

### 4.4 与路径一的关系

两条路径**共享同一个根因：per-CPU BH 锁饥饿**。区别仅在于受害者不同：

| | 路径一 | 路径二 |
|---|---|---|
| 受害者 | 用户线程的 `close()` → `write_lock_bh()` | 内核 softirq 线程（`ktimers/N` 或 `ksoftirqd`） |
| 阻塞点 | `sock_orphan()` → `write_lock_bh()` → `local_bh_disable()` | `hrtimer_run_softirq()` 入口的 `local_bh_disable()` |
| 表现 | 心跳发送线程卡在 `close()` 上 | SCHED_NORMAL 线程的定时器超时不准 |
| 共同根因 | IRQ handler 在 `irq_forced_thread_fn()` 中持有 BH 锁，被内层 folio/writeback 锁阻塞 |

一个系统可能同时经历两条路径：部分线程卡在 `close()` 上，部分线程因 soft hrtimer 延迟而超时。最终都表现为 watchdog timeout。

## 五、工程规避与内核修复方案

### 5.1 应用层规避

#### 5.1.1 复用 heartbeat socket（P0，改动最小，见效最快）

将心跳路径从"每次新建并关闭"改为"初始化时创建，复用 socket"：

```c
// 修改前：每次 close 都可能竞争 BH 锁
void heartbeat_once(void)
{
    int fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    sendto(fd, &msg, sizeof(msg), 0, ...);
    close(fd);   // ← 每次都走 unix_release_sock() → sock_orphan() → write_lock_bh() → local_bh_disable()
}

// 修改后：复用 socket
static int g_heartbeat_fd = -1;

void heartbeat_once(void)
{
    if (g_heartbeat_fd < 0)
        g_heartbeat_fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    sendto(g_heartbeat_fd, &msg, sizeof(msg), 0, ...);
    // 不 close，进程退出时自动释放
}
```

复用 socket 后，心跳路径不再经过 `sock_orphan()` → `write_lock_bh()` 链路，绕开了本文讨论的 BH 锁竞争。即使 I/O 风暴仍在发生，`sendto()` 不会因 per-CPU BH 锁而阻塞。

#### 5.1.2 提升关键线程为 RT 调度类（P0，消除 soft hrtimer 延迟）

将依赖超时机制的关键线程设为 `SCHED_FIFO`：

```c
struct sched_param param;
param.sched_priority = 1;  // 最低 RT 优先级即可
pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
```

RT 调度类线程的 futex/select/poll 超时使用 hard hrtimer（硬中断上下文处理），不受 softirq 线程调度延迟影响。

#### 5.1.3 降低 I/O 风暴强度（P1）

如果系统存在大块数据写入（例如 OTA 刷写、日志压缩），减小单次 `fsync()` 前累积的脏页数量可以缩短 IRQ handler 单次 BH 锁持有时间。具体来说：

- 减小写入批次大小（如 OTA 分段大小）
- 消除无意义的 I/O（如块设备写入前的预填零）
- 评估 Direct I/O 替代方案（绕过 page cache，消除 folio writeback 锁争用）

### 5.2 系统层配置

#### 5.2.1 IRQ 亲和性隔离（P2）

将存储 IRQ 线程绑定到非关键 CPU，避免 BH 锁饥饿影响关键线程：

```bash
# 将 UFS IRQ 绑定到 CPU 6-7
echo c0 > /proc/irq/<irq_num>/smp_affinity

# 同时将关键线程绑定到其他 CPU
taskset -p 0x3f <pid>  # CPU 0-5
```

局限性：需要同时管理 IRQ 线程和关键线程的 CPU 亲和性，否则调度器可能将它们迁移到同一 CPU。

### 5.3 内核层修复

#### 5.3.1 方案 A：将存储 IRQ 改为原生线程化（推荐，改动最小）

将 IRQ handler 从 `devm_request_irq()`（在 RT 下被 forced-threaded，走 `irq_forced_thread_fn`）改为 `devm_request_threaded_irq()`（原生线程化，走 `irq_thread_fn`，**无 BH 锁包裹**）：

```diff
- ret = devm_request_irq(dev, desc->irq,
-                        handler_fn,
-                        IRQF_SHARED, "name", desc);
+ ret = devm_request_threaded_irq(dev, desc->irq,
+                                 NULL,
+                                 handler_fn,
+                                 IRQF_SHARED | IRQF_ONESHOT,
+                                 "name", desc);
```

原理：`request_threaded_irq(irq, NULL, thread_fn, ...)` 注册时，handler 被设为 `irq_default_primary_handler`。`irq_setup_forced_threading()`（`kernel/irq/manage.c:1370-1407`）对已经是原生线程化的 IRQ 直接 return，不设置 `IRQTF_FORCED_THREAD`，运行时走 `irq_thread_fn`（无 `local_bh_disable()` 包裹）。

社区先例：hisi_sas 驱动已用相同方式将 SCSI HBA 的 CQ 中断改为原生线程化（[已合入 Linux 主线](https://lore.kernel.org/lkml/1579522957-4393-2-git-send-email-john.garry@huawei.com/)）。

风险点：需要审计 handler 的 I/O 完成链中是否有代码依赖 `in_softirq()` 判断来选择不同路径。

#### 5.3.2 方案 B：CQE 处理循环增加批量限制

现代存储控制器（UFS MCQ、NVMe 等）使用硬件完成队列（Completion Queue）：设备完成 I/O 后将结果写入 CQ，每条记录称为一个 CQE（Completion Queue Entry）。IRQ handler 的工作就是遍历 CQ、逐条处理 CQE。

如果 handler 在一个 `while` 循环中一次性处理所有 pending CQE，可以增加批量限制，让 `irq_forced_thread_fn` 有机会释放并重新获取 BH 锁：

```c
#define CQE_BATCH_LIMIT  8

while (!is_cq_empty(hwq)) {
    process_cqe(hba, hwq);
    completed++;
    if (completed >= CQE_BATCH_LIMIT)
        break;  // 先返回，剩余 CQE 在下一次 handler 迭代中处理
}
```

局限性：需要确保未处理的 CQE 能重新触发硬件中断。

#### 5.3.3 方案 C：RT 下跳过 `irq_forced_thread_fn` 的 BH 锁

社区 RFC Patch（[Vladimir Kondratiev @ Mobileye, 2024-04-15](https://lore.kernel.org/linux-kernel/20240415112800.314649-1-vladimir.kondratiev@mobileye.com/T/)）提出在 RT 下完全跳过 `irq_forced_thread_fn` 中的 `local_bh_disable()/enable()`。

该 patch 描述的问题与本文完全一致。但 review 中有两个顾虑：(1) 去掉 `local_bh_disable` 后 handler 中 raise 的 softirq 不会在 `local_bh_enable()` 中立即执行；(2) `in_interrupt()` / `in_softirq()` 在 handler 内不再返回 true。**该 patch 未被合入。**

### 5.4 社区长期方向：nested-BH locking

当前问题的根本矛盾是 `local_bh_disable()` 在 RT 下充当 **per-CPU 大锁（BKL）**：任何需要 BH 禁止的代码路径都竞争同一把锁，导致不相关的子系统（存储 I/O 完成 vs. AF_UNIX socket 关闭）互相阻塞。

Sebastian Siewior（Linutronix）提出的 nested-BH locking 系列 patch 引入 `local_lock_nested_bh()` / `local_unlock_nested_bh()`，将保护粒度从"整个 CPU 的 BH"细化到"具体的 per-CPU 数据结构"：

- 非 RT 内核：编译优化掉，零开销
- RT 内核：获取**专属的 per-CPU lock**，而非共享的 BH 大锁

基础设施已于 **v6.10 合入主线**（[commit `c5bcab755822`](https://git.zx2c4.com/wireguard-linux/commit/include/linux/local_lock_internal.h?id=c5bcab7558220bbad8bd4863576afd1b340ce29f)）。网络子系统（NAPI、TCP、bridge）的转换已跟进合入。**存储/块设备子系统的转换仍在进行中。**

相关资料：
- Patch 系列：[[PATCH net-next 00/24] locking: Introduce nested-BH locking](https://lore.kernel.org/netdev/20231215171020.687342-25-bigeasy@linutronix.de/T/)
- LWN 分析：[Nested bottom-half locking for realtime kernels](https://lwn.net/Articles/978189/)

### 5.5 方案对比

| | 方案 A：原生线程化 | 方案 B：CQE 批量限制 | 方案 C：RT 跳过 BH 锁 | nested-BH（社区方向） |
|---|---|---|---|---|
| 修改范围 | 驱动 1 处 | 驱动约 10 行 | `manage.c` 约 6 行 | 全子系统逐步转换 |
| 彻底程度 | 彻底 | 部分 | 彻底 | 彻底 |
| 社区先例 | hisi_sas（已合入） | 无 | RFC（未合入） | 基础设施已合入 v6.10+ |
| 风险 | 需审计完成链 BH 上下文依赖 | 需确认硬件重触发 | 影响所有 forced-threaded IRQ | 需等待存储子系统转换 |
| 推荐场景 | **首选** | 方案 A 不可行时的保守选择 | 全局解决 | 跟踪上游进展 |


## 附录：hardirq、softirq、ksoftirqd 与 forced-threaded IRQ handler 对比

这四个概念容易混淆，但它们并不是同一层次的东西。

| 概念 | 本质是什么 | 典型执行身份 | 能否睡眠 | 与本文的关系 |
|---|---|---|---|---|
| `hardirq` 上下文 | 真正的硬件中断处理上下文 | 不是普通线程；CPU 响应硬中断时直接进入 | 不能 | hard hrtimer 直接在这里处理；非 RT 内核中的很多 IRQ 处理也更接近这种语义 |
| `softirq` 上下文 | 中断下半部机制，用来延后处理较重工作 | 逻辑上仍是 softirq，不等同于某个固定线程 | 不能主动睡眠 | `HRTIMER_SOFTIRQ` 属于这一类；soft hrtimer 到期后最终要在这里被处理 |
| `ksoftirqd/%u` | 每 CPU 一个内核线程，用来在进程上下文中代跑 pending softirq | 普通内核线程 | 可以被调度、可被抢占；进入 softirq 处理区后受具体锁语义约束 | 在当前这套 kernel 中，soft hrtimer 的延迟处理通常会落到这里执行 |
| forced-threaded IRQ handler | PREEMPT_RT 下由 `irq_forced_thread_fn()` 驱动的 IRQ 线程化执行方式 | 对应 IRQ 的内核线程 | 可以被调度；在 RT 内核中可能在持有外层 BH 锁时被内层 sleeping lock 阻塞 | 本文两条失效路径的共同触发源：它既可能直接持有 per-CPU BH 锁，也可能间接拖慢 softirq 处理 |

可以用一句话快速区分：

- `hardirq`：中断来了，CPU 立刻处理
- `softirq`：把一部分工作延后到下半部机制里处理
- `ksoftirqd`：softirq 处理不过来或需要在线程上下文执行时，由它代跑
- forced-threaded IRQ handler：PREEMPT_RT 把很多原本更接近 hardirq 语义的 IRQ 处理，改成由 IRQ 内核线程执行

在本文语境下，最关键的区别是：

1. `hardirq` / hard hrtimer 处理路径更短，延迟更小
2. soft hrtimer 依赖 softirq 执行路径，因此可能受到 `ksoftirqd` 调度和 per-CPU BH 锁竞争影响
3. forced-threaded IRQ handler 在 PREEMPT_RT 下会改变原本 IRQ 处理的锁语义，从而成为 BH 锁饥饿和 softirq 延迟的共同上游因素
