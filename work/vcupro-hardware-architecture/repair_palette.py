"""Apply reviewed neutral palette in place, without rebuilding the architecture."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from native_builder import SKILL, cell, styles


PATH = Path(__file__).resolve().parent / "vcupro-system-architecture.drawio"
TOKENS = json.loads((SKILL / "assets/tokens.json").read_text())
COLORS = TOKENS["colors"]
ALLOWED = {"fillColor", "strokeColor", "strokeWidth", "fontColor"}


def update(element, **changes):
    native = cell(element)
    parts = native.get("style", "").split(";")
    remaining = dict(changes)
    result = []
    for part in parts:
        if not part:
            continue
        key = part.split("=", 1)[0]
        if key in changes:
            result.append(f"{key}={changes[key]}")
            remaining.pop(key, None)
        else:
            result.append(part)
    result.extend(f"{key}={value}" for key, value in remaining.items())
    native.set("style", ";".join(result) + ";")


def unchanged_content(tree):
    """Ignore only the four paint properties authorized by this patch."""
    result = deepcopy(tree.getroot())
    for native in result.iter("mxCell"):
        if "style" in native.attrib:
            native.set("style", ";".join(
                part for part in native.get("style", "").split(";")
                if part and part.split("=", 1)[0] not in ALLOWED))
    return ET.tostring(result)


def main():
    tree = ET.parse(PATH)
    before = unchanged_content(tree)
    # Preserve every native edge exactly, including icons and legend samples.
    before_edges = [ET.tostring(c) for c in tree.iter("mxCell") if c.get("edge") == "1"]
    counts = Counter()
    for element in tree.findall("./diagram/mxGraphModel/root/*"):
        native = cell(element)
        if native.get("edge") == "1":
            continue
        kind = element.get("kind")
        layout = element.get("layoutClass")
        if layout in {"device", "processor", "connector", "port-strip"}:
            if element.get("status", "").casefold() in {"reserved", "optional", "dnp"}:
                role = "reserved"
            elif layout in {"connector", "port-strip"}:
                role = "connector"
            elif element.get("symbolType") in {"soc", "mcu"}:
                role = "core"
            else:
                role = "device"
            update(element, fillColor=COLORS[role + "Fill"],
                   strokeColor=COLORS[role + "Border"], strokeWidth=TOKENS["strokes"]["node"])
            counts[role] += 1
        elif kind in {"physical-enclosure", "board", "functional-group"}:
            functional = kind == "functional-group"
            update(element, fillColor="none" if functional else COLORS["panel"],
                   strokeColor=COLORS["functionalBorder" if functional else "border"],
                   strokeWidth=TOKENS["strokes"]["container"])
            counts[kind] += 1
        if styles(element).get("fontColor", "").upper() == "#647286":
            update(element, fontColor=COLORS["muted"])
            counts["secondaryText"] += 1
    assert unchanged_content(tree) == before, "Non-palette content changed; refusing to save"
    assert [ET.tostring(c) for c in tree.iter("mxCell") if c.get("edge") == "1"] == before_edges
    tree.write(PATH, encoding="utf-8", xml_declaration=True)
    print(json.dumps({"updated": dict(counts), "unchangedNativeEdges": len(before_edges),
                      "geometryLabelsAndMetadataUnchanged": True}, indent=2))


if __name__ == "__main__":
    main()
