+++
date = '2026-03-15T22:30:00+08:00'
draft = false
title = 'Linux trace-cmd 原理与分析技巧'
+++

## 1. 为什么要学 trace-cmd

`trace-cmd` 是 Linux 内核 `ftrace` 能力的一层用户态封装。它最适合回答这类问题：

- 某个线程为什么长时间没有运行
- 某个进程为什么进入 `D` 状态
- 某段时间 CPU 在跑谁
- 哪个锁、哪个等待链把系统拖慢了
- 某次 watchdog timeout 前后，系统到底发生了什么

如果说日志更像“应用自己说了什么”，那么 `trace-cmd` 更像“内核真实记录了什么”。

---

## 2. trace-cmd 的基本原理

### 2.1 本质上它是 ftrace 的采集器

Linux 内核里有一套 `ftrace`/tracepoint 机制。内核在调度、锁、中断、块设备、文件系统、电源等关键路径上埋了很多事件点，例如：

- `sched:sched_switch`
- `sched:sched_wakeup`
- `irq:*`
- `block:*`
- `syscalls:*`
- `workqueue:*`

`trace-cmd record` 的工作就是：

1. 打开内核 trace buffer
2. 选择要采集的 tracepoint
3. 持续把事件写入 trace buffer
4. 结束后把数据导出成 `trace.dat`

随后再用：

- `trace-cmd report`
- `trace-cmd extract`
- `kernelshark`

去消费这些数据。

### 2.2 它记录的不是“进程快照”，而是“事件流”

这点很重要。

`trace-cmd` 不是在某个时间点拍一张系统照片，而是记录“什么时候发生了什么事件”。因此分析时要建立时间线，而不是只盯某一条日志。

例如：

- `1719.423841`：`sched_waking`
- `1719.423845`：`sched_wakeup`
- `1719.423852`：`sched_switch` 进入 `D`
- `1724.132573`：被唤醒

把这些连起来，才能知道一个线程是“被调度慢”还是“卡在不可中断睡眠里”。

---

## 3. 需要先掌握的操作系统基础

### 3.1 CPU 视角：线程只有两种真实状态

从 CPU 角度看，一个线程只有两种核心状态：

- 正在 CPU 上执行
- 没在 CPU 上执行

但“没在 CPU 上执行”还要继续细分，因为原因完全不同。

### 3.2 常见进程/线程状态

在调度分析里最常见的是这些状态：

- `R`：Running/Runnable，可运行，可能正在跑，也可能在 runqueue 里等 CPU
- `S`：Interruptible sleep，可中断睡眠，通常在等事件、poll、epoll、定时器、消息
- `D`：Uninterruptible sleep，不可中断睡眠，通常在等内核资源，例如 IO、锁、页、块设备、文件系统、某些驱动路径
- `T`：Stopped，被暂停
- `Z`：Zombie，僵尸进程

其中最关键的是：

- `S` 不一定有问题，很多线程本来就应该大部分时间睡着
- `D` 往往值得高度关注，尤其是持续时间达到毫秒级、秒级时

### 3.3 `sched_switch` 里状态是什么意思

典型事件：

```text
watchdog-7304 [017] 1719.423852: sched_switch: watchdog:7304 [49] D ==> swapper/17:0 [120]
```

含义是：

- 当前切出的线程是 `watchdog:7304`
- 它切出时状态是 `D`
- 下一个上 CPU 的线程是 `swapper/17`

这个事件本身通常非常关键，因为它告诉你：

- 是谁下了 CPU
- 下 CPU 时是什么状态
- CPU 被谁接管了

### 3.4 锁状态要怎么理解

性能分析里常见几类锁：

- 自旋锁 `spinlock`
- RT 化后的 `rt_spin_lock`
- 互斥锁 `mutex`
- 读写锁 `rwsem`
- 等待队列、完成量、条件变量

尤其在 `PREEMPT_RT` 内核中，要小心一个误区：

- 很多传统上“忙等”的锁，在 RT 化后会变成可睡眠等待
- 所以线程可能不是“在 CPU 上空转”，而是直接进 `D` 或睡眠等待

这也是为什么你会在内核栈里看到：

- `schedule_rtlock`
- `rtlock_slowlock_locked`
- `rt_spin_lock`

一旦看到这类栈，往往说明问题已经进入“锁等待链”而不是普通调度抖动。

### 3.5 中断、软中断、kthread、用户线程的区别

trace 里经常会看到：

