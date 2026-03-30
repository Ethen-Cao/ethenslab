#!/bin/bash

# =============================================================================
# 脚本名称: logcatv2.bash
# 逻辑模式: Scoped OR with Exclusion
#          Time AND (NOT Exclude) AND ( PID OR Source OR Keyword )
# 功能:
#       1. 兼容现有 logcat 的主要 CLI: -f/-p/-s/-k/-e/-t/--plain
#       2. 支持三类文本行:
#          a) 常规 DLT 文本: app/ctx/message
#          b) JOUR 文本: 外层 DLT + 内层 proc[pid] 消息
#          c) Linux syslog: Mon DD HH:MM:SS(.us) host proc[pid]: message
#       3. 支持多文件/目录搜索。
# 核心: 基于 ripgrep (rg) + awk。
# =============================================================================

COLOR_RESET="\033[0m"
COLOR_FILE="\033[35m"
COLOR_LINE="\033[32m"
CMD_NAME="$(basename "$0")"

function show_usage() {
    echo "Usage: ${CMD_NAME} [options] [file/dir...]"
    echo ""
    echo "Note: syslog lines do not carry year; full-date filters match by MM/DD HH:MM:SS."
    echo ""
    echo "Logic: Time AND (NOT Exclude) AND ( PID OR Source OR Keyword )"
    echo ""
    echo "Options:"
    echo "  -f <paths...>           Specify files/dirs to search (Space separated)"
    echo "  -p <pids...>            Filter by Process ID from JOUR/syslog payload (Space separated)"
    echo "  -s <sources...>         Filter by DLT app/ctx, JOUR proc or syslog proc (Space separated)"
    echo "  -k <keywords...>        Filter by Keyword (Include) (Space separated)"
    echo "  -e <keywords...>        Exclude lines containing keywords (Space separated)"
    echo "  -t <start> <end>        Filter by Time Range (HH:MM or YYYY/MM/DD HH:MM:SS)"
    echo "  --plain                 Output plain text (no filename/line numbers)"
    echo ""
    echo "Examples:"
    echo "  1. Filter app/context: ${CMD_NAME} -s ivcd JOUR"
    echo "  2. Filter JOUR pid:    ${CMD_NAME} -p 2204 -k Warning"
    echo "  3. Filter by time:     ${CMD_NAME} -t \"18:07\" \"18:08\""
    exit 1
}

function has_date_prefix() {
    [[ "$1" =~ ^[0-9]{4}[-/][0-9]{2}[-/][0-9]{2} ]]
}

function is_time_arg() {
    [[ "$1" =~ ^[0-9]{2}:[0-9]{2} || "$1" =~ ^[0-9]{4}[-/][0-9]{2}[-/][0-9]{2} ]]
}

