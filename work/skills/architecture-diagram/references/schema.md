# Model, build and verification

The maintained source is a version-2 JSON model. The builder inlines the shared model validator, renderer, CSS, theme and pinned font resources into a standalone HTML. Do not edit generated HTML to fix a model or style problem; edit its source and rebuild. `assets/theme.json` is the shared visual-token source, not a per-model override. Its `presentation.minNodeFontSize` and `presentation.minTextFontSize` own the effective-text thresholds; presentation mode is a build option, not a required model field.

All geometry uses absolute SVG logical pixels. All figure text, including accessibility text, is English. Source locators may retain original filenames and URLs. Source titles are non-visible metadata and may preserve the original language. The automated language check catches accidental CJK figure text; it is not an English-language detector, so review the rendered wording manually.

## Model fields

| Field | Contract |
| --- | --- |
| `version` | Required; `2` |
| `meta` | Required classification, purpose and figure identity; see below |
| `canvas` | Required positive logical `width`, `height`, determined by content and layout; no required slide ratio, one-screen fit or node-count ceiling |
| `sources` | Evidence records `{id, title, locator}`; locator is a document path, source location or authoritative URL |
| `deployment` | Required for real diagrams: selected deployment profile and, for a virtualized SoC, explicit references to its required domains and substrate |
| `containers` | Domain, layer, process and resource-region geometry |
| `nodes` | Nonempty concrete or scope-appropriate logical entities |
| `edges` | Directed typed relationships; endpoints are node IDs |
| `junctions` | Optional true common-prefix fan-outs |
| `parties` | Responsibility-mode party records; not origin categories |

### Metadata

```json
{
  "id": "android-system",
  "title": "Android Platform Architecture",
  "subtitle": "Automotive API and service expansion",
  "scope": "system",
  "view": "layered",
  "colorMode": "technical"
}
```

- `scope`: `system` or `subsystem`; controls allowed abstraction, not canvas shape.
- `view`: `layered` or `dataflow`. Layered diagrams may include main data/control paths. A dataflow supplement does not replace a requested layered main diagram.
- `colorMode`: `technical` (default intent), `origin`, or `responsibility`. Supply it explicitly in the model.
- `responsibilityBasis`: required only in responsibility mode; one of `development`, `delivery`, `integration`, `maintenance`.
- `description`: optional English accessibility description; not a place for a visible verification disclaimer.
- `specimen`: default false; true only for expressly abstract layout specimens such as `layout-primitives`. It relaxes factual evidence and concrete-name requirements, never geometry requirements. Do not enable it to bypass validation of a real architecture.

### Containers

Every container has unique `id`, `kind`, English `title`, optional `subtitle`, and `x`, `y`, `w`, `h`. Optional `parent` names its nearest enclosing container.

| `kind` | Required semantics / extra fields |
| --- | --- |
| `domain` | OS / VM / SoC / MCU / TEE; `domainType`: `os`, `vm`, `soc`, `mcu`, `tee`; real OS / VM domains also declare `platform`: `android`, `qnx`, `linux`, `other` |
| `layer` | Required integer `order` ≥ 0; layers inside a platform domain also declare technical `role`. Sibling layers of different order must appear top-to-bottom without vertical overlap; equal order permits horizontally parallel regions |
| `process` | Actual process name in `title`; role in `subtitle`; nonempty `evidence` unless specimen |
| `group` | Logical grouping, not an invented process |
| `hypervisor` | Required `hosts` array of actual hosted `domain` IDs with `domainType: "vm"`; band below and spanning those VMs |
| `hardware-region` | Physical resource grouping, not a rule forcing every memory object into hardware |

Logical containers may include `evidence`. Text is measured by the shared renderer; reserve room for computed header plus content padding. A layer and a process are different boundaries: use correct containment and do not duplicate process instances merely to fill rows.

A layer title names its technical capability category; its child nodes name the actual implementation entities at the selected scope. A layer with only one implementation is valid. For example, the QNX layer is `Microkernel & Process Manager`, containing the actual `procnto` module.

A source saying only `Application` does not establish an executable/process name. In a system overview it can be a logical `group`, not a `process` with a made-up identifier. If an essential process identity is missing from a requested subsystem view, ask or agree on a narrower scope rather than bypassing process membership or enabling specimen mode.

