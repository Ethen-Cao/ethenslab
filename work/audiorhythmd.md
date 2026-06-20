## 需求
1. audio 音律律动服务负载从android audioflinger 中捕捉音频，然后调用算法模块提供的 RhythmAnalyzer so 分析音频，获得一个结果，最终将这个结果发送给vehicle/MCU.
2. audio 音频服务要提供接口给应用层设置应用调用：开启、关闭 音乐律动功能
3. audio 音律律动服务要提供接口给多媒体应用，多媒体应用会传递当前播放的音乐封面的颜色值给音乐律动服务
4. audio捕获的代码可以参考：~/workspace/voyah/projects/8397/code/qssi/frameworks/native/services/audiocaptureservice，但要注意这个参考代码是在android 16上调通的，而我们的目标平台是android12
5. RhythmAnalyzer的集成方案参考：/home/ethen/workspace/voyah/projects/8397/code/qssi/frameworks/native/services/audiocaptureservice/docs 。
6. audio音律服务最终是一个vendor hal服务。

## QA

1. audio 音律律动服务要开机就运行，注册Mixer？
2. 快进快退如何处理？
3. 由于接收音律处理结果的模块命名暂时没有确定，为了抽象，是否可以将其命名为IRhythmClient？