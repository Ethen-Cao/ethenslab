# SA8397 Thermal-Engine GPU 调频原理和策略

## 1. 背景

当前项目的 PVM 侧运行 Qualcomm `thermal-engine`，用于监控芯片温度并对 CPU/GPU/CDSP/ADSP 等设备做热管理限频或告警。

本文聚焦 SA8397 项目中 `thermal-engine` 对 GPU 的调频策略。源码主要位于：

```text
vendor/qcom/proprietary/thermal-engine/
```

核心文件：

```text
thermal.c
ss-data.c
ss_algorithm.c
thermal_monitor-data.c
thermal_monitor.c
devices/devices.c
devices/devices_actions.c
devices/devices_manager.c
```

## 2. 初始化路径

`thermal-engine` 启动后会根据 softsku 判断当前软件配置类型：

```c
if (thermal_non_safe_config) {
    thermal_init_devices();
} else {
    thermal_init_devices_adas();
}
```

non-safe IVI 路径会初始化 GPU 调频：

```c
void thermal_init_devices(void)
{
    devices_manager_init();
    devices_init(minimum_mode);
    sensors_manager_init();
    sensors_init(minimum_mode);
    init_settings(&thermal_settings);
    thermal_monitor_init_data_non_safe(&thermal_settings);
    ss_init_data(&thermal_settings);
    load_config(&thermal_settings, config_file, LOAD_ALL_FLAG);
    thermal_monitor(&thermal_settings);
    ss_algo_init(&thermal_settings);
}
```

其中：

- `devices_init()` 注册可被调节的设备，包括 `gpu0` / `gpu1`。
- `thermal_monitor_init_data_non_safe()` 注册 PMIC die 温度触发的固定阈值策略。
- `ss_init_data()` 注册 GPU 本体温度闭环控制策略。
- `thermal_monitor()` 启动 monitor 阈值算法。
- `ss_algo_init()` 启动 steady state 闭环算法。

ADAS / safe IVI / flex 路径调用 `thermal_init_devices_adas()`，当前源码中只注册 safety monitor/report 相关设备，不注册 `gpu0` / `gpu1`，也不启动 `ss_init_data()`。

## 3. GPU 设备注册

GPU 设备注册在 `devices/devices.c`：

```c
gpufreq_init();
tmd_init_gpu_devs();
```

`gpufreq_init()` 当前硬编码：

```c
num_gpus = 2;
```

`tmd_init_gpu_devs()` 对 `gpu0` 和 `gpu1` 分别执行：

```c
gsl_profiler_get_gpu_clock_frequency_plan(idx, freqtable_data);
num_freqs = freqtable_data->num_levels;
gpu_numfreq[idx] = num_freqs;
snprintf(dev->dev_info.name, DEVICES_MAX_NAME_LEN, "gpu%d", idx);
```

然后把 GPU 注册为 thermal-engine 内部 device：

```c
dev->dev_info.num_of_levels = num_freqs - 1;
dev->dev_info.dev_type = DEVICE_CDEV_TYPE;
dev->dev_info.min_lvl = 0;
dev->dev_info.max_dev_op_value = dev->lvl_info[num_freqs - 2].lvl.value;
dev->active_req.value = dev->dev_info.min_dev_op_value;
dev->action = gpu_action;
devices_manager_add_dev(dev);
```

这里的 `lvl.value` 不是 Hz 频率值，而是 thermal-engine 内部 mitigation level。源码虽然把 `device_units_name` 设置为 `Hz`，但实际下发的是 level。

## 4. 实际下发方式

GPU 限频不直接写 `/sys/class/kgsl/kgsl-3d*/max_gpuclk`，当前实现通过 PM server 通知 KGSL：

```c
static char *kgsl_nodes[MAX_GPUS] = {
    "kgsl@0",
    "kgsl@1",
};

int gpufreq_set(int gpu, int freq_level, int cdev_id)
{
    char *kgsl_node = kgsl_nodes[gpu];

    if (pm_send_notif(kgsl_node, "impose", freq_level) == 0) {
        msg("GPU[%d] frequency level limited to %d\n", gpu, freq_level);
        return 0;
    }

    msg("Failed to set desired GPU[%d] frequency level limit to %d\n",
        gpu, freq_level);
    return 1;
}
```

也就是：

```text
thermal-engine request -> devices_manager -> gpu_action
  -> gpufreq_request()
  -> gpufreq_set()
  -> pm_send_notif("kgsl@0/1", "impose", level)
  -> PM server / KGSL 执行 GPU 限频
```

Yocto 侧对 service 也保证 thermal-engine 在 KGSL 后启动：

```ini
[Unit]
After=safetymonitor.service kgsl.service
```

## 5. Level 映射逻辑

