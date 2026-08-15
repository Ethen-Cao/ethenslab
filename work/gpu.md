• 我在 GVM 上跑通 qprof 的关键是三步：补库、补数据库、控制库加载顺序。

  1. 补完整 LA 库集到 GVM 临时路径：

  adb -s d7df5883 shell mkdir -p /data/local/tmp/qprof

  adb -s d7df5883 push \
    /home/ethen/Downloads/QualcommProfiler/API/target-la/aarch64/libs \
    /data/local/tmp/qprof/

  2. 补 ExtQProfiler.db

  GVM 原来缺这个文件，qprof --capabilities 会报：

  Failure opening database "/data/shared/qcom/Shared/Prof_Ext/ExtQProfiler.db"

  我从 PVM 拉下来再推到 GVM：

  adb -s e66b06ea pull \
    /data/shared/qcom/Shared/Prof_Ext/ExtQProfiler.db \
    /tmp/ExtQProfiler.db

  adb -s d7df5883 shell mkdir -p /data/shared/qcom/Shared/Prof_Ext

  adb -s d7df5883 push \
    /tmp/ExtQProfiler.db \
    /data/shared/qcom/Shared/Prof_Ext/ExtQProfiler.db

  3. 用 vendor 库优先的 LD_LIBRARY_PATH

  这个顺序很重要：

  export LD_LIBRARY_PATH=/vendor/qprof/libs:/data/local/tmp/qprof/libs
  export QMONITOR_BACKEND_LIB_PATH=/data/local/tmp/qprof/libs/backends

  不能把 /data/local/tmp/qprof/libs 放前面，否则会覆盖 GVM /vendor/qprof/libs 里的本机库，之前出现过 Segmentation fault。

  最终运行命令：

  adb -s d7df5883 shell '
  export LD_LIBRARY_PATH=/vendor/qprof/libs:/data/local/tmp/qprof/libs
  export QMONITOR_BACKEND_LIB_PATH=/data/local/tmp/qprof/libs/backends

  /vendor/bin/qprof --profile --profile-type async \
    --capabilities-list profiler:proc-gpu-specific-metrics \
    --profile-time 10 --streaming-rate 500 --sampling-rate 100 \
    --metric-id-list 4864 4865 4866 4867 4868 \
    --result-format verbose --live
  '

  验证结果：

  /vendor/bin/qprof --version

  输出：

  Version : 2.25.10.16

  GPU0/GPU1 都能正常采集：

  profiler:proc-gpu-specific-metrics
  profiler:proc-gpu1-specific-metrics

  其中 GPU0 指标包括 clock、utilization、memory bus busy、read/write bandwidth。