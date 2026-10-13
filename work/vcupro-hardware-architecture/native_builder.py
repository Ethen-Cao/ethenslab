"""Native, icon-based draw.io primitives for the VCUPro architecture document.

All public geometry is in page coordinates, including edge waypoints. Containers
remain real native parents; this helper converts geometry into parent coordinates.
Only the caller supplies architecture facts. Icons and fonts come from the local
cockpit-system-diagram template and remain editable/offline.
"""

from __future__ import annotations

from copy import deepcopy
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


SKILL = Path(__file__).resolve().parents[1] / "skills" / "cockpit-system-diagram"


def cell(element):
    """Return the mxCell belonging to a raw cell or object wrapper."""
    return element.find("mxCell") if element.tag in {"object", "UserObject"} else element


def styles(element):
    return dict(part.split("=", 1) if "=" in part else (part, "1")
                for part in cell(element).get("style", "").split(";") if part)


def style(element, **updates):
    """Update native style keys, preserving keys such as embedded fontSource."""
    values = styles(element)
    values.update({key: str(value) for key, value in updates.items() if value is not None})
    cell(element).set("style", ";".join(f"{key}={value}" for key, value in values.items()) + ";")
    return element


def _n(value):
    return f"{float(value):g}"


def _plain(value):
    return html.unescape(re.sub(r"<[^>]*>", " ", value)).strip()