thermal-engine 内部对 GPU 的 request value 是 `frequency` 参数，但实际表示 mitigation level。

`gpufreq_request()` 中会做一次反向映射：

```c
int max_freq = gpu_numfreq[gpu] - 1;
int mit_freq_level = max_freq - frequency;

gpu_freq_req[gpu] = mit_freq_level;

if ((gpu_freq_req[gpu] > 0) && (gpu_freq_req[gpu] < max_freq))
    max_freq = gpu_freq_req[gpu];

if (max_freq != prev_gpu_max[gpu]) {
    gpufreq_set(gpu, max_freq, cdev_id);
    prev_gpu_max[gpu] = max_freq;
}
```

含义：

- thermal-engine 的 `frequency` 越大，转换后的 `mit_freq_level` 越小。
- 最终下发给 `kgsl@N impose` 的是 `max_freq` 变量，实际是限制 level。
- `prev_gpu_max` 用于避免重复下发相同 level。

需要注意，这段命名存在误导：`max_freq` 并不是实际频率，`frequency` 也不是 Hz，而是 level。

## 6. 多个温度源同时调节同一 GPU

`devices_manager` 对不同 client 的 request 做聚合。GPU 注册为 `DEVICE_CDEV_TYPE`，聚合逻辑是取所有 active request 的最大值：

```c
req.value = dev_mgr->dev_info.min_lvl;

while (client != NULL) {
    if (client->request_active)
        req.value = MAX(req.value, client->request.value);
    client = client->next_clnt;
}
```

因此：

- 多个传感器同时作用 `gpu0` 时，取最强 mitigation request。
- 任一传感器高温都可以拉低 GPU 性能。
- 当某个 client 清除 request 后，`devices_manager` 会重新聚合剩余 client 的 request。

## 7. SS_GPU 闭环控制策略

`ss-data.c` 中定义了 GPU 本体温度的 steady state 策略。

`gpu0` 受以下 sensor 控制：

```text
gpuss-0-0-0-0
gpuss-0-0-1-1
gpucore-0-1-0
gpucore-0-0-1
```

`gpu1` 受以下 sensor 控制：

```text
gpuss-1-0
gpuss-1-1
gpuss-1-2
gpucore-1-0
```

每个 SS_GPU 配置相同：

```c
.sampling_period_ms = 100,
.set_point = 105000,
.set_point_clr = 101000,
.time_constant = 0,
```

单位是 milli-Celsius：

```text
set_point     = 105000 = 105 C
set_point_clr = 101000 = 101 C
sampling      = 100 ms
```

算法在 `ss_algorithm.c`：

```c
error = active_set_point - temp;

if (E0 < 0 || (E0 == 0 && curr_lvl <= 0)) {
    increase_mitigation_lvl(&algo_clnt[idx]);
} else {
    decrease_mitigation_lvl(&algo_clnt[idx]);
}
```

行为：

- 温度达到 `105 C` 后进入 sampling 状态。
- 每 100ms 读取一次温度。
- `temp > set_point` 时，逐级增加 mitigation。
- `temp < set_point` 时，逐级降低 mitigation。
- 温度低于 `101 C` 后，退出闭环，取消该 client 的 GPU request。

触发/清除状态机：

```c
if (STOP 状态 && temp >= active_set_point) {
    state = SS_STATE_START_SAMPLING;
} else if (START/STOP_SAMPLING 状态 && temp <= active_set_point_clr) {
    state = SS_STATE_STOP_ALGO;
}
```

清除时会取消 device request：

```c
device_clnt_cancel_request(algo_clnt[idx].dev_clnt);
```

## 8. PMIC 过温固定阈值策略

除了 GPU 本体传感器闭环控制，`thermal_monitor-data.c` 里还有 non-safe 的 PMIC die 温度固定阈值策略：

### PMIC_KAI_I_GPU0

```c
.sensor = "pm-i-die-temp",
.sampling_period_ms = 500,
.lvl_trig = 115000,
.lvl_clr = 110000,
.actions[0] = {
    .device = "gpu0",
    .info = 5,
},
```

含义：

- `pm-i-die-temp >= 115 C` 时，对 `gpu0` 下发 request level `5`。
- `pm-i-die-temp <= 110 C` 时清除 request。

### PMIC_KAI_J_GPU1

```c
.sensor = "pm-j-die-temp",
.sampling_period_ms = 500,
.lvl_trig = 115000,
.lvl_clr = 110000,
.actions[0] = {
    .device = "gpu1",
    .info = 4,
},
```

含义：

- `pm-j-die-temp >= 115 C` 时，对 `gpu1` 下发 request level `4`。
- `pm-j-die-temp <= 110 C` 时清除 request。

