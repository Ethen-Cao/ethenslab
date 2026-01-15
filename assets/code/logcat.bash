#!/bin/bash

# =============================================================================
# 脚本名称: logcat.bash
# 功能: 模拟 adb logcat 的参数习惯，递归搜索当前目录下的离线日志文件。
# 核心: 基于 ripgrep (rg) + awk 的高性能过滤。
# =============================================================================

# --- 颜色定义 (可选，为了更好看，如果不需要可删除) ---
COLOR_RESET="\033[0m"
COLOR_FILE="\033[35m" # 紫色文件名
COLOR_LINE="\033[32m" # 绿色行号

# --- 帮助函数 ---
function show_usage() {
    echo "Usage: logcat [options]"
    echo ""
    echo "Options:"
    echo "  -p <pid>                Filter by Process ID (PID)"
    echo "  -s <tag>                Filter by Log Tag (e.g., ActivityManager)"
    echo "  -k <keyword>            Filter by Keyword (content search)"
    echo "  -t <start> <end>        Filter by Time Range (MM-DD HH:MM:SS)"
    echo "  --plain                 Output plain text (no filename/line numbers)"
    echo ""
    echo "Examples:"
    echo "  logcat -t \"01-15 09:28:00\" \"01-15 09:30:00\""
    echo "  logcat -p 1375 -s InputDispatcher"
    echo "  logcat -k \"Exception\" -t \"09:00\" \"09:05\""
    exit 1
}

# --- 核心搜索逻辑 (复用之前的 Time_Awk 逻辑) ---
function execute_search() {
    local s_time="$1"
    local e_time="$2"
    local use_time_filter=1

    # 如果没有指定时间，则关闭时间过滤
    if [[ -z "$s_time" ]]; then
        use_time_filter=0
    fi

    # 优化策略：如果仅有关键字，无其他限制，直接使用 rg (极速模式)
    if [[ $use_time_filter -eq 0 && -z "$FILTER_PID" && -z "$FILTER_TAG" && -n "$FILTER_KEY" ]]; then
        local rg_opts="--line-number --with-filename"
        if [[ $PLAIN_MODE -eq 1 ]]; then rg_opts="--no-line-number --no-filename"; fi
        rg $rg_opts "$FILTER_KEY" .
        return
    fi

    # 默认模式：rg 预搜索 + awk 精确过滤
    local rg_pattern="."
    if [[ -n "$FILTER_KEY" ]]; then rg_pattern="$FILTER_KEY"; fi

    rg --files-with-matches --null "$rg_pattern" . | xargs -0 awk \
        -v s="$s_time" \
        -v e="$e_time" \
        -v enable_time="$use_time_filter" \
        -v p="$PLAIN_MODE" \
        -v f_pid="$FILTER_PID" \
        -v f_tag="$FILTER_TAG" \
        -v f_key="$FILTER_KEY" \
        -v c_file="$COLOR_FILE" \
        -v c_line="$COLOR_LINE" \
        -v c_reset="$COLOR_RESET" '
        BEGIN { }
        {
            # 1. 格式校验
            if ($1 !~ /^[0-9]{2}-[0-9]{2}$/ || $2 !~ /^[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+$/) next

            # 2. 时间过滤
            if (enable_time == 1) {
                current_time = $1 " " $2
                # 支持仅输入 HH:MM:SS 的情况 (自动补全日期太复杂，这里假设用户输入完整或者日志匹配)
                # 为了简单，如果用户只输了时间，这里进行简单字符串比较
                if ((s != "" && current_time < s) || (e != "" && current_time > e)) next
            }

            # 3. 属性过滤
            if (f_pid != "" && $3 != f_pid) next
            if (f_tag != "" && index($6, f_tag) != 1) next
            if (f_key != "" && index($0, f_key) == 0) next

            # 4. 输出
            if (p == 1) {
                print $0
            } else {
                # 带颜色的输出格式: 文件名:行号: 内容
                printf "%s%s%s:%s%s%s: %s\n", c_file, FILENAME, c_reset, c_line, FNR, c_reset, $0
            }
        }
    '
}

# --- 参数解析 (关键修改) ---
# 使用 while loop 手动解析，以支持 -t start end 这种双参数结构

PLAIN_MODE=0
FILTER_PID=""
FILTER_TAG=""
FILTER_KEY=""
START_TIME=""
END_TIME=""

if [ $# -eq 0 ]; then
    show_usage
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        -p)
            FILTER_PID="$2"
            shift 2
            ;;
        -s)
            FILTER_TAG="$2"
            shift 2
            ;;
        -k)
            FILTER_KEY="$2"
            shift 2
            ;;
        -t)
            # 处理 -t start_time [end_time]
            START_TIME="$2"
            # 检查下一个参数是否存在，且不是以 - 开头 (说明是 end_time)
            if [[ -n "$3" && "$3" != -* ]]; then
                END_TIME="$3"
                shift 3
            else
                # 只有开始时间，没有结束时间 (意味着直到最后)
                END_TIME="99-99 23:59:59.999" 
                shift 2
            fi
            ;;
        --plain)
            PLAIN_MODE=1
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            ;;
    esac
done

# --- 执行 ---
execute_search "$START_TIME" "$END_TIME"