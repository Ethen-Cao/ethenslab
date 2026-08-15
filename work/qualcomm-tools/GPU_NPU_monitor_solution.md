## 背景
智能座舱芯片
Soc:sa8397
软件：Yocto Linux + qcrosvm + Android Guset

## 目标
常态监视 GPU, NPU的使用率。

## 功能

1. 每分钟上报一次GPU,NPU的使用率
2. 当GPU/NPU的使用率超过95%,要产生一条告警信息
3. 当GPU/NPU的使用率降低到90%以下,要产生一条状态恢复正常的信息
4. 当GPU使用率超过95%，使用qprof统计一分钟的GPU per process的详情，保存到/log/perf/qprof目录
5. 持续高于95%,不会一直产生告警，也不会再次运行qprof
6. 上报的字节数要小于700字节

  
## 约束
1. 对系统要无感，CPU，内存要极致的小
2. 安全稳定，不引入不可控风险

## 参考信息
1. 使用adb shell可以查看qprof支持的能力：
   ```txt
    root@sa8797:~# export PATH=/var/QualcommProfiler/bins/:$PATH
    root@sa8797:~# export LD_LIBRARY_PATH=/var/QualcommProfiler/libs
    root@sa8797:~# qprof -h
   ```
2. 如何查看某个capbility的所支持的metrics id:
   ```txt
    root@sa8797:~# qprof --metrics-info --capabilities-list profiler:proc-gpu-specif
        ic-metrics
        [DRM_FE] drm_fe_dbg_init(413)::drm fe debug is not enabled
        gbm_create_device(172): Info: backend name is: ki-umd
        gbm_create_device(172): Info: backend name is: ki-umd

        --------------------------------------------------------------------------------------------------------------------------------------------------
        Capability: GPU Processor (profiler:proc-gpu-specific-metrics)
        --------------------------------------------------------------------------------------------------------------------------------------------------
        ID     Name                             Unit             Description                                                                                                                     
        --------------------------------------------------------------------------------------------------------------------------------------------------
        4864   GPU Clocks Cycle Executed        Mhz              Number of GPU clocks per second.
        4865   GPU Utilization                  %                Percentage utilization of the GPU's maximum performance (i.e. max clock frequency)
        4866   GPU Memory Bus Busy              %                Approximate percentage of time the GPU's bus to system memory is busy.
        4867   GPU Memory Read Total            bytes/sec        Total number of bytes read by the GPU from memory, per second.
        4868   GPU Memory Write Total           bytes/sec        Total number of bytes written by the GPU to memory, per second.
        -------------------------------------------------------------------------------------------------------------------------------------------------
    ```