- 普通用户线程：如 `system_server`、`watchdog`、`Binder:xxx`
- 内核线程：如 `kworker/*`、`ksoftirqd/*`、`rcuc/*`
- IRQ 线程：如 `irq/314-qcom-mc`
- idle 线程：`swapper/N`

分析时要先分清对象类型，因为它们的行为模型完全不同。

---

## 4. 最重要的几个 tracepoint

### 4.1 调度类

必学：

- `sched:sched_switch`
- `sched:sched_wakeup`
- `sched:sched_waking`

用途：

- 看线程什么时候被唤醒
- 看线程什么时候真正上 CPU
- 看线程何时被切走、切走时是什么状态

### 4.2 块设备和文件系统

常用：

- `block:block_rq_issue`
- `block:block_rq_complete`
- `writeback:*`
- `filemap:*`

用途：

- 看 IO 是否堆积
- 看写回是否拖慢系统
- 看某个进程是不是在持续刷盘

### 4.3 中断相关

常用：

- `irq:*`
- `softirq:*`

用途：

- 看某段时间 IRQ 是否过密
- 看某个 IRQ 线程是否异常繁忙或阻塞

### 4.4 syscall 与内核栈

常用：

- `syscalls:sys_enter_*`
- `syscalls:sys_exit_*`
- `kernel_stack`

用途：

- 把“线程在干什么”落到具体系统调用和内核路径上
- 尤其适合定位 `D` 状态到底卡在什么路径

---

## 5. 最基础的分析思路

### 5.1 先定时间窗，再看对象

不要一上来全局扫大文件。

正确顺序通常是：

1. 找到异常发生时间，例如 watchdog timeout 的时刻
2. 取前后一个小窗口，例如 `-2s ~ +2s`
3. 只关注相关线程、相关 CPU、相关事件
4. 逐步扩展，不要一口气看全量 trace

### 5.2 先看状态变化，再看调用栈

推荐顺序：

1. `sched_waking`
2. `sched_wakeup`
3. `sched_switch`
4. `kernel_stack`

因为：

- 先搞清楚“什么时候醒、什么时候跑、什么时候睡”
- 再去看“睡死在哪个栈”

这样不容易迷失在大段内核栈里。

### 5.3 先分清三种问题

分析调度类问题时，通常要先判断属于哪一类：

1. 线程根本没被唤醒
2. 线程被唤醒了，但很久才拿到 CPU
3. 线程拿到 CPU 后很快进了 `D`，卡在内核路径里

这三类问题对应的根因方向完全不同。

---

## 6. 常见分析套路

### 6.1 分析“某线程为什么超时”

步骤：

1. 先用日志确定 timeout 时间点
2. 找到该线程最后一次正常运行的时间
3. 看它最后一次 `sched_switch` 出去时的状态
4. 如果是 `D`，立刻接 `kernel_stack`
5. 看恢复时刻是谁唤醒了它

### 6.2 分析“某 CPU 当时在忙什么”

步骤：

1. 只过滤目标 CPU
2. 重点看 `sched_switch`
3. 统计该窗口里这个 CPU 主要跑了哪些线程
4. 看有没有异常高频的 IRQ/kworker/ksoftirqd

### 6.3 分析“多个进程一起出问题”

步骤：

1. 不要先猜是应用共因
2. 先找它们共同落到的内核路径
3. 如果都卡在同类锁/IO/文件系统路径，优先考虑内核共因

---

## 7. 常用命令

### 7.1 采集

```bash
trace-cmd record \
  -e sched:sched_switch \
  -e sched:sched_wakeup \
  -e sched:sched_waking \
  -e irq \
  -e block \
  -T
```

说明：

- `-e`：选择事件
- `-T`：记录内核栈

### 7.2 查看摘要

```bash
trace-cmd report trace.dat | less
```

### 7.3 只看某个关键词

```bash
trace-cmd report trace.dat | rg 'watchdog|pmonitor|qcom-mc'
```

### 7.4 导出成文本后再做脚本分析

```bash
trace-cmd report trace.dat > report.txt
```

大文件分析时要注意：

- 不要整文件一次性读入内存
- 用 `rg`、`sed`、`awk`、`tail -n +N | head -n M` 做小窗口处理

---

## 8. 基础脚本方法

下面给几个最实用的脚本例子。

### 8.1 提取某段时间内某个进程的调度事件

假设你已经有 `report.txt`，要看 `watchdog:7304` 在 `1719.0 ~ 1725.0` 内的事件：

```bash
awk '
$3 >= 1719.0 && $3 <= 1725.0 && $1 ~ /watchdog-7304/ {
    print
}
' report.txt
```

