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
    "primitives, page-wide icons/plain style, compact-card geometry/declared typography, "
    "and native legend samples/coverage. Does not measure "
    "rendered text, detect routed crossings, verify electrical semantics, or "
    "replace draw.io render/save/move review."
)
EXPECTED = {
    "node": ("height", "paddingX", "paddingY", "iconSlot", "iconMax", "iconGap",
             "nameFont", "nameLineHeight", "descriptionFont", "descriptionLineHeight", "textGap"),
    "connector": ("height", "paddingX", "iconSlot", "iconMax", "iconGap", "font", "minFont", "lineHeight"),
}
PLAIN_EXPECTED = {
    "node": ("height", "paddingX", "paddingY", "nameFont", "nameLineHeight",
             "descriptionFont", "descriptionLineHeight", "textGap"),
    "connector": ("height", "paddingX", "font", "minFont", "lineHeight"),
}
NODE_STYLES = {"icons", "plain"}
SIGNAL_COLORS = {
    "video": "#356dc9", "audio": "#8055b5", "communication": "#087f83",
    "control": "#5f6368", "power": "#be532e", "rf": "#846342",
}
NATIVE_ARROWS = {
    "none", "classic", "classicThin", "block", "blockThin", "open", "openThin",
    "diamond", "diamondThin", "oval", "baseDash", "doubleBlock", "doubleBlockThin",
    "async", "cross",
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
        self.alignments = []
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
        self.alignments.extend(match.group(1).lower() for match in re.finditer(r"(?:^|;)\s*text-align\s*:\s*(left|center|right|justify)\b", inline, re.I))

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
    if not isinstance(result, dict):
        raise ValueError("tokens must be an object")
    if result.get("version") != 1:
        raise ValueError("tokens.version must be 1")
    if number(result.get("grid")) <= 0:
        raise ValueError("tokens.grid must be positive")
    families = []
    if "node" in result or "connector" in result:
        families.append((result, EXPECTED, "tokens"))
    if "plain" in result:
        families.append((result["plain"], PLAIN_EXPECTED, "tokens.plain"))
    if not families:
        raise ValueError("tokens need an icons or plain card family")
    for family, contract, prefix in families:
        if not isinstance(family, dict):
            raise ValueError(f"{prefix} must be an object")
        for section, keys in contract.items():
            if not isinstance(family.get(section), dict):
                raise ValueError(f"{prefix}.{section} must be an object")
            for key in keys:
                if number(family[section].get(key)) <= 0:
                    raise ValueError(f"{prefix}.{section}.{key} must be positive")
        if family["connector"]["minFont"] > family["connector"]["font"]:
            raise ValueError(f"{prefix}.connector minFont must not exceed font")
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
        declared_node_style = model.get("nodeStyle")
        self.node_style = model.get("nodeStyle", "icons")
        self.cells = {}
        if self.node_style not in NODE_STYLES:
            self.issue("node-style", f"unknown page nodeStyle: {self.node_style!r}")
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
        # draw.io may drop custom mxGraphModel attributes on the active page
        # during save. A native page-title object preserves the same contract.
        # Do not infer the page mode from arbitrary cards or silently resolve
        # conflicting/duplicate declarations.
        markers = [cell for cell in self.cells.values() if cell.metadata.get("kind") == "page-contract"]
        if len(markers) > 1:
            self.issue("page-contract-count", "page must have at most one native page-contract marker")
        for marker in markers:
            marker_style = marker.metadata.get("nodeStyle")
            if marker_style not in NODE_STYLES:
                self.issue("node-style", f"unknown or missing page-contract nodeStyle: {marker_style!r}", marker.id)
            if declared_node_style is not None and marker_style != declared_node_style:
                self.issue("node-style-conflict", "graph and page-contract marker declare different nodeStyle values", marker.id)
        if declared_node_style is None and len(markers) == 1 and markers[0].metadata.get("nodeStyle") in NODE_STYLES:
            self.node_style = markers[0].metadata["nodeStyle"]

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

    def check_font(self, cell, minimum, maximum, alignment="left"):
        declared = number(cell.style.get("fontSize"))
        label = Label(cell.value)
        fonts = [declared, *label.fonts]
        if any(font < minimum - EPSILON or font > maximum + EPSILON for font in fonts):
            self.issue("card-font", f"font must be {minimum:g}–{maximum:g}px, including inline CSS", cell.id)
        if cell.style.get("align") != alignment or any(value != alignment for value in label.alignments):
            self.issue("card-text-align", f"card labels must be {alignment}-aligned", cell.id)
        if cell.style.get("verticalAlign", "middle") != "middle":
            self.issue("card-text-align", "text boxes must use middle vertical alignment", cell.id)
        return label

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

    def check_plain_icon_absence(self, card):
        for child in self.cells.values():
            chain = self.ancestors(child.id)
            if not chain or card.id not in chain:
                continue
            if child.id == card.id + "-icon" or child.metadata.get("kind") in {"icon-group", "icon-stroke"}:
                self.issue("plain-icon", "plain cards must not contain icon groups or icon strokes", child.id)

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
        node_style = cell.metadata.get("nodeStyle", "icons")
        if node_style not in NODE_STYLES:
            self.issue("node-style", f"unknown card nodeStyle: {node_style!r}", cell.id)
            return True
        if node_style != self.node_style:
            self.issue("node-style-mismatch", f"card nodeStyle {node_style!r} differs from page {self.node_style!r}; plain pages require explicit plain card metadata", cell.id)
        plain = node_style == "plain"
        if plain:
            self.check_plain_icon_absence(cell)
        if kind == "processor":
            if cell.metadata.get("symbolType", "").lower() not in {"soc", "mcu"}:
                self.issue("processor-exception", "only SoC/MCU may use processor height exception", cell.id)
            if not plain:
                return True
        if kind == "port-strip":
            if cell.metadata.get("symbolType") not in {"connector", "port-strip", "connector-strip"}:
                self.issue("port-strip-type", "port-strip is only for explicitly expanded connector terminals", cell.id)
            return True
        family = self.tokens.get("plain", {}) if plain else self.tokens
        section = "connector" if kind == "connector" else "node"
        contract = PLAIN_EXPECTED if plain else EXPECTED
        if not isinstance(family, dict) or not isinstance(family.get(section), dict) or any(key not in family[section] for key in contract[section]):
            self.issue("missing-style-tokens", f"tokens do not define the {node_style} {section} contract", cell.id)
            return True
        cfg = family[section]
        _, _, width, height = cell.rect()
        if kind != "processor" and not near(height, cfg["height"]):
            self.issue("card-height", f"{kind} height must be {cfg['height']}", cell.id)
        icon = None if plain else self.child(cell, "-icon")
        name = self.child(cell, "-name")
        description = self.cells.get(cell.id + "-description")
        if icon:
            self.check_icon(icon, cell, cfg)
        if not name:
            return True
        alignment = "center" if plain else "left"
        desc_height = 0
        if kind == "connector":
            label = self.check_font(name, cfg["minFont"], cfg["font"], alignment)
            expected_name_height = cfg["lineHeight"]
            if len(label.lines) != 1:
                self.issue("connector-line", "connector label must have exactly one explicit line", name.id)
            if description:
                self.issue("connector-description", "compact connector has a single label, not a subtitle", description.id)
            gap = 0
        else:
            label = self.check_font(name, cfg["nameFont"], cfg["nameFont"], alignment)
            if not 1 <= len(label.lines) <= 2:
                self.issue("name-lines", "device name must contain 1–2 explicit lines", name.id)
            expected_name_height = max(1, len(label.lines)) * cfg["nameLineHeight"]
            gap = 0
            if description:
                if not description.vertex or description.parent != cell.id:
                    self.issue("card-child", "description must be a direct native card child", description.id)
                desc_label = self.check_font(description, cfg["descriptionFont"], cfg["descriptionFont"], alignment)
                if len(desc_label.lines) != 1:
                    self.issue("description-lines", "description must have one explicit line; omit empty subtitle cells", description.id)
                desc_height, gap = cfg["descriptionLineHeight"], cfg["textGap"]
        expected_x = cfg["paddingX"] if plain else cfg["paddingX"] + cfg["iconSlot"] + cfg["iconGap"]
        expected_width = width - expected_x - cfg["paddingX"]
        if expected_width <= 0:
            self.issue("card-width", "card is too narrow for its selected layout and text", cell.id)
        total = expected_name_height + gap + desc_height
        expected_y = (height - total) / 2
        if kind != "connector" and expected_y < cfg["paddingY"] - EPSILON:
            self.issue("text-padding", "text group violates vertical safe padding", cell.id)
        expected = [(name, expected_y, expected_name_height)]
        if kind != "connector" and description:
            expected.append((description, expected_y + expected_name_height + gap, desc_height))
        for text, y, h in expected:
            actual = text.rect()
            if not all(near(a, b) for a, b in zip(actual, (expected_x, y, expected_width, h))):
                self.issue("text-geometry", f"text box must be x={expected_x:g}, y={y:g}, width={expected_width:g}, height={h:g}; center actual line group", text.id)
        return True

    def check_edge(self, cell):
        source, target = cell.xml.get("source"), cell.xml.get("target")
        if self.is_decoration(cell):
            return False
        if not source and not target:
            # Older icon primitives used this prefix without kind metadata.
            # A bound relationship does not become decoration because of its ID.
            if not cell.id.startswith("legend-"):
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

    def is_decoration(self, cell):
        if cell.metadata.get("kind") in {"decoration", "legend", "icon-stroke", "legend-sample"}:
            return True
        return any(self.cells[identity].metadata.get("kind") == "legend-entry"
                   for identity in self.ancestors(cell.id) or [] if identity in self.cells)

    def visible(self, cell, text=False):
        for item in [cell, *(self.cells[identity] for identity in self.ancestors(cell.id) or []
                             if identity in self.cells)]:
            if any(attributes.get("visible") == "0" for attributes in (item.xml.attrib, item.metadata, item.style)):
                return False
            if number(item.style.get("opacity"), 100) <= 0:
                return False
            if item is not cell and item.xml.get("collapsed") == "1":
                return False
        opacity_key = "textOpacity" if text else "strokeOpacity"
        color_key = "fontColor" if text else "strokeColor"
        if number(cell.style.get(opacity_key), 100) <= 0:
            return False
        if cell.style.get(color_key, "").strip().lower() in {"none", "transparent"}:
            return False
        if text and re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden|(?:^|[;\"'])\s*opacity\s*:\s*0(?:\D|$)|color\s*:\s*transparent)", cell.value, re.I):
            return False
        return True

    @staticmethod
    def direction(cell):
        # Samples require explicit arrow styles below. Legacy body edges without
        # arrow metadata are treated as physical links only on a legend-aware page.
        arrows = sum(cell.style.get(key, "none") not in {"", "none"}
                     for key in ("startArrow", "endArrow"))
        return ("physical", "single", "bidirectional")[arrows]

    def check_legend_entry(self, entry, colors, used_signals):
        if not entry.vertex or not (entry.style.get("group") == "1" or entry.style.get("shape") == "group"):
            self.issue("legend-entry", "legend-entry must be a native group vertex", entry.id)
        kind = entry.metadata.get("legendType")
        value = entry.metadata.get("signalClass") if kind == "signal" else entry.metadata.get("legendValue")
        allowed = {"signal": set(colors), "direction": {"single", "bidirectional", "physical"}, "linestyle": {"dashed"}}
        if kind not in allowed or value not in allowed[kind]:
            self.issue("legend-metadata", "legend needs a supported legendType and signalClass/legendValue", entry.id)
            return None
        label = self.cells.get(entry.id + "-label")
        if label is None or not label.vertex or label.parent != entry.id:
            self.issue("legend-label", "legend needs a direct native text child <entry>-label", entry.id)
        elif (not (label.style.get("text") == "1" or label.style.get("shape") == "text")
              or not any(char.isalnum() for char in Label(label.value).text)
              or any(size <= 0 for size in [number(label.style.get("fontSize"), 11), *Label(label.value).fonts])
              or not self.visible(label, text=True)):
            self.issue("legend-label", "legend label must contain visible text", label.id)
        sample = self.cells.get(entry.id + "-sample")
        if (sample is None or not sample.edge or sample.parent != entry.id
                or sample.metadata.get("kind") != "legend-sample"):
            self.issue("legend-sample", "legend needs a direct native edge child <entry>-sample with kind=legend-sample", entry.id)
            return kind, value
        if sample.xml.get("source") or sample.xml.get("target"):
            self.issue("legend-sample", "legend sample must be free-ended, independent of body relationships", sample.id)
        if (sample.style.get("shape", "connector") not in {"connector", "line"}
                or sample.style.get("text") == "1" or sample.style.get("group") == "1"):
            self.issue("legend-sample", "legend sample must render as a native line, not a text/group shape", sample.id)
        points = {} if sample.geometry is None else {
            role: sample.geometry.findall(f"mxPoint[@as='{role}']")
            for role in ("sourcePoint", "targetPoint")}
        if not points or any(len(items) != 1 for items in points.values()):
            self.issue("legend-sample-geometry", "legend sample needs explicit sourcePoint and targetPoint", sample.id)
        else:
            ends = [tuple(number(point.get(axis), 0) for axis in ("x", "y"))
                    for items in points.values() for point in items]
            if all(near(a, b) for a, b in zip(*ends)):
                self.issue("legend-sample-geometry", "legend sample must have nonzero length", sample.id)
        width = number(sample.style.get("strokeWidth"), 1)
        if width <= 0 or not self.visible(sample) or not sample.style.get("strokeColor", "").strip():
            self.issue("legend-sample-visible", "legend sample needs a visible native stroke of positive width", sample.id)
        if any(sample.style.get(key) not in NATIVE_ARROWS for key in ("startArrow", "endArrow")):
            self.issue("legend-sample-arrow", "legend samples must explicitly declare native startArrow and endArrow styles", sample.id)
        dashed = sample.style.get("dashed", "0") == "1"
        if kind == "signal":
            if sample.style.get("strokeColor", "").strip().lower() != colors[value]:
                self.issue("legend-signal-color", f"{value} sample must use {colors[value]}", sample.id)
            widths = [number(edge.style.get("strokeWidth"), 1) for edge in used_signals.get(value, [])]
            if widths and not any(near(width, actual) for actual in widths):
                self.issue("legend-signal-width", "signal sample width must match a body edge in its signal family", sample.id)
            if dashed or self.direction(sample) != "physical":
                self.issue("legend-signal-style", "signal-family samples must be solid and arrowless; explain direction/style separately", sample.id)
        elif kind == "direction":
            if self.direction(sample) != value or dashed:
                self.issue("legend-direction-style", f"direction sample must show a solid {value} connection", sample.id)
        elif not dashed or self.direction(sample) != "physical":
            self.issue("legend-linestyle-style", "dashed-style sample must be dashed and arrowless", sample.id)
        return kind, value

    def check_legends(self, relationships):
        colors = {key: str(self.tokens.get("signalColors", {}).get(key, value)).strip().lower()
                  for key, value in SIGNAL_COLORS.items()}
        used_signals = {}
        for edge in relationships:
            family = edge.metadata.get("signalClass")
            if family not in colors:
                family = next((key for key, color in colors.items()
                               if edge.style.get("strokeColor", "").strip().lower() == color), None)
            if family:
                used_signals.setdefault(family, []).append(edge)
        entries = [cell for cell in self.cells.values() if cell.metadata.get("kind") == "legend-entry"]
        for sample in self.cells.values():
            if sample.metadata.get("kind") != "legend-sample":
                continue
            owner = self.cells.get(sample.parent)
            if owner is None or owner.metadata.get("kind") != "legend-entry" or sample.id != owner.id + "-sample":
                self.issue("legend-sample-parent", "legend-sample must be the named direct child of a legend-entry", sample.id)
        coverage = set()
        for entry in entries:
            try:
                result = self.check_legend_entry(entry, colors, used_signals)
                if result:
                    coverage.add(result)
            except (ValueError, TypeError, OverflowError) as error:
                self.issue("legend-value", str(error), entry.id)
        for family in used_signals:
            if ("signal", family) not in coverage:
                self.issue("legend-signal-missing", f"used signal family {family!r} needs a native line sample and label")
        # Old uncolored fixtures predate the legend contract. Recognized palette,
        # typed entries, or explicit line semantics opt a page into coverage.
        legend_aware = used_signals or entries or any(
            "startArrow" in edge.style or "endArrow" in edge.style or edge.style.get("dashed") == "1"
            for edge in relationships)
        if legend_aware:
            for value in sorted({self.direction(edge) for edge in relationships}):
                if ("direction", value) not in coverage:
                    self.issue("legend-direction-missing", f"used {value} direction needs a native sample and label")
            if any(edge.style.get("dashed") == "1" for edge in relationships) and ("linestyle", "dashed") not in coverage:
                self.issue("legend-linestyle-missing", "used dashed line style needs a native sample and label")

    def validate(self):
        roots = [cell for cell in self.cells.values() if not cell.parent]
        if len(roots) != 1 or roots[0].vertex or roots[0].edge:
            self.issue("graph-root", "graph needs one non-drawable parentless root")
        components, connections = 0, 0
        relationships = []
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
                    if self.check_edge(cell):
                        connections += 1
                        relationships.append(cell)
                else:
                    components += int(self.check_card(cell))
            except (ValueError, TypeError, OverflowError) as error:
                self.issue("contract-value", str(error), cell.id)
        self.check_legends(relationships)
        if components == 0:
            self.issue("no-classified-cards", "page has no classified hardware cards; inspect whether it is a legend-only page", warning=True)
        return {"name": self.name, "compressed": self.compressed, "nodeStyle": self.node_style, "cells": len(self.cells),
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
