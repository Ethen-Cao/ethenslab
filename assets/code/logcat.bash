#!/bin/bash

# =============================================================================
# 脚本名称: logcat.bash
# 逻辑模式: Scoped OR with Exclusion
#          Time AND (NOT Exclude) AND ( PID OR Tag OR Keyword )
# 功能: 
#       1. 支持多 Tag、多 PID、多关键字、多排除词 (空格分隔)。
#       2. 支持多文件/目录搜索。
#       3. 智能区分关键字和文件路径。
# 核心: 基于 ripgrep (rg) + awk。
# =============================================================================

# --- 颜色定义 ---
COLOR_RESET="\033[0m"
COLOR_FILE="\033[35m" # 紫色文件名
COLOR_LINE="\033[32m" # 绿色行号

# --- 帮助函数 ---
function show_usage() {
    echo "Usage: logcat [options] [file/dir...]"
    echo ""
    echo "Logic: Time AND (NOT Exclude) AND ( PID OR Tag OR Keyword )"
    echo ""
    echo "Options:"
    echo "  -f <paths...>           Specify files/dirs to search (Space separated)"
    echo "  -p <pids...>            Filter by Process ID (Space separated)"
    echo "  -s <tags...>            Filter by Log Tag (Space separated)"
    echo "  -k <keywords...>        Filter by Keyword (Include) (Space separated)"
    echo "  -e <keywords...>        Exclude lines containing keywords (Space separated)"
    echo "  -t <start> <end>        Filter by Time Range (HH:MM or MM-DD HH:MM:SS)"
    echo "  --plain                 Output plain text (no filename/line numbers)"
    echo ""
    echo "Examples:"
    echo "  1. Exclude noise:  logcat -t \"09:00\" \"09:05\" -e \"chatty\" \"debug\""
    echo "  2. Complex filter: logcat -p 1234 -k \"Error\" -e \"ignorable error\""
    exit 1
}

