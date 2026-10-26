# ART App 性能与稳定性机制研究任务清单（Task Checklist）

> **源码基线**：[art](file:///home/ethen/workspace/voyah/projects/8397/code/qssi/art)（Android 15/16 主线级 QSSI 仓库）  
> **产出目录**：`/home/ethen/workspace/github/ethenslab/work/art-wiki/`

## 阶段零：源码盘点与研究规划
- [x] 全量扫描 `art` 仓库源码目录，确认 App 性能与稳定性核心机制清单（共 4 大域、16 条独立机制）
- [x] 对齐研究边界、输出路径与单文件自包含图文规范，输出 [implementation_plan.md](file:///home/ethen/.gemini/antigravity/brain/db260ba4-b7ce-4b54-9228-5adc342f0f21/implementation_plan.md)

## 专题一：App 执行、编译与启动性能加速机制
- [/] **Task 01**：研究并输出 `01-tiered-execution-and-jit-aot.md` —— 混合执行引擎与分层编译机制（Switch / Nterp / Fast Baseline JIT / Optimizing JIT & OSR / AOT）
- [/] **Task 02**：研究并输出 `02-pgo-profile-and-dexopt-pipeline.md` —— PGO 热点画像采集与编译治理闭环（`ProfileSaver` / `profman` / Cloud DM / `artd` & Pre-reboot Dexopt）
- [/] **Task 03**：研究并输出 `03-app-startup-and-image-caching.md` —— App 启动加速与类/镜像预热机制（BootImage / JitZygote / AppImage / `RuntimeImage` / `StartupCompletedTask` / `madvise`）
- [/] **Task 04**：研究并输出 `04-fast-jni-transition-optimization.md` —— 高性能 JNI 跨界调用优化机制（Normal JNI / `@FastNative` / `@CriticalNative` 与编译器 JNI Stub）

## 专题二：App 内存管理、并发同步与防卡顿（Anti-Jank）机制
- [ ] **Task 05**：研究并输出 `05-concurrent-gc-cmc-and-cc.md` —— 并发垃圾回收与亚毫秒级 STW 机制（Generational CMC `userfaultfd` / Concurrent Copying / TLAB 分配与前后台感知）
- [ ] **Task 06**：研究并输出 `06-native-gc-trigger-and-ref-processing.md` —— Native 内存压力联动回收与引用处理防卡顿机制（`NativeAllocationRegistry` 紧急度节流 / `ReferenceProcessor` 并发状态机）
- [ ] **Task 07**：研究并输出 `07-monitor-lock-inflation-and-priority.md` —— Java 锁膨胀状态机与线程优先级防反转机制（Thin/Fat Lock 膨胀收缩 / `futex` / `ScopedPriorityChange`）

## 专题三：App 性能可观测性、指标遥测与低开销剖析机制
- [ ] **Task 08**：研究并输出 `08-art-telemetry-metrics-and-statsd.md` —— ART 运行时与编译服务遥测指标体系（`ArtMetrics` 48 项指标 / Statsd / `VMDebug.getRuntimeStat` / Dexopt & Odrefresh 遥测）
- [ ] **Task 09**：研究并输出 `09-gc-and-lock-jank-observability.md` —— GC 与锁竞争卡顿实时监测体系（慢 GC 日志 / Systrace 缺页打点 / `dvm_lock_sample` 采样 / `PerfMonitor` 阻塞期抓栈）
- [ ] **Task 10**：研究并输出 `10-method-tracing-and-cpu-profiling.md` —— 方法追踪、低开销环形缓冲与原生符号桥接机制（`Trace` / `TraceProfiler` 长方法捕获 / JIT ELF 符号注册 / eBPF 偏移接口 / JVMTI）
- [ ] **Task 11**：研究并输出 `11-java-heap-sampling-and-hprof.md` —— Java 堆采样剖析与双 Fork 快照机制（Perfetto `HeapSampler` TLAB 采样 / `perfetto_hprof` 双 Fork 零拷贝抓堆 / HPROF）

## 专题四：App 稳定性防护、超时看门狗与崩溃取证机制
- [ ] **Task 12**：研究并输出 `12-anr-sigquit-dump-and-diagnostics.md` —— ANR 全景诊断转储与 Pre-ANR 长方法录制机制（`SignalCatcher` / `SIGUSR1` 联动 / `DumpOrder` 防截断排序 / `DebugStore`）
- [ ] **Task 13**：研究并输出 `13-thread-suspension-and-watchdog.md` —— 线程安全点挂起机制与超时精准自杀看门狗（安全点协议 / `WaitForSuspendBarrier` 动态豁免 / `AbortInThis` 肇事线程归因）
- [ ] **Task 14**：研究并输出 `14-signal-chaining-and-fault-handler.md` —— 硬件异常拦截与 Native Crash 信号链机制（`libsigchain` 防覆盖劫持 / `FaultManager` 隐式异常转换与 MTE 崩溃分流）
- [ ] **Task 15**：研究并输出 `15-checkjni-ref-leak-and-heap-verify.md` —— CheckJNI 契约防护、引用表溢出诊断与堆踩踏取证机制（`CheckJNI` 慢锁与违规拦截 / GlobalRef 泄漏栈追踪 / `LogHeapCorruption`）
- [ ] **Task 16**：研究并输出 `16-oom-verifier-hiddenapi-and-watchdogs.md` —— OOM 死亡抓堆、字节码校验、API 管控与编译防变砖机制（OOM 晋升回收与自动抓堆 / `MethodVerifier` / `hidden_api` & DCL / `dex2oat` & `odrefresh` 看门狗）

## 阶段五：全景总览索引与质量校验
- [ ] **Task 17**：输出知识库总入口 `README.md`（ART 性能与稳定性全景架构图、16 大机制导航矩阵、排障场景速查决策树）并完成全量链接与图表语法校验
