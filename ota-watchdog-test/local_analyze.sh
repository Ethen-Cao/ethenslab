#!/bin/bash
# ============================================================
# [本地] OTA Watchdog 超时复现 - Trace 分析
# 用法: ./local_analyze.sh [车端数据目录]
#   如不指定目录，自动从设备 pull 最新数据
# 示例:
#   ./local_analyze.sh                    # 自动 pull 最新
#   ./local_analyze.sh data/              # 分析已有数据
# ============================================================

set -e

DATA_DIR="${1:-}"

# ---- 如果没有指定目录，自动从设备 pull 最新数据 ----
if [ -z "$DATA_DIR" ]; then
    echo "[1/4] 从设备获取最新数据目录..."
    REMOTE_DIR=$(adb shell "ls -td /log/wd_reproduce_* 2>/dev/null | head -n 1" | tr -d '\r\n')
    if [ -z "$REMOTE_DIR" ]; then
        echo "错误: 设备上未找到 /log/wd_reproduce_* 目录"
        echo "请先在车端运行 device_collect.sh"
        exit 1
    fi
    echo "  设备端目录: $REMOTE_DIR"

    DATA_DIR="data"
    mkdir -p "$DATA_DIR"
    echo ""
    echo "[2/4] Pull 数据到本地 $DATA_DIR/ ..."
    adb pull "$REMOTE_DIR/" "$DATA_DIR/"
    echo ""
else
    echo "[1/4] 使用本地数据: $DATA_DIR"
    echo "[2/4] 跳过 pull"
fi

# ---- 检查必要文件 ----
for f in trace.txt dlt_during_io.txt dlt_baseline.txt pids.txt; do
    if [ ! -f "$DATA_DIR/$f" ]; then
        echo "错误: 缺少 $DATA_DIR/$f"
        exit 1
    fi
done

TRACE="$DATA_DIR/trace.txt"
DLT_IO="$DATA_DIR/dlt_during_io.txt"
DLT_BASE="$DATA_DIR/dlt_baseline.txt"

# 加载测试元数据
if [ -f "$DATA_DIR/test_meta.txt" ]; then
    . "$DATA_DIR/test_meta.txt"
fi

echo ""
echo "================================================"
echo "  [本地] ftrace 分析"
echo "================================================"
echo "trace 文件: $TRACE ($(du -h "$TRACE" | cut -f1))"
echo "trace 行数: ${trace_lines:-$(wc -l < "$TRACE")}"
echo ""

# ============ 1. DLT 分析 ============
echo "--- 1. DLT 分析 ---"
echo ""

baseline_count=$(grep -ci "timeout" "$DLT_BASE" 2>/dev/null || true)
io_count=$(grep -ci "timeout" "$DLT_IO" 2>/dev/null || true)
echo "timeout 消息: 基线=${baseline_count:-0}, I/O期间=${io_count:-0}"

echo ""
echo "timeout/watchdog 相关 DLT 日志:"
grep -i "timeout\|watchdog\|wdt" "$DLT_IO" 2>/dev/null || echo "(无)"

echo ""
echo "pmonitor 告警:"
grep -i "pmon" "$DLT_IO" 2>/dev/null | grep -iv "SYS-" || echo "(无)"

# ============ 2. UFS IRQ 线程运行时间分析 ============
echo ""
echo "--- 2. UFS IRQ 线程运行时间 ---"
echo ""
echo "计算中 (扫描 trace)..."

awk '
    /==>.*irq\/[0-9]+-qcom/ {
        split($4, a, ".")
        t_in = a[1] * 1000000 + a[2]
    }
    /irq\/[0-9]+-qcom.*==>/ {
        split($4, a, ".")
        t_out = a[1] * 1000000 + a[2]
        if (t_in > 0 && t_out > t_in) {
            d = t_out - t_in
            n++
            if (d > max) max = d
            # 收集所有运行时间用于 Top N
            durations[n] = d
        }
    }
    END {
        printf "总切入/切出对数: %d\n", n
        printf "最长单次运行: %d us (%d ms)\n", max, max/1000
        # 简单冒泡找 Top 10
        for (i = 1; i <= 10 && i <= n; i++) {
            max_idx = i
            for (j = i + 1; j <= n; j++) {
                if (durations[j] > durations[max_idx]) max_idx = j
            }
            tmp = durations[i]; durations[i] = durations[max_idx]; durations[max_idx] = tmp
        }
        printf "\nTop 10 最长运行 (us):\n"
        for (i = 1; i <= 10 && i <= n; i++) {
            printf "  #%d: %d us (%d ms)\n", i, durations[i], durations[i]/1000
        }
    }
' "$TRACE"

# ============ 3. ktimers D 状态分析 ============
echo ""
echo "--- 3. ktimers D 状态分析 ---"
echo ""

ktimers_d_count=$(grep -c "ktimers.*prev_state=D" "$TRACE" 2>/dev/null || true)
echo "ktimers 进入 D 状态总次数: ${ktimers_d_count:-0}"