如果是标准 `trace-cmd report` 文本格式，时间戳在第 3 列，这种写法通常就够用了。

### 8.2 提取某段时间内某个 CPU 上的调度切换

```bash
awk '
$2 == "[017]" && $3 >= 1719.0 && $3 <= 1725.0 && /sched_switch/ {
    print
}
' report.txt
```

用途：

- 看 CPU17 在事故窗口里到底跑了谁

### 8.3 提取某个线程的状态变化轨迹

```bash
awk '
/watchdog-7304/ && /sched_switch|sched_wakeup|sched_waking/ {
    print
}
' report.txt
```

如果只想看状态字段：

```bash
awk '
/watchdog-7304/ && /sched_switch/ {
    print $3, $0
}
' report.txt
```

### 8.4 提取某段时间内某个线程相关的内核栈

```bash
awk '
$3 >= 1719.42 && $3 <= 1719.43 {
    print
}
' report.txt | sed -n '1,120p'
```

更常见的做法是先用 `grep -n` 找到目标时间点，再向后读固定行数：

```bash
grep -n '1719.423852' report.txt
tail -n +590413693 report.txt | head -n 40
```

### 8.5 统计某线程在窗口内运行了多少次

```bash
awk '
$3 >= 1719.0 && $3 <= 1722.0 && /pmonitor_main-4402/ && /sched_switch/ {
    cnt++
}
END {
    print cnt
}
' report.txt
```

### 8.6 统计某 CPU 在窗口内主要运行哪些线程

```bash
awk '
$2 == "[017]" && $3 >= 1719.0 && $3 <= 1725.0 && /sched_switch/ {
    split($0, a, ">>>")
    print $0
}
' report.txt
```

更实用的版本通常是先把 `==>` 后面的 next task 抽出来再计数，但不同 trace 文本格式略有差异，脚本要按你手头格式调整。

---

## 9. 分析 `D` 状态的几个关键点

当你看到线程进入 `D`：

1. 先找进入 `D` 的准确时刻
2. 看紧跟着的 `kernel_stack`
3. 看恢复时刻
4. 看恢复前后是谁唤醒了它
5. 判断它是锁等待、IO 等待，还是页/文件系统等待

经验上：

- `unix_release_sock`、`rt_spin_lock`：要想到锁竞争
- `bio_endio`、`blk_update_request`、`scsi_io_completion`：要想到块层或存储完成路径
- `__folio_end_writeback`：要想到写回完成链
- `do_unlinkat`、`down_write`：要想到文件系统目录项/写锁

---

## 10. 如何避免误判

### 10.1 不要把 wall time 当成唯一真相

某些日志里的 wall time 可能漂移、跳变、不连续。做调度分析时：

- 优先信 trace 的 event timestamp
- 如果还有 DLT ticks，优先做 ticks 与 trace time 的对齐

### 10.2 不要把“被唤醒”误判成“已经运行”

- `sched_wakeup` 只表示它具备运行资格
- 真正拿到 CPU 要看后续 `sched_switch`

### 10.3 不要把“恢复时解锁的人”误判成“最初持锁的人`

在 RT 锁链里，经常看到：

- A 被唤醒
- A 执行到 `rt_spin_unlock`
- A 唤醒 B

这只能证明 A 参与了锁链释放，不等于 A 就是最初把锁拖住几秒的人。

---

## 11. 一个实际分析模板

拿到一份 `report.txt` 后，我一般按这个顺序：

1. 找异常时间点
2. 抽前后 1~5 秒小窗口
3. 锁定相关线程
4. 看 `sched_switch/wakeup/waking`
5. 对进入 `D` 的线程补 `kernel_stack`
6. 如果多个线程同时异常，找共同内核路径
7. 再去和应用日志、DLT、watchdog 超时点对齐

这个方法的核心不是“背事件名”，而是：

- 先建立时序
- 再定位状态变化
- 最后用栈把根因钉死

---

## 12. 总结

`trace-cmd` 的价值，在于它把“系统到底怎么调度、怎么等待、怎么卡住”的事实直接摆在你面前。

真正实用的能力不是会背多少 tracepoint，而是这三件事：

1. 能按时间窗收缩问题范围
2. 能从 `sched_*` 事件判断线程处于哪种异常模式
3. 能把 `D` 状态和内核栈、IO、锁等待链连起来

当你把这些基础打牢之后，分析 watchdog timeout、系统卡顿、秒级抖动、IRQ 风暴、写回阻塞，都会快很多。


