## 项目基本信息
Soc：sa8397
软件：PVM(Linux) + qcrosvm + GVM（Android16）

台架信息：两路adb,一路PVM，一路Andrioid

## 源码

PVM: ~/workspace/voyah/projects/8397/code/linux/apps/apps_proc/
GVM：采用高通的qssi, vendor拆分的方案
* qssi：~/workspace/voyah/projects/8397/code/qssi/
* vendor: ~/workspace/voyah/projects/8397/code/qssi/
* 参考文档：[text](../../content/android-dev/build/qssi.md)

## 工作约定

后续执行任务时，若发现全局、长期有效的重要信息，需要用非常简短的summary追加到本文件，方便后续唤醒项目记忆。当前电脑已连接台架，并接入Linux adb。

2026-05-21：当前adb两路设备中，PVM Linux侧为`e66b06ea`，Android/GVM侧为`d7df5883`；PVM主机名`sa8797`，内核`6.6.110-rt61-debug`。Linux进程清单见`linux_process_inventory.md`。

2026-05-21：用户态进程业务分类按5类口径整理：OS基础设施、车业务中间件、座舱多媒体/人机交互、虚拟化/GVM、芯片硬件平台/安全资源；分类结果见`linux_user_process_business_classification.md`。

2026-05-21：`dmpolicy`源码位于PVM `voyah-cluster/dmpolicy`，是显示策略服务，负责多屏背光/开关、吸顶屏控制，连接IVCD/MCD/RPCD并通过CAN下发显示相关控制。