function normalize_time_value() {
    local t="$1"
    local date_prefix=""

    if [[ "$t" =~ ^([0-9]{4})[-/]([0-9]{2})[-/]([0-9]{2})[[:space:]]+(.*) ]]; then
        date_prefix="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}/${BASH_REMATCH[3]} "
        t="${BASH_REMATCH[4]}"
    fi

    if [[ "$t" =~ ^([0-9]{2}):([0-9]{2})(:([0-9]{2})(\.([0-9]+))?)?$ ]]; then
        local h="${BASH_REMATCH[1]}"
        local m="${BASH_REMATCH[2]}"
        local s="${BASH_REMATCH[4]:-00}"
        local f="${BASH_REMATCH[6]:-000000}"
        while [[ ${#f} -lt 6 ]]; do
            f="${f}0"
        done
        echo "${date_prefix}${h}:${m}:${s}.${f}"
    else
        echo "${date_prefix}${t}"
    fi
}

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

    local rg_pattern="."
    if [[ -z "$FILTER_PID" && -z "$FILTER_SOURCE" && -z "$FILTER_EXCLUDE" && -n "$FILTER_KEY" ]]; then
        rg_pattern="$FILTER_KEY"
    fi

    rg --files-with-matches --null "$rg_pattern" "${SEARCH_TARGETS[@]}" | xargs -0 awk \
        -v s="$s_time" \
        -v e="$e_time" \
        -v enable_time="$use_time_filter" \
        -v time_only="$TIME_ONLY" \
        -v p="$PLAIN_MODE" \
        -v f_pid="$FILTER_PID" \
        -v f_source="$FILTER_SOURCE" \
        -v f_key="$FILTER_KEY" \
        -v f_exclude="$FILTER_EXCLUDE" \
        -v c_file="$COLOR_FILE" \
        -v c_line="$COLOR_LINE" \
        -v c_reset="$COLOR_RESET" '
        function normalize_fractional_time(t,    frac) {
            if (t !~ /^[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?$/) return t

            frac = "000000"
            if (index(t, ".") > 0) {
                frac = substr(t, index(t, ".") + 1)
            }
            while (length(frac) < 6) {
                frac = frac "0"
            }
            if (length(frac) > 6) {
                frac = substr(frac, 1, 6)
            }

            return substr(t, 1, 8) "." frac
        }

        function month_to_num(mon) {
            return \
                mon == "Jan" ? "01" : \
                mon == "Feb" ? "02" : \
                mon == "Mar" ? "03" : \
                mon == "Apr" ? "04" : \
                mon == "May" ? "05" : \
                mon == "Jun" ? "06" : \
                mon == "Jul" ? "07" : \
                mon == "Aug" ? "08" : \
                mon == "Sep" ? "09" : \
                mon == "Oct" ? "10" : \
                mon == "Nov" ? "11" : \
                mon == "Dec" ? "12" : ""
        }

        function reset_parsed_fields() {
            PARSED_FORMAT = ""
            PARSED_DATE = ""
            PARSED_TIME = ""
            PARSED_SOURCE1 = ""
            PARSED_SOURCE2 = ""
            PARSED_SOURCE3 = ""
            PARSED_PID = ""
            PARSED_MSG = ""
        }

        function extract_dlt_msg() {
            if (NF < 13) return ""
            return substr($0, index($0, $13))
        }

        function extract_jour_proc(msg,    body, rest, proc_pid, pos) {
            JOUR_PROC = ""
            JOUR_PID = ""

            if (msg !~ /^\[[0-9]{4}\/[0-9]{2}\/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+ /) {
                return
            }

            body = substr(msg, 2)
            if (!match(body, /^[0-9]{4}\/[0-9]{2}\/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+ /)) {
                return
            }

            rest = substr(body, RLENGTH + 1)
            if (!match(rest, /^[^][]+\[[0-9]+\]:/)) {
                return
            }

            proc_pid = substr(rest, RSTART, RLENGTH)
            sub(/:$/, "", proc_pid)
            pos = match(proc_pid, /\[[0-9]+\]$/)
            if (pos == 0) {
                return
            }

            JOUR_PROC = substr(proc_pid, 1, pos - 1)
            JOUR_PID = substr(proc_pid, pos + 1, RLENGTH - 2)
        }

        function parse_dlt_line(    msg) {
            if ($1 !~ /^[0-9]+$/) return 0
            if ($2 !~ /^[0-9]{4}\/[0-9]{2}\/[0-9]{2}$/) return 0
            if ($3 !~ /^[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?$/) return 0
            if (NF < 12) return 0

            msg = extract_dlt_msg()
            extract_jour_proc(msg)

            PARSED_FORMAT = "dlt"
            PARSED_DATE = $2
            PARSED_TIME = normalize_fractional_time($3)
            PARSED_SOURCE1 = $7
            PARSED_SOURCE2 = $8
            PARSED_SOURCE3 = JOUR_PROC
            PARSED_PID = JOUR_PID
            PARSED_MSG = msg

            return 1
        }

        function parse_syslog_line(    month_num, proc_token, msg, rest, pid_pos) {
            month_num = month_to_num($1)
            if (month_num == "") return 0
            if ($2 !~ /^[0-9]{1,2}$/) return 0
            if ($3 !~ /^[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?$/) return 0
            if (NF < 5) return 0

            rest = substr($0, index($0, $5))
            if (!match(rest, /^[^:]+:/)) return 0

            proc_token = substr(rest, 1, RLENGTH)
            sub(/:$/, "", proc_token)

            msg = substr(rest, RLENGTH + 1)
            sub(/^[[:space:]]+/, "", msg)

            PARSED_FORMAT = "syslog"
            PARSED_DATE = month_num "/" sprintf("%02d", $2 + 0)
            PARSED_TIME = normalize_fractional_time($3)
            PARSED_SOURCE1 = proc_token
            PARSED_SOURCE2 = ""
            PARSED_SOURCE3 = ""
            PARSED_PID = ""
            PARSED_MSG = msg

            if (match(proc_token, /\[[0-9]+\]$/)) {
                pid_pos = RSTART
                PARSED_SOURCE1 = substr(proc_token, 1, pid_pos - 1)
                PARSED_PID = substr(proc_token, pid_pos + 1, RLENGTH - 2)
            }

            return 1
        }

        function parse_line() {
            reset_parsed_fields()
            JOUR_PROC = ""
            JOUR_PID = ""

            if (parse_dlt_line()) return 1
            if (parse_syslog_line()) return 1
            return 0
        }

        function format_filter_time(val, format) {
            if (val == "") return ""
            if (time_only == 1) return val
            if (format == "syslog") return substr(val, 6)
            return val
        }

        function line_time_key() {
            if (time_only == 1) return PARSED_TIME
            if (PARSED_FORMAT == "syslog") return PARSED_DATE " " PARSED_TIME
            return PARSED_DATE " " PARSED_TIME
        }

        BEGIN { }
        {
            if (!parse_line()) next

            if (enable_time == 1) {
                current_time = line_time_key()
                start_time = format_filter_time(s, PARSED_FORMAT)
                end_time = format_filter_time(e, PARSED_FORMAT)
                if ((start_time != "" && current_time < start_time) || (end_time != "" && current_time > end_time)) next
            }

            if (f_exclude != "" && $0 ~ f_exclude) next

            has_condition = 0
            is_matched = 0

            if (f_pid != "") {
                has_condition = 1
                if (PARSED_PID ~ f_pid) is_matched = 1
            }

            if (f_source != "" && is_matched == 0) {
                has_condition = 1
                if (PARSED_SOURCE1 ~ f_source || PARSED_SOURCE2 ~ f_source || PARSED_SOURCE3 ~ f_source) is_matched = 1
            }

            if (f_key != "" && is_matched == 0) {
                has_condition = 1
                if ($0 ~ f_key) is_matched = 1
            }

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

PLAIN_MODE=0
FILTER_PID=""
FILTER_SOURCE=""
FILTER_KEY=""
FILTER_EXCLUDE=""
START_TIME=""
END_TIME=""
TIME_ONLY=0
declare -a SEARCH_TARGETS=()

if [[ $# -eq 0 ]]; then
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
    case "$key" in
        -f)
            shift
            while [[ $# -gt 0 ]]; do
                if [[ "$1" == -* ]]; then break; fi
                SEARCH_TARGETS+=("$1")
                shift
            done
            ;;
        -p)
            shift
            _pids=""
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$_pids" ]]; then _pids="$1"; else _pids="${_pids}|$1"; fi
                shift
            done
            if [[ -n "$_pids" ]]; then FILTER_PID="^(${_pids})$"; fi
            ;;
        -s)
            shift
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$FILTER_SOURCE" ]]; then FILTER_SOURCE="$1"; else FILTER_SOURCE="${FILTER_SOURCE}|$1"; fi
                shift
            done
            ;;
        -k)
            shift
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$FILTER_KEY" ]]; then FILTER_KEY="$1"; else FILTER_KEY="${FILTER_KEY}|$1"; fi
                shift
            done
            ;;
        -e)
            shift
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$FILTER_EXCLUDE" ]]; then FILTER_EXCLUDE="$1"; else FILTER_EXCLUDE="${FILTER_EXCLUDE}|$1"; fi
                shift
            done
            ;;
        -t)
            if [[ -n "$2" && "$2" != -* ]]; then
                if ! has_date_prefix "$2"; then TIME_ONLY=1; fi
                START_TIME="$(normalize_time_value "$2")"
                if [[ -n "$3" && "$3" != -* ]] && is_time_arg "$3"; then
                    END_TIME="$(normalize_time_value "$3")"
                    shift 3
                else
                    END_TIME=""
                    shift 2
                fi
            else
                echo "Warning: Option -t requires time args." >&2
                shift 1
            fi
            ;;
        --plain)
            PLAIN_MODE=1
            shift
            ;;
        *)
            if [[ "$1" != -* ]]; then
                SEARCH_TARGETS+=("$1")
                shift 1
            else
                echo "Unknown option: $1"
                show_usage
            fi
            ;;
    esac
done

execute_search "$START_TIME" "$END_TIME" "$TIME_ONLY"
