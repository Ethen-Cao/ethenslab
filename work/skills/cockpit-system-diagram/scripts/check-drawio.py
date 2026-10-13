#!/usr/bin/env python3
"""Validate the native structure and compact-card contract of cockpit draw.io.

Read-only; Python standard library only. This is not a renderer, font-measuring
engine, electrical validator, or a substitute for visual/architecture review.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from dataclasses import dataclass
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zlib


EPSILON = 0.01
SCOPE = (
    "Native XML identity, nesting, bound endpoints, normalized ports, editable "
    "primitives, and compact-card geometry/declared typography. Does not measure "
    "rendered text, detect routed crossings, verify electrical semantics, or "
    "replace draw.io render/save/move review."
)
EXPECTED = {
    "node": ("height", "paddingX", "paddingY", "iconSlot", "iconMax", "iconGap",
             "nameFont", "nameLineHeight", "descriptionFont", "descriptionLineHeight", "textGap"),
    "connector": ("height", "paddingX", "iconSlot", "iconMax", "iconGap", "font", "minFont", "lineHeight"),
}


def number(value, default=None):
    if value is None:
        if default is not None:
            return default
        raise ValueError("missing number")
    if isinstance(value, bool):
        raise ValueError("boolean is not a geometry value")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("number must be finite")
    return result


def near(a, b):
    return abs(a - b) <= EPSILON


def styles(value):
    return dict(item.split("=", 1) if "=" in item else (item, "1")
                for item in value.split(";") if item)


class Label(HTMLParser):
    """Count explicit lines only; wrapping/actual glyph metrics need rendering."""

    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.fonts = []
        self.feed(value)
        self.close()
        self.text = "".join(self.parts).strip()
        self.lines = [line.strip() for line in self.text.splitlines() if line.strip()]

    def newline(self):
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_starttag(self, tag, attributes):
        if tag == "br" or tag in {"div", "p", "li"}:
            self.newline()
        inline = dict(attributes).get("style", "")
        for match in re.finditer(r"(?:^|;)\s*font-size\s*:\s*([\d.]+)\s*(px|pt)\b", inline, re.I):
            self.fonts.append(float(match.group(1)) * (4 / 3 if match.group(2).lower() == "pt" else 1))

    def handle_endtag(self, tag):
        if tag in {"div", "p", "li"}:
            self.newline()

    def handle_data(self, data):
        self.parts.append(data)


def parse_xml(raw):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DTD/entity declarations are unsupported")
    return ET.fromstring(raw)


def read_pages(path):
    document = parse_xml(path.read_bytes())
    if document.tag == "mxGraphModel":
        return [("graph", document, False)]
    if document.tag != "mxfile":
        raise ValueError("expected mxfile or mxGraphModel")
    pages = []
    for index, diagram in enumerate(document.findall("diagram"), 1):
        name = diagram.get("name") or diagram.get("id") or f"page-{index}"
        graph = diagram.find("mxGraphModel")
        compressed = False
        if graph is None:
            payload = (diagram.text or "").strip()
            if not payload:
                raise ValueError(f"{name}: empty diagram payload")
            if payload.startswith("<"):
                graph = parse_xml(payload.encode("utf-8"))
            else:
                try:
                    packed = base64.b64decode("".join(payload.split()), validate=True)
                    inflated = zlib.decompress(packed, -15).decode("utf-8")
                    graph = parse_xml(unquote(inflated, errors="strict").encode("utf-8"))
                    compressed = True
                except (binascii.Error, zlib.error, UnicodeError, ValueError, ET.ParseError) as error:
                    raise ValueError(f"{name}: invalid compressed diagram ({error})") from error
        if graph.tag != "mxGraphModel":
            raise ValueError(f"{name}: payload is not mxGraphModel")
        pages.append((name, graph, compressed))
    if not pages:
        raise ValueError("mxfile contains no pages")
    return pages


def read_tokens(path):
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("version") != 1:
        raise ValueError("tokens.version must be 1")
    if number(result.get("grid")) <= 0:
        raise ValueError("tokens.grid must be positive")
    for section, keys in EXPECTED.items():
        for key in keys:
            if number(result.get(section, {}).get(key)) <= 0:
                raise ValueError(f"tokens.{section}.{key} must be positive")
    if result["connector"]["minFont"] > result["connector"]["font"]:
        raise ValueError("connector minFont must not exceed font")
    return result


@dataclass
class Cell:
    id: str
    xml: ET.Element
    metadata: dict
    style: dict
    geometry: ET.Element | None

    @property
    def parent(self):
        return self.xml.get("parent")

    @property
    def vertex(self):
        return self.xml.get("vertex") == "1"

    @property
    def edge(self):
        return self.xml.get("edge") == "1"

    @property
    def value(self):
        return self.metadata.get("label", self.xml.get("value", ""))

    def rect(self):
        if self.geometry is None:
            raise ValueError("missing geometry")
        return tuple(number(self.geometry.get(key), 0) for key in ("x", "y", "width", "height"))


class Graph:
    def __init__(self, name, model, compressed, tokens, report):
        self.name, self.compressed, self.tokens, self.report = name, compressed, tokens, report
        self.cells = {}
        root = model.find("root")
        if root is None:
            self.issue("missing-root", "mxGraphModel has no root")
            return
        for element in root:
            if element.tag == "mxCell":
                xml, metadata, identity = element, dict(element.attrib), element.get("id")
            elif element.tag in {"object", "UserObject"}:
                children = element.findall("mxCell")
                if len(children) != 1:
                    self.issue("object-cell", "wrapper must contain one mxCell", element.get("id"))
                    continue
                xml, metadata, identity = children[0], dict(element.attrib), element.get("id")
                if xml.get("id") and xml.get("id") != identity:
                    self.issue("object-id", "wrapper/child IDs disagree", identity)
            else:
                self.issue("root-entry", f"unsupported root entry {element.tag}")
                continue
            if not identity:
                self.issue("missing-id", "every logical cell needs an ID")
                continue
            if identity in self.cells:
                self.issue("duplicate-id", "duplicate logical cell ID", identity)
                continue
            geometries = xml.findall("mxGeometry")
            if len(geometries) > 1:
                self.issue("geometry-count", "cell has multiple geometries", identity)
            self.cells[identity] = Cell(identity, xml, metadata, styles(xml.get("style", "")), geometries[0] if geometries else None)

    def issue(self, code, message, identity=None, warning=False):
        item = {"page": self.name, "code": code, "message": message}
        if identity:
            item["cell"] = identity
        self.report["warnings" if warning else "errors"].append(item)

    def ancestors(self, identity):
        result, seen = [], {identity}
        cell = self.cells.get(identity)
        while cell and cell.parent:
            if cell.parent in seen:
                return None
            seen.add(cell.parent)
            result.append(cell.parent)
            cell = self.cells.get(cell.parent)
        return result

    def child(self, owner, suffix):
        child = self.cells.get(owner.id + suffix)
        if child is None or not child.vertex or child.parent != owner.id:
            self.issue("card-child", f"needs direct native child {owner.id + suffix}", owner.id)
            return None
        return child

    def check_font(self, cell, minimum, maximum):
        declared = number(cell.style.get("fontSize"))
        fonts = [declared, *Label(cell.value).fonts]
        if any(font < minimum - EPSILON or font > maximum + EPSILON for font in fonts):
            self.issue("card-font", f"font must be {minimum:g}–{maximum:g}px, including inline CSS", cell.id)
        if cell.style.get("align") != "left":
            self.issue("card-text-align", "card labels must be left-aligned", cell.id)
        if cell.style.get("verticalAlign", "middle") != "middle":
            self.issue("card-text-align", "text boxes must use middle vertical alignment", cell.id)
        return Label(cell.value)

    def check_icon(self, icon, card, cfg):
        x, y, width, height = icon.rect()
        card_height = card.rect()[3]
        if not (near(width, cfg["iconSlot"]) and near(height, cfg["iconSlot"])):
            self.issue("icon-slot", f"icon slot must be {cfg['iconSlot']}×{cfg['iconSlot']}", icon.id)
        if not (near(x, cfg["paddingX"]) and near(y, (card_height - cfg["iconSlot"]) / 2)):
            self.issue("icon-position", "icon slot must use fixed left padding and vertical centering", icon.id)
        bounds = []
        for cell in self.cells.values():
            chain = self.ancestors(cell.id)
            if not chain or icon.id not in chain or cell.geometry is None:
                continue
            # Native group children use parent-relative coordinates. Relative
            # icon glyphs are deliberately unsupported: use absolute primitives.
            if cell.geometry.get("relative") == "1" and cell.vertex:
                self.issue("icon-relative", "icon primitives need absolute parent-relative geometry", cell.id)
                continue
            ox, oy = 0.0, 0.0
            parent = self.cells.get(cell.parent)
            while parent and parent.id != icon.id:
                px, py, _, _ = parent.rect()
                ox, oy = ox + px, oy + py
                parent = self.cells.get(parent.parent)
            if cell.vertex:
                gx, gy, gw, gh = cell.rect()
                if cell.style.get("shape") == "group" or cell.style.get("group") == "1":
                    continue
                theta = math.radians(number(cell.style.get("rotation"), 0))
                rw = abs(gw * math.cos(theta)) + abs(gh * math.sin(theta))
                rh = abs(gw * math.sin(theta)) + abs(gh * math.cos(theta))
                cx, cy = ox + gx + gw / 2, oy + gy + gh / 2
                bounds.append((cx - rw / 2, cy - rh / 2, cx + rw / 2, cy + rh / 2))
            elif cell.edge:
                for point in cell.geometry.iter("mxPoint"):
                    if point.get("as") == "offset":
                        continue
                    px, py = number(point.get("x"), 0), number(point.get("y"), 0)
                    bounds.append((ox + px, oy + py, ox + px, oy + py))
        if not bounds:
            self.issue("empty-icon", "icon slot has no editable native glyph primitives", icon.id)
            return
        left, top = min(r[0] for r in bounds), min(r[1] for r in bounds)
        right, bottom = max(r[2] for r in bounds), max(r[3] for r in bounds)
        if left < -EPSILON or top < -EPSILON or right > width + EPSILON or bottom > height + EPSILON:
            self.issue("icon-bounds", "glyph geometry lies outside its icon slot", icon.id)
        if right - left > cfg["iconMax"] + EPSILON or bottom - top > cfg["iconMax"] + EPSILON:
            self.issue("icon-size", f"glyph geometry must fit {cfg['iconMax']}×{cfg['iconMax']}", icon.id)

    def check_card(self, cell):
        kind = cell.metadata.get("layoutClass")
        if kind not in {"device", "connector", "processor", "port-strip"}:
            if cell.metadata.get("entityType") in {"hardware", "memory"}:
                self.issue("layout-class", "hardware/memory entity needs an explicit compact layoutClass", cell.id)
            elif kind:
                self.issue("layout-class", f"unknown hardware layoutClass: {kind}", cell.id)
            return False
        for field in ("canonicalName", "symbolType"):
            if not cell.metadata.get(field, "").strip():
                self.issue("card-metadata", f"classified node needs {field}", cell.id)
        if not cell.vertex:
            self.issue("card-role", "classified hardware object must be a vertex", cell.id)
            return True
        if kind == "processor":
            if cell.metadata.get("symbolType", "").lower() not in {"soc", "mcu"}:
                self.issue("processor-exception", "only SoC/MCU may use processor height exception", cell.id)
            return True
        if kind == "port-strip":
            if cell.metadata.get("symbolType") not in {"connector", "port-strip", "connector-strip"}:
                self.issue("port-strip-type", "port-strip is only for explicitly expanded connector terminals", cell.id)
            return True
        cfg = self.tokens["node" if kind == "device" else "connector"]
        _, _, width, height = cell.rect()
        if not near(height, cfg["height"]):
            self.issue("card-height", f"{kind} height must be {cfg['height']}", cell.id)
        icon, name = self.child(cell, "-icon"), self.child(cell, "-name")
        description = self.cells.get(cell.id + "-description")
        if icon:
            self.check_icon(icon, cell, cfg)
        if not name:
            return True
        desc_height = 0
        if kind == "connector":
            label = self.check_font(name, cfg["minFont"], cfg["font"])
            expected_name_height = cfg["lineHeight"]
            if len(label.lines) != 1:
                self.issue("connector-line", "connector label must have exactly one explicit line", name.id)
            if description:
                self.issue("connector-description", "compact connector has a single label, not a subtitle", description.id)
            gap = 0
        else:
            label = self.check_font(name, cfg["nameFont"], cfg["nameFont"])
            if not 1 <= len(label.lines) <= 2:
                self.issue("name-lines", "device name must contain 1–2 explicit lines", name.id)
            expected_name_height = max(1, len(label.lines)) * cfg["nameLineHeight"]
            gap = 0
            if description:
                if not description.vertex or description.parent != cell.id:
                    self.issue("card-child", "description must be a direct native card child", description.id)
                desc_label = self.check_font(description, cfg["descriptionFont"], cfg["descriptionFont"])
                if len(desc_label.lines) != 1:
                    self.issue("description-lines", "description must have one explicit line; omit empty subtitle cells", description.id)
                desc_height, gap = cfg["descriptionLineHeight"], cfg["textGap"]
        expected_x = cfg["paddingX"] + cfg["iconSlot"] + cfg["iconGap"]
        expected_width = width - expected_x - cfg["paddingX"]
        if expected_width <= 0:
            self.issue("card-width", "card is too narrow for its icon, gap, and text", cell.id)
        total = expected_name_height + gap + desc_height
        expected_y = (height - total) / 2
        if kind == "device" and expected_y < cfg["paddingY"] - EPSILON:
            self.issue("text-padding", "text group violates vertical safe padding", cell.id)
        expected = [(name, expected_y, expected_name_height)]
        if kind == "device" and description:
            expected.append((description, expected_y + expected_name_height + gap, desc_height))
        for text, y, h in expected:
            actual = text.rect()
            if not all(near(a, b) for a, b in zip(actual, (expected_x, y, expected_width, h))):
                self.issue("text-geometry", f"text box must be x={expected_x:g}, y={y:g}, width={expected_width:g}, height={h:g}; center actual line group", text.id)
        return True

    def check_edge(self, cell):
        source, target = cell.xml.get("source"), cell.xml.get("target")
        decoration = cell.id.startswith("legend-") or cell.metadata.get("kind") in {"decoration", "legend", "icon-stroke"}
        if not source and not target:
            if not decoration:
                self.issue("unbound-edge", "relationship needs source and target; only explicit legend/decoration may be free-ended", cell.id)
            return False
        ends = [self.cells.get(source), self.cells.get(target)]
        if any(end is None or not end.vertex or (self.cells.get(end.parent) and self.cells[end.parent].edge) for end in ends):
            self.issue("edge-endpoint", "source and target must reference existing non-label vertices", cell.id)
            return False
        source_chain, target_chain = self.ancestors(source), self.ancestors(target)
        if source_chain is not None and target_chain is not None:
            common = next((identity for identity in source_chain if identity in set(target_chain)), None)
            if cell.parent != common:
                self.issue("edge-parent", f"edge parent must be nearest common ancestor {common!r}", cell.id)
        for prefix in ("exit", "entry"):
            x, y = number(cell.style.get(prefix + "X")), number(cell.style.get(prefix + "Y"))
            if not (0 <= x <= 1 and 0 <= y <= 1):
                self.issue("edge-port", f"{prefix} coordinates must be normalized to 0…1", cell.id)
            elif not (near(x, 0) or near(x, 1) or near(y, 0) or near(y, 1)):
                self.issue("edge-port", f"{prefix} port must lie on the component boundary", cell.id)
            if cell.style.get(prefix + "Perimeter") != "0":
                self.issue("edge-port", f"fixed ports require {prefix}Perimeter=0", cell.id)
        return True

    def validate(self):
        roots = [cell for cell in self.cells.values() if not cell.parent]
        if len(roots) != 1 or roots[0].vertex or roots[0].edge:
            self.issue("graph-root", "graph needs one non-drawable parentless root")
        components, connections = 0, 0
        for cell in self.cells.values():
            if cell.parent and cell.parent not in self.cells:
                self.issue("missing-parent", f"parent {cell.parent!r} does not exist", cell.id)
            if self.ancestors(cell.id) is None:
                self.issue("parent-cycle", "cyclic parent hierarchy", cell.id)
            if cell.vertex and cell.edge:
                self.issue("cell-role", "cell cannot be both vertex and edge", cell.id)
            parent = self.cells.get(cell.parent)
            is_label = cell.style.get("edgeLabel") == "1"
            if is_label and not (parent and parent.edge):
                self.issue("label-parent", "edgeLabel must be a child of its native edge", cell.id)
            if is_label or (parent and parent.edge and cell.vertex):
                if cell.geometry is None or cell.geometry.get("relative") != "1":
                    self.issue("label-relative", "edge-child labels/markers need relative geometry", cell.id)
                elif is_label:
                    try:
                        if not -1 <= number(cell.geometry.get("x"), 0) <= 1:
                            self.issue("label-position", "relative edge-label x must be within -1…1", cell.id)
                    except ValueError as error:
                        self.issue("geometry-number", str(error), cell.id)
            if not (cell.vertex or cell.edge):
                continue
            if cell.style.get("image") or cell.style.get("shape") == "image" or "<img" in cell.value.lower():
                self.issue("image-cell", "hardware symbols and diagrams must remain native editable primitives", cell.id)
            if cell.style.get("locked") == "1" or cell.metadata.get("locked") == "1":
                self.issue("locked-cell", "diagram components must remain editable", cell.id)
            if cell.geometry is None or cell.geometry.get("as") != "geometry":
                self.issue("missing-geometry", "drawable cell needs mxGeometry as='geometry'", cell.id)
                continue
            try:
                _, _, width, height = cell.rect()
                if cell.vertex and not (parent and parent.edge) and (width <= 0 or height <= 0):
                    self.issue("vertex-size", "vertex width and height must be positive", cell.id)
                for point in cell.geometry.iter("mxPoint"):
                    number(point.get("x"), 0)
                    number(point.get("y"), 0)
                if cell.edge:
                    if cell.geometry.get("relative") != "1":
                        self.issue("edge-geometry", "edge geometry must be relative", cell.id)
                    connections += int(self.check_edge(cell))
                else:
                    components += int(self.check_card(cell))
            except (ValueError, TypeError, OverflowError) as error:
                self.issue("contract-value", str(error), cell.id)
        if components == 0:
            self.issue("no-classified-cards", "page has no classified hardware cards; inspect whether it is a legend-only page", warning=True)
        return {"name": self.name, "compressed": self.compressed, "cells": len(self.cells),
                "classifiedCards": components, "boundEdges": connections}


def validate(path, tokens):
    report = {"ok": False, "file": str(path), "pages": [], "errors": [], "warnings": [], "scope": SCOPE}
    for name, graph, compressed in read_pages(Path(path)):
        report["pages"].append(Graph(name, graph, compressed, tokens, report).validate())
    report["ok"] = not report["errors"]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagram", type=Path)
    parser.add_argument("--tokens", type=Path, default=Path(__file__).resolve().parent.parent / "assets" / "tokens.json")
    args = parser.parse_args(argv)
    try:
        result = validate(args.diagram, read_tokens(args.tokens))
    except (OSError, ValueError, ET.ParseError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "file": str(args.diagram), "inputError": str(error), "scope": SCOPE}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