### Deployment contract

Select the profile from confirmed deployment facts **before** coordinates. `deployment` is non-visible model metadata, not a disclaimer in the figure. It is required for real diagrams; an abstract specimen may also declare it to exercise the topology checks.

```json
{
  "profile": "virtualized-soc",
  "soc": "soc-domain",
  "vms": ["pvm", "gvm"],
  "hypervisor": "hypervisor",
  "hardware": "soc-hardware",
  "tee": "tee-domain",
  "independent": ["mcu"],
  "evidence": ["platform-source"]
}
```

- `profile`: `single-domain`, `multi-domain`, or `virtualized-soc`. The first two do not impose a SoC frame on unrelated systems. Do not select them to disguise a virtualized system.
- `soc`, `vms`, `hypervisor`, `hardware`, and nonempty `evidence` are required for a real `virtualized-soc` diagram. All references must resolve to their declared container types. Removing a required container remains an error even if no container of that kind survives.
- The SoC is a `domain` with `domainType: soc`; its VM domains, Hypervisor band and hardware region share it as their immediate parent. VMs are horizontally separate and top-aligned. Hypervisor `hosts` must match the declared VM set and its band must span that set only.
- `tee` is optional: include it only when involved and evidenced. In this deployment layout it is the VM-left peer inside the SoC, top-aligned with the VMs and bottom-aligned with the Hypervisor. Do not infer a platform's TEE implementation from the abstract example.
- `hardware` references the shared `hardware-region` below the VM / Hypervisor / participating TEE, spanning their combined horizontal extent. It is not the SoC outer boundary.
- `independent` lists participating independent domains such as MCU. They are outside the SoC, share its parent, and are horizontally beside it with aligned top/bottom boundaries. A short IPC edge is not a reason to move one below the SoC.
- Focused single-VM software excerpts may use `{profile: "single-domain", domain: "pvm", excerpt: true, evidence: ["source"]}` only in `subsystem` scope: exactly that one execution domain, no cross-domain endpoints, no physical hardware nodes or hardware regions. Keep the VM identity. This is not a deployment overview and cannot replace one.

### Technical-role contract

Roles are non-visible identifiers independent of display titles and `order` numbers. They express an evidence-backed classification, not the order of jobs or requests.

Allowed `layer.role` / `node.layerRole` values: `applications`, `framework-api`, `client-api`, `system-services`, `services`, `native-libraries`, `runtime`, `hal`, `platform-adaptation`, `resource-managers`, `user-drivers`, `kernel`, `firmware`, `hardware`.

In a layered view, software nodes within a platform domain declare `layerRole`, matching their nearest technical-layer ancestor; assigning the tag without placing the node in a real technical-layer container is not sufficient. This is the macro placement role, not every local class responsibility: a private messaging client inside a service is not automatically a shared Framework API. Hardware and memory nodes do not need it. A process remains a runtime container, not a layer. Do not duplicate a runtime process to fill multiple technical rows; real distinct instances of the same executable are not forbidden merely because their names match.

Platform checks enforce technical rank separately from the author-supplied `order`:

| Platform | Top-to-bottom role order |
| --- | --- |
| Android | Applications → Framework / Client APIs → System Services → parallel Native Libraries / Runtime → HAL → Kernel |
| QNX | Applications → Client APIs → peer Services / Resource Managers / User-space Drivers → Microkernel & Process Manager (`kernel` rank) |
| Linux | Applications → Framework / Client APIs → Services → evidenced Platform Adaptation → Kernel |

Omitted roles do not require empty layers. Android service expansion is an implementation view, not a claim that the official platform diagram has a separate services row. A native service stays a service; its language does not move it into Native Libraries. QNX `kernel` rank positions `procnto` system capabilities; it does not claim Process Manager or user-space drivers are pure kernel code.

The validator checks consistency of **declared** roles. It does not independently establish that a class or library really has that role: review the evidence and client/server distinction before routing. No component-name blacklist or automatic suffix-to-layer inference substitutes for this check.

### Nodes

Required fields: unique `id`, `entityType`, canonical identity, nearest container `parent`, `x`, `y`, `w`, `h`, and nonempty `evidence` source IDs unless specimen. Optional `description` becomes the concise subtitle, not the title.

