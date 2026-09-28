# EV high-spec architecture diagrams

`index.html` is a self-contained page with the A-platform electrical/electronic and IVI hardware views, the B-platform system view, the high-level software view, and its OTA child architecture. Open it directly in a browser. Click **OTA & Update Management** or **OTA Service** in the high-level software view to open the OTA architecture; `?tab=software&view=ota` opens that child view directly.

Edit the Python (including `software_ota.py`), HTML, CSS, JavaScript, or TSV sources in this directory, then regenerate the page:

```sh
python3 build.py
```

The build also refreshes `architecture.svg`, `ivi-hardware.svg`, and `b-platform-system.svg`. Commit the edited sources and regenerated outputs together. `template.html` is a build template; open `index.html` for the finished page.

The B-platform diagram is a vector redraw of the supplied system overview and enlarged detail images. It preserves the three configuration columns, component part numbers, connector positions, branch topology, load matrix, and state colors. Project identifiers and SoC signal-level labels are intentionally omitted.
