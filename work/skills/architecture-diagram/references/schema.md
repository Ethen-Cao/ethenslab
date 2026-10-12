# Model, build and verification

The maintained source is a version-2 JSON model. The builder inlines the shared model validator, renderer, CSS, theme and pinned font resources into a standalone HTML. Do not edit generated HTML to fix a model or style problem; edit its source and rebuild. `assets/theme.json` is the shared visual-token source, not a per-model override.

All geometry uses absolute SVG logical pixels. All figure text, including accessibility text, is English. Source locators may retain original filenames and URLs. Source titles are non-visible metadata and may preserve the original language. The automated language check catches accidental CJK figure text; it is not an English-language detector, so review the rendered wording manually.

## Model fields

| Field | Contract |
| --- | --- |
| `version` | Required; `2` |
| `meta` | Required classification, purpose and figure identity; see below |
| `canvas` | Required positive `width`, `height`; no slide ratio |
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

Commands below run from the skill directory. Use the existing Node runtime; do not install packages or change the environment merely to follow these examples.

```bash
node scripts/build-diagram.mjs /absolute/path/input.diagram.json /absolute/path/output.html
```

Verify that task artifact with the same browser geometry and screenshot engine:

```bash
node scripts/verify-examples.mjs --input /absolute/path/output.html --output /tmp/diagram-qa
```

Single-input mode checks only the supplied artifact; it does not run the canonical examples' negative cases or palette variants. It also accepts `--browser /path/to/chromium`. Review the generated screenshot rather than treating a successful capture as visual approval.

Start a new model from `assets/base-model.json` or the relevant `assets/models/<example>.json`. Replace the technical content, classification, evidence and coordinates. `assets/base-template.html` is a generated preview, not a second hand-maintained source.

When maintaining the skill itself:

```bash
node scripts/build-examples.mjs
node scripts/test-model.mjs
node scripts/verify-examples.mjs --output /tmp/architecture-diagram-qa
```

The browser harness accepts `--browser /path/to/chromium` when a browser binary must be specified. It uses an existing Playwright installation, resolved through `PLAYWRIGHT_MODULE` (module path) or the normal Node lookup including `NODE_PATH`; do not install dependencies merely for this test. Use only permitted browser/environment access; if unavailable or denied, report the missing visual verification rather than claiming it succeeded or bypassing a restriction.

## Validation and delivery

Pass the deployment and component-role gates in `modeling.md` before routing. There are four distinct acceptance results; none replaces another:

1. **Model structure and declared roles**: `ArchitectureModel.validate(model)` returns `{ok, errors, warnings}`. The builder rejects model errors. It checks required deployment references, containment, relative positions, declared role ordering, identity formats and typed relationships. A source ID being present does not prove the source supports a claim.
2. **Technical evidence review**: verify the deployment skeleton, each entity's actual role and execution ownership, and every main-path endpoint/mechanism against evidence. Check whether omissions falsely imply direct API-to-hardware or Guest-to-protected-hardware access. If unresolved, stop or agree on a narrower scope; a geometry pass does not authorize delivery as a correct architecture.
3. **Browser geometry and style**: await `architectureReady` and require `{ok: true}` before checking; the renderer exposes `architectureModel` and `architectureGeometry`. Inject `scripts/check-diagram.js`, then call `checkDiagram({quiet: true})`. Require actual loaded embedded font faces, semantic font selection, shared radii / line styles, exact model/render node, edge and container counts, nonempty recognized content, and zero errors. A font-family declaration or `document.fonts.check()` alone does not prove the intended font loaded. Review every warning; no empty-DOM or legacy-schema fallback is a pass.
4. **Visual review**: inspect the full deployment outline and readable OS / subsystem regions, then names, ownership, layering, routing, labels and bridges. A saved screenshot is not a reviewed screenshot.

Generated canonical examples target zero errors and zero warnings. For task diagrams fix warnings or state each retained warning with a concrete reason; do not silently downgrade violations. After a source or style edit rebuild and rerun the relevant checks.

Delivery reports name the generated HTML and source model, structure/role and geometry error/warning counts separately, technical review result, what was visually inspected, and any intentionally omitted non-main-path detail. Never describe automated “zero errors” as proof of full architecture compliance. If browser review was unavailable, say so explicitly. Do not replace the user's original document unless asked.

When changing this skill's contract, update the source examples and add negative tests for the changed invariants, rebuild generated examples, and inspect them. Retain factual models separately from abstract layout specimens; otherwise a template may look compliant while teaching unsupported platform facts.
