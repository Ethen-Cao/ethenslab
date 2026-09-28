# EV high-spec architecture diagrams

`index.html` is a self-contained page with the A-platform electrical/electronic and IVI hardware views, the B-platform system view, the high-level software view, and its OTA and Diagnostic child architectures. Open it directly in a browser. Click **OTA & Update Management** or **OTA Service** in the high-level software view to open the OTA architecture; `?tab=software&view=ota` opens OTA directly; click **Diagnostics & Observability**, **Manufacturing Diagnostics**, or **Dcm** for Diagnostics, or use `?tab=software&view=diag`. The OTA diagram now shows directed component interactions and status return; its path controls highlight QNX, Android, MCU, or feedback routes. Empty layers are omitted. Module rows use an aligned grid with orthogonal routes; matched `SPI` and `PKG` ports represent the same connection at its two endpoints, and gaps at crossings indicate no junction. MCU internals are marked as reference-only because the firmware source is not present in this workspace.

Edit the Python (including `software_ota.py`, `software_ota_graph.py`, `software_diagnostics.py`, and `software_diagnostics_graph.py`), HTML, CSS, JavaScript, or TSV sources in this directory, then regenerate the page:

```sh
python3 build.py
```

The build also refreshes `architecture.svg`, `ivi-hardware.svg`, and `b-platform-system.svg`. Commit the edited sources and regenerated outputs together. `template.html` is a build template; open `index.html` for the finished page.

The B-platform diagram is a vector redraw of the supplied system overview and enlarged detail images. It preserves the three configuration columns, component part numbers, connector positions, branch topology, load matrix, and state colors. Project identifiers and SoC signal-level labels are intentionally omitted.


Click **System Image Banks (A/B)** in the OTA graph or its responsibility list to open `storage-partitions.html`. The partition page is a single static table of partition names, device nodes, A/B states, capacities, QNX filesystems, QNX mount points, and a purpose column (说明), with a return link to the OTA view. Keep both HTML files together when copying the viewer. `storage-8295.json` is the portable diagnostic snapshot used to generate it. The table lists partition nodes only, excluding whole LUs, RAM disks, and in-memory IFS mounts. Truncated device names are matched only when unique; unknown partition capacities remain unknown and are never replaced by filesystem sizes.

The current snapshot was captured on **2026-09-28 15:19:15 UTC+08:00**, the latest run by its manifest capture time. All 35 observed A/B pairs resolve to slot A; the 2026-09-04 snapshot resolved to B. The 115 partition nodes are unchanged. `/mnt` resolves to `system_a` and `/firmware` to `modem_a`. These are snapshot observations, not a claim that both captures came from the same physical device.

`storage_partition_descriptions.json` keeps purpose notes separate from live diagnostic data, with evidence references to project configuration, the diagnostic run, and AOSP documentation. A/B counterparts share a purpose by their recorded pair name. Any unresolved purpose renders exactly as `unknown`; Android guest mounts appear only in explanations, while the mount columns show QNX observations.

To import another diagnostic run, pass its directory containing `parsed/` and `raw/`:

```sh
python3 import_storage_snapshot.py /path/to/storage-diagnostic/runs/<run>
python3 build.py
```

The virtualization overview now separates VM management, vCPU scheduling, memory isolation, VirtIO devices, shared memory, and event notification. The OTA view includes only relevant platform facilities. Project evidence is in `bsp/apps/qnx_ap/target/hypervisor/gvm/ivi/la/linux-la.config` and `la_dp_enabled_b.config` in the HBEZ source workspace. Doorbell is described as a notification mechanism; no independent deployed Doorbell device is claimed. SoC hardware labels identify controllers and interfaces, not TCP/IP.

The Diagnostic child view uses the same QNX/AAOS/MCU frame, path filters, clickable components, right-click deselection, responsibilities, and interface register as OTA. Its QNX blocks are grounded in HBEZ staged SLM services and the diagnostic binaries, and its Android blocks in `android/android/vendor/voyah/system/diagnostic/`. The MCU blocks and internal arrows follow the supplied reference image and are marked reference-only because matching MCU firmware source is absent. A dashed cross-domain DTC path identifies the Android Vehicle HAL property and QNX dtcagent endpoints while explicitly leaving the intermediate mapping unverified.
