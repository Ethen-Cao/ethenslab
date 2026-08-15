## GVM Android端：
   1. adb shell:
      1. 安装库文件到GVM: /opt/qcom/Shared/QualcommProfiler/API/target-la/InstallerLA
      2. export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/vendor/qprof/libs/
      3. export QMONITOR_BACKEND_LIB_PATH=/vendor/qprof/backends/
      4. qmonitor-grpc-server

## PVM端
1. 执行： /opt/qcom/Shared/QualcommProfiler/API/target-le/InstallerLE
2. adb shell登陆PVM
   1. export PATH=/data/shared/QualcommProfiler/bins:$PATH
   2. export LD_LIBRARY_PATH=/var/QualcommProfiler/libs
   3. export QMONITOR_BACKEND_LIB_PATH=/var/QualcommProfiler/libs/backends
   4. 数据采集：
      1. PVM实时显示：/data/shared/QualcommProfiler/bins/qprof --profile --profile-type async --file-format json --capabilities-list profiler:apps-proc-gpu-process-metrics --profile-time 100 --streaming-rate 500 --result-format verbose --live
      2. 如果要将结果写入到文件：  
         mkdir -p /log/perf/gpuperformance
         /data/shared/QualcommProfiler/bins/qprof --profile --profile-type async \
            --file-format json \
            --capabilities-list profiler:apps-proc-gpu-process-metrics \
            --profile-time 100 --streaming-rate 500 \
            --result-format verbose --live \
            --result-dir-path /log/perf/gpuperformance

      3. 或者也可以开一个server：/data/shared/QualcommProfiler/bins/qmonitor-grpc-server。然后再PC端端启动：/opt/qcom/QualcommProfiler/GUI/bin/qcprofiler

注意：
 GPU 通过 capability 名字指定

  系统里两个 GPU 对应两个不同的 capability(不是参数):

  ┌──────┬─────────────────────────────────────┬───────────┐
  │ GPU  │           Capability 名字           │ Metric ID │
  ├──────┼─────────────────────────────────────┼───────────┤
  │ GPU0 │ profiler:proc-gpu-specific-metrics  │ 4864–4868 │
  ├──────┼─────────────────────────────────────┼───────────┤
  │ GPU1 │ profiler:proc-gpu1-specific-metrics │ 4864–4868 │
  └──────┴─────────────────────────────────────┴───────────┘
 per-process GPU Busy(4633)无法分 GPU

  profiler:apps-proc-gpu-process-metrics 只有一个 capability,没有 GPU1 变体。我实采验证过,它的结果参数里只有 pid 和 name,没有 GPU 索引:

  Metric ID:4633  GPU Busy:4.687 %   pid:5775  name:GVM_surfaceflinger
  Metric ID:4633  GPU Busy:5.071 %   pid:6155  name:GVM_ockpit.launcher

  所以每进程的 GPU Busy% 是跨两个 GPU 聚合的,无法指定单个 GPU。如果你需要"某进程在 GPU1 上的占用",当前 profiler API 给不了——只能拿到总使用率层面的 GPU0/GPU1 区分(即 proc-gpu-specific-metrics vs proc-gpu1-specific-metrics)。


qprof --profile --profile-type async --file-format json --capabilities-list profiler:proc-gpu-specific-metrics --profile-time 10 --streaming-rate 500 --result-format verbose --live


台架原始的命令：
export PATH=/var/QualcommProfiler/bins/:$PATH
export LD_LIBRARY_PATH=/var/QualcommProfiler/libs
qprof --profile --profile-type async --file-format json --profile-time 100 --streaming-rate 2000 --result-format verbose --live --capabilities-list profiler:apps-proc-gpu-process-metrics
qprof --profile --profile-type async --file-format json --profile-time 100 --streaming-rate 2000 --result-format verbose --live --capabilities-list profiler:proc-gpu-specific-metrics


Friendly Name                                      Capability                Streaming Rate(s)         Sampling Rate(s)               
----------------------------------------------------------------------------------------------------------------------------------
GPU Process Stats     profiler:apps-proc-gpu-process-metrics                2000                       2000                         
GPU-PROC-MEM              profiler:apps-gpu-proc-mem-metrics                1000                       200                        
GPU Processor             profiler:proc-gpu-specific-metrics                1000                       70                          
GPU1 Processor           profiler:proc-gpu1-specific-metrics                1000                       70                        

NPU0                                profiler:nsp-dsp-metrics                1000                       200                          
                                                                                                                                    
NPU1                               profiler:nsp1-dsp-metrics                1000                       200                          
                                                                                                                                   
NPU2                               profiler:nsp2-dsp-metrics                1000                       200                          
                                                                                                                                    
NPU3                               profiler:nsp3-dsp-metrics                1000                        200                          
                                                                                                                                                        