3. qprof支持的能力：
   ```txt
    root@sa8797:~# qprof --capabilities
    [DRM_FE] drm_fe_dbg_init(413)::drm fe debug is not enabled
    gbm_create_device(172): Info: backend name is: ki-umd
    gbm_create_device(172): Info: backend name is: ki-umd

    Friendly Name                                      Capability                Streaming Rate(s)         Sampling Rate(s)               Available Metric(s)           
    -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    CPU                           profiler:apps-proc-cpu-metrics                200-1000                  10-200                         4609-4616 4618-4624 4696 4720-4735 6413-6436 6455-6463 6633-6641 
    GPU Process Stats     profiler:apps-proc-gpu-process-metrics                2000-4000                 2000                           4633 
    GPU-PROC-MEM              profiler:apps-gpu-proc-mem-metrics                200-1000                  50-200                         4676 
    GPU Processor             profiler:proc-gpu-specific-metrics                200-1000                  50-70                          4864-4868 
    GPU1 Processor           profiler:proc-gpu1-specific-metrics                200-1000                  50-70                          4864-4868 
    IO                             profiler:apps-proc-io-metrics                1000                      200-1000                       4646-4647 
    Memory                        profiler:apps-proc-mem-metrics                200-1000                  50-200                         4639-4641 4643-4645 4648-4649 
    Net Metrics                   profiler:apps-proc-net-metrics                200-1000                  50-200                         4656-4659 4678-4682 
    Process                   profiler:apps-proc-process-metrics                200-1000                  50-200                         4642 
    Process Memory        profiler:apps-proc-process-mem-metrics                200-1000                  50-200                         4683-4686 
    NPU0                                profiler:nsp-dsp-metrics                200-1000                  1-200                          4096-4184 4187-4188 4190-4192 4195 4204-4205 4236-4241 4266-4267 4352 4356 
                                                                                                                                        4358 4360-4362 4366-4374 4377-4385 4480-4481 4496-4524 
    NPU1                               profiler:nsp1-dsp-metrics                200-1000                  1-200                          4096-4184 4187-4188 4190-4192 4195 4204-4205 4236-4241 4266-4267 4352 4356 
                                                                                                                                        4358 4360-4362 4366-4374 4377-4385 4480-4481 4496-4524 
    NPU2                               profiler:nsp2-dsp-metrics                200-1000                  1-200                          4096-4184 4187-4188 4190-4192 4195 4204-4205 4236-4241 4266-4267 4352 4356 
                                                                                                                                        4358 4360-4362 4366-4374 4377-4385 4480-4481 4496-4524 
    NPU3                               profiler:nsp3-dsp-metrics                200-1000                  1-200                          4096-4184 4187-4188 4190-4192 4195 4204-4205 4236-4241 4266-4267 4352 4356 
                                                                                                                                        4358 4360-4362 4366-4374 4377-4385 4480-4481 4496-4524 
    Hi-Fi-Audio-DSP0                 profiler:hpass0-dsp-metrics                200-1000                  1-200                          4096-4197 4204-4205 4352 4367 4377 
    Hi-Fi-Audio-DSP1                 profiler:hpass1-dsp-metrics                200-1000                  1-200                          4096-4197 4204-4205 4352 4367 4377 
    Hi-Fi-Audio-DSP2                 profiler:hpass2-dsp-metrics                200-1000                  1-200                          4096-4197 4204-4205 4352 4367 4377 
    NPU0 Stats                            profiler:nsp-dsp-stats                1000-2000                 1000-2000                      5888-5890 5893-5900 5903-5907 5909-5912 5914 
    NPU1 Stats                           profiler:nsp1-dsp-stats                1000-2000                 1000-2000                      5888-5890 5893-5900 5903-5907 5909-5912 5914 
    NPU2 Stats                           profiler:nsp2-dsp-stats                1000-2000                 1000-2000                      5888-5890 5893-5900 5903-5907 5909-5912 5914 
    NPU3 Stats                           profiler:nsp3-dsp-stats                1000-2000                 1000-2000                      5888-5890 5893-5900 5903-5907 5909-5912 5914 
    Hi-Fi-Audio-DSP0 Stats             profiler:hpass0-dsp-stats                1000-2000                 1000-2000                      5888-5898 5900 5903-5907 5909-5910 5912 5914 
    Hi-Fi-Audio-DSP1 Stats             profiler:hpass1-dsp-stats                1000-2000                 1000-2000                      5888-5898 5900 5903-5907 5909-5910 5912 5914 
    Hi-Fi-Audio-DSP2 Stats             profiler:hpass2-dsp-stats                1000-2000                 1000-2000                      5888-5898 5900 5903-5907 5909-5910 5912 5914 
    Thermal                   profiler:apps-proc-thermal-metrics                200-1000                  10-160                         6464-6465 
    THREAD                   profiler:apps-proc-thread-profiling                200-400                   100-200                        4660 
    --------------------------------------------------------------------------------------------------------------------------------------------------
    DDR                           profiler:apps-proc-ddr-metrics                DDR Profiler failed due to underlying dependency.

    ```

4. qprof使用 --metric-id-list 可以指定的metric
5. QualcommProfiler API文档路径：/opt/qcom/Shared/QualcommProfiler/API/documents/；示例代码：/opt/qcom/Shared/QualcommProfiler/API/sample-code/
6. PVM预集成的Qualcomm库：/home/ethen/workspace/voyah/projects/8397/code/linux/apps/apps_proc/vendor/qcom/proprietary/qualcomm-profiler

