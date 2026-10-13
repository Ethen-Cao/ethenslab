#!/usr/bin/env python3
"""Isolated positive/negative regression tests; no draw.io or external modules."""

import base64
import importlib.util
import json
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
    "plain": {
        "node": {"height": 64, "paddingX": 12, "paddingY": 6, "nameFont": 14,
                 "nameLineHeight": 18, "descriptionFont": 12, "descriptionLineHeight": 14, "textGap": 2},
        "connector": {"height": 32, "paddingX": 8, "font": 13, "minFont": 12, "lineHeight": 18},
    },
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


def plain_fixture():
    graph = fixture()
    graph.set("nodeStyle", "plain")
    root = graph.find("root")
    for element in list(root):
        if element.get("id", "").endswith(("-icon", "-glyph")):
            root.remove(element)
    for identity in ("adc", "j11"):
        wrapper = find(graph, identity)
        wrapper.set("nodeStyle", "plain")
        connector = wrapper.get("layoutClass") == "connector"
        shape = drawable(graph, identity).find("mxGeometry")
        height, padding = (32, 8) if connector else (64, 12)
        shape.set("height", str(height))
        text_width = float(shape.get("width")) - 2 * padding
        name = find(graph, identity + "-name")
        name.set("style", f'text;align=center;verticalAlign=middle;fontSize={13 if connector else 14};')
        group_height = 18 if connector else 34
        name_y = (height - group_height) / 2
        name.find("mxGeometry").attrib.update({"x": str(padding), "y": str(name_y), "width": str(text_width), "height": "18"})
        if not connector:
            description = find(graph, identity + "-description")
            description.set("style", "text;align=center;verticalAlign=middle;fontSize=12;")
            description.find("mxGeometry").attrib.update({"x": str(padding), "y": str(name_y + 20), "width": str(text_width), "height": "14"})
    return graph


def page_contract(graph, style="plain", identity="page-title"):
    return cell(graph.find("root"), identity, "1", 24, 8, 240, 24,
                "text;fontSize=16;", "Hardware", kind="page-contract", nodeStyle=style)


def set_style(element, **values):
    element.set("style", element.get("style", "") + ";" + ";".join(f"{key}={value}" for key, value in values.items()) + ";")


def legend_entry(graph, kind, value, width=2.6):
    root = graph.find("root")
    identity = f"key-{kind}-{value}"
    metadata = {"kind": "legend-entry", "legendType": kind,
                "signalClass" if kind == "signal" else "legendValue": value}
    cell(root, identity, "1", 24, 240, 240, 24, "group;", **metadata)
    color = CHECKER.SIGNAL_COLORS[value] if kind == "signal" else "#263445"
    start = "open" if kind == "direction" and value == "bidirectional" else "none"
    end = "open" if kind == "direction" and value in {"single", "bidirectional"} else "none"
    sample = ET.SubElement(root, "mxCell", {
        "id": identity + "-sample", "parent": identity, "edge": "1", "kind": "legend-sample",
        "style": f"strokeColor={color};strokeWidth={width};startArrow={start};endArrow={end};dashed={int(kind == 'linestyle')};",
    })
    geometry = ET.SubElement(sample, "mxGeometry", {"relative": "1", "as": "geometry"})
    for role, x in (("sourcePoint", 0), ("targetPoint", 64)):
        ET.SubElement(geometry, "mxPoint", {"x": str(x), "y": "12", "as": role})
    cell(root, identity + "-label", identity, 76, 0, 164, 24, "text;fontSize=13;fontColor=#647286;", value.title())
    return identity


def legend_fixture(mode="icons", direction="single", dashed=False):
    graph = plain_fixture() if mode == "plain" else fixture()
    edge = find(graph, "audio-link")
    edge.set("signalClass", "audio")
    set_style(edge, strokeColor="#8055B5", strokeWidth=2.6,
              startArrow="open" if direction == "bidirectional" else "none",
              endArrow="none" if direction == "physical" else "open", dashed=int(dashed))
    legend_entry(graph, "signal", "audio")
    legend_entry(graph, "direction", direction, width=1.8)
    if dashed:
        legend_entry(graph, "linestyle", "dashed", width=1.8)
    return graph