if [ "${ktimers_d_count:-0}" -gt 0 ]; then
    echo ""
    echo "ktimers D 状态事件:"
    grep "ktimers.*prev_state=D" "$TRACE" | head -20
    echo ""

    # 分析每个 ktimers/N 的 D 状态持续时间
    echo "ktimers D 状态持续时间分析:"
    awk '
    /prev_comm=ktimers\/[0-9]+.*prev_state=D/ {
        # ktimers 被切出且进入 D 状态
        match($0, /prev_comm=ktimers\/([0-9]+)/, m)
        cpu = m[1]
        split($4, a, ".")
        t_out[cpu] = a[1] * 1000000 + a[2]
        in_d[cpu] = 1
    }
    /prev_comm=ktimers\/[0-9]+/ && !/prev_state=D/ {
        # ktimers 被切出但不是 D 状态，清除标记
        match($0, /prev_comm=ktimers\/([0-9]+)/, m)
        in_d[m[1]] = 0
    }
    /next_comm=ktimers\/[0-9]+/ {
        # ktimers 被切入
        match($0, /next_comm=ktimers\/([0-9]+)/, m)
        cpu = m[1]
        if (in_d[cpu]) {
            split($4, a, ".")
            t_in = a[1] * 1000000 + a[2]
            if (t_out[cpu] > 0 && t_in > t_out[cpu]) {
                d = t_in - t_out[cpu]
                if (d > max[cpu]) max[cpu] = d
                count[cpu]++
                total[cpu] += d
            }
            in_d[cpu] = 0
        }
    }
    END {
        for (cpu in count) {
            printf "  ktimers/%s: D状态 %d 次, 最长 %d us (%d ms), 累计 %d us (%d ms)\n",
                cpu, count[cpu], max[cpu], max[cpu]/1000, total[cpu], total[cpu]/1000
        }
    }
    ' "$TRACE"
fi

# ============ 4. 关键进程调度间隔分析 ============
echo ""
echo "--- 4. 关键进程调度间隔 ---"
echo ""

