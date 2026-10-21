# UHAB 最小请求/响应示例

`hab_rpc_demo.c` 为两端共用的单源程序。分别编译为 Linux PVM 与 Android GVM 的目标程序，在 PVM 运行 `server`，在 GVM 运行 `client`。服务只处理一个连接，每条合法请求返回输入值加一；当前客户端发送 41，验证响应为 42。

## 协议与 MMID

每个 HAB 消息恰好 20 字节，五个字段均为显式编码的 32 位无符号大端整数：

|偏移|字段|值|
|---|---|---|
|0|magic|0x48414231|
|4|version|1|
|8|opcode|请求 1，响应 2|
|12|request_id|响应原样返回；客户端逐次增加|
|16|value|请求输入；响应为输入加一，按 uint32_t 模 2^32 运算|

代码使用真实头文件的 `HAB_MMID_CREATE(MM_MISC, minor)`，`MM_MISC=601`。minor 通过命令行指定，范围 0–255；**这个范围不表示所有值都可使用**。必须先由部署者查清既有业务分配并保留一个未占用 minor，两端用相同值。示例没有默认 minor，也不修改通道配置。

使用同一已部署 major 下的新 minor，需要确认业务分配、访问策略和两端匹配；增加新的 major 则还需 HAB 设备表、VM/pchan 配置、virtio/vhost 资源等平台适配。两端调用同一 open API，FE/BE 由平台配置决定，`server/client` 参数只选择示例业务角色。

## 目标编译

PVM 使用对应 Yocto/Linux SDK；GVM 使用对应 Android/Bionic 工具链与本镜像的 UHAB 开发文件。两者 ABI 不同，不要共用一个目标可执行文件。以下为单个目标的编译命令模板，变量必须设成对应目标的实际值：

```sh
"$TARGET_CC" --sysroot="$TARGET_SYSROOT" -std=c11 -Wall -Wextra -Werror \
  -fPIE -pie -I"$UHAB_INCLUDE" -I"$HAB_UAPI_INCLUDE" \
  hab_rpc_demo.c -L"$UHAB_LIBDIR" -luhab -o hab_rpc_demo
```

- `UHAB_INCLUDE` 包含用户态 `habmm.h`，不是内核内部的 `include/linux/habmm.h`。
- `HAB_UAPI_INCLUDE` 包含 `linux/habmmid.h`。
- `UHAB_LIBDIR` 必须提供对应目标架构、libc ABI 和镜像版本的 `libuhab.so`。
- 若 SDK 已把头文件、库和 sysroot 纳入编译器配置，可使用其推荐命令等价编译此源文件。
- 实机运行还需让动态链接器找到目标的 `libuhab.so` 及依赖，且进程可以访问实际 HAB 节点。Android 的安装路径和域应按项目既有部署规则安排。

## 运行

先在每端设置已经分配的相同 `ASSIGNED_MINOR`。以下命令不会自行选择或分配 minor：

```sh
# PVM，使用为 PVM 编译的程序
./hab_rpc_demo server "${ASSIGNED_MINOR:?set an assigned minor}" 30

# GVM，使用为 GVM 编译的程序
./hab_rpc_demo client "${ASSIGNED_MINOR:?set the same assigned minor}" 30
```

`30` 是运行时长（秒，可选，默认 30，允许 1–3600）。收到 SIGINT/SIGTERM 也会退出。程序为 SIGALRM 设置重复通知，在期限后持续中断可中断等待，避免只检查循环时钟而卡在握手里；这不是对失去响应的内核的强制抢占保证。

正常客户端输出 `request=1 result=42` 等记录。**退出码 0 表示正常结束，不证明曾经连接成功；请求/响应记录才是业务往返证据。**

## 超时、断连与错误

- UHAB 返回 0 或负 errno，打印 `r`，不能把 API 结果当作 POSIX 的 -1 再读旧 `errno`。
- open 参数为 500 ms；内部握手还可能采用自身的等待常量，所以同时设进程定时信号。
- send 使用 `HABMM_SOCKET_SEND_FLAGS_NON_BLOCKING`，对 `-EAGAIN` 的用户态重试预算约 2 秒；单次调用耗时受内核实现与调度影响。其他失败直接结束本连接。
- 每次 recv 都重设容量 20，并同时传 200 ms 与 `HABMM_SOCKET_RECV_FLAGS_TIMEOUT`。只有 timeout 参数而没有 flag 会被忽略。服务把空闲超时作为继续等待；客户端限制本次响应等待约 2 秒（含单次接收窗口的粒度）。
- `-ENODEV` 或其他会话错误使程序 close/reopen；`-EOVERFLOW` 表示接收区不足、消息仍在 HAB 队列。固定 20 字节协议将它视为协议错误并关闭连接。不要无条件用同样小的接收区反复 recv；可变长协议需设置上限后分配足够空间重新接收。
- 客户端收到消息后还校验长度、magic/version、opcode、request_id 和结果。send 返回 0 不等于业务已完成。
- 超时请求可能已经被远端执行。示例不会重放同一请求，而是在新会话发起新的无副作用加一请求；生产协议需有跨重连的请求身份、幂等/去重或结果查询。
- 若一直出现权限、无设备或非法参数错误，修复部署配置，重连本身不能解决这些错误。
