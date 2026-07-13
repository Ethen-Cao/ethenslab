# Monkey dmabuf black-screen monitor

## Files

- `monkey_dmabuf_black_screen_monitor.py`: main script.
- `blacklist.txt`: local package blacklist. The script pushes it to `/log/blacklist.txt` before starting Monkey.
- `default_config.json`: monitor thresholds.
- `monkey_dmabuf_black_screen_monitor_design.md`: design and bench validation notes.

## One-shot validation

This does not start Monkey. It verifies adb, dumps, dmabuf sampling, screencap, and local output.

```bash
python3 monkey_dmabuf_black_screen_monitor.py --oneshot --config default_config.json --output-root runs
```

If multiple devices are connected, add:

```bash
--serial <device-serial>
```

## Run Monkey

The script default Monkey arguments match the requested command:

```bash
adb shell monkey --pkg-blacklist-file /log/blacklist.txt --ignore-crashes --ignore-timeouts --ignore-security-exceptions --ignore-native-crashes --pct-touch 60 --pct-motion 30 --pct-trackball 0 --pct-syskeys 0 --pct-nav 0 --pct-majornav 0 --pct-appswitch 10 --pct-anyevent 0 --throttle 300 -s 988441 -v -v -v 1152000000
```

Run:

```bash
python3 monkey_dmabuf_black_screen_monitor.py --config default_config.json --output-root runs
```

With an explicit serial:

```bash
python3 monkey_dmabuf_black_screen_monitor.py --serial <device-serial> --config default_config.json --output-root runs
```

## Blacklist handling

By default, before Monkey starts, the script runs:

```bash
adb shell mkdir -p /log
adb push blacklist.txt /log/blacklist.txt
```

To use a different local blacklist:

```bash
python3 monkey_dmabuf_black_screen_monitor.py --blacklist-file ./blacklist.txt
```

To skip pushing the file:

```bash
python3 monkey_dmabuf_black_screen_monitor.py --no-push-blacklist
```

## Output

Each run writes to:

```text
runs/run-YYYYmmdd-HHMMSS/
```

Important files:

- `logcat/all.log`: PC-local `adb logcat -b all -v threadtime` output.
- `monitor.jsonl`: per-sample metrics.
- `events.jsonl`: matched runtime events.
- `monkey.cmd`: exact adb monkey command.
- `triggers/*_pre_stop/` and `triggers/*_post_stop/`: stop-condition snapshots.