---

## 13. `trace-cmd report` 文本格式逐列解释

`trace-cmd report` 的文本格式会因为事件类型、内核版本、是否带栈而略有差异，但大体上可以按下面的方式理解。

先看一个典型例子：

```text
watchdog-7304 [017] 1719.423852: sched_switch: watchdog:7304 [49] D ==> swapper/17:0 [120]
```

可以拆成下面几列：

| 位置 | 示例 | 含义 |
|---|---|---|
| 第 1 列 | `watchdog-7304` | 当前事件归属的线程名和 PID，通常格式是 `comm-pid` |
| 第 2 列 | `[017]` | 事件发生时所在 CPU |
| 第 3 列 | `1719.423852:` | 时间戳，单位通常是秒 |
| 第 4 列 | `sched_switch:` | 事件名 |
| 后续字段 | `watchdog:7304 [49] D ==> swapper/17:0 [120]` | 事件自己的 payload |

### 13.1 `sched_switch` 的 payload 怎么看

`sched_switch` 的 payload 通常表示：

```text
prev_comm:prev_pid [prev_prio] prev_state ==> next_comm:next_pid [next_prio]
```

例如：

```text
watchdog:7304 [49] D ==> swapper/17:0 [120]
```

含义：

- 切下去的是 `watchdog:7304`
- 它切出时优先级是 `49`
- 它切出时状态是 `D`
- 接下来运行的是 `swapper/17:0`
- 对方优先级是 `120`

### 13.2 `sched_wakeup` / `sched_waking` 的 payload 怎么看

典型例子：

```text
<idle>-0 [017] 1719.423845: sched_wakeup: pmonitor:4402 [52] CPU:017
```

含义：

- 当前记录这条事件的上下文是 `<idle>-0`
- 被唤醒的目标线程是 `pmonitor:4402`
- 目标线程优先级是 `52`
- 目标 CPU 是 `017`

要注意：

- `sched_waking` 更接近“开始尝试唤醒”
- `sched_wakeup` 更接近“成功进入 runnable”
- 真正运行还要等到后续 `sched_switch`

### 13.3 `kernel_stack` 怎么看

典型例子：

```text
watchdog-7304 [017] 1719.423853: kernel_stack: <stack trace >
=> __schedule
=> schedule_rtlock
=> rtlock_slowlock_locked
=> rt_spin_lock
=> __local_bh_disable_ip
=> unix_release_sock
=> __fput
=> close_fd
=> __arm64_sys_close
```

含义：

- 这通常是“上一条事件对应时刻”的内核栈快照
- 要和它前面的 `sched_switch`、`sys_enter`、`block_*` 事件一起看
- 栈底附近更接近“这条路径从哪来的”
- 栈顶附近更接近“当前卡在什么点”

### 13.4 `block_rq_issue` / `block_rq_complete` 怎么看

例如：

```text
zstdext-7343 [010] 1579.534829: block_bio_queue: 8,0 WS 223963224 + 8 [zstdext]
irq/307-qcom-mc-402 [010] 1579.535338: block_rq_complete: 8,0 WS () 223963224 + 1024 [0]
```

常见字段：

- `8,0`：块设备主次设备号
- `WS`：IO 属性，常见含义是 `Write` / `Sync` 之类的组合标记
- `223963224 + 8`：起始扇区和长度
- `[zstdext]`：发起这个请求的进程上下文

这类事件很适合和 `qcom-mc`、`ufshcd_*`、`writeback` 栈配合起来看存储路径。

### 13.5 为什么不能把“列位置”写死

虽然很多脚本喜欢直接写 `$1 $2 $3`，但你要知道：

- 不同事件 payload 长度不同
- 线程名中可能有特殊字符
- 有些文本前面可能带缩进或额外字段

所以更稳妥的做法通常是：

- 先用 `grep -n` 或 `rg -n` 缩小范围
- 再用 `awk` 针对具体事件格式写脚本
- 不要幻想一个脚本吃遍所有 trace 文本

---

## 14. 案例：如何结合 `sched_switch + kernel_stack` 分析线程卡死

下面用一个典型案例说明分析过程。

### 14.1 现象

假设日志告诉你：

- `watchdog` 线程超时
- 超时前几秒系统没有明显 ANR
- 但服务没有再向监控进程发送 heartbeat

这时最关键的问题是：

- 线程没被唤醒？
- 被唤醒但抢不到 CPU？
- 还是拿到 CPU 后马上卡进了内核？

