# EV high-spec architecture diagrams

`index.html` is a self-contained page with the A-platform electrical/electronic and IVI hardware views, the B-platform system view, the high-level software view, and its OTA child architecture. Open it directly in a browser. Click **OTA & Update Management** or **OTA Service** in the high-level software view to open the OTA architecture; `?tab=software&view=ota` opens that child view directly. The OTA diagram now shows directed component interactions and status return; its path controls highlight QNX, Android, MCU, or feedback routes. Empty layers are omitted. Module rows use an aligned grid with orthogonal routes; matched `SPI` and `PKG` ports represent the same connection at its two endpoints, and gaps at crossings indicate no junction. MCU internals are marked as reference-only because the firmware source is not present in this workspace.

Edit the Python (including `software_ota.py` and `software_ota_graph.py`), HTML, CSS, JavaScript, or TSV sources in this directory, then regenerate the page:

```sh
python3 build.py
```

The build also refreshes `architecture.svg`, `ivi-hardware.svg`, and `b-platform-system.svg`. Commit the edited sources and regenerated outputs together. `template.html` is a build template; open `index.html` for the finished page.

The B-platform diagram is a vector redraw of the supplied system overview and enlarged detail images. It preserves the three configuration columns, component part numbers, connector positions, branch topology, load matrix, and state colors. Project identifiers and SoC signal-level labels are intentionally omitted.


Click **System Image Banks (A/B)** in the OTA graph or its responsibility list to open `storage-partitions.html`. The partition page is a single static table of partition names, device nodes, A/B states, capacities, filesystems, and mount points, with a return link to the OTA view. Keep both HTML files together when copying the viewer. `storage-8295.json` is the portable diagnostic snapshot used to generate it. The table lists partition nodes only, excluding whole LUs, RAM disks, and in-memory IFS mounts. Truncated device names are matched only when unique; unknown partition capacities remain unknown and are never replaced by filesystem sizes.

To import another diagnostic run, pass its directory containing `parsed/` and `raw/`:

```sh
python3 import_storage_snapshot.py /path/to/storage-diagnostic/runs/<run>
python3 build.py
```

The virtualization overview now separates VM management, vCPU scheduling, memory isolation, VirtIO devices, shared memory, and event notification. The OTA view includes only relevant platform facilities. Project evidence is in `bsp/apps/qnx_ap/target/hypervisor/gvm/ivi/la/linux-la.config` and `la_dp_enabled_b.config` in the HBEZ source workspace. Doorbell is described as a notification mechanism; no independent deployed Doorbell device is claimed. SoC hardware labels identify controllers and interfaces, not TCP/IP.
