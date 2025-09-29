# **Android 应用权限审计脚本**

## **概述**

这是一个 Python 脚本，用于通过 ADB (Android Debug Bridge) 连接到 Android 设备，自动获取系统中所有已安装应用程序的详细信息，包括它们申请的权限、用户ID (userId) 和用户组ID (gids)。

脚本会将审计结果整理并输出到一个 Excel（.xlsx）文件中。在文件中，每个应用程序都对应一个单独的 Sheet，清晰地列出了其权限和用户信息，并为权限申请预留了“申请理由”一列，方便分发给应用开发者进行填写和说明。

这有助于系统开发工程师、安全工程师或合规团队对设备中的应用权限进行全面的、标准化的排查和管理。

## **功能特性**

* **自动连接**: 自动检测通过 ADB 连接的设备。  
* **全面扫描**: 获取设备上所有应用的包名列表。  
* **详细解析**: 针对每个应用，解析其 dumpsys 信息，提取以下关键数据：  
  * **用户ID (userId)**  
  * **用户组ID (gids)**  
  * **Manifest中申请的所有权限 (requestedPermissions)**  
* **报告生成**:  
  * 创建一个结构清晰的 Excel 文件。  
  * 每个应用占用一个独立的 Sheet，以应用包名命名。  
  * 每个 Sheet 中包含用户信息和权限列表。  
  * 预留 **“申请理由”** 列，便于后续跟进。

## **环境要求**

1. **Python 3**: 脚本需要 Python 3.x 环境。  
2. **ADB (Android Debug Bridge)**:  
   * 确保 adb 命令已经安装在你的电脑上。  
   * 确保 adb 所在路径已经添加到了系统的环境变量 PATH 中，以便脚本可以全局调用。  
3. **Python 库**: 需要安装 openpyxl 库来操作 Excel 文件。  
4. **Android 设备**:  
   * 一台已连接到电脑的 Android 设备。  
   * 设备已开启“开发者选项”和“USB调试”功能。

## **如何使用**

1. **保存脚本**: 将 permission\_auditor.py 脚本保存到你的电脑上。  
2. **创建并激活虚拟环境 (推荐)**: 为了避免与系统自带的Python包冲突，强烈建议在项目目录中创建一个虚拟环境。  
   \# 在当前目录下创建一个名为 venv 的虚拟环境  
   python3 \-m venv venv

   \# 激活虚拟环境 (适用于 Linux/macOS)  
   source venv/bin/activate

   \# 提示: 如果你使用的是 Windows，请使用 \`venv\\Scripts\\activate\` 命令

   成功激活后，你的终端提示符前面会出现 (venv) 字样。  
3. **安装依赖**: 在**已激活**的虚拟环境中，运行以下命令来安装所需的库：  
   pip install openpyxl

4. **连接设备**: 使用 USB 数据线将你的 Android 设备连接到电脑，并确保 USB 调试已授权。你可以在终端运行 adb devices 来确认设备是否成功连接。  
5. **运行脚本**: 确保你仍处于激活的虚拟环境中，然后执行脚本：  
   python permission\_auditor.py

6. **查看报告**: 脚本运行结束后，会在同一目录下生成一个名为 android\_permissions\_audit.xlsx 的 Excel 文件。打开它即可查看详细的审计报告。  
7. **退出虚拟环境 (可选)**: 当你完成工作后，可以随时在终端运行 deactivate 命令来退出虚拟环境。

## **输出示例**

生成的 Excel 文件中，每个 Sheet 的内容格式如下：

| Type | Detail | Reason for Application (Please fill in) |
| :---- | :---- | :---- |
| User ID | 10189 |  |
| Group IDs | 3003, 9997, 20189, 50189 |  |
|  |  |  |
| Permission |  |  |
|  | android.permission.ACCESS\_NETWORK\_STATE |  |
|  | android.permission.INTERNET |  |
|  | ... |  |

你可以直接将这个 Excel 文件分发给相关的应用开发团队，让他们填写每一项权限的申请理由。