+++
date = '2025-09-27T17:17:50+08:00'
draft = false
title = 'repo基础知识'
+++

## 基础概念

* Manifest：在 AOSP 或使用 repo 工具管理的多仓库项目中，Manifest 是一个 XML 文件（通常名为 manifest.xml），由 repo 工具使用，定义了项目的多个 Git 仓库的地址、分支、版本（commit 或 tag）等信息。它就像一个“蓝图”，告诉 repo 需要从哪些仓库拉取哪些代码。开发者运行 repo sync 时，repo 工具会读取 Manifest 文件（通常从 **Manifest 仓库**获取），根据其中的配置（如仓库 URL、分支、版本）决定需要拉取哪些 Git 仓库的代码。
  
* Gerrit：Gerrit 是一个代码审核服务器，通常作为 Git 仓库的代理层（proxy）。它不仅托管代码仓库，还提供代码审核功能（如 Code Review、Verified 分数）。在实际操作中，开发者的 repo sync 请求会通过 Gerrit 获取代码，而不是直接访问原始 Git 仓库。

* repo命令的含义：
  * ```repo init -u ssh://h-caoquanli@10.82.64.202:8787/8397/DLS-Qualcomm-U/manifest -b dev_rc16_3.1_20250730 -m qssi.xml```
    
    这行命令是使用 `repo` 工具来初始化一个代码仓库的本地工作区。`repo` 是一个基于 Git 的仓库管理工具，通常用于管理包含多个 Git 仓库的大型项目，最典型的就是 Android 开源项目 (AOSP)。
    简单来说，这条命令的意思是：**准备从一个内部服务器上，下载一个名为 “DLS-Qualcomm-U” 的高通平台项目，并指定其版本为 `dev_rc16_3.1_20250730`，同时使用 `qssi.xml` 这个配置文件来决定具体下载哪些代码模块。**
    
    下面我们来逐段分解这个命令：
    1. `repo init`
       * **`repo`**: 这是使用的工具名称。
       * **`init`**: 这是 `repo` 的一个子命令，意思是 “初始化 (initialize)”。它的作用是在你当前的目录下创建一个名为 `.repo` 的隐藏文件夹。这个文件夹里包含了 `repo` 工具的源代码以及一个关键的 "清单仓库 (manifest repository)"。这个清单仓库本身也是一个 Git 仓库，它定义了整个项目由哪些子项目（也就是哪些 Git 仓库）组成。
        **执行 `repo init` 只是第一步，它只下载了项目的“目录”或“清单”，还没有下载任何实际的源代码。**

    2. `-u ssh://h-caoquanli@10.82.64.202:8787/8397/DLS-Qualcomm-U/manifest`
       * **`-u`**: 这个参数是 "URL" 的缩写，它指定了清单仓库所在的远程地址。
       * **`ssh://...`**: 这部分是具体的地址，我们可以进一步分析：
           * **`ssh://`**: 表示使用 SSH (Secure Shell) 协议进行连接。这是一种安全的、加密的连接方式，通常用于公司内部的代码服务器。这需要你的电脑上已经配置好了正确的 SSH 密钥。
           * **`h-caoquanli`**: 这是你用来登录 SSH 服务器的用户名。
           * **`10.82.64.202`**: 这是代码服务器的 IP 地址。这是一个内网 IP，表明你正在连接一个公司内部的服务器，而不是像 GitHub 这样的公共服务器。
           * **`:8787`**: 这是 SSH 服务的端口号。标准的 SSH 端口是 22，这里使用了自定义端口 8787。
           * **`/8397/DLS-Qualcomm-U/manifest`**: 这是清单仓库在服务器上的具体路径。路径的起始 / 应该被理解为 相对于 Git 仓库存储的根路径，这个根路径是由服务器上的 Git/SSH 服务（例如 Gerrit, GitLab, 或者一个标准的 Git 服务）预先配置好的。在一个代码服务器上，成百上千个 Git 仓库通常被统一存放在一个主目录下，比如 /srv/git/，/var/opt/gitlab/git-data/repositories/ 或者 /home/git/repositories/ 等。这样做便于统一管理、备份和迁移。所以这个路径  /8397/DLS-Qualcomm-U/manifest 是一个逻辑路径或者相对路径，服务器端的 Git 服务会把它和你配置的基础路径拼接起来，构成服务器上的实际物理路径。假设服务器管理员将所有 Git 仓库的存储基础路径设置为 /var/git_repos/。当你执行 repo init 或者 git clone 时，你提供的 URL 中的路径 /8397/DLS-Qualcomm-U/manifest 会被服务器这样解析：
           **基础路径 + 你提供的路径 = 服务器上的实际路径**
            也就是：/var/git_repos/ + 8397/DLS-Qualcomm-U/manifest = /var/git_repos/8397/DLS-Qualcomm-U/manifest
            所以，Git 服务最终会去服务器的 /var/git_repos/8397/DLS-Qualcomm-U/manifest 这个位置寻找清单仓库。
           **这部分合起来告诉 `repo` 工具：去哪里获取项目的“总目录”。**
    3. `-b dev_rc16_3.1_20250730`

       * **`-b`**: 这个参数是 "branch" (分支) 的缩写。它指定了在清单仓库中要使用的分支。
       * **`dev_rc16_3.1_20250730`**: 这是分支的名称。在软件开发中，分支名通常包含了丰富的信息：
           * **`dev`**: 可能表示这是一个开发 (development) 分支。
           * **`rc16`**: 可能表示 "Release Candidate 16"，即第16个发布候选版本。
           * **`3.1`**: 可能表示项目的主版本号。
           * **`20250730`**: 这是一个日期，表示该版本的代码基线是 2025年7月30日。

        **这部分的作用是：锁定一个特定的项目版本。通过切换清单仓库的分支，你可以获取项目在不同时间点或不同发布阶段的完整代码快照。**

    4. `-m qssi.xml`

       * **`-m`**: 这个参数是 "manifest" (清单文件) 的缩写。它指定了在清单仓库中要使用的具体 XML 文件名。
       * **`qssi.xml`**: 这是清单文件的名字。一个清单仓库里可以有多个 XML 文件，用于不同的产品配置或编译目标。
           * `qssi` 在高通的语境下，通常是 "Qualcomm Single System Image" 的缩写。这表明你正在初始化的代码是用于构建一个整合了多个子系统（如 Modem, Application Processor 等）的统一系统镜像。

        **这部分的作用是：选择一个特定的项目配置文件。比如，`a.xml` 可能是为产品A的配置，而 `qssi.xml` 可能是为某个特定平台的整合版配置。如果不指定 `-m`，`repo` 会默认使用 `default.xml`。**

    **总而言之，这条命令的完整含义是：**
    > 在当前目录下，初始化一个 `repo` 工作区。该工作区的配置信息（即项目的构成清单）来自于地址为 `ssh://h-caoquanli@10.82.64.202:8787/8397/DLS-Qualcomm-U/manifest` 的 Git 仓库。在获取清单时，请检出 (checkout) `dev_rc16_3.1_20250730` 分支，并使用该分支下的 `qssi.xml` 文件作为最终的项目清单。

  * `repo init` 成功执行后，你的 `.repo` 目录就已经配置好了。接下来，你需要运行：
    ```bash
    repo sync
    ```
    `repo sync` 命令会读取 `.repo/manifests/qssi.xml` 文件，然后根据文件中列出的所有 Git 仓库地址和版本号，开始并行下载所有项目的实际源代码到你的本地工作区。这通常是一个漫长的、占用大量网络带宽和磁盘空间的过程。

    ![](/ethenslab/images/repo.png)