### 14.2 第一步：先找 `sched_switch`

先定位该线程最后一次切出：

```text
watchdog-7304 [017] 1719.423852: sched_switch: watchdog:7304 [49] D ==> swapper/17:0 [120]
```

这一条已经能告诉你两件事：

1. 它确实运行到了 `1719.423852`
2. 它不是普通睡眠，而是带着 `D` 状态切出

到这里，方向就已经从“调度慢”切到“内核不可中断等待”。

### 14.3 第二步：立刻接 `kernel_stack`

继续看它后面的内核栈：

```text
=> __schedule
=> schedule_rtlock
=> rtlock_slowlock_locked
=> rt_spin_lock
=> __local_bh_disable_ip
=> unix_release_sock
=> __fput
=> close_fd
=> __arm64_sys_close
```

这说明：

- 线程不是卡在用户态逻辑
- 它是在 `close()` 系统调用里卡住了
- 更具体地说，是卡在 `unix_release_sock -> __local_bh_disable_ip -> rt_spin_lock`
- 也就是说，问题核心已经变成一条 RT 锁等待链

### 14.4 第三步：判断它是不是“单点问题”

这时不要急着说“就是 watchdog 自己的问题”，而要继续查：

- 同时间窗里别的 watchdog 线程是否也进了 `D`
- `clusterservice`、`mcd`、`audiomgr` 是否落到了同类栈

如果你发现多个线程都在相近时间落到：

- `rt_spin_lock`
- `unix_release_sock`
- `__folio_end_writeback`
- `scsi_io_completion`

那就要警惕这是**系统共因**，不是单线程 bug。

### 14.5 第四步：看恢复时刻

接着看线程什么时候恢复：

- 它是被谁唤醒的
- 唤醒后有没有立刻继续执行
- 恢复栈是不是 `rt_spin_unlock`

如果恢复时看到的是：

```text
=> wake_up_state
=> rt_mutex_slowunlock
=> rt_spin_unlock
=> __local_bh_enable_ip
```

那通常说明：

- 它此时处在锁链释放阶段
- 它可能是“被唤醒后继续执行到解锁”的 waiter
- 但它不一定是最初把锁拖住很久的 owner

### 14.6 第五步：把上层现象和下层根因连起来

到这里，一条完整链路就建立起来了：

1. 应用线程执行 `close()`
2. 在内核里卡进 `rt_spin_lock`
3. 长时间无法继续执行
4. 上层 heartbeat 无法继续发送
5. 监控进程长时间收不到 heartbeat
6. watchdog timeout

如果再往下追到：

- `__folio_end_writeback`
- `bio_endio`
- `scsi_io_completion`
- `ufshcd_compl_one_cqe`

那就进一步说明，这条锁等待链和写回/块设备/UFS completion 路径发生了耦合。

### 14.7 一个实用结论

`trace-cmd` 真正厉害的地方不是“看到某线程进了 `D`”，而是能用下面这个最小闭环把问题定性：

- `sched_switch`：确认线程何时进入异常状态
- `kernel_stack`：确认卡在哪条内核路径
- 恢复事件：确认何时、如何恢复
- 同窗口其他线程：判断是否为系统共因

这四步走完，很多“看起来像应用卡住”的问题，都会被还原成锁等待、写回阻塞、IRQ 完成链拥塞，或者调度链放大问题。

---

## 15. 后续建议

如果你已经能熟练用这些基础方法，下一步建议继续补这几类能力：

1. 学会按 CPU 维度做时间窗统计
2. 学会把 trace 时间和业务日志/DLT ticks 对齐
3. 学会区分“释放锁的人”和“最初拖住链路的人”
4. 学会从 `block`、`writeback`、`sched` 三类事件建立统一时间线

这几项能力一旦建立起来，trace 分析效率会明显提高。


---

## 16. 通用 `awk` / `rg` 命令模板

下面这些模板不追求“一条命令解决所有问题”，而是追求：

- 先快速缩小范围
- 再围绕具体问题改一两处参数即可复用

约定：

- 输入文件是 `report.txt`
- 时间戳在第 3 列附近，格式如 `1719.423852:`
- 如果你的文本格式不同，需要按实际格式微调

### 16.1 用 `rg` 快速缩小范围

#### 只看某个线程

```bash
rg 'watchdog-7304|watchdog:7304' report.txt
```

#### 只看某类事件

```bash
rg 'sched_switch|sched_wakeup|sched_waking|kernel_stack' report.txt
```

#### 同时看线程和事件