class Builder:
    """Build an uncompressed multipage mxfile from native template subtrees.

    ``page`` selects a new current page; ``rects``, ``objects``, ``parents``,
    ``root``, and ``graph`` refer to that page. ``pages[id]`` retains these maps
    for earlier pages. Methods return the created XML element, except ``page``
    which returns the builder and ``save`` which returns the output Path.
    """

    ALIASES = {
        "microphone": "mic", "amplifier": "amp", "touch-display": "touch",
        "storage": "flash", "memory": "dram", "transceiver": "can",
        "wireless": "rfmodule", "wireless-module": "rfmodule",
        "generic-connector": "connector", "coax": "coax-connector",
        "fakra": "coax-connector", "shielded": "shielded-connector",
        "usb-type-a": "usb-a", "usb-type-c": "usb-c",
    }

    def __init__(self, source="", unknowns=None,
                 purpose="Hardware connectivity architecture", skill_dir=SKILL,
                 **metadata):
        self.skill_dir = Path(skill_dir)
        self.template = ET.parse(self.skill_dir / "assets/cockpit-hardware-symbols.drawio").getroot()
        self.tokens = json.loads((self.skill_dir / "assets/tokens.json").read_text())
        self.source = source
        self.templates = {
            page.get("id"): {e.get("id"): e for e in page.findall("./mxGraphModel/root/*")}
            for page in self.template.findall("diagram")
        }
        self.symbols = {}
        for page_id in ("symbols", "connector-symbols"):
            for identity, element in self.templates[page_id].items():
                if element.get("layoutClass"):
                    self.symbols.setdefault(element.get("symbolType"), (page_id, identity))
        variables = json.loads(self.template.get("vars", "{}"))
        variables.update(purpose=purpose, status="Architecture document", source=source,
                         unknowns=unknowns or [], **metadata)
        self.doc = ET.Element("mxfile", host="Electron", compressed="false",
                              vars=json.dumps(variables, ensure_ascii=False))
        self.pages = {}
        self.root = self.graph = None
        self.objects, self.parents, self.rects = {}, {}, {}

    def _append(self, element):
        identity = element.get("id")
        if self.root is None:
            raise ValueError("Call page() before adding elements")
        if identity in self.objects:
            raise ValueError(f"Duplicate cell ID: {identity}")
        native = cell(element)
        self.root.append(element)
        self.objects[identity] = element
        self.parents[identity] = native.get("parent")
        geometry = native.find("mxGeometry")
        if geometry is not None and native.get("vertex") == "1" and geometry.get("relative") != "1":
            px, py = self._origin(native.get("parent"))
            self.rects[identity] = (px + float(geometry.get("x", 0)),
                                    py + float(geometry.get("y", 0)),
                                    float(geometry.get("width", 0)), float(geometry.get("height", 0)))
        return element

    def _origin(self, parent):
        if parent in {None, "0", "1"}:
            return 0, 0
        if parent not in self.rects:
            raise ValueError(f"Unknown or nongeometric parent: {parent}")
        return self.rects[parent][:2]

    def _position(self, element, x, y, w, h, parent):
        px, py = self._origin(parent)
        native = cell(element)
        native.set("parent", parent)
        geometry = native.find("mxGeometry")
        if geometry is None:
            geometry = ET.SubElement(native, "mxGeometry", {"as": "geometry"})
        geometry.attrib.update(x=_n(x - px), y=_n(y - py), width=_n(w), height=_n(h))

    def _copy(self, page_id, old, identity, parent="1"):
        element = deepcopy(self.templates[page_id][old])
        element.set("id", identity)
        native = cell(element)
        if element is not native:
            native.attrib.pop("id", None)
        native.set("parent", parent)
        return element

    def page(self, id, title, subtitle, width, height):
        if id in self.pages:
            raise ValueError(f"Duplicate page ID: {id}")
        diagram = ET.SubElement(self.doc, "diagram", id=id, name=title)
        original = self.template.find("diagram[@id='audio-example']/mxGraphModel")
        self.graph = ET.SubElement(diagram, "mxGraphModel", dict(original.attrib))
        self.graph.attrib.update(pageWidth=_n(width), pageHeight=_n(height),
                                 dx=_n(width), dy=_n(height), nodeStyle="icons")
        self.root = ET.SubElement(self.graph, "root")
        self.objects, self.parents, self.rects = {}, {}, {}
        self.pages[id] = dict(graph=self.graph, root=self.root, objects=self.objects,
                              parents=self.parents, rects=self.rects)
        self._append(ET.Element("mxCell", id="0"))
        self._append(ET.Element("mxCell", id="1", parent="0"))
        heading = self._copy("audio-example", "title", "title")
        heading.attrib.update(label=title, kind="page-contract", nodeStyle="icons")
        self._position(heading, 40, 28, width - 80, 38, "1")
        self._append(heading)
        if subtitle:
            self.text("subtitle", subtitle, 40, 72, width - 80, 24,
                      color=self.tokens["colors"]["muted"])
        self._append(self._copy("audio-example", "font-mono", "font-mono"))
        return self

    def text(self, id, label, x, y, w, h, parent="1", size=14,
             bold=False, color=None, **style_updates):
        element = self._copy("audio-example", "subtitle", id, parent)
        element.set("label", str(label).replace("\n", "<br>"))
        style(element, **dict(dict(fontSize=size, fontStyle=1 if bold else 0,
              fontColor=color or self.tokens["colors"]["ink"],
              whiteSpace="nowrap"), **style_updates))
        self._position(element, x, y, w, h, parent)
        return self._append(element)

    def container(self, id, title, x, y, w, h, parent="1", kind="functional-group",
                  source=None, subtitle="", **metadata):
        if kind not in {"physical-enclosure", "board", "functional-group"}:
            raise ValueError(f"Unknown container kind: {kind}")
        original = "audio-ecu" if kind == "physical-enclosure" else "audio-board"
        element = self._copy("audio-example", original, id, parent)
        element.attrib.update(canonicalName=_plain(title), kind=kind,
                              source=self.source if source is None else source,
                              **{key: str(value) for key, value in metadata.items()})
        for key in ("entityType", "layoutClass", "symbolType"):
            element.attrib.pop(key, None)
        colors = self.tokens["colors"]
        style(element, fillColor=colors["panel"], strokeColor=colors["border"],
              strokeWidth=self.tokens["strokes"]["container"])
        if kind == "functional-group":
            style(element, dashed=1, dashPattern="6 5", fillColor="none",
                  strokeColor=colors["functionalBorder"])
        self._position(element, x, y, w, h, parent)
        self._append(element)
        self.text(id + "-heading", title, x + 20, y + 12, w - 40, 28,
                  parent=id, size=18, bold=True)
        if subtitle:
            self.text(id + "-subheading", subtitle, x + 20, y + 40, w - 40, 18,
                      parent=id, size=12, color=self.tokens["colors"]["muted"])
        return element

    def card(self, id, symbolType, title, subtitle, x, y, w, parent="1",
             status="", h=None, source=None, **metadata):
        symbol_type = self.ALIASES.get(symbolType, symbolType)
        if symbol_type not in self.symbols:
            raise ValueError(f"Unknown native symbol {symbolType!r}; available: {', '.join(self.symbols)}")
        page_id, old = self.symbols[symbol_type]
        catalog = self.templates[page_id]
        original = catalog[old]
        connector = original.get("layoutClass") == "connector"
        processor = original.get("layoutClass") == "processor"
        height = h if h is not None else (48 if connector else 80)
        if not processor and height != (48 if connector else 80):
            raise ValueError("Only SoC/MCU may use variable-height cards")
        if height < 80 and processor:
            raise ValueError("Processor cards need at least an 80 px header")
        title = str(title).replace("\n", "<br>")
        subtitle = str(subtitle or "").replace("\n", "<br>")
        if connector and subtitle:
            raise ValueError("Compact connectors use a single title; put extra detail in external text")
        if status and status.casefold() not in (title + " " + subtitle).casefold():
            if connector:
                title += f" ({status})"
            else:
                subtitle = f"{subtitle} · {status}" if subtitle else status
        selected = {old}
        while True:
            expanded = selected | {identity for identity, e in catalog.items()
                                   if cell(e).get("parent") in selected}
            if expanded == selected:
                break
            selected = expanded
        if not subtitle:
            selected.discard(old + "-description")
        mapping = {identity: id + identity[len(old):] if identity.startswith(old)
                   else id + "-" + identity for identity in selected}
        copies = {}
        for identity, original_child in catalog.items():
            if identity not in selected:
                continue
            copied = deepcopy(original_child)
            copied.set("id", mapping[identity])
            native = cell(copied)
            if native is not copied:
                native.attrib.pop("id", None)
            if native.get("edge") == "1" and not native.get("source") and not native.get("target"):
                copied.set("kind", "icon-stroke")
            for key in ("parent", "source", "target"):
                if native.get(key) in mapping:
                    native.set(key, mapping[native.get(key)])
            copies[identity] = copied
        element = copies[old]
        element.attrib.update(canonicalName=_plain(title), symbolType=symbol_type,
                              nodeStyle="icons", source=self.source if source is None else source,
                              status=status, **{key: str(value) for key, value in metadata.items()})
        if status.casefold() in {"reserved", "optional", "dnp"}:
            style(element, dashed=1, dashPattern="6 5",
                  fillColor=self.tokens["colors"]["reservedFill"],
                  strokeColor=self.tokens["colors"]["reservedBorder"])
        self._position(element, x, y, w, height, parent)
        # Expanded processors keep the compact icon/text header at the top.
        cfg = self.tokens["connector" if connector else "node"]
        header_height = 80 if processor else height
        name_height = cfg["lineHeight"] if connector else cfg["nameLineHeight"] * (title.count("<br>") + 1)
        total_height = name_height + (20 if subtitle else 0)
        name_y = (header_height - total_height) / 2
        name_x = cfg["paddingX"] + cfg["iconSlot"] + cfg["iconGap"]
        name = copies[old + "-name"]
        name.set("label", title)
        cell(name).find("mxGeometry").attrib.update(x=_n(name_x), y=_n(name_y),
                                                    width=_n(w - name_x - cfg["paddingX"]), height=_n(name_height))
        if subtitle:
            description = copies.get(old + "-description")
            if description is None:
                description = self._copy("audio-example", "subtitle", id + "-description", id)
                copies[old + "-description"] = description
            description.set("label", subtitle)
            style(description, fontSize=12, fontStyle=0, whiteSpace="nowrap",
                  fontColor=self.tokens["colors"]["muted"])
            cell(description).find("mxGeometry").attrib.update(x=_n(name_x), y=_n(name_y + name_height + 4),
                                                               width=_n(w - name_x - cfg["paddingX"]), height="16")
        # The native template lists parents before descendants. Explicitly retain
        # that property so absolute rectangles can be recorded as cells arrive.
        pending = list(copies.values())
        while pending:
            available = [e for e in pending if cell(e).get("parent") in self.objects]
            if not available:
                raise ValueError(f"Could not remap native icon subtree for {id}")
            for e in available:
                self._append(e)
                pending.remove(e)
        return element

    def _ancestors(self, identity):
        ancestors = []
        current = self.parents.get(identity)
        while current is not None:
            ancestors.append(current)
            current = self.parents.get(current)
        return ancestors

    def edge(self, id, source, target, family="communication", label="",
             from_=(1, .5), to=(0, .5), points=(), arrow=True, both=False,
             dash=False, label_pos=0, label_offset=(0, -14), **metadata):
        if source not in self.objects or target not in self.objects:
            raise ValueError(f"Unknown edge endpoint: {source} -> {target}")
        for port in (from_, to):
            if len(port) != 2 or not all(0 <= value <= 1 for value in port) or not any(value in {0, 1} for value in port):
                raise ValueError(f"Port must lie on a normalized card boundary: {port}")
        if not -1 <= label_pos <= 1:
            raise ValueError("Edge label position must be in -1…1")
        target_ancestors = set(self._ancestors(target))
        parent = next(identity for identity in self._ancestors(source) if identity in target_ancestors)
        px, py = self._origin(parent)
        element = self._copy("audio-example", "soc-dsp-stream", id, parent)
        element.attrib.update(signalClass=family, sourceEvidence=self.source,
                              **{key: str(value) for key, value in metadata.items()})
        native = cell(element)
        native.attrib.update(source=source, target=target)
        style(element, edgeStyle="segmentEdgeStyle" if points else "orthogonalEdgeStyle",
              strokeColor=self.tokens["signalColors"][family], strokeWidth=self.tokens["strokes"]["control"],
              startArrow="open" if both else "none", endArrow="open" if arrow or both else "none",
              dashed=1 if dash else 0, exitX=from_[0], exitY=from_[1],
              entryX=to[0], entryY=to[1], exitPerimeter=0, entryPerimeter=0)
        geometry = native.find("mxGeometry")
        for child in list(geometry):
            geometry.remove(child)
        if points:
            array = ET.SubElement(geometry, "Array", {"as": "points"})
            for waypoint_x, waypoint_y in points:
                ET.SubElement(array, "mxPoint", x=_n(waypoint_x - px), y=_n(waypoint_y - py))
        self._append(element)
        if label:
            label_cell = self._copy("audio-example", "soc-dsp-stream-label", id + "-label", id)
            label_cell.set("value", str(label).replace("\n", "<br>"))
            style(label_cell, fontColor=self.tokens["signalColors"][family], fillColor="none")
            label_geometry = label_cell.find("mxGeometry")
            label_geometry.set("x", _n(label_pos))
            label_geometry.find("mxPoint").attrib.update(x=_n(label_offset[0]), y=_n(label_offset[1]))
            self._append(label_cell)
        return element

    def style(self, element_or_id, **updates):
        return style(self.objects[element_or_id] if isinstance(element_or_id, str) else element_or_id,
                     **updates)

    def legend_entry(self, id, label, x, y, w=240, parent="1", *,
                     legend_type="signal", family=None, value=None, width=1.8):
        """Editable sample+label group using the skill's legend contract."""
        cfg = self.tokens["legend"]
        length, gap, height = cfg["sampleWidth"], cfg["labelGap"], cfg["rowHeight"]
        if w <= length + gap:
            raise ValueError("Legend width must leave room for its label")
        meta = {"id": id, "label": "", "kind": "legend-entry", "legendType": legend_type}
        if family:
            meta["signalClass"] = family
        if value:
            meta["legendValue"] = value
        group = ET.Element("object", meta)
        native = ET.SubElement(group, "mxCell", parent=parent, vertex="1",
                               style="group;container=1;recursiveResize=0;collapsible=0;fillColor=none;strokeColor=none;")
        ET.SubElement(native, "mxGeometry", {"as": "geometry"})
        self._position(group, x, y, w, height, parent)
        self._append(group)
        sample = ET.Element("object", id=id + "-sample", label="", kind="legend-sample")
        line = ET.SubElement(sample, "mxCell", parent=id, edge="1")
        color = self.tokens["signalColors"][family] if family else self.tokens["colors"]["muted"]
        style(sample, strokeColor=color, strokeWidth=width, startArrow="open" if value == "bidirectional" else "none",
              endArrow="open" if value in {"single", "bidirectional"} else "none",
              startFill=0, endFill=0, startSize=8, endSize=8, dashed=1 if value == "dashed" else 0,
              dashPattern="6 5", rounded=0, edgeStyle="none")
        geometry = ET.SubElement(line, "mxGeometry", relative="1", **{"as": "geometry"})
        ET.SubElement(geometry, "mxPoint", x="0", y=_n(height/2), **{"as": "sourcePoint"})
        ET.SubElement(geometry, "mxPoint", x=_n(length), y=_n(height/2), **{"as": "targetPoint"})
        self._append(sample)
        self.text(id + "-label", label, x + length + gap, y, w - length - gap, height,
                  parent=id, size=cfg["fontSize"], color=self.tokens["colors"]["ink"])
        return group

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ET.indent(self.doc, space="  ")
        ET.ElementTree(self.doc).write(path, encoding="utf-8", xml_declaration=True)
        return path
