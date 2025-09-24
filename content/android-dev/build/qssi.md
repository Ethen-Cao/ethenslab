+++
date = '2025-08-27T11:36:11+08:00'
draft = true
title = 'Qualcomm build'
+++

## QSSI
QSSI comprises the following:

* Android Open Source Project (AOSP) code from Google (EAP tag or GPP tag depending on the phase of the development)
  > EAP tag 和 GPP tag 是指谷歌在安卓开源项目 (AOSP) 开发过程中，用来标记不同发布阶段的源代码版本标签。
  > * **EAP (Early Access Program) tag**: 早期访问计划标签。这通常是提供给手机制造商 (OEMs) 和芯片供应商（如高通）的早期、非公开的安卓版本。这个版本的目的是让他们能尽早地开始集成和开发工作，但它可能不稳定且包含错误。
  > * **GPP (General Public Project) tag**: 通用公开项目标签。这指的是安卓正式向公众发布的开源版本标签。当一个新的安卓版本（例如 Android 15）正式发布时，其源代码就会以 GPP 标签的形式推送到 AOSP 中，供所有人下载使用。这个版本相对稳定。
  > * 简单来说，**EAP tag 是内部预览版，GPP tag 是公开发行版 。**
* QTI value added features and any bug fixes. The Contents of QSSI gets into the System/System-Ext/Product partitions.

### HLOS software split
APSS(Application processor subsystem) software release model for multiple images allows customers to **compile QSSI-only tree** or **Vendor tree** with dependencies from QSSI (either in the form of prebuilt final QSSI images or sources + prebuilts package).

As part of the initial rollout, manifest is split into two logical parts, which is delivered in QSSI software image and Vendor software image.

The following are the approaches through which QSSI provides the option to integrate source code from QTI:

* For customers who use system/Vendor modularization of QSSI using split tree, the sources and prebuilts can be downloaded:
  * QSSI standalone tree
  * Vendor standalone tree
  * Kernel platform standalone tree
  * Display standalone tree
  * Camera standalone tree
  * Video standalone tree
* Customers who use single tree, source can be downloaded as a single tree

Both QSSI and Vendor software image consists of OSS and proprietary sources/prebuilt libs/binaries/headers.

Sync script (sync_snap_v2.sh) is shared via grease utilities project or Qualcomm ChipCode and helps the customers download QSSI and Vendor software from private/public CLO, Grease/Qualcomm ChipCode depending on the type of content.

> Grease: 这是高通公司用来向客户分发其专有软件 (proprietary software) 和预编译文件 (prebuilts) 的一个平台或服务器的名称 。

### Split manifest details

* The legacy approach for software delivery delivers single manifest containing entire
HLOS projects.

* The latest approach for software delivery delivers separate manifests for QSSI and
Vendor projects.

| Delivery type | QSSI release SI|Vendor release SI
|--|--|--
|Legacy approach for software delivery|Not applicable|Both AOSP and Vendor projects are part of single software image/manifest
| Latest approach for software delivery|AOSP and QTI value-added feature projects are part of QSSI release SI | Vendor specific projects (OSS and Prop) are part of Vendor SI

### Possible location of source code/prebuilt bins
Both Vendor SI and QSSI SI contain OSS and Prop projects

|Code/prebuilt bins|Private CLO|Public CLO|Grease/Qualcomm ChipCode HF|Qualcomm ChipCode
|--|--|--|--|--
|QSSI SI (OSS)|Yes|Yes|Not applicable(N/A)|N/A
|QSSI SI (Prop)|N/A|N/A|Yes|Yes
|Vendor SI (OSS)|Yes|Yes|N/A|N/A
|Vendor SI (Prop)|N/A|N/A|Yes|Yes

### Software delivery approaches – Changes
The following are the changes in the latest software delivery approach:

* A new script is provided to handle sync and download software.
* Ability to download, sync and build SW using split manifest tree and single tree are
provided.

![Legacy approach for software delivery](/ethenslab/images/Legacy_approach_for_software_delivery.png)

![Latest approach for software delivery](/ethenslab/images/Latest_approach_for_software_delivery.png)

## Sync and download software