```bash
rg 'watchdog-7304|watchdog:7304|sched_switch|sched_wakeup|sched_waking|kernel_stack' report.txt
```

#### 看多个可疑对象

```bash
rg 'watchdog|clusterservice|pmonitor|qcom-mc|ufshcd|writeback' report.txt
```

#### 找精确时间点附近的原始位置

```bash
rg -n '1719\.423852' report.txt
```

找到行号后，再读固定窗口：

```bash
tail -n +590413693 report.txt | head -n 40
```

这是处理超大文本时最稳的方法之一。

### 16.2 时间窗过滤模板

#### 抽某段时间内的全部事件

```bash
awk '
{
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.0 && t <= 1725.0) print
}
' report.txt
```

#### 抽某段时间内某个线程的事件

```bash
awk '
{
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.0 && t <= 1725.0 && $0 ~ /watchdog-7304|watchdog:7304/) print
}
' report.txt
```

#### 抽某段时间内某个 CPU 的事件

```bash
awk '
{
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.0 && t <= 1725.0 && $2 == "[017]") print
}
' report.txt
```

### 16.3 调度相关模板

#### 提取某线程的调度轨迹

```bash
awk '
/watchdog-7304|watchdog:7304/ && /sched_switch|sched_wakeup|sched_waking/ {
    print
}
' report.txt
```

#### 只看进入 `D` 的 `sched_switch`

```bash
awk '
/sched_switch/ && / D ==> / {
    print
}
' report.txt
```

#### 只看某线程进入 `D` 的时刻

```bash
awk '
/watchdog-7304|watchdog:7304/ && /sched_switch/ && / D ==> / {
    print
}
' report.txt
```

#### 只看某 CPU 上的 `sched_switch`

```bash
awk '
$2 == "[017]" && /sched_switch/ {
    print
}
' report.txt
```

#### 统计某线程在窗口内被调度了多少次

```bash
awk '
{
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.0 && t <= 1722.0 && /pmonitor_main-4402/ && /sched_switch/) cnt++
}
END {
    print cnt
}
' report.txt
```

### 16.4 内核栈相关模板

#### 提取某线程相关的 `kernel_stack`

```bash
awk '
/watchdog-7304|watchdog:7304/ || /kernel_stack|=>/ {
    print
}
' report.txt
```

这个模板太宽时，可以先用 `grep -n` 找起点，再局部读取。

#### 找某个关键函数栈

```bash
rg '__folio_end_writeback|unix_release_sock|rt_spin_lock|ufshcd_compl_one_cqe' report.txt
```

#### 找某个时间点后面的 30 行栈

```bash
grep -n '1719.423852' report.txt
# 假设输出行为 590413693

tail -n +590413693 report.txt | head -n 30
```

### 16.5 存储/写回相关模板

#### 看某进程是否持续刷盘

```bash
rg 'zstdext.*block_bio_queue|zstdext.*block_rq_insert|zstdext.*__arm64_sys_fsync' report.txt
```

#### 看某段时间内的块层完成事件

```bash
awk '
{
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.0 && t <= 1725.0 && /block_rq_complete|block_bio_queue|block_rq_insert/) print
}
' report.txt
```

#### 看 UFS completion IRQ

```bash
rg 'qcom-mc|ufshcd_compl_one_cqe|ufs_qcom_mcq_esi_handler' report.txt
```

### 16.6 CPU 维度模板

#### 统计某窗口内一个 CPU 上主要是谁在运行

这个模板依赖 `sched_switch` 格式，思路是抽 `==>` 右边的 next task：

```bash
awk '
$2 == "[017]" {
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.0 && t <= 1725.0 && /sched_switch/) {
        n = split($0, a, "==> ")
        if (n >= 2) print a[2]
    }
}
' report.txt | sort | uniq -c | sort -nr
```

用途：

- 看事故窗口里 CPU17 最常运行的是谁

#### 看某 CPU 上 idle 是否异常多

```bash
awk '
$2 == "[017]" && /sched_switch/ && /==> swapper\/17:0/ {
    print
}
' report.txt
```

如果在问题窗口里大量切到 `swapper/N`，通常表示：

- 要么真的没活干
- 要么关键线程都在 `D`，CPU 只能 idle

### 16.7 多线程共因分析模板

#### 找同一窗口里所有进入 `D` 的线程

```bash
awk '
{
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.0 && t <= 1725.0 && /sched_switch/ && / D ==> /) print
}
' report.txt
```

#### 把进入 `D` 的线程名做去重统计