| `entityType` | Naming / membership rule |
| --- | --- |
| `subsystem` | Logical subsystem / API group name; allowed only in system scope |
| `process` | Actual process identity; use a process container when showing internals, not a duplicate node for the same process |
| `library` | Actual artifact name, e.g. `.so` (including versioned suffix), `.a`, `.jar`, `.dll`, `.dylib`; not a role description |
| `class`, `interface` | Actual class / interface identifier, not a functional slogan |
| `kernel-interface` | Required `interfacePath` and `moduleName`; title derived as `<path> · <module>` |
| `driver` | Actual driver/module identifier; use when no exported device file is being represented |
| `hardware`, `firmware`, `runtime` | Actual identity; keep these categories distinct |
| `memory` | Required stable `resourceId`; one physical resource cannot appear as multiple memory entities |

Use `canonicalName` for entity identity, except kernel-interface nodes may omit it because the title is derived. If provided for a kernel interface, it must exactly equal the derived title. Do not add a free-form display-name override that bypasses these rules.

In subsystem scope, userspace library / class / interface nodes require a process ancestor. A system overview may show libraries logically without claiming their runtime ownership. Genuine kernel, hypervisor or firmware implementations use an explicit, evidence-backed `executionContext` instead of an invented userspace process.

Optional fields:

- `executionContext`: `userspace` (default), `kernel`, `hypervisor`, or `firmware`. The process-ancestor requirement applies to subsystem library / class / interface nodes whose context is userspace. Other contexts describe actual execution environments and require the same factual evidence as other nodes; never set one merely to bypass a missing process container.
- `origin`: `oem`, `native`, `vendor`, `unknown`; required for software nodes in origin mode. Technical mode does not require guessing it.
- `responsibleParty`: a declared party ID, or `unknown`; required for software nodes in responsibility mode.
- `configured`: true for configured but inactive objects; neutral dashed style.
- `resourceId`: stable physical resource identity, not just a copy of a per-VM display label.

Responsibility parties use `{id, label, category, paletteKey?}`. Categories are `oem`, `tier1`, `soc-vendor`, `os-vendor`, `other`; their default palette keys are respectively `blue`, `amber`, `purple`, `green`, `cyan`. Optional `paletteKey` selects one of `blue`, `green`, `amber`, `purple`, `cyan`, `orange`, `pink`, `indigo`, not an arbitrary CSS color. Different parties actually used in the diagram must resolve to distinct palette keys; for example, two Tier1 parties need explicitly different slots. The legend names the selected responsibility basis. Source origin does not establish delivery or integration responsibility.

### Edges

Required: unique `id`, `from`, `to`, `relation`, and nonempty `evidence` unless specimen.

| `relation` | Rendered meaning |
| --- | --- |
| `dependency` | Muted thin solid dependency, not an asserted runtime call |
| `call`, `ipc` | Blue solid control; `ipc` also requires `mechanism` |
| `read`, `write`, `transfer` | Green data line connecting actual readers / writers |
| `notification` | Blue dotted notification |
| `configuration` | Muted dashed setup / allocation relationship |

- `mechanism`: required for IPC, optional otherwise. It names an evidenced transport or protocol; phrases such as `Client connection` or `Local IPC` merely restate a relationship and do not establish its mechanism. If the source only establishes a dependency, use `dependency`, not invented IPC. If the requested main chain needs transport details that are missing, ask or agree on a narrower scope. `label` is optional; IPC defaults to its mechanism as label.
- `dataKind`: optional `payload` or `handle`. A `read` / `write` / `transfer` edge must not carry `handle`; use the actual IPC / call / notification / configuration relationship instead.
- Data arrows follow payload movement: `write` is producer → storage; `read` is storage → consumer. A read request in the opposite direction is a separate control operation, not the data edge.
- `fromSide`, `toSide`: `top`, `bottom`, `left`, `right`; default bottom → top. Choose sides according to real relative positions, not because of the default.
- `fromOffset`, `toOffset`: pixels from side center, default 0. A single attachment stays centered. Multiple distinct inputs can use ordered ports.
- `keepAnchor` with `anchorReason`: exception for an explicit user-requested or real named-port placement, not a shortcut around a bad layout.
- `via`: optional orthogonal route waypoints, each with exactly one coordinate, e.g. `[{"y": 260}, {"x": 440}]`. Anchors derive from node bounds; recheck routes after node movement.
- `labelPosition`: optional `{x, y, anchor}`; x/y is the label's visual center, not its text baseline. `anchor` is `middle` (default), `start` or `end`. Prefer automatic placement until a label needs deliberate positioning, then verify its rendered bounds.