def remove_tree(graph, identity):
    root = graph.find("root")
    identities = {identity}
    while True:
        expanded = identities | {element.get("id") for element in root
                                 if drawable(graph, element.get("id")).get("parent") in identities}
        if expanded == identities:
            break
        identities = expanded
    for element in list(root):
        if element.get("id") in identities:
            root.remove(element)


class NativeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit-check-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.drawio"

    def check(self, graph, tokens=TOKENS):
        self.path.write_bytes(ET.tostring(graph, encoding="utf-8"))
        return CHECKER.validate(self.path, tokens)

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

    def test_plain_valid(self):
        report = self.check(plain_fixture())
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["pages"][0]["nodeStyle"], "plain")

    def test_plain_without_any_icon_tokens(self):
        only_plain = {"version": 1, "grid": 8, "plain": TOKENS["plain"]}
        token_path = Path(self.temp.name) / "plain-tokens.json"
        token_path.write_text(json.dumps(only_plain), encoding="utf-8")
        report = self.check(plain_fixture(), CHECKER.read_tokens(token_path))
        self.assertTrue(report["ok"], report)

    def test_legacy_tokens_without_plain_still_work_for_icons(self):
        legacy = {key: value for key, value in TOKENS.items() if key != "plain"}
        token_path = Path(self.temp.name) / "legacy-tokens.json"
        token_path.write_text(json.dumps(legacy), encoding="utf-8")
        report = self.check(fixture(), CHECKER.read_tokens(token_path))
        self.assertTrue(report["ok"], report)

    def test_plain_missing_tokens_fails_cleanly(self):
        legacy = {key: value for key, value in TOKENS.items() if key != "plain"}
        result = self.check(plain_fixture(), legacy)
        self.assertFalse(result["ok"])
        self.assertIn("missing-style-tokens", {item["code"] for item in result["errors"]})

    def test_plain_requires_explicit_card_style(self):
        graph = plain_fixture()
        del find(graph, "adc").attrib["nodeStyle"]
        self.assert_issue(graph, "node-style-mismatch")

    def test_plain_card_on_icons_page_rejected(self):
        graph = plain_fixture()
        graph.set("nodeStyle", "icons")
        self.assert_issue(graph, "node-style-mismatch")

    def test_unknown_page_node_style(self):
        graph = fixture()
        graph.set("nodeStyle", "unknown")
        self.assert_issue(graph, "node-style")

    def test_unknown_card_node_style(self):
        graph = fixture()
        find(graph, "adc").set("nodeStyle", "unknown")
        self.assert_issue(graph, "node-style")

    def test_plain_unexpected_icon_id(self):
        graph = plain_fixture()
        cell(graph.find("root"), "adc-icon", "adc", 12, 8, 48, 48, "group;")
        self.assert_issue(graph, "plain-icon")

    def test_plain_unexpected_nested_icon_group(self):
        graph = plain_fixture()
        cell(graph.find("root"), "extra-group", "adc", 0, 0, 20, 20, "group;")
        cell(graph.find("root"), "pictogram", "extra-group", 0, 0, 20, 20, "group;", kind="icon-group")
        self.assert_issue(graph, "plain-icon")

    def test_plain_unexpected_nested_icon_stroke(self):
        graph = plain_fixture()
        cell(graph.find("root"), "pictogram-stroke", "adc", 0, 0, 20, 20, "ellipse;", kind="icon-stroke")
        self.assert_issue(graph, "plain-icon")

    def test_plain_leftover_icon_gutter(self):
        graph = plain_fixture()
        find(graph, "adc-name").find("mxGeometry").set("x", "72")
        self.assert_issue(graph, "text-geometry")

    def test_plain_left_alignment_rejected(self):
        graph = plain_fixture()
        name = find(graph, "adc-name")
        name.set("style", name.get("style").replace("align=center", "align=left"))
        self.assert_issue(graph, "card-text-align")

    def test_plain_inline_left_alignment_rejected(self):
        graph = plain_fixture()
        find(graph, "adc-name").set("value", '<div style="text-align:left">Audio ADC</div>')
        self.assert_issue(graph, "card-text-align")

    def test_plain_wrong_device_height(self):
        graph = plain_fixture()
        drawable(graph, "adc").find("mxGeometry").set("height", "80")
        self.assert_issue(graph, "card-height")

    def test_plain_wrong_connector_height(self):
        graph = plain_fixture()
        drawable(graph, "j11").find("mxGeometry").set("height", "48")
        self.assert_issue(graph, "card-height")

    def test_plain_two_line_name(self):
        graph = plain_fixture()
        name = find(graph, "adc-name")
        name.set("value", "Audio ADC<br>Variant")
        name.find("mxGeometry").attrib.update({"y": "6", "height": "36"})
        find(graph, "adc-description").find("mxGeometry").set("y", "44")
        self.assertTrue(self.check(graph)["ok"])

    def test_plain_soc_height_exception(self):
        graph = plain_fixture()
        find(graph, "adc").attrib.update({"layoutClass": "processor", "symbolType": "soc"})
        drawable(graph, "adc").find("mxGeometry").set("height", "192")
        find(graph, "adc-name").find("mxGeometry").set("y", "79")
        find(graph, "adc-description").find("mxGeometry").set("y", "99")
        self.assertTrue(self.check(graph)["ok"])

    def test_plain_processor_still_bans_icons(self):
        graph = plain_fixture()
        find(graph, "adc").attrib.update({"layoutClass": "processor", "symbolType": "soc"})
        cell(graph.find("root"), "adc-icon", "adc", 12, 8, 48, 48, "group;")
        self.assert_issue(graph, "plain-icon")

    def test_plain_bogus_processor_rejected(self):
        graph = plain_fixture()
        find(graph, "adc").set("layoutClass", "processor")
        self.assert_issue(graph, "processor-exception")

    def test_plain_page_contract_fallback_after_save(self):
        graph = plain_fixture()
        del graph.attrib["nodeStyle"]
        page_contract(graph)
        report = self.check(graph)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["pages"][0]["nodeStyle"], "plain")

    def test_plain_matching_graph_and_marker(self):
        graph = plain_fixture()
        page_contract(graph)
        self.assertTrue(self.check(graph)["ok"])

    def test_icons_page_contract_marker(self):
        graph = fixture()
        page_contract(graph, "icons")
        report = self.check(graph)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["pages"][0]["nodeStyle"], "icons")

    def test_conflicting_graph_and_page_contract(self):
        graph = plain_fixture()
        page_contract(graph, "icons")
        self.assert_issue(graph, "node-style-conflict")

    def test_duplicate_page_contract_markers(self):
        graph = plain_fixture()
        page_contract(graph)
        page_contract(graph, identity="second-title")
        self.assert_issue(graph, "page-contract-count")

    def test_invalid_page_contract_style(self):
        graph = plain_fixture()
        page_contract(graph, "unknown")
        self.assert_issue(graph, "node-style")

    def test_missing_page_contract_style(self):
        graph = plain_fixture()
        marker = page_contract(graph)
        del marker.attrib["nodeStyle"]
        self.assert_issue(graph, "node-style")

    def test_marker_does_not_override_unknown_graph_style(self):
        graph = plain_fixture()
        graph.set("nodeStyle", "unknown")
        page_contract(graph)
        self.assert_issue(graph, "node-style")

    def test_native_legends_valid_both_modes_and_not_body_edges(self):
        for mode in ("icons", "plain"):
            with self.subTest(mode=mode):
                report = self.check(legend_fixture(mode))
                self.assertTrue(report["ok"], report)
                self.assertEqual(report["pages"][0]["boundEdges"], 1)

    def test_missing_legend_both_modes(self):
        for mode in ("icons", "plain"):
            with self.subTest(mode=mode):
                graph = legend_fixture(mode)
                remove_tree(graph, "key-signal-audio")
                self.assert_issue(graph, "legend-signal-missing")

    def test_colored_text_only_legend_is_insufficient(self):
        for mode in ("icons", "plain"):
            with self.subTest(mode=mode):
                graph = legend_fixture(mode)
                remove_tree(graph, "key-signal-audio")
                cell(graph.find("root"), "legend-audio", value="Audio ───", style="text;fontColor=#8055B5;")
                self.assert_issue(graph, "legend-signal-missing")

    def test_legend_sample_removed(self):
        graph = legend_fixture()
        remove_tree(graph, "key-signal-audio-sample")
        self.assert_issue(graph, "legend-sample")

    def test_text_vertex_cannot_impersonate_line_sample(self):
        graph = legend_fixture()
        sample = find(graph, "key-signal-audio-sample")
        sample.attrib.pop("edge")
        sample.attrib.update({"vertex": "1", "value": "────", "style": "text;fontColor=#8055B5;"})
        sample.find("mxGeometry").attrib.update({"width": "64", "height": "24"})
        self.assert_issue(graph, "legend-sample")

    def test_legend_sample_wrong_color(self):
        graph = legend_fixture()
        set_style(find(graph, "key-signal-audio-sample"), strokeColor="#356DC9")
        self.assert_issue(graph, "legend-signal-color")

    def test_legend_sample_wrong_width(self):
        graph = legend_fixture()
        set_style(find(graph, "key-signal-audio-sample"), strokeWidth=1.8)
        self.assert_issue(graph, "legend-signal-width")

    def test_signal_sample_cannot_explain_arrow_or_dashed_style(self):
        for styles in ({"endArrow": "open"}, {"dashed": 1}):
            with self.subTest(styles=styles):
                graph = legend_fixture()
                set_style(find(graph, "key-signal-audio-sample"), **styles)
                self.assert_issue(graph, "legend-signal-style")

    def test_all_direction_types_require_matching_samples(self):
        for direction in ("single", "bidirectional", "physical"):
            with self.subTest(direction=direction):
                graph = legend_fixture(direction=direction)
                self.assertTrue(self.check(graph)["ok"])
                remove_tree(graph, "key-direction-" + direction)
                self.assert_issue(graph, "legend-direction-missing")

    def test_direction_metadata_alone_is_insufficient(self):
        graph = legend_fixture(direction="bidirectional")
        set_style(find(graph, "key-direction-bidirectional-sample"), startArrow="none")
        self.assert_issue(graph, "legend-direction-style")

    def test_dashed_relationship_requires_sample(self):
        graph = legend_fixture(dashed=True)
        self.assertTrue(self.check(graph)["ok"])
        remove_tree(graph, "key-linestyle-dashed")
        self.assert_issue(graph, "legend-linestyle-missing")

    def test_dashed_sample_must_actually_be_dashed(self):
        graph = legend_fixture(dashed=True)
        set_style(find(graph, "key-linestyle-dashed-sample"), dashed=0)
        self.assert_issue(graph, "legend-linestyle-style")

    def test_partial_legend_and_palette_inference(self):
        graph = legend_fixture()
        edge = find(graph, "audio-link")
        del edge.attrib["signalClass"]
        self.assertTrue(self.check(graph)["ok"])
        set_style(edge, strokeColor="#356dc9")
        self.assert_issue(graph, "legend-signal-missing")

    def test_each_signal_family_requires_its_own_sample(self):
        for family, color in CHECKER.SIGNAL_COLORS.items():
            with self.subTest(family=family):
                graph = legend_fixture()
                edge = find(graph, "audio-link")
                edge.set("signalClass", family)
                set_style(edge, strokeColor=color)
                remove_tree(graph, "key-signal-audio")
                self.assert_issue(graph, "legend-signal-missing")
                legend_entry(graph, "signal", family)
                self.assertTrue(self.check(graph)["ok"])

    def test_catalog_extra_signals_are_allowed(self):
        graph = legend_fixture()
        legend_entry(graph, "signal", "video", width=1.8)
        self.assertTrue(self.check(graph)["ok"])

    def test_legend_signal_width_can_match_any_same_family_edge(self):
        graph = legend_fixture()
        edge = ET.fromstring(ET.tostring(find(graph, "audio-link")))
        edge.set("id", "audio-secondary")
        set_style(edge, strokeWidth=1.8)
        graph.find("root").append(edge)
        set_style(find(graph, "key-signal-audio-sample"), strokeWidth=1.8)
        self.assertTrue(self.check(graph)["ok"])

    def test_jumpstyle_alone_does_not_require_crossing_legend(self):
        graph = legend_fixture()
        set_style(find(graph, "audio-link"), jumpStyle="arc", jumpSize=10)
        self.assertTrue(self.check(graph)["ok"])

    def test_symbol_only_page_needs_no_legend(self):
        graph = fixture()
        remove_tree(graph, "audio-link")
        self.assertTrue(self.check(graph)["ok"])

    def test_decoration_does_not_introduce_signal_or_direction_requirements(self):
        graph = fixture()
        find(graph, "audio-link").set("kind", "decoration")
        set_style(find(graph, "audio-link"), strokeColor="#356DC9", endArrow="open", dashed=1)
        report = self.check(graph)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["pages"][0]["boundEdges"], 0)

    def test_legend_descendants_do_not_count_as_relationships(self):
        graph = legend_fixture()
        edge = ET.fromstring(ET.tostring(find(graph, "audio-link")))
        edge.attrib.update({"id": "example-wire", "parent": "key-signal-audio", "signalClass": "power"})
        graph.find("root").append(edge)
        report = self.check(graph)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["pages"][0]["boundEdges"], 1)

    def test_bound_edge_id_cannot_hide_relationship(self):
        graph = legend_fixture()
        find(graph, "audio-link").set("id", "legend-named-real-link")
        find(graph, "audio-label").set("parent", "legend-named-real-link")
        remove_tree(graph, "key-signal-audio")
        self.assert_issue(graph, "legend-signal-missing")

    def test_zero_length_and_missing_endpoint_samples_rejected(self):
        for mutation in ("zero", "missing"):
            with self.subTest(mutation=mutation):
                graph = legend_fixture()
                geometry = find(graph, "key-signal-audio-sample").find("mxGeometry")
                point = geometry.find("mxPoint[@as='targetPoint']")
                if mutation == "zero":
                    point.set("x", "0")
                else:
                    geometry.remove(point)
                self.assert_issue(graph, "legend-sample-geometry")

    def test_hidden_or_invisible_stroke_rejected(self):
        for styles in ({"strokeColor": "none"}, {"strokeColor": "transparent"},
                       {"opacity": 0}, {"strokeOpacity": 0}, {"strokeWidth": 0}, {"visible": 0}):
            with self.subTest(styles=styles):
                graph = legend_fixture()
                set_style(find(graph, "key-signal-audio-sample"), **styles)
                self.assert_issue(graph, "legend-sample-visible")

    def test_hidden_group_rejected(self):
        graph = legend_fixture()
        find(graph, "key-signal-audio").set("visible", "0")
        self.assert_issue(graph, "legend-sample-visible")

    def test_empty_or_hidden_legend_labels_rejected(self):
        for value in ("", "---", '<span style="display:none">Audio</span>'):
            with self.subTest(value=value):
                graph = legend_fixture()
                find(graph, "key-signal-audio-label").set("value", value)
                self.assert_issue(graph, "legend-label")

    def test_sample_must_be_free_ended(self):
        graph = legend_fixture()
        find(graph, "key-signal-audio-sample").attrib.update({"source": "adc", "target": "j11"})
        self.assert_issue(graph, "legend-sample")

    def test_sample_arrow_names_must_be_native(self):
        graph = legend_fixture()
        set_style(find(graph, "key-direction-single-sample"), endArrow="single")
        self.assert_issue(graph, "legend-sample-arrow")

    def test_text_style_cannot_disguise_edge_as_a_line(self):
        graph = legend_fixture()
        set_style(find(graph, "key-signal-audio-sample"), text=1)
        self.assert_issue(graph, "legend-sample")

    def test_orphan_sample_metadata_cannot_hide_a_body_edge(self):
        graph = fixture()
        find(graph, "audio-link").set("kind", "legend-sample")
        self.assert_issue(graph, "legend-sample-parent")

    def test_legend_from_other_page_cannot_cover_missing_sample(self):
        document = ET.Element("mxfile")
        for mode in ("icons", "plain"):
            graph = legend_fixture(mode)
            if mode == "plain":
                remove_tree(graph, "key-signal-audio")
            ET.SubElement(document, "diagram", {"name": mode}).append(graph)
        result = self.check(document)
        self.assertEqual([(item["page"], item["code"]) for item in result["errors"]],
                         [("plain", "legend-signal-missing")])

    def test_zero_font_size_label_rejected(self):
        graph = legend_fixture()
        set_style(find(graph, "key-signal-audio-label"), fontSize=0)
        self.assert_issue(graph, "legend-label")

    def test_explicit_unclassified_direction_still_requires_legend(self):
        graph = fixture()
        set_style(find(graph, "audio-link"), startArrow="none", endArrow="open")
        self.assert_issue(graph, "legend-direction-missing")

    def test_legend_tokens_are_optional(self):
        tokens = {**TOKENS, "legend": {"sampleLength": 64, "rowHeight": 24}}
        self.assertTrue(self.check(legend_fixture(), tokens)["ok"])


if __name__ == "__main__":
    unittest.main()