```bash
awk '
/sched_switch/ && / D ==> / {
    print $1
}
' report.txt | sort | uniq -c | sort -nr
```

#### 找多个线程共同落到的关键栈函数

```bash
rg '__folio_end_writeback|rt_spin_lock|unix_release_sock|bio_endio|scsi_io_completion' report.txt
```

### 16.8 一个推荐的组合拳

实际分析时，我经常这样组合：

1. 先定位时间点

```bash
rg -n 'watchdog timeout|1719\.423852|1724\.132573' report.txt
```

2. 再抽时间窗

```bash
awk '
{
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.3 && t <= 1724.2) print
}
' report.txt > mini_report.txt
```

3. 再在小文件里做局部分析

```bash
rg 'watchdog|clusterservice|qcom-mc|sched_switch|kernel_stack' mini_report.txt
```

4. 再对精确点位做小范围上下文读取

```bash
grep -n '1719.340056' mini_report.txt -A 20
```

这个方法比直接在超大 `report.txt` 上反复扫全文更稳，也更省资源。

### 16.9 一个提醒

不要把这些脚本当成固定公式。

正确用法是：

- 先理解你要回答什么问题
- 再选最小必要的筛选条件
- 最后根据手头 trace 文本格式调整字段位置和正则

脚本只是放大器，不是分析本身。


---

## 17. 超大 `report.txt` 的低内存分析原则

真实项目里，`trace-cmd report` 导出的文本可能非常大，几 GB 并不罕见。处理这种文件时，最重要的不是命令花哨，而是**不要一次性把文件全部读进内存**。

### 17.1 基本原则

1. 先缩时间窗，不要先全局扫全文
2. 先缩对象范围，不要同时看所有线程
3. 先用 `rg -n` 找行号，再按行号读取局部
4. 优先使用流式工具：`rg`、`grep`、`awk`、`sed`、`head`、`tail`
5. 尽量生成更小的中间文件，例如 `mini_report.txt`

### 17.2 不推荐的做法

下面这些做法在大文件上容易把机器拖死：

- 用 Python/Pandas 一次性 `read()` 或 `readlines()` 整个文件
- 先把全文件读进列表再过滤
- 在编辑器里直接打开几 GB 文本
- 写很多重复全表扫描的脚本

### 17.3 推荐做法 1：先找精确时间点

```bash
rg -n '1719\.423852|1724\.132573|watchdog timeout' report.txt
```

先拿到行号，再决定往前后各看多少行。

### 17.4 推荐做法 2：按行号读取局部

```bash
tail -n +590413693 report.txt | head -n 60
```

这个模式的好处是：

- 不需要把全文读入内存
- 只读取你关心的那几十行

### 17.5 推荐做法 3：先切出一个小窗口文件

如果你已经知道事故时间窗，例如 `1719.3 ~ 1724.2`：

```bash
awk '
{
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.3 && t <= 1724.2) print
}
' report.txt > mini_report.txt
```

然后后续所有分析都优先在 `mini_report.txt` 上做。

### 17.6 推荐做法 4：先按线程或 CPU 再切一次

```bash
rg 'watchdog|clusterservice|qcom-mc|kernel_stack|sched_switch' mini_report.txt > focus.txt
```

这样你就把“全窗口文件”进一步缩成了“与问题强相关的小文件”。

### 17.7 推荐做法 5：分层处理

一个实用流程通常是：

1. `report.txt`：原始全量文本
2. `mini_report.txt`：事故时间窗
3. `focus.txt`：目标线程/目标 CPU/目标事件
4. 再做统计或人工阅读

这种分层方式比在原始大文件上来回跑复杂脚本稳定得多。

### 17.8 一个经验

如果你开始写脚本时发现自己想：

- “先全部读进来再说”
- “我先建个大字典”
- “我先转成 DataFrame”

那通常就是方法错了。

对于大 trace 文本，正确思路几乎总是：

- 先局部定位
- 再局部抽取
- 最后局部统计

---

## 18. 从 `trace.dat` 到 `report.txt` 到 `mini_report.txt` 的完整工作流

下面给一个偏实战的工作流模板，适合定位 watchdog timeout、卡顿、`D` 状态阻塞、IRQ 风暴这类问题。

### 18.1 第一步：采集 `trace.dat`

```bash
trace-cmd record   -e sched:sched_switch   -e sched:sched_wakeup   -e sched:sched_waking   -e irq   -e block   -T
```

如果你已经拿到别人提供的 `trace.dat`，这一步可以跳过。

