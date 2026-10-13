#!/usr/bin/env python3
"""Isolated positive/negative regression tests; no draw.io or external modules."""

import base64
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zlib


HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("cockpit_checker", HERE / "check-drawio.py")
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)

TOKENS = {
    "version": 1, "grid": 8,
    "node": {"height": 80, "paddingX": 12, "paddingY": 8, "iconSlot": 48,
             "iconMax": 40, "iconGap": 12, "nameFont": 16, "nameLineHeight": 20,
             "descriptionFont": 12, "descriptionLineHeight": 16, "textGap": 4},
    "connector": {"height": 48, "paddingX": 8, "iconSlot": 24, "iconMax": 24,
                  "iconGap": 8, "font": 13, "minFont": 12, "lineHeight": 18},
}


def cell(root, identity, parent="1", x=0, y=0, width=240, height=80, style="", value="", **attributes):
    element = ET.SubElement(root, "mxCell", {"id": identity, "parent": parent, "vertex": "1", "style": style, "value": value, **attributes})
    ET.SubElement(element, "mxGeometry", {"x": str(x), "y": str(y), "width": str(width), "height": str(height), "as": "geometry"})
    return element


def card(root, identity, kind, symbol, name, x, description=None):
    connector = kind == "connector"
    width, height = (220, 48) if connector else (240, 80)
    wrapper = ET.SubElement(root, "object", {"id": identity, "layoutClass": kind, "symbolType": symbol, "canonicalName": name, "entityType": "hardware"})
    xml = ET.SubElement(wrapper, "mxCell", {"parent": "1", "vertex": "1", "style": "rounded=1;"})
    ET.SubElement(xml, "mxGeometry", {"x": str(x), "y": "40", "width": str(width), "height": str(height), "as": "geometry"})
    slot = 24 if connector else 48
    cell(root, identity + "-icon", identity, 8 if connector else 12, (height - slot) / 2, slot, slot, "group;")
    cell(root, identity + "-glyph", identity + "-icon", 0 if connector else 4, 0 if connector else 12, 24 if connector else 40, 24, "rounded=1;")
    nh = 18 if connector else 20
    group_height = nh + (20 if description else 0)
    ty = (height - group_height) / 2
    tx = 40 if connector else 72
    tw = width - tx - (8 if connector else 12)
    cell(root, identity + "-name", identity, tx, ty, tw, nh,
         f"text;align=left;verticalAlign=middle;fontSize={13 if connector else 16};", name)
    if description:
        cell(root, identity + "-description", identity, tx, ty + nh + 4, tw, 16,
             "text;align=left;verticalAlign=middle;fontSize=12;", description)
    return wrapper


def fixture():
    graph = ET.Element("mxGraphModel")
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    card(root, "adc", "device", "audio-adc", "Audio ADC", 24, "Microphone inputs")
    card(root, "j11", "connector", "coax", "J11 (FAKRA ×4)", 400)
    style = "edgeStyle=segmentEdgeStyle;exitX=1;exitY=0.5;exitPerimeter=0;entryX=0;entryY=0.5;entryPerimeter=0;"
    edge = ET.SubElement(root, "mxCell", {"id": "audio-link", "parent": "1", "edge": "1", "source": "adc", "target": "j11", "style": style})
    ET.SubElement(edge, "mxGeometry", {"relative": "1", "as": "geometry"})
    label = cell(root, "audio-label", "audio-link", 0, 0, 64, 18, "edgeLabel=1;fontSize=12;", "Audio")
    label.find("mxGeometry").set("relative", "1")
    return graph


def find(graph, identity):
    return next(element for element in graph.iter() if element.get("id") == identity)


def drawable(graph, identity):
    element = find(graph, identity)
    return element.find("mxCell") if element.tag == "object" else element


class NativeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit-check-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.drawio"

    def check(self, graph):
        self.path.write_bytes(ET.tostring(graph, encoding="utf-8"))
        return CHECKER.validate(self.path, TOKENS)

    def assert_issue(self, graph, code):
        result = self.check(graph)
        self.assertFalse(result["ok"])
        self.assertIn(code, {issue["code"] for issue in result["errors"]}, result)

    def test_valid_raw_model(self):
        report = self.check(fixture())
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["pages"][0]["boundEdges"], 1)

    def test_valid_uncompressed_multi_page(self):
        file = ET.Element("mxfile")
        for name in ("Symbols", "Example"):
            ET.SubElement(file, "diagram", {"name": name}).append(fixture())
        report = self.check(file)
        self.assertTrue(report["ok"], report)
        self.assertEqual(len(report["pages"]), 2)

    def test_valid_compressed_page(self):
        file = ET.Element("mxfile")
        diagram = ET.SubElement(file, "diagram", {"name": "Compressed"})
        encoded = quote(ET.tostring(fixture(), encoding="unicode"), safe="~()*!.'").encode("utf-8")
        compressor = zlib.compressobj(wbits=-15)
        diagram.text = base64.b64encode(compressor.compress(encoded) + compressor.flush()).decode("ascii")
        report = self.check(file)
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["pages"][0]["compressed"])

    def test_wrong_height(self):
        graph = fixture()
        drawable(graph, "adc").find("mxGeometry").set("height", "120")
        self.assert_issue(graph, "card-height")

    def test_connector_font_below_minimum(self):
        graph = fixture()
        element = find(graph, "j11-name")
        element.set("style", element.get("style").replace("fontSize=13", "fontSize=11"))
        self.assert_issue(graph, "card-font")

    def test_connector_font_minimum_allowed(self):
        graph = fixture()
        element = find(graph, "j11-name")
        element.set("style", element.get("style").replace("fontSize=13", "fontSize=12"))
        self.assertTrue(self.check(graph)["ok"])

    def test_inline_css_font_override(self):
        graph = fixture()
        find(graph, "j11-name").set("value", '<span style="font-size:10px">J11 (FAKRA ×4)</span>')
        self.assert_issue(graph, "card-font")

    def test_unbound_edge(self):
        graph = fixture()
        edge = find(graph, "audio-link")
        del edge.attrib["source"]
        del edge.attrib["target"]
        self.assert_issue(graph, "unbound-edge")

    def test_one_missing_endpoint(self):
        graph = fixture()
        del find(graph, "audio-link").attrib["target"]
        self.assert_issue(graph, "edge-endpoint")

    def test_non_normalized_port(self):
        graph = fixture()
        edge = find(graph, "audio-link")
        edge.set("style", edge.get("style").replace("exitX=1", "exitX=240"))
        self.assert_issue(graph, "edge-port")

    def test_wrong_edge_parent(self):
        graph = fixture()
        find(graph, "audio-link").set("parent", "0")
        self.assert_issue(graph, "edge-parent")

    def test_label_not_relative(self):
        graph = fixture()
        del find(graph, "audio-label").find("mxGeometry").attrib["relative"]
        self.assert_issue(graph, "label-relative")

    def test_label_wrong_parent(self):
        graph = fixture()
        find(graph, "audio-label").set("parent", "1")
        self.assert_issue(graph, "label-parent")

    def test_bogus_processor_exception(self):
        graph = fixture()
        find(graph, "adc").set("layoutClass", "processor")
        self.assert_issue(graph, "processor-exception")

    def test_soc_processor_exception(self):
        graph = fixture()
        find(graph, "adc").set("layoutClass", "processor")
        find(graph, "adc").set("symbolType", "soc")
        drawable(graph, "adc").find("mxGeometry").set("height", "192")
        self.assertTrue(self.check(graph)["ok"])

    def test_duplicate_id(self):
        graph = fixture()
        ET.SubElement(graph.find("root"), "mxCell", {"id": "adc"})
        self.assert_issue(graph, "duplicate-id")

    def test_missing_parent(self):
        graph = fixture()
        drawable(graph, "adc").set("parent", "missing")
        self.assert_issue(graph, "missing-parent")

    def test_parent_cycle(self):
        graph = fixture()
        drawable(graph, "adc").set("parent", "adc")
        self.assert_issue(graph, "parent-cycle")

    def test_unclassified_hardware(self):
        graph = fixture()
        del find(graph, "adc").attrib["layoutClass"]
        self.assert_issue(graph, "layout-class")

    def test_missing_canonical_name(self):
        graph = fixture()
        del find(graph, "adc").attrib["canonicalName"]
        self.assert_issue(graph, "card-metadata")

    def test_image_not_native(self):
        graph = fixture()
        find(graph, "adc-glyph").set("style", "shape=image;image=data:image/png;base64,AAAA;")
        self.assert_issue(graph, "image-cell")

    def test_text_box_reserves_excess_height(self):
        graph = fixture()
        find(graph, "adc-name").find("mxGeometry").set("height", "42")
        self.assert_issue(graph, "text-geometry")

    def test_oversize_icon(self):
        graph = fixture()
        find(graph, "adc-glyph").find("mxGeometry").set("width", "44")
        self.assert_issue(graph, "icon-size")

    def test_missing_icon(self):
        graph = fixture()
        graph.find("root").remove(find(graph, "adc-icon"))
        self.assert_issue(graph, "card-child")

    def test_two_line_device_name(self):
        graph = fixture()
        name = find(graph, "adc-name")
        name.set("value", "Audio ADC<br>Variant")
        name.find("mxGeometry").set("height", "40")
        name.find("mxGeometry").set("y", "10")
        find(graph, "adc-description").find("mxGeometry").set("y", "54")
        self.assertTrue(self.check(graph)["ok"])

    def test_two_line_connector_rejected(self):
        graph = fixture()
        find(graph, "j11-name").set("value", "J11<br>(FAKRA ×4)")
        self.assert_issue(graph, "connector-line")

    def test_bad_xml_rejected(self):
        self.path.write_text('<!DOCTYPE mxfile [<!ENTITY x "value">]><mxfile/>', encoding="utf-8")
        with self.assertRaises(ValueError):
            CHECKER.validate(self.path, TOKENS)


if __name__ == "__main__":
    unittest.main()
