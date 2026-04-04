#!/bin/bash

set -euo pipefail

COLOR_RESET=$'\033[0m'
COLOR_FILE=$'\033[35m'
COLOR_LINE=$'\033[32m'
STREAM_SEP=$'\037'
CMD_NAME="$(basename "$0")"

function show_usage() {
    cat <<EOF
Usage: ${CMD_NAME} [options] [file/dir...]

Options:
  -f <paths...>           Specify files/dirs to search
  -p <pid...>             Filter by PID regex; repeatable
  -s <source...>          Filter by source/tag regex; repeatable
  -k <keyword...>         Filter by keyword regex; repeatable
  -e <keyword...>         Exclude keyword regex; repeatable
  -i, --ignore-case       Ignore case for source/keyword matching
  -t <start> <end>        Time range: HH:MM[:SS[.frac]] or "YYYY-MM-DD HH:MM[:SS[.frac]]"
  --plain                 Output plain text (no file:line prefix)
  -h, --help              Show this help
  --                      End options; following args are treated as paths

Notes:
  - -p/-s/-k/-e accept one or more values and stop at the next option.
  - To avoid ambiguity with positional paths, prefer -f or -- before paths.
  - Raw .dlt files are skipped; convert them to text before running this script.
  - Logic: Time AND (NOT Exclude) AND ( PID OR Source OR Keyword )
EOF
}

function die() {
    echo "Error: $*" >&2
    exit 1
}

function warn() {
    echo "Warning: $*" >&2
}