### Generate the tree/sync software

#### sync_snap_v2.sh
* The Grease customers can get sync_snap_v2.sh by cloning grease_utilities project with the instructions shared in the Release Notes.
* The Qualcomm ChipCode customers get it as part of Qualcomm ChipCode content.

sync_snap_v2.sh is an extension to existing script (sync_snap.sh) to support feature scalability.

While sync_snap_v2.sh defines new input options for easy use/scalability with meaningful input options, customers can still use existing/legacy options that are being used with current sync script (sync_snap.sh) listed in Table 3-1 sync_snap.sh arguments (legacy and existing).

sync_snap_v2.sh also accepts the following existing arguments (legacy options) to support backward compatibility apart from new options.

The table lists both legacy and existing options.Customers cannot club the existing and legacy, and new options (For example, use either one of the old/legacy or new options).

sync_snap.sh arguments (legacy and existing)

|Argument|Description
|--|--|
|D|Workspace destination PATH
|T|tree_type (possible options: "st" for single_tree , "qt" for qssi tree and "vt" for Vendor standalone Tree)
|R|prop_dest= (possible options: "gr" for prop location Grease and "ch" for prop location ChipCode)
|C|Vendor_caf_manifest_repo (Vendor Manifest repo, such as external/private_LA.UM.9.12/la/Vendor/manifest)
|L|Vendor_caf_server_url (Vendor CAF/CLO server URL, such as https://git.codelinaro.org)
|G|Vendor_grease_server (Vendor Grease server, such as grease-sd-stg.qualcomm.com)
|U|Vendor_grease_user (Vendor Grease user, such as <grease user name>)
|P|Vendor_grease_pass (Vendor Grease user pwd, such as <Grease user pwd>)
|A|Vendor_au_tag="$OPTARG (Vendor SI AU TAG, such as AU_LINUX_ANDROID_LA.UM.9.12.10.00.00.638.065)
|M|M-> Vendor_crm_label (Vendor SI CRM Label, such as TBD)
|B|Vendor_branch (Vendor SI branch on Grease server, such as CDR026/LA.UM.9.12.r1)
|H|Vendor_chipcode_path (Vendor SI Chipcode PATH: TBD)
|c|qssi_caf_manifest_repo (QSSI Manifest repo, such as external/private_LA.UM.9.12/la/system/manifest
|l|qssi_caf_server_url (QSSI CAF/CLO server URL, such as ssh://git@git.codelinaro.org)
|g|qssi_grease_server (QSSI Grease server, such as TBD, this may not be needed as -G option is sufficient)
|u|qssi_grease_user (QSSI Grease user)
|p|qssi_grease_pass (QSSI Grease user pwd)
|a|qssi_au_tag (QSSI AU TAG, such as AU_LINUX_ANDROID_LA.QSSI.11.0.R1.10.00.00.668.003)
|m|qssi_crm_label (QSSI CRM label, such as TBD)
|b|qssi_branch (QSSI branch on grease server, such as CDR026/LA.QSSI.11.0.r1)
|h|h-> qssi_chipcode_path (QSSI prop ChipCode path, such as TBD)
|j|j-> repo sync threads(j#) option (default will be 32 if this argument is not passed, such as -j 64)
|s|s-> source groups to pull from QSSI while syncing Vendor (upcoming). This option -s will be supported in the upcoming releases to sync the minimal sources from the QSSI source code used to build Vendor. This option will only be applicable when tree_type is st (single tree). The qc-commonsys and qc-commonsys-intf groups are synced and they the default recommendation to sync subset of sources from QSSI while syncing and building Vendor.This groups option is the same as supported by repo. For reference, see https://android.googlesource.com/tools/repo/+/refs/heads/master/docs/manifest-format.md


While sync_snap_v2.sh supports backward compatibility, the script supports new
meaningful options as listed in the table.

|Sync_snap_v2.sh input option|Description|Example
|--|--|--
|--workspace_path|Destination workspace path where the tree has to be synced|--workspace_path=/usr/tree_path/android/
|--image_type|Image type can be Linux Android/Linux Embedded|--image_type=la --image_type=le Default option (if no input): la
|