for proc in ivcd mcd audiomgr pmonitor updatemgr; do
    result=$(awk -v p="$proc" '
    BEGIN { last_seen = 0; max = 0; max_at = 0; n = 0 }
    {
        if ($0 ~ "==>.*"p) {
            split($4, a, ".")
            now = a[1] * 1000000 + a[2]
            if (last_seen > 0 && now > last_seen) {
                gap = now - last_seen
                n++
                if (gap > max) { max = gap; max_at = now }
            }
        }
        if ($0 ~ p".*==>") {
            split($4, a, ".")
            last_seen = a[1] * 1000000 + a[2]
        }
    }
    END {
        printf "%d %d %d", max, max/1000, n
    }
    ' "$TRACE" 2>/dev/null)

    max_us=$(echo "$result" | awk '{print $1}')
    max_ms=$(echo "$result" | awk '{print $2}')
    count=$(echo "$result" | awk '{print $3}')

    flag=""
    if [ "$max_ms" -gt 3000 ] 2>/dev/null; then
        flag=" <<< 超过 watchdog 3000ms 阈值!"
    elif [ "$max_ms" -gt 1000 ] 2>/dev/null; then
        flag=" <<< 超过心跳 1000ms 阈值!"
    elif [ "$max_ms" -gt 500 ] 2>/dev/null; then
        flag=" <- 偏高"
    fi
    printf "  %-12s %8d us (%4d ms) [%d 次调度切换]%s\n" "$proc" "$max_us" "$max_ms" "$count" "$flag"
done

# ============ 5. updatemgr 调度时间线 (异常区间) ============
echo ""
echo "--- 5. updatemgr 调度时间线 (显示异常间隔) ---"
echo ""

awk '
/==>.*updatemgr/ {
    split($4, a, ".")
    t = a[1] * 1000000 + a[2]
    t_s = a[1] + a[2] / 1000000
    if (last > 0) {
        gap_ms = (t - last) / 1000
        if (gap_ms > 600) {
            printf "*** 异常 %.0f ms *** 切入: %.6f\n", gap_ms, t_s
        }
    }
    last = t
}
' "$TRACE"

abnormal_count=$(awk '
/==>.*updatemgr/ {
    split($4, a, "."); t = a[1]*1000000+a[2]
    if (last>0 && (t-last)/1000 > 600) c++
    last = t
}
END { print c+0 }
' "$TRACE")

if [ "$abnormal_count" -eq 0 ]; then
    echo "(未发现 >600ms 的异常间隔)"
fi

# ============ 6. UFS IRQ D 状态分析 ============
echo ""
echo "--- 6. UFS IRQ 线程 D 状态 ---"
echo ""

irq_d_count=$(grep -c "irq/.*qcom.*prev_state=D" "$TRACE" 2>/dev/null || true)
echo "UFS IRQ 线程进入 D 状态次数: ${irq_d_count:-0}"
if [ "${irq_d_count:-0}" -gt 0 ]; then
    echo "前 10 条:"
    grep "irq/.*qcom.*prev_state=D" "$TRACE" | head -10
fi

# ============ 7. CPU 活动热点 (异常区间) ============
echo ""
echo "--- 7. 异常区间 CPU 活动 ---"
echo ""

# 找到 updatemgr 最大异常间隔的时间范围，分析该时段 CPU 上跑的进程
awk '
/==>.*updatemgr/ {
    split($4, a, ".")
    t = a[1] * 1000000 + a[2]
    if (last > 0) {
        gap = t - last
        if (gap > max_gap) {
            max_gap = gap
            max_start_s = last_s
            max_end = a[1] "." a[2]
        }
    }
    last = t
    last_s = a[1] "." a[2]
}
END {
    if (max_gap > 0) {
        printf "%s %s %d\n", max_start_s, max_end, max_gap/1000
    }
}
' "$TRACE" | while read start end gap_ms; do
    if [ -z "$start" ]; then
        echo "(无异常区间)"
        break
    fi
    echo "最大异常区间: $start → $end (${gap_ms} ms)"
    echo ""
    # 提取起始秒数用于 grep
    start_sec=$(echo "$start" | cut -d. -f1)
    end_sec=$(echo "$end" | cut -d. -f1)
    echo "该区间内频繁运行的进程 (sched_switch 中 ==> 切入次数):"
    awk -v s="$start_sec" -v e="$end_sec" '
    {
        split($4, a, ".")
        sec = a[1] + 0
        if (sec >= s && sec <= e && /==>/) {
            match($0, /==> +([^ ]+)/, m)
            if (m[1] != "") procs[m[1]]++
        }
    }
    END {
        for (p in procs) printf "  %6d  %s\n", procs[p], p
    }
    ' "$TRACE" | sort -rn | head -15
done

# ============ 综合判定 ============
echo ""
echo "================================================"
echo "  综合判定"
echo "================================================"
echo ""

reproduced=0

# DLT 判定
pmon_timeout=$(grep -c "pmon.*timeout\|watchdog timeout" "$DLT_IO" 2>/dev/null || true)
if [ "${pmon_timeout:-0}" -gt 0 ]; then
    echo "[FAIL] DLT 捕获到 ${pmon_timeout} 条 pmonitor/watchdog timeout"
    reproduced=1
fi

io_timeout=$(grep -ci "timeout" "$DLT_IO" 2>/dev/null || true)
base_timeout=$(grep -ci "timeout" "$DLT_BASE" 2>/dev/null || true)
if [ "${io_timeout:-0}" -gt "${base_timeout:-0}" ] 2>/dev/null; then
    echo "[FAIL] DLT timeout 消息: 基线 ${base_timeout} → 测试 ${io_timeout} (增加 $((io_timeout - base_timeout)) 条)"
    reproduced=1
fi

# ktimers 判定
if [ "${ktimers_d_count:-0}" -gt 0 ]; then
    echo "[FAIL] ktimers 进入 D 状态 ${ktimers_d_count} 次 (RT 定时器线程被锁阻塞)"
    reproduced=1
fi

# updatemgr 调度间隔判定
updm_max_ms=$(awk '
/==>.*updatemgr/ {
    split($4, a, "."); t = a[1]*1000000+a[2]
    if (last>0) { gap=t-last; if(gap>max) max=gap }
    last = t
}
END { printf "%d", max/1000 }
' "$TRACE" 2>/dev/null)
if [ "${updm_max_ms:-0}" -gt 1000 ] 2>/dev/null; then
    echo "[FAIL] updatemgr 最大调度间隔 ${updm_max_ms}ms > 1000ms 心跳阈值"
    reproduced=1
fi

# IRQ 判定
irq_max_ms=$(awk '
    /==>.*irq\/[0-9]+-qcom/ { split($4,a,"."); t_in=a[1]*1000000+a[2] }
    /irq\/[0-9]+-qcom.*==>/ {
        split($4,a,"."); t_out=a[1]*1000000+a[2]
        if(t_in>0 && t_out>t_in) { d=t_out-t_in; if(d>max) max=d }
    }
    END { printf "%d", max/1000 }
' "$TRACE" 2>/dev/null)
if [ "${irq_max_ms:-0}" -gt 3000 ] 2>/dev/null; then
    echo "[FAIL] UFS IRQ 最长运行 ${irq_max_ms}ms > 3000ms (BH 锁饥饿路径)"
    reproduced=1
elif [ "${irq_max_ms:-0}" -gt 500 ] 2>/dev/null; then
    echo "[WARN] UFS IRQ 最长运行 ${irq_max_ms}ms > 500ms"
fi

echo ""
if [ "$reproduced" -gt 0 ]; then
    echo "结论: Watchdog 超时已复现"
    echo ""
    echo "根因: UFS I/O 密集期间，writeback 路径的锁阻塞了 ktimers RT 线程，"
    echo "      导致 SCHED_NORMAL 进程的 soft hrtimer 延迟 → watchdog 心跳超时。"
    echo "      问题出在 PREEMPT_RT 内核的锁转换 × UFS 驱动 IRQ 注册方式冲突，"
    echo "      不是 I/O 负载量问题。"
else
    echo "结论: 本次未触发 watchdog timeout"
    echo "建议: 增大写入量或多次运行"
fi
