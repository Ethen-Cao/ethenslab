# EV high-spec architecture diagrams

`index.html` is a self-contained page with the A-platform electrical/electronic and IVI hardware views, the B-platform system view, and the high-level software view. Open it directly in a browser.

Edit the Python, HTML, CSS, JavaScript, or TSV sources in this directory, then regenerate the page:

```sh
python3 build.py
```

The build also refreshes `architecture.svg`, `ivi-hardware.svg`, and `b-platform-system.svg`. Commit the edited sources and regenerated outputs together. `template.html` is a build template; open `index.html` for the finished page.

The B-platform diagram is a vector redraw of the supplied system overview and enlarged detail images. It preserves the three configuration columns, component part numbers, connector positions, branch topology, load matrix, and state colors. Project identifiers and SoC signal-level labels are intentionally omitted.
