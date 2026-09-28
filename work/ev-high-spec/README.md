# EV high-spec architecture diagrams

`index.html` is a self-contained page with the A-platform electrical/electronic and IVI hardware views, the B-platform system view, and the high-level software view. Open it directly in a browser.

Edit the Python, HTML, CSS, JavaScript, or TSV sources in this directory, then regenerate the page:

```sh
python3 build.py
```

The build also refreshes `architecture.svg`, `ivi-hardware.svg`, and `b-platform-system.svg`. Commit the edited sources and regenerated outputs together. `template.html` is a build template; open `index.html` for the finished page.

The B-platform diagram is a functional system view based on supplied hardware drawings. It intentionally omits project variant identifiers and SoC signal-level labels; dashed endpoint boxes indicate optional or reserved paths.