### 18.2 第二步：导出文本

```bash
trace-cmd report trace.dat > report.txt
```

注意：

- `trace.dat` 适合保存和回放
- `report.txt` 适合用 `rg/awk/sed` 进行脚本分析

### 18.3 第三步：先从日志侧确定事故时间

例如：

- watchdog timeout 的时间
- 某个进程最后一次 heartbeat 的时间
- 某次异常发生的 tick/time

先拿到一个近似时间窗，例如：

- `1719.3 ~ 1724.2`

### 18.4 第四步：先在 `report.txt` 里定位关键点

```bash
rg -n '1719\.423852|1724\.132573|watchdog timeout|qcom-mc|pmonitor' report.txt
```

目标是找到：

- 关键时间点
- 关键线程
- 关键栈函数
- 对应行号

### 18.5 第五步：切出 `mini_report.txt`

```bash
awk '
{
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.3 && t <= 1724.2) print
}
' report.txt > mini_report.txt
```

现在后面的分析都尽量基于 `mini_report.txt`。

### 18.6 第六步：围绕问题对象建立第一层聚焦

例如：

```bash
rg 'watchdog|clusterservice|pmonitor|qcom-mc|kernel_stack|sched_switch|sched_wakeup|sched_waking' mini_report.txt > focus.txt
```

这一步的目标不是最终结论，而是把阅读负担从“几百万行”降到“几百或几千行”。

### 18.7 第七步：做三类核心分析

#### A. 单线程轨迹

```bash
awk '
/watchdog-7304|watchdog:7304/ && /sched_switch|sched_wakeup|sched_waking|kernel_stack/ {
    print
}
' mini_report.txt
```

回答：

- 它什么时候被唤醒
- 什么时候真正运行
- 什么时候进 `D`
- 卡在哪条内核栈

#### B. CPU 轨迹

```bash
awk '
$2 == "[017]" && /sched_switch/ {
    print
}
' mini_report.txt
```

回答：

- CPU17 在事故窗口主要运行了谁
- 是不是大量在跑 IRQ / idle / kworker

#### C. 存储 / 写回链路

```bash
rg 'block_bio_queue|block_rq_complete|__folio_end_writeback|scsi_io_completion|ufshcd_compl_one_cqe|qcom-mc' mini_report.txt
```

回答：

- 是否有重刷盘
- 是否有写回完成链阻塞
- UFS completion IRQ 是否卷入

### 18.8 第八步：必要时回到原始 `report.txt` 取更大上下文

当你在 `mini_report.txt` 里发现关键点，例如：

- `1719.340056`
- `1724.132573`

就回原始文件取上下文：

```bash
grep -n '1719.340056' report.txt
tail -n +590246469 report.txt | head -n 40
```

原因很简单：

- `mini_report.txt` 可能已经裁掉了前后依赖信息
- 原始文件的行号更适合精准取证

### 18.9 第九步：把证据整理成时间轴

最终写结论时，不要只写“怀疑”。

最好按这个结构：

1. 时间点
2. 线程/CPU
3. 事件
4. 内核栈/关键函数
5. 推导出的含义

例如：

- `1719.423852`，`watchdog:7304`，`sched_switch`，状态 `D`
- 紧随其后 `kernel_stack` 落在 `unix_release_sock -> rt_spin_lock`
- 因此可确认它不是普通调度延迟，而是在 `close()` 路径里进入不可中断等待

### 18.10 第十步：分清“已确认”和“推断”

trace 分析最怕两种错误：

- 没证据也写成“已确认”
- 明明证据很强，却只写成模糊猜测

建议输出时分两层：

- 已直接确认的事实
- 基于事实的高置信推断

这样技术表达会更严谨。

### 18.11 一个完整示例命令流

```bash
trace-cmd report trace.dat > report.txt

rg -n 'watchdog timeout|1719\.423852|1724\.132573' report.txt

awk '
{
    t = $3
    sub(/:$/, "", t)
    if (t >= 1719.3 && t <= 1724.2) print
}
' report.txt > mini_report.txt

rg 'watchdog|clusterservice|qcom-mc|kernel_stack|sched_switch' mini_report.txt

awk '
/watchdog-7304|watchdog:7304/ && /sched_switch|sched_wakeup|sched_waking|kernel_stack/ {
    print
}
' mini_report.txt

rg '__folio_end_writeback|unix_release_sock|rt_spin_lock|ufshcd_compl_one_cqe' mini_report.txt
```

这套流程已经足够解决大多数第一轮排查问题。