`junctions` entries are `{id, edges: [edgeIds...]}`. They represent a true fan-out with common source and relation and a shared route prefix; never use them to merge unrelated incoming edges or hide different mechanisms. Crossings are generated from actual route geometry, not manually drawn as decorative curves.

## Build workflow

Before building, record delivery context outside the factual model: standalone or article, actual available content widths, target viewports and whether an overview/detail split is needed. Content determines logical canvas size. Do not expand the test viewport to make an over-wide canvas fit, and do not use node count as a fixed splitting threshold.

Commands below run from the skill directory. Use the existing Node runtime; do not install packages or change the environment merely to follow these examples.

```bash
# Default: original logical dimensions, compatible with existing callers.
node scripts/build-diagram.mjs /absolute/path/input.diagram.json /absolute/path/original.html

# Article: common width adaptation, never enlarging above logical size.
node scripts/build-diagram.mjs /absolute/path/input.diagram.json /absolute/path/article.html --presentation article
```

The corresponding JavaScript interface is:

```js
await buildDiagram(input, output); // presentation: 'original'
await buildDiagram(input, output, {presentation: 'article'});
```

Only `original` and `article` are presentation modes. Both retain the logical typography tokens, including 24px node names. `original` keeps the original display scale; `article` adapts to available width with scale at most 1. In article mode, effective node-name text must remain at least 18 CSS px and all other visible text at least 14 CSS px, as defined centrally by `theme.presentation.minNodeFontSize` and `minTextFontSize`. Do not reduce tokens or add page-level scaling to bypass this check. Rearrange or split into a readable overview and detail when fitting would violate the thresholds. A failed mobile width remains failed unless that width receives a readable alternative; a link to an unreadable diagram's detail page is not a pass.

Verify an original artifact with the geometry harness:

```bash
node scripts/verify-examples.mjs --input /absolute/path/original.html --output /tmp/diagram-qa --browser /path/to/chromium
```

Single-input mode checks the supplied artifact, not the canonical examples' negative cases or palette variants. The original harness preserves original-scale geometry checks without enlarging the viewport to the canvas. Inspect its viewport screenshot and, when needed, the full-page or regional detail views; a full-page image alone cannot establish article readability.

Verify the actual article artifact in an embedded fixture at the agreed iframe widths:

```bash
node scripts/verify-article.mjs --input /absolute/path/article.html --output /tmp/article-qa --widths 1200,960 --browser /path/to/chromium
```

`--widths` specifies iframe outer widths; record the resulting inner content widths as well. These are explicit test inputs, not universal site dimensions. Include required mobile widths. The fixture checks the delivered HTML and common iframe adapter at those widths; it does not prove the real site's CSS, content column, CSP or URL paths are correct. Inspect the actual article page as described in [publishing.md](publishing.md), and report separately when that verification was unavailable.

Start a new model from `assets/base-model.json` or the relevant `assets/models/<example>.json`. Replace the technical content, classification, evidence and coordinates. `assets/base-template.html` is a generated preview, not a second hand-maintained source.

When maintaining the skill itself:

```bash
node scripts/build-examples.mjs
node scripts/test-model.mjs
node scripts/verify-examples.mjs --output /tmp/architecture-diagram-qa --browser /path/to/chromium
node scripts/test-presentation.mjs --output /tmp/architecture-presentation-qa --browser /path/to/chromium
```

Also build and verify relevant article-mode task diagrams; canonical original examples alone do not exercise publishing. Both browser harnesses use an existing Playwright installation, resolved through `PLAYWRIGHT_MODULE` or the normal Node lookup including `NODE_PATH`. Use only permitted browser/environment access; if unavailable or denied, report the missing verification rather than claiming success or bypassing a restriction.

## Validation and delivery

Pass the deployment and component-role gates in `modeling.md` before routing. Keep the following acceptance results separate:

1. **Model structure and declared roles**: `ArchitectureModel.validate(model)` returns `{ok, errors, warnings}`. The builder rejects model errors. It checks required deployment references, containment, relative positions, declared role ordering, identity formats and typed relationships. A source ID being present does not prove the source supports a claim.
2. **Technical evidence review**: verify the deployment skeleton, each entity's actual role and execution ownership, and every main-path endpoint/mechanism against evidence. Check whether omissions falsely imply direct API-to-hardware or Guest-to-protected-hardware access. If unresolved, stop or agree on a narrower scope; a geometry pass does not authorize delivery as a correct architecture.
3. **Browser geometry and style**: await `architectureReady` and require `{ok: true}` before checking; the renderer exposes `architectureModel` and `architectureGeometry`. Inject `scripts/check-diagram.js`, then call `checkDiagram({quiet: true})`. Require actually loaded embedded font faces, semantic font selection, shared radii / line styles, exact model/render node, edge and container counts, nonempty recognized content, and zero errors. A font-family declaration or `document.fonts.check()` alone does not prove the intended font loaded. Review every warning; no empty-DOM or legacy-schema fallback is a pass.
4. **Presentation and embedding**: check the declared mode in its intended environment. For article mode, measure effective display sizes, horizontal overflow and clipping, iframe internal scrolling and height synchronization at each available width. Read CSS/font sizes together with the actual rendering scale; a 24px logical declaration alone is insufficient. The same-origin adapter must reject messages with the wrong source, origin or type. Original-scale geometry success does not waive article failures.
5. **Visual and real-page review**: inspect viewport screenshots for the entire readable overview, names, ownership, layering, routing, labels and bridges; use full-page/detail images as supplements. A long diagram may require normal page scrolling, not one-screen compression. Inspect the actual article page for its real layout and loading behavior. A saved screenshot is not a reviewed screenshot, and a fixture is not the site.

Generated canonical examples target zero errors and zero warnings. For task diagrams fix warnings or state each retained warning with a concrete reason; do not silently downgrade violations. After source or style edits, rebuild and rerun the relevant mode and width checks.

Delivery reports name the generated HTML and source model, presentation mode, tested content widths and viewports, structure/role and geometry error/warning counts, effective-text and embedding results, technical review result, actual screenshots reviewed and intentionally omitted non-main-path detail. Distinguish a layout failure from a missing browser or real-page check. Never describe automated zero errors as proof of full architecture compliance. Do not replace the user's original document unless asked.

## Regression cases from authored diagrams

When the contract changes, preserve the existing original examples and exercise the changed behavior with actual author-generated diagrams. Record the author's request, source model and generated artifact before checking. Do not substitute a hand-picked tiny specimen for a difficult article diagram, and do not count regex matches on documentation or generated text as behavioral acceptance.

A reusable case record contains:

| Record | Required evidence |
| --- | --- |
| Authored case | Actual task/request, source-model path, generated HTML path, and relevant article path or URL |
| Delivery context | `original` or `article`, target content widths and browser viewports, supported mobile widths or explicitly unverified scope |
| Automated observations | Structure/geometry results, effective text sizes, overflow/clipping, iframe height and message-source/origin/type checks |
| Visual observations | Viewport screenshot paths and what was inspected; optional full-page/detail images; real-page result recorded separately |
| Resolution | Passed widths, failed or unverified widths, and any re-layout or readable overview/detail split |

For this repository, the authored AAOS overview is a concrete regression candidate: source `content/android-automotive-os-dev/CarAudio/models/aaos17-audio-overview.diagram.json`, published artifact `static/diagrams/aaos17-audio-overview.html`, article `content/android-automotive-os-dev/CarAudio/01-architecture.md`. The adjacent routing and playback models provide different layouts. Build trial outputs into a temporary directory and test those actual author models in article mode without overwriting published files unless authorized. If these paths are unavailable, choose an existing task artifact and record its real paths; do not leave the case as an unexecuted placeholder.

Use positive and negative behavior cases for the changed invariants: a readable article fixture, a width that genuinely drops below the text thresholds, overflow or clipping, height changes on resize, and messages from the wrong source/origin/type. Retain factual models separately from abstract layout specimens. Inspect the produced diagrams and screenshots as well as assertions; tests that only require particular headings or words do not establish the intended layout behavior.
