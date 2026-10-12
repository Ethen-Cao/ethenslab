#!/usr/bin/env python3
"""Check editable draw.io structure, optionally against an architecture v2 model.

This checks the native graph and exporter contract, not appearance or the truth
of an architecture. It does not invoke draw.io or modify either input file.
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
import sys
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zlib


EPSILON = 0.001
CANVAS_ID = "architecture-canvas"
NORMAL = {"top": (0, -1), "bottom": (0, 1), "left": (-1, 0), "right": (1, 0)}
ORIGINS = {"oem": "#4285f4", "native": "#34a853", "vendor": "#fbbc04"}
PALETTE = {
    "blue": "#4285f4", "green": "#34a853", "amber": "#fbbc04",
    "purple": "#a78bfa", "cyan": "#38bdf8", "orange": "#fb923c",
    "pink": "#f472b6", "indigo": "#818cf8",
}
CATEGORIES = {"oem": "blue", "tier1": "amber", "soc-vendor": "purple", "os-vendor": "green", "other": "cyan"}
RELATIONS = {
    "dependency": ("dependency", "#5f6368", None),
    "call": ("control", "#356dc9", None),
    "ipc": ("control", "#356dc9", None),
    "read": ("data", "#237a44", None),
    "write": ("data", "#237a44", None),
    "transfer": ("data", "#237a44", None),
    "notification": ("notification", "#356dc9", "3 5"),
    "configuration": ("config", "#5f6368", "6 5"),
}


def close(a, b):
    return abs(a - b) < EPSILON


def number(value, default=None):
    if value is None:
        if default is not None:
            return default
        raise ValueError("missing numeric value")
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric geometry value")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("geometry and port values must be finite")
    return result


def style_map(raw):
    result = {}
    for entry in raw.split(";"):
        if "=" in entry:
            key, value = entry.split("=", 1)
            result[key] = value
        elif entry:
            result[entry] = "1"
    return result


class TextContent(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def text_content(value):
    parser = TextContent()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


@dataclass
class Cell:
    id: str
    xml: ET.Element
    metadata: dict
    style: dict
    geometry: ET.Element | None

    @property
    def vertex(self):
        return self.xml.get("vertex") == "1"

    @property
    def edge(self):
        return self.xml.get("edge") == "1"

    @property
    def parent(self):
        return self.xml.get("parent")

    @property
    def label(self):
        return self.metadata.get("label", self.xml.get("value", ""))

    @property
    def image(self):
        return bool(self.style.get("image")) or self.style.get("shape") == "image"


class Report:
    def __init__(self, file, model):
        self.file = str(file)
        self.model = str(model) if model else None
        self.errors = []
        self.warnings = []
        self.pages = []

    def issue(self, code, message, page=None, cell=None, warning=False):
        item = {"code": code, "message": message}
        if page is not None:
            item["page"] = page
        if cell is not None:
            item["cell"] = cell
        (self.warnings if warning else self.errors).append(item)

    def output(self):
        return {
            "ok": not self.errors, "file": self.file, "model": self.model,
            "pages": self.pages, "errors": self.errors, "warnings": self.warnings,
            "scope": "Native XML structure and optional exporter/model consistency; no rendering or architecture semantics validation.",
        }


def parse_xml(raw):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DTD/entity declarations are unsupported; export ordinary draw.io XML")
    return ET.fromstring(raw)


def graph_pages(file):
    document = parse_xml(file.read_bytes())
    if document.tag == "mxGraphModel":
        return [("graph", document, False)]
    if document.tag != "mxfile":
        raise ValueError("expected an mxfile or mxGraphModel XML document")
    pages = []
    for index, diagram in enumerate(document.findall("diagram"), 1):
        name = diagram.get("name") or diagram.get("id") or f"page-{index}"
        embedded = diagram.find("mxGraphModel")
        compressed = False
        if embedded is None:
            payload = (diagram.text or "").strip()
            if not payload:
                raise ValueError(f"{name}: diagram contains no graph payload")
            if payload.startswith("<"):
                embedded = parse_xml(payload.encode("utf-8"))
            else:
                try:
                    decoded = base64.b64decode("".join(payload.split()), validate=True)
                    inflated = zlib.decompress(decoded, -15).decode("utf-8")
                    embedded = parse_xml(unquote(inflated, errors="strict").encode("utf-8"))
                    compressed = True
                except (binascii.Error, zlib.error, UnicodeError, ET.ParseError, ValueError) as error:
                    raise ValueError(f"{name}: cannot decode compressed graph ({error}); export uncompressed .drawio XML") from error
        if embedded.tag != "mxGraphModel":
            raise ValueError(f"{name}: payload is not an mxGraphModel")
        pages.append((name, embedded, compressed))
    if not pages:
        raise ValueError("mxfile contains no diagram pages")
    return pages


class Graph:
    def __init__(self, name, model_xml, compressed, report):
        self.name = name
        self.report = report
        self.cells = {}
        self.paths = {}
        self.positions = {}
        self.compressed = compressed
        root = model_xml.find("root")
        if root is None:
            self.error("missing-root", "mxGraphModel needs a root element")
            return
        for element in root:
            if element.tag == "mxCell":
                xml, metadata, identity = element, {}, element.get("id")
            elif element.tag in {"object", "UserObject"}:
                children = element.findall("mxCell")
                if len(children) != 1:
                    self.error("object-cell", "object wrapper must contain exactly one mxCell", element.get("id"))
                    continue
                xml, metadata, identity = children[0], dict(element.attrib), element.get("id")
                if xml.get("id") and xml.get("id") != identity:
                    self.error("object-id", "wrapper and child mxCell IDs disagree", identity)
            else:
                self.error("root-entry", f"unsupported graph root entry: {element.tag}")
                continue
            if not identity:
                self.error("missing-id", "every logical cell needs a nonempty ID")
                continue
            if identity in self.cells:
                self.error("duplicate-id", "logical cell ID occurs more than once", identity)
                continue
            geometries = xml.findall("mxGeometry")
            if len(geometries) > 1:
                self.error("geometry-count", "cell contains multiple mxGeometry elements", identity)
            self.cells[identity] = Cell(identity, xml, metadata, style_map(xml.get("style", "")), geometries[0] if geometries else None)

    def error(self, code, message, cell=None, warning=False):
        self.report.issue(code, message, self.name, cell, warning)

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

    def nearest_common_parent(self, source, target):
        a, b = self.ancestors(source), self.ancestors(target)
        if a is None or b is None:
            return None
        return next((identity for identity in a if identity in set(b)), None)

    def position(self, identity, seen=None):
        if identity in self.positions:
            return self.positions[identity]
        seen = set() if seen is None else seen
        if identity in seen or identity not in self.cells:
            raise ValueError("cannot resolve cyclic or missing parent geometry")
        seen.add(identity)
        cell = self.cells[identity]
        parent = self.position(cell.parent, seen) if cell.parent else (0, 0)
        x, y = 0, 0
        if cell.geometry is not None:
            x = number(cell.geometry.get("x"), 0)
            y = number(cell.geometry.get("y"), 0)
            if cell.geometry.get("relative") == "1" and cell.vertex:
                p = self.cells.get(cell.parent)
                if p and p.geometry is not None:
                    x *= number(p.geometry.get("width"), 0)
                    y *= number(p.geometry.get("height"), 0)
                offset = cell.geometry.find("mxPoint[@as='offset']")
                if offset is not None:
                    x += number(offset.get("x"), 0)
                    y += number(offset.get("y"), 0)
        self.positions[identity] = (parent[0] + x, parent[1] + y)
        return self.positions[identity]

    def point(self, element):
        return (number(element.get("x"), 0), number(element.get("y"), 0))

    def port(self, edge, endpoint, prefix):
        style = edge.style
        x, y = number(style.get(prefix + "X")), number(style.get(prefix + "Y"))
        if not (0 <= x <= 1 and 0 <= y <= 1) or not any(close(v, side) for v in (x, y) for side in (0, 1)):
            raise ValueError(f"{prefix} port must lie on a vertex boundary")
        if style.get(prefix + "Perimeter") != "0":
            raise ValueError(f"{prefix}Perimeter must be 0 for a fixed port")
        node = self.cells[endpoint]
        if node.geometry is None:
            raise ValueError("endpoint has no geometry")
        origin = self.position(endpoint)
        width = number(node.geometry.get("width"))
        height = number(node.geometry.get("height"))
        return (
            origin[0] + width * x + number(style.get(prefix + "Dx"), 0),
            origin[1] + height * y + number(style.get(prefix + "Dy"), 0),
        )

    def route(self, edge, connected):
        geometry = edge.geometry
        if geometry is None:
            return None
        parent = self.position(edge.parent) if edge.parent else (0, 0)
        arrays = geometry.findall("Array[@as='points']")
        if len(arrays) > 1:
            raise ValueError("edge has multiple waypoint arrays")
        hints = []
        for array in arrays:
            for child in array:
                if child.tag != "mxPoint":
                    raise ValueError("waypoint array may contain only mxPoint entries")
                x, y = self.point(child)
                hints.append((x + parent[0], y + parent[1]))
        if connected:
            start = self.port(edge, edge.xml.get("source"), "exit")
            end = self.port(edge, edge.xml.get("target"), "entry")
        else:
            ends = [geometry.find(f"mxPoint[@as='{name}Point']") for name in ("source", "target")]
            if any(point is None for point in ends):
                raise ValueError("free-ended decorative line needs explicit sourcePoint and targetPoint")
            start, end = [(point[0] + parent[0], point[1] + parent[1]) for point in map(self.point, ends)]
        return [start, *hints, end]

    def validate(self):
        roots = [cell for cell in self.cells.values() if not cell.parent]
        if len(roots) != 1 or roots[0].vertex or roots[0].edge:
            self.error("graph-root", "graph needs exactly one parentless root cell")
        native = 0
        connected_count = 0
        free_count = 0
        labels = 0
        endpoint_ids = {cell.xml.get(key) for cell in self.cells.values() if cell.edge for key in ("source", "target")}
        for cell in self.cells.values():
            if cell.vertex and cell.edge:
                self.error("cell-role", "cell cannot be both a vertex and an edge", cell.id)
            if cell.parent and cell.parent not in self.cells:
                self.error("missing-parent", f"unknown parent: {cell.parent}", cell.id)
            if self.ancestors(cell.id) is None:
                self.error("parent-cycle", "parent hierarchy contains a cycle", cell.id)
            p = self.cells.get(cell.parent)
            edge_label = p is not None and p.edge
            if edge_label:
                labels += int(cell.style.get("edgeLabel") == "1" or cell.id.endswith("-label"))
                if not cell.vertex or cell.geometry is None or cell.geometry.get("relative") != "1":
                    self.error("edge-label", "edge child must be a native vertex with relative geometry", cell.id)
            elif cell.style.get("edgeLabel") == "1":
                self.error("edge-label-parent", "edgeLabel vertex must be parented to an edge", cell.id)
            if cell.vertex or cell.edge:
                if cell.geometry is None or cell.geometry.get("as") != "geometry":
                    self.error("missing-geometry", "drawable cell needs mxGeometry as='geometry'", cell.id)
                else:
                    try:
                        for key in ("x", "y", "width", "height"):
                            number(cell.geometry.get(key), 0)
                        for point in cell.geometry.iter("mxPoint"):
                            self.point(point)
                        if cell.vertex and not edge_label and (number(cell.geometry.get("width"), 0) <= 0 or number(cell.geometry.get("height"), 0) <= 0):
                            self.error("vertex-size", "native vertex needs positive width and height", cell.id)
                    except (ValueError, TypeError) as error:
                        self.error("geometry-number", str(error), cell.id)
                if cell.style.get("locked") == "1" or cell.xml.get("locked") == "1" or cell.metadata.get("locked") == "1":
                    self.error("locked-cell", "drawable cells must remain editable and unlocked", cell.id)
            if cell.vertex and not edge_label:
                component = cell.id in endpoint_ids or bool(cell.metadata.get("entityType"))
                if cell.image:
                    component = component or bool(cell.metadata.get("modelId")) or bool(p and p.metadata.get("entityType"))
                    self.error("image-component" if component else "decorative-image", "image is not an editable native diagram component" if component else "unconnected image is treated as decoration, not a diagram component", cell.id, warning=not component)
                elif component or (cell.style.get("shape") not in {"text", "group", "swimlane"} and cell.style.get("container") != "1"):
                    native += 1
            if not cell.edge:
                continue
            source, target = cell.xml.get("source"), cell.xml.get("target")
            connected = bool(source or target)
            if connected:
                connected_count += 1
                valid_ends = True
                for key, identity in (("source", source), ("target", target)):
                    endpoint = self.cells.get(identity)
                    if endpoint is None or not endpoint.vertex or (self.cells.get(endpoint.parent) and self.cells[endpoint.parent].edge):
                        self.error("edge-endpoint", f"{key} must reference an existing component vertex: {identity}", cell.id)
                        valid_ends = False
                if not valid_ends:
                    continue
                common = self.nearest_common_parent(source, target)
                if cell.parent != common:
                    self.error("edge-owner", f"edge parent must be nearest common ancestor {common!r}, got {cell.parent!r}", cell.id)
                if cell.style.get("edgeStyle") not in {"segmentEdgeStyle", "none"}:
                    self.error("edge-routing", "connected edges need manual segmentEdgeStyle or explicit straight edgeStyle=none", cell.id)
                if cell.style.get("curved", "0") != "0" or cell.style.get("rounded", "0") != "0":
                    self.error("edge-routing", "manual orthogonal route must not be curved or rounded", cell.id)
            else:
                free_count += 1
                if cell.metadata.get("modelId") or cell.metadata.get("relation"):
                    self.error("free-model-edge", "model relationship cannot be a free-ended decorative line", cell.id)
            if cell.geometry is not None and cell.geometry.get("relative") != "1":
                self.error("edge-geometry", "edge geometry must be relative", cell.id)
            try:
                path = self.route(cell, connected)
                if path is not None:
                    self.paths[cell.id] = path
                    # segmentEdgeStyle may add orthogonal doglegs between moved
                    # terminals and retained hints. XML does not contain those
                    # rendered segments; only consecutive explicit hints are
                    # evidence of malformed manual waypoint structure. Keep the
                    # anchors in self.paths for strict initial model comparison.
                    hints = path[1:-1]
                    if connected and any(not close(a[0], b[0]) and not close(a[1], b[1]) for a, b in zip(hints, hints[1:])):
                        self.error("non-orthogonal", "consecutive explicit manual waypoints contain a diagonal segment", cell.id)
            except (ValueError, TypeError, KeyError, RecursionError) as error:
                self.error("edge-geometry", str(error), cell.id)
        if native == 0:
            self.error("no-native-components", "graph contains no editable native diagram components")
        if connected_count == 0:
            self.error("no-native-edges", "no native component relationships found", warning=True)
        semantic_nodes = sum(cell.vertex and bool(cell.metadata.get("entityType")) and not cell.image for cell in self.cells.values())
        return {"name": self.name, "compressed": self.compressed, "cells": len(self.cells), "vertices": sum(cell.vertex for cell in self.cells.values()), "nativeComponents": semantic_nodes if semantic_nodes else native, "containers": sum(cell.vertex and bool(cell.metadata.get("kind")) for cell in self.cells.values()), "connectedEdges": connected_count, "decorativeEdges": free_count, "edgeLabels": labels}


def simplify(points):
    result = []
    for point in points:
        if result and all(close(a, b) for a, b in zip(result[-1], point)):
            continue
        if len(result) >= 2:
            a, b = result[-2:]
            if ((close(a[0], b[0]) and close(b[0], point[0]) and (b[1] - a[1]) * (point[1] - b[1]) > 0)
                    or (close(a[1], b[1]) and close(b[1], point[1]) and (b[0] - a[0]) * (point[0] - b[0]) > 0)):
                result.pop()
        result.append(point)
    return result


def model_port(node, side, offset=0):
    if side in {"top", "bottom"}:
        return ((node["w"] / 2 + offset) / node["w"], 0 if side == "top" else 1)
    return (0 if side == "left" else 1, (node["h"] / 2 + offset) / node["h"])


def model_route(edge, nodes):
    source, target = nodes[edge["from"]], nodes[edge["to"]]
    fs, ts = edge.get("fromSide", "bottom"), edge.get("toSide", "top")
    f, t = model_port(source, fs, edge.get("fromOffset", 0)), model_port(target, ts, edge.get("toOffset", 0))
    a = (source["x"] + source["w"] * f[0], source["y"] + source["h"] * f[1])
    b = (target["x"] + target["w"] * t[0], target["y"] + target["h"] * t[1])
    points = [a]
    if edge.get("via"):
        point = a
        for step in edge["via"]:
            point = (step.get("x", point[0]), step.get("y", point[1]))
            points.append(point)
        if not close(point[0], b[0]) and not close(point[1], b[1]):
            points.append((b[0], point[1]) if ts in {"top", "bottom"} else (point[0], b[1]))
    else:
        u, v = NORMAL[fs], NORMAL[ts]
        direction = lambda value: (value > 0) - (value < 0)
        straight = ((close(a[0], b[0]) and u[0] == v[0] == 0 and u[1] == -v[1] and direction(b[1] - a[1]) == u[1])
                    or (close(a[1], b[1]) and u[1] == v[1] == 0 and u[0] == -v[0] and direction(b[0] - a[0]) == u[0]))
        if not straight:
            if u[0] == v[0] == 0:
                y = (a[1] + b[1]) / 2 if u[1] != v[1] else min(a[1], b[1]) - 24 if u[1] < 0 else max(a[1], b[1]) + 24
                points.extend(((a[0], y), (b[0], y)))
            elif u[1] == v[1] == 0:
                x = (a[0] + b[0]) / 2 if u[0] != v[0] else min(a[0], b[0]) - 24 if u[0] < 0 else max(a[0], b[0]) + 24
                points.extend(((x, a[1]), (x, b[1])))
            else:
                points.append((a[0], b[1]) if u[0] == 0 else (b[0], a[1]))
    return simplify([*points, b])


def model_fill(node, model):
    if node["entityType"] in {"memory", "hardware"}:
        return "#edf0f2"
    if node.get("configured") is True:
        return "#ffffff"
    mode = model["meta"].get("colorMode", "technical")
    if mode == "origin":
        return ORIGINS.get(node.get("origin"), "#ffffff")
    if mode == "responsibility":
        party = next((party for party in model.get("parties", []) if party.get("id") == node.get("responsibleParty")), {})
        return PALETTE.get(party.get("paletteKey") or CATEGORIES.get(party.get("category")), "#ffffff")
    return "#edf3f8"


def label_geometry(points, position):
    """The exporter projects a label onto its edge, then preserves its offset."""
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    total = sum(lengths)
    if total == 0:
        raise ValueError("edge label needs a nonzero path length")
    walk, best = 0, None
    for a, b, length in zip(points, points[1:], lengths):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0, min(1, ((position["x"] - a[0]) * dx + (position["y"] - a[1]) * dy) / (length ** 2)))
        point = (a[0] + t * dx, a[1] + t * dy)
        distance = math.hypot(position["x"] - point[0], position["y"] - point[1])
        if best is None or distance < best[0]:
            best = (distance, 2 * (walk + t * length) / total - 1, position["x"] - point[0], position["y"] - point[1])
        walk += length
    return best[1:]


def compare_model(graph, model, theme_file=None):
    containers = {item["id"]: item for item in model["containers"]}
    nodes = {item["id"]: item for item in model["nodes"]}
    theme_file = theme_file or Path(__file__).resolve().parents[2] / "architecture-diagram/assets/theme.json"
    if not theme_file.is_file():
        raise ValueError(f"model style comparison needs {theme_file}; provide --theme <theme.json> from the builder's architecture skill")
    strokes = json.loads(theme_file.read_text(encoding="utf-8")).get("strokes", {})
    expected_ids = {CANVAS_ID}

    def check(cell, actual, expected, field, numeric=False):
        try:
            matches = close(number(actual), number(expected)) if numeric else actual == expected
        except (ValueError, TypeError):
            matches = False
        if not matches:
            graph.error("model-mismatch", f"{field}: expected {expected!r}, got {actual!r}", cell.id)

    def expected_cell(identity, item, role):
        expected_ids.add(identity)
        cell = graph.cells.get(identity)
        if cell is None:
            graph.error("missing-model-cell", f"missing native {role} for model ID {item['id']}", identity)
            return None
        check(cell, cell.metadata.get("modelId"), item["id"], "modelId")
        check(cell, cell.edge if role == "edge" else cell.vertex, True, f"native {role}")
        return cell

    canvas = graph.cells.get(CANVAS_ID)
    if canvas is None:
        graph.error("missing-model-canvas", "model comparison requires architecture-canvas", CANVAS_ID)
    else:
        check(canvas, canvas.metadata.get("modelId"), model["meta"]["id"], "canvas modelId")
        if canvas.geometry is not None:
            for field, key in (("width", "width"), ("height", "height")):
                check(canvas, canvas.geometry.get(field), model["canvas"][key], f"canvas {field}", True)
    for role, items, prefix in (("container", model["containers"], "container-"), ("node", model["nodes"], "node-")):
        for item in items:
            cell = expected_cell(prefix + item["id"], item, role)
            if cell is None:
                continue
            parent = containers.get(item.get("parent"))
            check(cell, cell.parent, "container-" + parent["id"] if parent else CANVAS_ID, "parent")
            if cell.geometry is not None:
                check(cell, cell.geometry.get("relative", "0"), "0", "nonrelative vertex geometry")
                for field, value in (("x", item["x"] - (parent["x"] if parent else 0)), ("y", item["y"] - (parent["y"] if parent else 0)), ("width", item["w"]), ("height", item["h"])):
                    check(cell, cell.geometry.get(field, "0"), value, field, True)
            if role == "container":
                check(cell, cell.metadata.get("kind"), item["kind"], "container kind")
                fill = "#ffffff" if item["kind"] == "process" else "#f5f6f7" if item["kind"] in {"domain", "hypervisor", "hardware-region"} else "#fafbfc"
                check(cell, cell.style.get("fillColor", "").lower(), fill, "container fill")
                continue
            display_name = f"{item.get('interfacePath')} · {item.get('moduleName')}" if item["entityType"] == "kernel-interface" else item["canonicalName"]
            check(cell, cell.metadata.get("canonicalName"), display_name, "canonicalName (exporter displayName)")
            check(cell, cell.metadata.get("entityType"), item["entityType"], "entityType")
            if item.get("origin") is not None:
                check(cell, cell.metadata.get("origin"), item["origin"], "origin")
            # Memory is a native group of stacked native rectangles, not an image.
            painted = [cell]
            if item["entityType"] == "memory" and cell.style.get("shape") == "group":
                painted = [child for child in graph.cells.values() if child.parent == cell.id and child.vertex and not child.image and child.style.get("shape") != "text"]
                if not painted:
                    graph.error("memory-decoration", "memory group needs native visible child vertices", cell.id)
            for child in painted:
                check(child, child.style.get("fillColor", "").lower(), model_fill(item, model), "node fill")
                if item.get("configured") is True and item["entityType"] not in {"memory", "hardware"}:
                    check(child, child.style.get("dashed", "0"), "1", "configured node dashes")
            labels = " ".join(text_content(child.label) for child in painted)
            if display_name not in labels:
                graph.error("node-label", "native node label does not contain its canonical display name", cell.id)
    canvas_offset = graph.position(CANVAS_ID) if canvas is not None else (0, 0)
    for item in model["edges"]:
        cell = expected_cell("edge-" + item["id"], item, "edge")
        if cell is None:
            continue
        check(cell, cell.xml.get("source"), "node-" + item["from"], "source")
        check(cell, cell.xml.get("target"), "node-" + item["to"], "target")
        check(cell, cell.metadata.get("relation"), item["relation"], "relation")
        if item.get("mechanism") is not None:
            check(cell, cell.metadata.get("mechanism"), item["mechanism"], "mechanism")
        relation_type, color, dash = RELATIONS[item["relation"]]
        if relation_type not in strokes:
            raise ValueError(f"theme.strokes.{relation_type} is required for model style comparison")
        check(cell, cell.style.get("strokeColor", "").lower(), color, "edge color")
        check(cell, cell.style.get("strokeWidth"), strokes[relation_type], "edge width", True)
        check(cell, cell.style.get("dashed", "0"), "1" if dash else "0", "edge dashes")
        if dash:
            check(cell, " ".join(cell.style.get("dashPattern", "").split()), dash, "edge dash pattern")
        for end, prefix, default in (("from", "exit", "bottom"), ("to", "entry", "top")):
            port = model_port(nodes[item[end]], item.get(end + "Side", default), item.get(end + "Offset", 0))
            for field, value in (("X", port[0]), ("Y", port[1]), ("Dx", 0), ("Dy", 0)):
                check(cell, cell.style.get(prefix + field, "0" if field in {"Dx", "Dy"} else None), value, prefix + field, True)
        path = graph.paths.get(cell.id)
        if path is not None:
            actual = simplify([(point[0] - canvas_offset[0], point[1] - canvas_offset[1]) for point in path])
            expected = model_route(item, nodes)
            if len(actual) != len(expected) or any(not close(a[0], b[0]) or not close(a[1], b[1]) for a, b in zip(actual, expected)):
                graph.error("model-route", "manual waypoint path differs from the model/exporter route", cell.id)
        label = item.get("label") or (item.get("mechanism") if item["relation"] == "ipc" else None)
        if label:
            child = graph.cells.get(cell.id + "-label")
            if child is None or child.parent != cell.id or not child.vertex:
                graph.error("missing-edge-label", "model edge label needs a native relative child vertex", cell.id)
            elif label not in text_content(child.label):
                graph.error("edge-label-text", "native edge label does not contain the model label", child.id)
            if child is not None and child.geometry is not None and item.get("labelPosition"):
                x, dx, dy = label_geometry(model_route(item, nodes), item["labelPosition"])
                check(child, child.geometry.get("x", "0"), x, "label relative x", True)
                check(child, child.geometry.get("y", "0"), 0, "label relative y", True)
                offset = child.geometry.find("mxPoint[@as='offset']")
                for field, value in (("x", dx), ("y", dy)):
                    check(child, offset.get(field, "0") if offset is not None else "0", value, "label offset " + field, True)
    for cell in graph.cells.values():
        if cell.metadata.get("modelId") and cell.id not in expected_ids:
            graph.error("extra-model-cell", "model-tagged native cell is absent from the supplied model", cell.id)


def read_model(file):
    model = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(model, dict) or model.get("version") != 2:
        raise ValueError("--model requires an architecture v2 JSON object")
    if not isinstance(model.get("meta"), dict) or not model["meta"].get("id") or not isinstance(model.get("canvas"), dict):
        raise ValueError("model requires meta.id and canvas")
    for field in ("width", "height"):
        if number(model["canvas"].get(field)) <= 0:
            raise ValueError("model canvas needs positive width and height")
    maps = {}
    for kind in ("containers", "nodes", "edges"):
        items = model.get(kind)
        if not isinstance(items, list) or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] for item in items):
            raise ValueError(f"model.{kind} needs objects with nonempty string IDs")
        maps[kind] = {item["id"]: item for item in items}
        if len(maps[kind]) != len(items):
            raise ValueError(f"duplicate model {kind} IDs")
        if kind != "edges":
            for item in items:
                for field in ("x", "y", "w", "h"):
                    value = item.get(field)
                    number(value)
                    if not isinstance(value, (int, float)) or isinstance(value, bool) or (field in {"w", "h"} and value <= 0):
                        raise ValueError(f"{item['id']}.{field} needs finite numeric geometry")
    for item in model["containers"] + model["nodes"]:
        if item.get("parent") and item["parent"] not in maps["containers"]:
            raise ValueError(f"{item['id']}: unknown model parent")
    for item in model["nodes"]:
        display = (item.get("interfacePath") and item.get("moduleName")) if item.get("entityType") == "kernel-interface" else item.get("canonicalName")
        if not item.get("entityType") or not display or not item.get("parent"):
            raise ValueError(f"{item['id']}: node needs entityType, canonicalName (or interfacePath/moduleName for kernel-interface), and parent")
    for item in model["containers"]:
        if not item.get("kind"):
            raise ValueError(f"{item['id']}: container needs kind")
    for edge in model["edges"]:
        if edge.get("from") not in maps["nodes"] or edge.get("to") not in maps["nodes"] or edge.get("relation") not in RELATIONS:
            raise ValueError(f"{edge['id']}: invalid endpoints or relation")
        for key in ("fromSide", "toSide"):
            if key in edge and edge[key] not in NORMAL:
                raise ValueError(f"{edge['id']}: invalid {key}")
        for key in ("fromOffset", "toOffset"):
            if key in edge:
                number(edge[key])
        for step in edge.get("via", []):
            if not isinstance(step, dict) or len(step) != 1 or not set(step).issubset({"x", "y"}):
                raise ValueError(f"{edge['id']}: via steps need one x or y")
            number(next(iter(step.values())))
    return model


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="native .drawio XML, compressed or uncompressed")
    parser.add_argument("--model", type=Path, help="optional architecture v2 .diagram.json to compare")
    parser.add_argument("--theme", type=Path, help="override sibling architecture-diagram/assets/theme.json for --model style widths")
    args = parser.parse_args(argv)
    report = Report(args.file, args.model)
    try:
        pages = graph_pages(args.file)
        graphs = []
        for name, xml, compressed in pages:
            graph = Graph(name, xml, compressed, report)
            report.pages.append(graph.validate())
            graphs.append(graph)
        if args.model:
            model = read_model(args.model)
            candidates = [graph for graph in graphs if graph.cells.get(CANVAS_ID) and graph.cells[CANVAS_ID].metadata.get("modelId") == model["meta"]["id"]]
            if not candidates and len(graphs) == 1:
                candidates = graphs
            if len(candidates) != 1:
                report.issue("model-page", "--model must identify exactly one page by architecture-canvas.modelId")
            else:
                compare_model(candidates[0], model, args.theme)
    except (OSError, ValueError, TypeError, KeyError, ET.ParseError, RecursionError) as error:
        report.issue("invalid-input", str(error))
    print(json.dumps(report.output(), ensure_ascii=False, indent=2))
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