# --- 核心搜索逻辑 ---
function execute_search() {
    local s_time="$1"
    local e_time="$2"
    local TIME_ONLY="$3"
    local use_time_filter=1

    if [[ -z "$s_time" ]]; then
        use_time_filter=0
    fi

    if [[ ${#SEARCH_TARGETS[@]} -eq 0 ]]; then
        SEARCH_TARGETS=(".")
    fi

    # rg 仅作为读取器 (除非只有包含关键字且没有排除关键字，否则不预过滤)
    local rg_pattern="."
    if [[ -z "$FILTER_PID" && -z "$FILTER_TAG" && -z "$FILTER_EXCLUDE" && -n "$FILTER_KEY" ]]; then
        rg_pattern="$FILTER_KEY"
    fi

    rg --files-with-matches --null "$rg_pattern" "${SEARCH_TARGETS[@]}" | xargs -0 awk \
        -v s="$s_time" \
        -v e="$e_time" \
        -v enable_time="$use_time_filter" \
        -v time_only="$TIME_ONLY" \
        -v p="$PLAIN_MODE" \
        -v f_pid="$FILTER_PID" \
        -v f_tag="$FILTER_TAG" \
        -v f_key="$FILTER_KEY" \
        -v f_exclude="$FILTER_EXCLUDE" \
        -v c_file="$COLOR_FILE" \
        -v c_line="$COLOR_LINE" \
        -v c_reset="$COLOR_RESET" '
        BEGIN { }
        {
            # 1. 格式校验
            if ($1 !~ /^[0-9]{2}-[0-9]{2}$/ || $2 !~ /^[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+$/) next

            # 2. 时间过滤 (Gatekeeper 1)
            # time_only=1 时只比较时间部分 ($2)，否则比较完整时间戳 ($1 " " $2)
            if (enable_time == 1) {
                if (time_only == 1) {
                    current_time = $2
                } else {
                    current_time = $1 " " $2
                }
                if ((s != "" && current_time < s) || (e != "" && current_time > e)) next
            }

            # 3. 排除过滤 (Gatekeeper 2 - 新增功能)
            # 如果匹配任何排除关键词，直接丢弃
            if (f_exclude != "" && $0 ~ f_exclude) next

            # 4. 包含属性过滤 (Scoped OR 逻辑)
            
            has_condition = 0
            is_matched = 0

            # --- 检查 PID ---
            if (f_pid != "") {
                has_condition = 1
                if ($3 ~ f_pid) is_matched = 1
            }

            # --- 检查 Tag ---
            # $6 = 标准 threadtime 格式 (D Tag:)
            # $5 = 合并格式 (D/Tag:), 需从中提取 tag 部分
            if (f_tag != "" && is_matched == 0) {
                has_condition = 1
                tag = $6
                if (tag ~ f_tag) {
                    is_matched = 1
                } else if ($5 ~ /\//) {
                    split($5, _t, "/")
                    if (_t[2] ~ f_tag) is_matched = 1
                }
            }

            # --- 检查 Keyword ---
            if (f_key != "" && is_matched == 0) {
                has_condition = 1
                if ($0 ~ f_key) is_matched = 1
            }

            # 5. 输出决策
            # 如果没指定 PID/Tag/Key (只有排除或时间)，则输出。
            # 否则必须命中至少一个条件。
            if (has_condition == 0 || is_matched == 1) {
                if (p == 1) {
                    print $0
                } else {
                    printf "%s%s%s:%s%s%s: %s\n", c_file, FILENAME, c_reset, c_line, FNR, c_reset, $0
                }
            }
        }
    '
}

# --- 参数解析 ---

PLAIN_MODE=0
FILTER_PID=""
FILTER_TAG=""
FILTER_KEY=""
FILTER_EXCLUDE=""
START_TIME=""
END_TIME=""
TIME_ONLY=0
declare -a SEARCH_TARGETS=()

# 检测时间参数是否包含日期 (MM-DD)
function has_date_prefix() {
    [[ "$1" =~ ^[0-9]{2}-[0-9]{2} ]]
}

# 检测参数是否像时间值 (HH:MM... 或 MM-DD ...)
function is_time_arg() {
    [[ "$1" =~ ^[0-9]{2}:[0-9]{2} || "$1" =~ ^[0-9]{2}-[0-9]{2} ]]
}

# 规范化时间值为 logcat 可比较格式
# 输入: 任意格式如 "15:18", "15:18:00", "15:18:000000", "03-24 15:18:00.123"
# 输出: "HH:MM:SS.ffffff" 或 "MM-DD HH:MM:SS.ffffff"
function normalize_time_value() {
    local t="$1"
    local date_prefix=""
    # 提取日期前缀
    if [[ "$t" =~ ^([0-9]{2}-[0-9]{2})[[:space:]]+(.*) ]]; then
        date_prefix="${BASH_REMATCH[1]} "
        t="${BASH_REMATCH[2]}"
    fi
    # 解析 HH:MM[:SS[.frac]]
    if [[ "$t" =~ ^([0-9]{2}):([0-9]{2})(:([0-9]{2})(\.([0-9]+))?)? ]]; then
        local h="${BASH_REMATCH[1]}" m="${BASH_REMATCH[2]}"
        local s="${BASH_REMATCH[4]:-00}" f="${BASH_REMATCH[6]:-000000}"
        # 补齐小数部分到 6 位
        while [[ ${#f} -lt 6 ]]; do f="${f}0"; done
        echo "${date_prefix}${h}:${m}:${s}.${f}"
    else
        echo "${date_prefix}${t}"
    fi
}

if [ $# -eq 0 ]; then
    show_usage
fi

function is_stop_arg() {
    local arg="$1"
    if [[ "$arg" == -* ]]; then return 0; fi
    if [[ -e "$arg" ]]; then return 0; fi
    return 1
}

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -f) # File
            shift
            while [[ $# -gt 0 ]]; do
                if [[ "$1" == -* ]]; then break; fi
                SEARCH_TARGETS+=("$1")
                shift
            done
            ;;
        -p) # PID
            shift
            _pids=""
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$_pids" ]]; then _pids="$1"; else _pids="${_pids}|$1"; fi
                shift
            done
            if [[ -n "$_pids" ]]; then FILTER_PID="^(${_pids})$"; fi
            ;;
        -s) # Tag
            shift
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$FILTER_TAG" ]]; then FILTER_TAG="$1"; else FILTER_TAG="${FILTER_TAG}|$1"; fi
                shift
            done
            ;;
        -k) # Keyword (Include)
            shift
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$FILTER_KEY" ]]; then FILTER_KEY="$1"; else FILTER_KEY="${FILTER_KEY}|$1"; fi
                shift
            done
            ;;
        -e) # Exclude (新增参数)
            shift
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$FILTER_EXCLUDE" ]]; then FILTER_EXCLUDE="$1"; else FILTER_EXCLUDE="${FILTER_EXCLUDE}|$1"; fi
                shift
            done
            ;;
        -t) # Time
            if [[ -n "$2" && "$2" != -* ]]; then
                # 检测是否为短格式 (无日期前缀)
                if ! has_date_prefix "$2"; then TIME_ONLY=1; fi
                START_TIME=$(normalize_time_value "$2")
                if [[ -n "$3" && "$3" != -* ]] && is_time_arg "$3"; then
                    END_TIME=$(normalize_time_value "$3")
                    shift 3
                else
                    END_TIME=""
                    shift 2
                fi
            else
                echo "Warning: Option -t requires time args." >&2; shift 1
            fi
            ;;
        --plain)
            PLAIN_MODE=1
            shift
            ;;
        *)
            if [[ "$1" != -* ]]; then SEARCH_TARGETS+=("$1"); shift 1; else echo "Unknown option: $1"; show_usage; fi
            ;;
    esac
done

execute_search "$START_TIME" "$END_TIME" "$TIME_ONLY"