function normalize_time_fragment() {
    local value="$1"
    local hh mm ss frac

    if [[ "$value" =~ ^([0-9]{2}):([0-9]{2})$ ]]; then
        printf '%s:%s:00.000000\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
        return 0
    fi

    if [[ "$value" =~ ^([0-9]{2}):([0-9]{2}):([0-9]{2})(\.([0-9]{1,6}))?$ ]]; then
        hh="${BASH_REMATCH[1]}"
        mm="${BASH_REMATCH[2]}"
        ss="${BASH_REMATCH[3]}"
        frac="${BASH_REMATCH[5]:-}"
        while ((${#frac} < 6)); do
            frac+="0"
        done
        frac="${frac:0:6}"
        if [[ -z "$frac" ]]; then
            frac="000000"
        fi
        printf '%s:%s:%s.%s\n' "$hh" "$mm" "$ss" "$frac"
        return 0
    fi

    return 1
}

function normalize_datetime_filter() {
    local value="$1"
    local date_part time_part normalized_time

    if [[ "$value" =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2})[[:space:]]+(.+)$ ]]; then
        date_part="${BASH_REMATCH[1]}"
        time_part="${BASH_REMATCH[2]}"
        normalized_time="$(normalize_time_fragment "$time_part")" || return 1
        printf '%sT%s\n' "$date_part" "$normalized_time"
        return 0
    fi

    return 1
}

function append_values_until_boundary() {
    local -n out_array="$1"
    local mode="$2"
    local -n arg_array="$3"
    local -n index_ref="$4"
    local start_count="${#out_array[@]}"

    while (( index_ref < ${#arg_array[@]} )); do
        local candidate="${arg_array[index_ref]}"

        if [[ "$candidate" == -- || "$candidate" == -* ]]; then
            break
        fi

        if [[ "$mode" == "filter" && ${#out_array[@]} -gt "$start_count" && -e "$candidate" ]]; then
            break
        fi

        out_array+=("$candidate")
        index_ref=$((index_ref + 1))
    done

    if (( ${#out_array[@]} == start_count )); then
        die "Option requires at least one value"
    fi
}

function join_regex_array() {
    local -n in_array="$1"
    local joined=""
    local value

    for value in "${in_array[@]}"; do
        if [[ -z "$joined" ]]; then
            joined="$value"
        else
            joined="${joined}|${value}"
        fi
    done

    printf '%s\n' "$joined"
}

function prefilter_text_files_by_keyword() {
    local list_file="$1"
    local keyword_regex="$2"
    local filtered_list="${list_file}.filtered"
    local rg_cmd

    if [[ -z "$keyword_regex" || ! -s "$list_file" ]]; then
        return 0
    fi

    if ! rg_cmd="$(command -v rg 2>/dev/null)"; then
        return 0
    fi

    if [[ "$IGNORE_CASE" -eq 1 ]]; then
        xargs -0 "$rg_cmd" -0 -l -m 1 -i -e "$keyword_regex" -- < "$list_file" > "$filtered_list" 2>/dev/null || true
    else
        xargs -0 "$rg_cmd" -0 -l -m 1 -e "$keyword_regex" -- < "$list_file" > "$filtered_list" 2>/dev/null || true
    fi

    cat "$filtered_list" > "$list_file"
}

function emit_text_input_stream() {
    local list_file="$1"
    local rg_cmd

    if [[ ! -s "$list_file" ]]; then
        return 0
    fi

    if [[ -n "$FILTER_KEY" && -z "$FILTER_PID" && -z "$FILTER_SOURCE" ]] && rg_cmd="$(command -v rg 2>/dev/null)"; then
        if [[ "$IGNORE_CASE" -eq 1 ]]; then
            xargs -0 "$rg_cmd" -H -n --no-heading -i -e "$FILTER_KEY" -- < "$list_file" 2>/dev/null | awk -F ":" -v sep="$STREAM_SEP" '
                {
                    file = $1
                    line = $2
                    content = substr($0, length(file) + length(line) + 3)
                    printf "TEXT%s%s%s%d%s%s\n", sep, file, sep, line + 0, sep, content
                }
            '
        else
            xargs -0 "$rg_cmd" -H -n --no-heading -e "$FILTER_KEY" -- < "$list_file" 2>/dev/null | awk -F ":" -v sep="$STREAM_SEP" '
                {
                    file = $1
                    line = $2
                    content = substr($0, length(file) + length(line) + 3)
                    printf "TEXT%s%s%s%d%s%s\n", sep, file, sep, line + 0, sep, content
                }
            '
        fi
        return 0
    fi

    xargs -0 awk \
        -v sep="$STREAM_SEP" \
        '
        {
            printf "TEXT%s%s%s%d%s%s\n", sep, FILENAME, sep, FNR, sep, $0
        }
        ' < "$list_file"
}

function build_file_lists() {
    local text_list="$1"
    local search_found=0
    local target
    local path

    if [[ ${#SEARCH_TARGETS[@]} -eq 0 ]]; then
        SEARCH_TARGETS=(".")
    fi

    for target in "${SEARCH_TARGETS[@]}"; do
        if [[ ! -e "$target" ]]; then
            warn "Search target not found: $target"
            continue
        fi

        if [[ -f "$target" ]]; then
            if [[ "$target" == *.dlt ]]; then
                SKIPPED_DLT_COUNT=$((SKIPPED_DLT_COUNT + 1))
            else
                search_found=1
                printf '%s\0' "$target" >> "$text_list"
            fi
            continue
        fi

        while IFS= read -r -d '' path; do
            if [[ "$path" == *.dlt ]]; then
                SKIPPED_DLT_COUNT=$((SKIPPED_DLT_COUNT + 1))
            else
                search_found=1
                printf '%s\0' "$path" >> "$text_list"
            fi
        done < <(LC_ALL=C find "$target" -type f -not -path '*/.*' -print0)
    done

    return 0
}

PLAIN_MODE=0
IGNORE_CASE=0
TIME_FILTER_MODE="none"
START_FILTER=""
END_FILTER=""
SKIPPED_DLT_COUNT=0
declare -a SEARCH_TARGETS=()
declare -a PID_VALUES=()
declare -a SOURCE_VALUES=()
declare -a KEY_VALUES=()
declare -a EXCLUDE_VALUES=()

if [[ $# -eq 0 ]]; then
    SEARCH_TARGETS=(".")
else
    ARGS=("$@")
    ARG_INDEX=0

    while (( ARG_INDEX < ${#ARGS[@]} )); do
        ARG="${ARGS[ARG_INDEX]}"

        case "$ARG" in
            -f)
                ARG_INDEX=$((ARG_INDEX + 1))
                append_values_until_boundary SEARCH_TARGETS path ARGS ARG_INDEX
                ;;
            -p)
                ARG_INDEX=$((ARG_INDEX + 1))
                append_values_until_boundary PID_VALUES filter ARGS ARG_INDEX
                ;;
            -s)
                ARG_INDEX=$((ARG_INDEX + 1))
                append_values_until_boundary SOURCE_VALUES filter ARGS ARG_INDEX
                ;;
            -k)
                ARG_INDEX=$((ARG_INDEX + 1))
                append_values_until_boundary KEY_VALUES filter ARGS ARG_INDEX
                ;;
            -e)
                ARG_INDEX=$((ARG_INDEX + 1))
                append_values_until_boundary EXCLUDE_VALUES filter ARGS ARG_INDEX
                ;;
            -i|--ignore-case)
                IGNORE_CASE=1
                ARG_INDEX=$((ARG_INDEX + 1))
                ;;
            -t)
                ARG_INDEX=$((ARG_INDEX + 1))
                if (( ARG_INDEX + 1 >= ${#ARGS[@]} )); then
                    die "-t requires <start> <end>"
                fi
                RAW_START="${ARGS[ARG_INDEX]}"
                RAW_END="${ARGS[ARG_INDEX + 1]}"

                if [[ -n "$RAW_START" ]]; then
                    if START_FILTER="$(normalize_datetime_filter "$RAW_START")"; then
                        TIME_FILTER_MODE="datetime"
                    elif START_FILTER="$(normalize_time_fragment "$RAW_START")"; then
                        TIME_FILTER_MODE="clock"
                    else
                        die "Invalid start time: $RAW_START"
                    fi
                fi

                if [[ -n "$RAW_END" ]]; then
                    if END_FILTER_TMP="$(normalize_datetime_filter "$RAW_END")"; then
                        if [[ "$TIME_FILTER_MODE" != "none" && "$TIME_FILTER_MODE" != "datetime" ]]; then
                            die "Start and end time filters must use the same format family"
                        fi
                        END_FILTER="$END_FILTER_TMP"
                        TIME_FILTER_MODE="datetime"
                    elif END_FILTER_TMP="$(normalize_time_fragment "$RAW_END")"; then
                        if [[ "$TIME_FILTER_MODE" != "none" && "$TIME_FILTER_MODE" != "clock" ]]; then
                            die "Start and end time filters must use the same format family"
                        fi
                        END_FILTER="$END_FILTER_TMP"
                        TIME_FILTER_MODE="clock"
                    else
                        die "Invalid end time: $RAW_END"
                    fi
                fi

                ARG_INDEX=$((ARG_INDEX + 2))
                ;;
            --plain)
                PLAIN_MODE=1
                ARG_INDEX=$((ARG_INDEX + 1))
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            --)
                ARG_INDEX=$((ARG_INDEX + 1))
                while (( ARG_INDEX < ${#ARGS[@]} )); do
                    SEARCH_TARGETS+=("${ARGS[ARG_INDEX]}")
                    ARG_INDEX=$((ARG_INDEX + 1))
                done
                ;;
            -*)
                die "Unknown option: $ARG"
                ;;
            *)
                SEARCH_TARGETS+=("$ARG")
                ARG_INDEX=$((ARG_INDEX + 1))
                ;;
        esac
    done
fi

FILTER_PID="$(join_regex_array PID_VALUES)"
FILTER_SOURCE="$(join_regex_array SOURCE_VALUES)"
FILTER_KEY="$(join_regex_array KEY_VALUES)"
FILTER_EXCLUDE="$(join_regex_array EXCLUDE_VALUES)"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEXT_LIST="$TMP_DIR/text_files.list"

: > "$TEXT_LIST"

build_file_lists "$TEXT_LIST"

if (( SKIPPED_DLT_COUNT > 0 )); then
    warn "Skipped ${SKIPPED_DLT_COUNT} raw .dlt files; convert them to text before running ${CMD_NAME}"
fi

if [[ ! -s "$TEXT_LIST" ]]; then
    die "No readable text log files found under the given search targets"
fi

emit_text_input_stream "$TEXT_LIST" | awk \
    -F "$STREAM_SEP" \
    -v sep="$STREAM_SEP" \
    -v plain="$PLAIN_MODE" \
    -v f_pid="$FILTER_PID" \
    -v f_source="$FILTER_SOURCE" \
    -v f_key="$FILTER_KEY" \
    -v f_exclude="$FILTER_EXCLUDE" \
    -v ignore_case="$IGNORE_CASE" \
    -v time_mode="$TIME_FILTER_MODE" \
    -v start_filter="$START_FILTER" \
    -v end_filter="$END_FILTER" \
    -v c_file="$COLOR_FILE" \
    -v c_line="$COLOR_LINE" \
    -v c_reset="$COLOR_RESET" \
    -v current_year="$(date +%Y)" \
    -v current_month="$(date +%m)" \
    -v current_day="$(date +%d)" \
    '
    BEGIN {
        if (ignore_case == 1) {
            IGNORECASE = 1
        }
    }

    function trim(s) {
        sub(/^[[:space:]]+/, "", s)
        sub(/[[:space:]]+$/, "", s)
        return s
    }

    function month_to_num(mon) {
        return (mon == "Jan" ? 1 : mon == "Feb" ? 2 : mon == "Mar" ? 3 : mon == "Apr" ? 4 : \
                mon == "May" ? 5 : mon == "Jun" ? 6 : mon == "Jul" ? 7 : mon == "Aug" ? 8 : \
                mon == "Sep" ? 9 : mon == "Oct" ? 10 : mon == "Nov" ? 11 : mon == "Dec" ? 12 : 0)
    }

    function is_leap(year) {
        return ((year % 4 == 0 && year % 100 != 0) || (year % 400 == 0))
    }

    function days_in_month(year, month) {
        return (month == 1 ? 31 : month == 2 ? (is_leap(year) ? 29 : 28) : month == 3 ? 31 : \
                month == 4 ? 30 : month == 5 ? 31 : month == 6 ? 30 : month == 7 ? 31 : \
                month == 8 ? 31 : month == 9 ? 30 : month == 10 ? 31 : month == 11 ? 30 : 31)
    }

    function day_of_year(year, month, day,    idx, total) {
        total = 0
        for (idx = 1; idx < month; idx++) {
            total += days_in_month(year, idx)
        }
        return total + day
    }

    function normalize_clock(raw,    m, frac) {
        if (match(raw, /^([0-9]{2}):([0-9]{2})$/, m)) {
            return m[1] ":" m[2] ":00.000000"
        }

        if (match(raw, /^([0-9]{2}):([0-9]{2}):([0-9]{2})(\.([0-9]+))?$/, m)) {
            frac = m[5]
            if (frac == "") {
                frac = "000000"
            } else {
                while (length(frac) < 6) {
                    frac = frac "0"
                }
                frac = substr(frac, 1, 6)
            }
            return m[1] ":" m[2] ":" m[3] "." frac
        }

        return ""
    }

    function extract_anchor_date(path,    remaining, piece, candidate, offset) {
        remaining = path
        candidate = ""
        offset = 1

        while (match(remaining, /20[0-9]{6}/)) {
            candidate = substr(remaining, RSTART, RLENGTH)
            remaining = substr(remaining, RSTART + RLENGTH)
            offset += RSTART + RLENGTH - 1
        }

        return candidate
    }

    function init_anchor(path,    anchor) {
        if (path in anchor_year_cache) {
            return
        }

        anchor = extract_anchor_date(path)
        if (anchor != "") {
            anchor_year_cache[path] = substr(anchor, 1, 4) + 0
            anchor_month_cache[path] = substr(anchor, 5, 2) + 0
            anchor_day_cache[path] = substr(anchor, 7, 2) + 0
            return
        }

        anchor_year_cache[path] = current_year + 0
        anchor_month_cache[path] = current_month + 0
        anchor_day_cache[path] = current_day + 0
    }

    function infer_year(path, month, day,    year, anchor_ord, line_ord, delta) {
        init_anchor(path)
        year = anchor_year_cache[path]
        anchor_ord = day_of_year(year, anchor_month_cache[path], anchor_day_cache[path])
        line_ord = day_of_year(year, month, day)
        delta = line_ord - anchor_ord

        if (delta > 183) {
            year--
        } else if (delta < -183) {
            year++
        }

        return year
    }

    function time_matches(sort_key, clock_key) {
        if (time_mode == "none") {
            return 1
        }

        if (time_mode == "datetime") {
            if (start_filter != "" && sort_key < start_filter) {
                return 0
            }
            if (end_filter != "" && sort_key > end_filter) {
                return 0
            }
            return 1
        }

        if (time_mode == "clock") {
            if (start_filter != "" && end_filter != "") {
                if (start_filter <= end_filter) {
                    return (clock_key >= start_filter && clock_key <= end_filter)
                }
                return (clock_key >= start_filter || clock_key <= end_filter)
            }

            if (start_filter != "" && clock_key < start_filter) {
                return 0
            }
            if (end_filter != "" && clock_key > end_filter) {
                return 0
            }
        }

        return 1
    }

    function emit_record(file_path, line_no, raw_line, sort_key, clock_key, pid, source,    has_filter, matched, display) {
        if (!time_matches(sort_key, clock_key)) {
            return
        }

        if (f_exclude != "" && raw_line ~ f_exclude) {
            return
        }

        has_filter = (f_pid != "" || f_source != "" || f_key != "")
        matched = 0

        if (f_pid != "" && pid != "" && pid ~ f_pid) {
            matched = 1
        }
        if (!matched && f_source != "" && source != "" && source ~ f_source) {
            matched = 1
        }
        if (!matched && f_key != "" && raw_line ~ f_key) {
            matched = 1
        }

        if (has_filter && !matched) {
            return
        }

        if (plain == 1) {
            display = raw_line
        } else {
            display = sprintf("%s%s%s:%s%d%s: %s", c_file, file_path, c_reset, c_line, line_no, c_reset, raw_line)
        }

        printf "%s%s%s%s%012d%s%s\n", sort_key, sep, file_path, sep, line_no, sep, display
    }

    function parse_dlt_text(file_path, line_no, raw_line,    fields, field_count, clock_key, date_parts, sort_key, pid, source) {
        field_count = split(raw_line, fields, /[[:space:]]+/)
        if (field_count < 8) {
            return 0
        }
        if (fields[1] !~ /^[0-9]+$/ || fields[2] !~ /^[0-9]{4}\/[0-9]{2}\/[0-9]{2}$/) {
            return 0
        }

        clock_key = normalize_clock(fields[3])
        if (clock_key == "") {
            return 0
        }

        split(fields[2], date_parts, "/")
        sort_key = date_parts[1] "-" date_parts[2] "-" date_parts[3] "T" clock_key
        pid = (fields[5] ~ /^[0-9]+$/ ? fields[5] : "")
        source = fields[6] "/" fields[7] "/" fields[8]
        emit_record(file_path, line_no, raw_line, sort_key, clock_key, pid, source)
        return 1
    }

    function parse_text(file_path, line_no, raw_line,    clock_key, sort_key, month, day, year, pid, source, rest, colon_idx, day_token, month_num, fields) {
        if (match(raw_line, /^([0-9]{2})-([0-9]{2})[[:space:]]+([0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?)[[:space:]]+([0-9]+)[[:space:]]+([0-9]+)[[:space:]]+[A-Z][[:space:]]+(.+)$/, a)) {
            month = a[1] + 0
            day = a[2] + 0
            clock_key = normalize_clock(a[3])
            year = infer_year(file_path, month, day)
            sort_key = sprintf("%04d-%02d-%02dT%s", year, month, day, clock_key)
            pid = a[5]
            rest = a[7]
            colon_idx = index(rest, ":")
            if (colon_idx > 0) {
                source = trim(substr(rest, 1, colon_idx - 1))
            } else {
                source = trim(rest)
            }
            emit_record(file_path, line_no, raw_line, sort_key, clock_key, pid, source)
            return
        }

        split(raw_line, fields, /[[:space:]]+/)

        if (parse_dlt_text(file_path, line_no, raw_line)) {
            return
        }

        if (fields[1] ~ /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/) {
            clock_key = normalize_clock(fields[2])
            if (clock_key != "") {
                sort_key = fields[1] "T" clock_key
                pid = (fields[6] ~ /^[0-9]+$/ ? fields[6] : "")
                source = fields[5]
                emit_record(file_path, line_no, raw_line, sort_key, clock_key, pid, source)
                return
            }
        }

        if (match(raw_line, /^([A-Z][a-z]{2})[[:space:]]+([ 0-9][0-9])[[:space:]]+([0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?)[[:space:]]+(.+)$/, a)) {
            month_num = month_to_num(a[1])
            if (month_num == 0) {
                return
            }
            day_token = trim(a[2])
            day = day_token + 0
            clock_key = normalize_clock(a[3])
            year = infer_year(file_path, month_num, day)
            sort_key = sprintf("%04d-%02d-%02dT%s", year, month_num, day, clock_key)
            pid = ""
            source = ""
            rest = a[5]
            if (match(rest, /^[^[:space:]]+[[:space:]]+([^[:space:]:\[]+)(\[([0-9]+)\])?:/, b)) {
                source = b[1]
                pid = b[3]
            } else if (match(rest, /^([^[:space:]:\[]+)(\[([0-9]+)\])?:/, b)) {
                source = b[1]
                pid = b[3]
            } else if (match(rest, /^[^[:space:]]+[[:space:]]+([^[:space:]:]+):/, b)) {
                source = b[1]
            } else if (match(rest, /^([^[:space:]:]+):/, b)) {
                source = b[1]
            } else {
                source = rest
            }
            emit_record(file_path, line_no, raw_line, sort_key, clock_key, pid, source)
        }
    }

    {
        record_type = $1
        file_path = $2
        line_no = $3 + 0
        raw_line = $4

        if (record_type == "TEXT") {
            parse_text(file_path, line_no, raw_line)
        }
    }
    ' | LC_ALL=C sort -t "$STREAM_SEP" -s -k1,1 -k2,2 -k3,3n | awk -F "$STREAM_SEP" '
    {
        sub("^[^" FS "]*" FS "[^" FS "]*" FS "[^" FS "]*" FS, "", $0)
        print
    }
    '