### PMIC_KOBRA_A_GPU_DSP

```c
.sensor = "pm-a-die-temp",
.sampling_period_ms = 500,
.lvl_trig = 115000,
.lvl_clr = 110000,
.actions[0] = {
    .device = "gpu0",
    .info = 5,
},
.actions[1] = {
    .device = "gpu1",
    .info = 4,
},
```

含义：

- `pm-a-die-temp >= 115 C` 时，同时限制 `gpu0=5`、`gpu1=4`，并限制 CDSP/ADSP。
- `pm-a-die-temp <= 110 C` 后清除 request。

## 9. Monitor 阈值算法行为

monitor 算法通过 `sensor_threshold_trigger()` / `sensor_threshold_clear()` 判断阈值跨越。

触发时：

```c
req.value = action_info;
device_clnt_request(sensor->dev_clnt_list[action_idx], &req);
```

清除所有 alarm 时：

```c
device_clnt_cancel_request(sensor->dev_clnt_list[i]);
```

因此 PMIC 过温策略是“固定 level 限制”，不是闭环逐级调节。

## 10. 与内核 thermal cooling device 的关系

源码中保留了 cooling device 相关逻辑：

```c
#define GPU_COOLING_DEV_NAME  "thermal-devfreq-0"
#define GPU_COOLING_DEV_NAME1 "gpu"
```

也有 `get_cdevn()`、`CDEV_CUR_STATE` 等逻辑。但当前 GPU 注册路径中：

```c
// init_cooling_device(dev);
```

被注释掉了。因此 SA8397 当前实现并不主要依赖 `/sys/class/thermal/cooling_device*/cur_state` 来调 GPU，而是走 `pm_send_notif("kgsl@N", "impose", level)`。

## 11. 当前台架观察

在当前台架上：

```text
thermal-engine.service active
ExecStart=/usr/bin/thermal-engine
Drop-In=/etc/systemd/system/thermal-engine.service.d/thermal-engine_sa8775.conf
```

系统中存在 GPU thermal zone：

```text
gpuss-0-0-0-0
gpuss-0-1-0-0
gpuss-0-2-0-0
gpucore-0-0-0
gpuss-1-0
gpuss-1-1
gpuss-1-2
gpucore-1-0
...
```

当前 journal 没看到 GPU mitigation 记录，可能是未触发过 GPU 热限制，或启动早期日志已经轮转。

## 12. 调试建议

查看 thermal-engine 是否运行：

```sh
adb -s e66b06ea shell 'systemctl status thermal-engine --no-pager'
```

查看 GPU thermal zone：

```sh
adb -s e66b06ea shell '
for z in /sys/class/thermal/thermal_zone*/type; do
    v=$(cat "$z" 2>/dev/null)
    case "$v" in
        *gpu*|*GPU*|*kgsl*|*KGSL*) echo ${z%/type}:$v;;
    esac
done
'
```

查看当前温度：

```sh
adb -s e66b06ea shell '
for z in /sys/class/thermal/thermal_zone*/type; do
    v=$(cat "$z" 2>/dev/null)
    case "$v" in
        gpuss*|gpucore*)
            d=${z%/type}
            echo "$v $(cat $d/temp 2>/dev/null)"
        ;;
    esac
done
'
```

查看 GPU mitigation 日志：

```sh
adb -s e66b06ea shell '
journalctl -b --no-pager |
grep -Ei "thermal-engine|GPU\\[[0-9]\\]|SS_GPU|PMIC_.*GPU|kgsl@|impose|frequency level|Init GPU|Number of gpus"
'
```

如果要确认实际下发到 PM server 的 level，需要在 `gpufreq_set()` 附近增加日志，或者观察 PM server / KGSL 侧对 `kgsl@0/1 impose` 的处理日志。

## 13. 策略摘要

SA8397 当前 thermal-engine 对 GPU 的调频可以概括为：

```text
GPU 本体温度:
  gpuss/gpucore sensor >= 105 C
    -> SS 算法每 100ms 闭环调节 gpu0/gpu1 level
  gpuss/gpucore sensor <= 101 C
    -> 清除该传感器对应的 GPU request

PMIC die 温度:
  pm-i-die-temp >= 115 C
    -> gpu0 固定 request 5
  pm-j-die-temp >= 115 C
    -> gpu1 固定 request 4
  pm-a-die-temp >= 115 C
    -> gpu0 固定 request 5, gpu1 固定 request 4, 同时限制 DSP
  PMIC die 温度 <= 110 C
    -> 清除对应 request

多个 request 同时存在:
  devices_manager 对 gpu0/gpu1 取最大 request value
    -> 最强限制生效

实际下发:
  pm_send_notif("kgsl@0/1", "impose", level)
```
