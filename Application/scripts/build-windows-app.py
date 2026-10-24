#!/usr/bin/env python3
"""Assemble and exercise an unsigned Windows development package on Windows x64."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import time
import urllib.request
import zipfile

from windows_automation_gate import require_automation_protocol, require_automation_window
from windows_soxr_package import stage_soxr
from cpr_audition_gate import require_cpr_audition, require_cpr_audition_window

SDK = "10.0.402"
DOTNET_RUNTIME = "10.0.13"
SWIFT = "6.4.1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def inspect_pe(path):
    import pefile
    with pefile.PE(str(path), fast_load=True) as pe:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY[name] for name in
                                 ("IMAGE_DIRECTORY_ENTRY_IMPORT", "IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT")])
        clr = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR"]]
        flags = struct.unpack("<I", pe.get_data(clr.VirtualAddress + 16, 4))[0] if clr.VirtualAddress else 0
        if pe.FILE_HEADER.Machine != 0x8664 and not (pe.FILE_HEADER.Machine == 0x14c and flags & 1 and not flags & 2):
            raise RuntimeError("Package contains a non-x64 native image: " + path.name)
        imports = sorted({entry.dll.decode("ascii").lower() for kind in
                          ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT")
                          for entry in getattr(pe, kind, [])})
        if any(Path(name).name != name or ":" in name or "\\" in name for name in imports):
            raise RuntimeError("PE import contains a path")
        return imports


def runtime_index(directories):
    found = {}
    for directory in directories:
        for path in sorted(directory.rglob("*.dll")):
            key = path.name.lower()
            if key in found and digest(found[key]) != digest(path):
                raise RuntimeError("Ambiguous runtime dependency: " + path.name)
            found[key] = path
    return found


def assemble_dependencies(stage, swift_runtime, vc_runtime, system):
    # Only the pinned runtime component and VS redistributable CRT are sources.
    # Installed compiler tools and arbitrary PATH entries are never copied.
    swift = runtime_index([swift_runtime])
    vc = runtime_index(vc_runtime)
    sources = {**swift, **vc}
    copied, records = [], []
    for name, path in sources.items():
        # ICU loads data/components dynamically. Include its pinned runtime DLLs.
        if "icu" in name:
            shutil.copyfile(path, stage / path.name)
            copied.append({"name": path.name, "source": "swift-runtime-" + SWIFT})
    pending = sorted(p for p in stage.rglob("*") if p.suffix.lower() in (".dll", ".exe"))
    visited = set()
    while pending:
        path = pending.pop(0)
        key = str(path.relative_to(stage)).lower()
        if key in visited:
            continue
        visited.add(key)
        local = {p.name.lower(): p for p in stage.glob("*") if p.is_file()}
        imports = inspect_pe(path)
        resolved = []
        for name in imports:
            if name in local:
                origin = "application"
            elif name in sources:
                source = sources[name]
                target = stage / source.name
                shutil.copyfile(source, target)
                pending.append(target)
                origin = "visual-cpp-runtime" if name in vc else "swift-runtime-" + SWIFT
                copied.append({"name": source.name, "source": origin})
            elif name.startswith(("api-ms-", "ext-ms-")):
                origin = "windows-api-contract"
            elif name.startswith(("msvcp1", "msvcr1", "vcruntime", "concrt", "vcomp", "swift", "foundation", "dispatch")):
                raise RuntimeError("Required app-local runtime is missing: " + name)
            elif (system / name).is_file():
                origin = "windows-system"
            else:
                raise RuntimeError("Unresolved PE dependency: " + name + " from " + path.name)
            resolved.append({"name": name, "source": origin})
        records.append({"path": path.relative_to(stage).as_posix(), "imports": resolved})
    return {"copied": copied, "images": records}


def validate_modules(modules, stage, windows, required):
    if not isinstance(modules, list) or not modules:
        raise RuntimeError("Missing actual process module evidence")
    result = []
    names = set()
    for module in modules:
        path = Path(module["path"])
        if path.name.lower() != module["name"].lower() or not path.is_file():
            raise RuntimeError("Invalid process module evidence")
        if inside(path, stage):
            location = "application/" + path.resolve().relative_to(stage.resolve()).as_posix()
            names.add(path.name.lower())
        elif inside(path, windows):
            location = "windows/" + path.name
        else:
            raise RuntimeError("Process loaded a module outside the package and Windows: " + path.name)
        result.append({"name": path.name, "location": location, "sha256": digest(path)})
    if not set(required).issubset(names):
        raise RuntimeError("Required runtime was not observed loading from the application folder")
    return result


def copy_example(app, stage):
    manifest = json.loads((app / "Examples/example.json").read_text(encoding="utf-8"))
    target = stage / "Examples" / manifest["project"]
    for item in manifest["files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts or ":" in item["path"] or "\\" in item["path"]:
            raise RuntimeError("Invalid bundled example path")
        source = app / "Examples" / manifest["project"] / relative
        if source.is_symlink() or source.stat().st_size != item["bytes"] or digest(source) != item["sha256"]:
            raise RuntimeError("Authored example bytes do not match their manifest")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for name in ("README.md", "example.json"):
        shutil.copyfile(app / "Examples" / name, stage / "Examples" / name)
    return target


def require_window_visual(path, bounds=None):
    data = path.read_bytes()
    dimensions = struct.unpack_from(">II", data, 16) if len(data) >= 24 else (0, 0)
    if (len(data) < 1024 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR"
            or not all(0 < value <= 16_384 for value in dimensions)):
        raise RuntimeError("Missing or invalid WPF window visual")
    if bounds is not None:
        keys = ("outer_width", "outer_height", "client_width", "client_height", "dpi_x", "dpi_y")
        if any(type(bounds.get(key)) not in (int, float) or not math.isfinite(bounds[key]) or bounds[key] <= 0 for key in keys):
            raise RuntimeError("Missing finite client-window capture bounds")
        # The WPF capture deliberately renders logical client dimensions at 96 DPI;
        # reported host DPI describes the window, not a scaling of this PNG.
        if (dimensions != (math.ceil(bounds["client_width"]), math.ceil(bounds["client_height"]))
                or bounds["client_width"] > bounds["outer_width"] or bounds["client_height"] > bounds["outer_height"]):
            raise RuntimeError("Window PNG dimensions do not match its declared client capture")


def require_pinned_header_scroll(smoke):
    if smoke.get("timeline_scroll_screenshot") != "native-timeline-scroll-visual.png":
        raise RuntimeError("Missing scrolled timeline screenshot receipt")
    scroll = smoke.get("timeline_scroll", {})

    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise RuntimeError("Invalid timeline scroll geometry")
        return value

    def point(value):
        return (number(value["x"]), number(value["y"]))

    if number(scroll.get("zoom_pixels_per_second")) != 100:
        raise RuntimeError("Timeline scroll was not checked at the declared zoom")
    delta = number(scroll.get("offset_after")) - number(scroll.get("offset_before"))
    before, after = scroll.get("headers_before", []), scroll.get("headers_after", [])
    if delta < 50 or len(before) != 4 or len(after) != 4:
        raise RuntimeError("Timeline scroll did not exercise all four track headers")
    if any(abs(a - b) > 0.5 for first, last in zip(before, after) for a, b in zip(point(first), point(last))):
        raise RuntimeError("Track headers moved during horizontal timeline scroll")
    first, last = point(scroll["event_before"]), point(scroll["event_after"])
    if abs(last[0] - first[0] + delta) > 0.5 or abs(last[1] - first[1]) > 0.5:
        raise RuntimeError("Timeline event geometry did not follow the measured scroll")


def require_cpr_review_layout(path, bounds, layout, minimum_error=False):
    require_window_visual(path, bounds)
    width, height = math.ceil(bounds["client_width"]), math.ceil(bounds["client_height"])
    counts = ("alpha_minimum", "alpha_254_pixels", "alpha_255_pixels", "alpha_below_254_pixels", "total_pixels")
    if (any(type(layout.get(key)) is not int or layout[key] < 0 for key in counts)
            or layout["total_pixels"] != width * height or layout["alpha_below_254_pixels"] != 0
            or layout["alpha_254_pixels"] + layout["alpha_255_pixels"] != width * height
            or layout["alpha_minimum"] != (254 if layout["alpha_254_pixels"] else 255)):
        raise RuntimeError("CPR review capture lacks complete alpha 254-or-255 coverage")
    diagnostic = json.loads(path.with_name(path.stem + "-alpha.json").read_text(encoding="utf-8"))
    if (diagnostic.get("schema") != 1 or diagnostic.get("screenshot") != path.name
            or diagnostic.get("png_sha256") != digest(path) or diagnostic.get("root_background_alpha") != 255
            or diagnostic.get("window_bounds") != bounds or diagnostic.get("capture_layout") != layout):
        raise RuntimeError("CPR review alpha diagnostic does not match the capture and layout")
    viewport = layout.get("review_viewport_height")
    if type(viewport) not in (int, float) or not math.isfinite(viewport) or viewport < 40:
        raise RuntimeError("CPR review has no usable content viewport")
    controls = layout.get("footer_controls", [])
    if (len(controls) != 4 or {control.get("name") for control in controls} !=
            {"Previous", "Next", "Cancel", "Import Supported Data"}):
        raise RuntimeError("CPR review footer geometry is incomplete")
    for control in controls:
        if (any(type(control.get(key)) not in (int, float) or not math.isfinite(control[key])
                for key in ("x", "y", "width", "height"))
                or control["x"] < 0 or control["y"] < 0 or control["width"] <= 0 or control["height"] <= 0
                or control["x"] + control["width"] > bounds["client_width"] + 0.5
                or control["y"] + control["height"] > bounds["client_height"] + 0.5):
            raise RuntimeError("CPR review footer control lies outside the captured client")
    if minimum_error and (bounds["outer_width"] > 650.5 or bounds["outer_height"] > 480.5
                          or type(layout.get("error_characters")) is not int or layout["error_characters"] <= 0):
        raise RuntimeError("CPR review error layout was not checked at minimum window size")


def require_musical_ruler(smoke):
    ruler = smoke.get("musical_ruler", {})
    numeric = ("tempo", "duration", "pixels_per_second", "bar_two_seconds", "first_label_x", "second_label_x")
    if (type(ruler.get("revision")) is not int or ruler["revision"] <= 0
            or any(type(ruler.get(key)) not in (int, float) or not math.isfinite(ruler[key]) for key in numeric)):
        raise RuntimeError("Missing finite musical ruler geometry and revision")
    if (ruler["tempo"] != 96 or ruler["duration"] != 24 or ruler["pixels_per_second"] != 32
            or ruler["bar_two_seconds"] != 2.5 or ruler["first_label_x"] < 0
            or abs(ruler["second_label_x"] - ruler["first_label_x"] - 2.5 * ruler["pixels_per_second"]) > 0.5):
        raise RuntimeError("Musical ruler labels do not match the authored 96 BPM example")


WORKSPACE_CHECKS = {
    "workspace-compact-default", "workspace-normal-density", "workspace-event-hit-targets",
    "workspace-inspector-sections", "workspace-keyboard-pane-toggles", "workspace-pane-state-preserved",
    "workspace-splitter-bounds", "workspace-resized-fader-geometry", "workspace-source-only-actions",
    "workspace-source-auto-expand", "workspace-visual-artifacts", "workspace-active-capture-preserved",
}


TOP_ROWS_CHECKS = {
    "top-rows-compact-layout", "top-rows-empty-state", "top-rows-source-state",
    "top-rows-long-names", "top-rows-resize-preserves-state",
    "timeline-dividers-fill-width", "ruler-corner-stays-visible",
}


def require_timeline_dividers(state):
    """Bind every row baseline to the actual canvas, including expanded panes."""
    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise RuntimeError("Timeline divider geometry is missing or non-finite")
        return value

    if not isinstance(state, dict):
        raise RuntimeError("Timeline divider state is missing")
    width = number(state.get("canvas_width"))
    viewport_width = number(state.get("viewport_width"))
    row_height = number(state.get("row_height"))
    rows = state.get("headers", [])
    lines = state.get("divider_ends", [])
    if (width < viewport_width - 0.5 or viewport_width <= 0 or row_height not in (44, 68)
            or not isinstance(rows, list) or not isinstance(lines, list) or len(lines) != len(rows)):
        raise RuntimeError("Timeline dividers do not cover the measured canvas and tracks")
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise RuntimeError("Timeline divider is not a measured line")
        x1, y1, x2, y2 = (number(line.get(key)) for key in ("x1", "y1", "x2", "y2"))
        if (abs(x1) > 0.5 or abs(x2 - width) > 0.5 or abs(y1 - y2) > 0.5
                or abs(y1 - (26 + (index + 1) * row_height)) > 0.5):
            raise RuntimeError("Timeline divider ends early or uses the wrong track baseline")


def require_pinned_ruler_corner(smoke):
    """Require the measured ruler label to stay inside the pinned header corner."""
    scroll = smoke.get("timeline_scroll", {})
    if not isinstance(scroll, dict):
        raise RuntimeError("Pinned ruler scroll receipt is missing")
    labels = []
    header_boxes = []
    for suffix in ("before", "after"):
        label = scroll.get("ruler_" + suffix, {})
        header = scroll.get("ruler_header_" + suffix, {})
        if (not isinstance(label, dict) or label.get("text") != "Bars + Beats"
                or not isinstance(header, dict)):
            raise RuntimeError("Pinned ruler label was not observed before and after scroll")
        for item, keys in ((label, ("x", "y", "width", "height")), (header, ("x", "y", "width", "height"))):
            if (not isinstance(item, dict) or any(type(item.get(key)) not in (int, float)
                    or not math.isfinite(item[key]) for key in keys)):
                raise RuntimeError("Pinned ruler label has invalid measured geometry")
        if (label["width"] <= 0 or label["height"] <= 0 or abs(header["width"] - 198) > 0.5 or header["height"] not in (44, 68)
                or label["x"] < header["x"] - 0.5 or label["x"] + label["width"] > header["x"] + header["width"] + 0.5
                or label["y"] < header["y"] - 26.5 or label["y"] + label["height"] > header["y"] + 0.5):
            raise RuntimeError("Ruler label is clipped outside its pinned header corner")
        labels.append(label)
        header_boxes.append(header)
    if any(abs(boxes[0][key] - boxes[1][key]) > 0.5 for boxes in (labels, header_boxes) for key in ("x", "y", "width", "height")):
        raise RuntimeError("Pinned ruler label moved during horizontal scroll")


def require_top_rows_geometry(layout, bounds):
    """Check measured controls and text, including ellipsis and content-host bounds."""
    def fail(message):
        raise RuntimeError("Top-row geometry: " + message)

    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            fail("missing or non-finite measurement")
        return value

    if not isinstance(layout, dict) or not isinstance(bounds, dict):
        fail("missing layout or window bounds")
    width, height = (number(bounds.get(key)) for key in ("client_width", "client_height"))
    if (width <= 0 or height <= 107 or abs(number(layout.get("stack_height")) - 107) > 0.5
            or any(abs(number(layout.get(key)) - number(bounds.get(key))) > 0.5
                   for key in ("client_width", "client_height"))):
        fail("stack or client dimensions disagree")

    def records(key, names):
        values = layout.get(key)
        if (not isinstance(values, list) or len(values) != len(names)
                or any(not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in values)
                or {item.get("name") for item in values} != set(names)):
            fail("missing or duplicate " + key)
        return {item["name"]: item for item in values}

    def rectangle(item):
        for key in ("x", "y", "width", "height"):
            number(item.get(key))
        if type(item.get("visible")) is not bool:
            fail("missing visibility measurement")
        if not item["visible"]:
            if any(item[key] != 0 for key in ("x", "y", "width", "height")):
                fail("hidden control retains geometry")
            return
        if (item["width"] <= 0 or item["height"] <= 0 or item["x"] < -0.5 or item["y"] < -0.5
                or item["x"] + item["width"] > width + 0.5 or item["y"] + item["height"] > height + 0.5):
            fail("visible control is outside the client")

    def contains(parent, child):
        if child["visible"] and (child["x"] < parent["x"] - 0.5 or child["y"] < parent["y"] - 0.5
                or child["x"] + child["width"] > parent["x"] + parent["width"] + 0.5
                or child["y"] + child["height"] > parent["y"] + parent["height"] + 0.5):
            fail("control leaves its assigned region")

    def disjoint(values):
        values = [item for item in values if item["visible"]]
        for index, first in enumerate(values):
            for last in values[index + 1:]:
                if (min(first["x"] + first["width"], last["x"] + last["width"]) - max(first["x"], last["x"]) > 0.5
                        and min(first["y"] + first["height"], last["y"] + last["height"]) - max(first["y"], last["y"]) > 0.5):
                    fail("sibling controls overlap")

    def text_metrics(item):
        if not item["visible"]:
            return
        text = item.get("text")
        metrics = ("text_natural_width", "text_natural_height", "text_content_width", "text_content_height")
        if text is None:
            if any(item.get(key) is not None for key in (*metrics, "text_fits_width", "text_fits_height")):
                fail("non-text control has inconsistent text measurements")
            return
        if not isinstance(text, str) or not text:
            fail("invalid text measurement")
        natural_width, natural_height, content_width, content_height = (number(item.get(key)) for key in metrics)
        if (natural_width < 0 or natural_height <= 0 or content_width <= 0 or content_height <= 0
                or content_width > item["width"] + 0.5 or content_height > item["height"] + 0.5):
            fail("invalid text content-host bounds")
        fits_width, fits_height = natural_width <= content_width + 0.5, natural_height <= content_height + 0.5
        if item.get("text_fits_width") is not fits_width or item.get("text_fits_height") is not fits_height or not fits_height:
            fail("text-fit flags disagree with actual measurements or text is clipped vertically")
        if not fits_width and (item["name"] not in {"ProjectName", "ProjectInfo", "SelectionName", "SourceOffsetText"}
                or item.get("text_trimming") != "CharacterEllipsis" or item.get("tooltip") != text):
            fail("clipped text lacks an exact full-text tooltip and ellipsis")

    band_names = {"menu": "MenuBand", "toolbar": "ToolbarBand", "status": "ProjectStatusBand", "event": "EventInfoBand"}
    band_records = records("bands", band_names.values())
    bands = {key: band_records[name] for key, name in band_names.items()}
    y = 0
    for name, band_height in (("menu", 25), ("toolbar", 30), ("status", 18), ("event", 34)):
        band = bands[name]
        rectangle(band)
        if (not band["visible"] or any(abs(band[key] - value) > 0.5
                for key, value in (("x", 0), ("y", y), ("width", width), ("height", band_height)))):
            fail("bands do not form the measured 107-DIP stack")
        y += band_height
    toolbar = records("toolbar_controls", ("ExampleButton", "OpenProjectButton", "SaveProjectButton", "UndoButton", "RedoButton",
        "SplitToolbarButton", "DeleteToolbarButton", "SnapBox", "Zoom", "RulerModeBox", "RowDensityBox", "LeftZoneToggle", "MixerZoneToggle", "ExportButton"))
    cells = records("event_cells", ("EventNameCell", "EventStartCell", "EventEndCell", "EventOffsetCell"))
    controls = records("event_controls", ("SelectionName", "SelectionKind", "MoveBox", "MoveButton", "TrimBox", "TrimButton",
        "SourceOffsetText", "EventStartLabel", "EventEndLabel", "EventOffsetLabel"))
    status = records("status_controls", ("ProjectName", "ProjectInfo", "ProjectLimit"))
    for group, parent in ((toolbar, bands["toolbar"]), (cells, bands["event"]), (controls, bands["event"]), (status, bands["status"])):
        for item in group.values():
            rectangle(item)
            if not item["visible"] and item["name"] != "ProjectLimit":
                fail("required control is hidden")
            contains(parent, item)
            text_metrics(item)
        disjoint(group.values())
    for name, control in toolbar.items():
        if name == "Zoom" and (control["height"] < 12 or control["width"] < 20):
            fail("timeline zoom target became too small")
        if name != "Zoom" and (control["height"] < 24.5 or control["width"] < 24.5):
            fail("toolbar target became too small")
    for name in ("MoveBox", "MoveButton", "TrimBox", "TrimButton"):
        if controls[name]["height"] < 19.5 or controls[name]["width"] < 19.5:
            fail("event timing target became too small")
    mapping = {"EventNameCell": ("SelectionName", "SelectionKind"), "EventStartCell": ("MoveBox", "MoveButton", "EventStartLabel"),
               "EventEndCell": ("TrimBox", "TrimButton", "EventEndLabel"), "EventOffsetCell": ("SourceOffsetText", "EventOffsetLabel")}
    for cell, children in mapping.items():
        for child in children:
            contains(cells[cell], controls[child])
    return {"bands": bands, "toolbar": toolbar, "cells": cells, "controls": controls, "status": status}


def require_top_rows(smoke, evidence, example_manifest_sha256, expected_source):
    """Require native top-row state, layout, resize and capture evidence."""
    def fail(message):
        raise RuntimeError("Top-row receipt: " + message)

    def sha(value):
        if not isinstance(value, str) or len(value) != 64 or set(value) - set("0123456789abcdef"):
            fail("invalid SHA-256")
        return value

    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            fail("invalid finite geometry")
        return value

    receipt = smoke.get("top_rows")
    checks = smoke.get("checks")
    if (not isinstance(receipt, dict) or not isinstance(checks, list) or any(not isinstance(item, str) for item in checks)
            or len(checks) != len(set(checks)) or not TOP_ROWS_CHECKS.issubset(checks)
            or receipt.get("input_evidence") != "UIA and injected routed keyboard events; no physical input"):
        fail("missing native checks or evidence boundary")
    bounds = smoke.get("window_bounds", {})
    require_top_rows_geometry(receipt.get("layout"), bounds)
    workspace = smoke.get("workspace", {})
    if not isinstance(workspace, dict):
        fail("missing workspace receipt")
    states = workspace.get("states", [])
    if not isinstance(states, list) or len(states) != 8 or any(not isinstance(item, dict) for item in states):
        fail("missing workspace states")
    for state in states:
        require_timeline_dividers(state)
    compact = next((state for state in states if state.get("name") == "compact"), {})
    timeline, mixer = compact.get("timeline", {}), compact.get("mixer", {})
    if (abs(number(timeline.get("y")) - 107) > 0.5 or abs(number(mixer.get("height")) - 216) > 0.5
            or abs(number(timeline.get("height")) - (number(bounds.get("client_height")) - 107 - 58 - 216 - 5)) > 0.5):
        fail("saved top-row height did not reach the arrangement")
    require_pinned_ruler_corner(smoke)

    measured = receipt.get("states", [])
    names = {"startup-empty", "ordinary-zero", "retained-source", "empty-track"}
    if (not isinstance(measured, list) or len(measured) != 4 or any(not isinstance(item, dict) for item in measured)
            or {item.get("name") for item in measured} != names):
        fail("missing or duplicate timing states")
    for state in measured:
        if (sha(state.get("before_sha256")) != sha(state.get("after_sha256"))
                or type(state.get("revision")) is not int or state["revision"] < 0):
            fail("timing inspection changed the session")
        layout = require_top_rows_geometry(state.get("layout"), bounds)
        markers = state.get("markers", {})
        if not isinstance(markers, dict):
            fail("missing timing markers")
        name = state["name"]
        context = "ordinary" if name == "ordinary-zero" else "source" if name == "retained-source" else "empty"
        kind = {"ordinary": "Selected event", "source": "Retained source event", "empty": "Event information"}[context]
        if (markers.get("context") != context or markers.get("kind") != kind
                or markers.get("editing_enabled") is not (context == "ordinary")
                or markers.get("project_limitation_visible") is not (name in {"retained-source", "empty-track"})
                or layout["status"]["ProjectLimit"]["visible"] != markers["project_limitation_visible"]):
            fail("timing context or project limitation is misleading")
        if markers["project_limitation_visible"] and layout["status"]["ProjectLimit"].get("text") != "Project playback unavailable":
            fail("visible source-project limitation has misleading text")
        for key, control in (("name", "SelectionName"), ("kind", "SelectionKind"), ("start", "MoveBox"), ("end", "TrimBox"), ("offset", "SourceOffsetText")):
            if not isinstance(markers.get(key), str) or markers[key] != layout["controls"][control].get("text"):
                fail("timing markers differ from rendered controls")
        if context == "ordinary":
            if (markers["start"] != "0" or markers["end"] != "5" or markers["offset"] != "0.000 s"
                    or state.get("selected_clip_id") != compact.get("selected_clip_id")
                    or state.get("selected_track_id") != compact.get("selected_track_id")):
                fail("ordinary authored zero-time event was not exercised")
        else:
            if any(markers[key] != "—" for key in ("start", "end", "offset")):
                fail("unavailable timing is displayed as an ordinary value")
            if context == "empty" and (markers["name"] != "No event selected" or state.get("selected_clip_id") is not None):
                fail("empty state implies an event selection")
            if context == "source" and (not markers["name"] or markers["name"] == "No event selected"
                    or state.get("selected_clip_id") != expected_source["eventID"]):
                fail("retained-source identity is missing")

    long = receipt.get("long_names", {})
    if (not isinstance(long, dict) or long.get("original_manifest_sha256") != sha(example_manifest_sha256)
            or sha(long.get("derived_manifest_sha256")) == example_manifest_sha256):
        fail("long-name fixture is not bound to the bundled example")
    for name_key, text_key in (("project_name", "project_text"), ("event_name", "event_text")):
        name, text = long.get(name_key), long.get(text_key, {})
        if (not isinstance(name, str) or len(name) < 100 or not isinstance(text, dict)
                or text.get("text") != name or text.get("tooltip") != name or text.get("trimming") != "CharacterEllipsis"
                or number(text.get("natural_width")) <= number(text.get("width")) or text["width"] <= 0):
            fail("long names were not bounded with full tooltips")
    captures = receipt.get("captures", [])
    capture_names = {"native-top-rows-long-names-visual.png", "native-top-rows-wide-visual.png"}
    if (not isinstance(captures, list) or len(captures) != 2 or any(not isinstance(item, dict) for item in captures)
            or {item.get("screenshot") for item in captures} != capture_names):
        fail("missing or duplicate top-row captures")
    captures = {item["screenshot"]: item for item in captures}
    for capture in captures.values():
        path = evidence / capture["screenshot"]
        layout = require_top_rows_geometry(capture.get("layout"), capture.get("window_bounds"))
        require_window_visual(path, capture.get("window_bounds"))
        if sha(capture.get("png_sha256")) != digest(path):
            fail("capture hash does not match its actual PNG")
        if (layout["status"]["ProjectName"].get("text") != long["project_name"]
                or layout["controls"]["SelectionName"].get("text") != long["event_name"]):
            fail("capture did not retain the authored long titles")
        if any(layout["controls"][key].get("text") != value for key, value in
               (("SelectionKind", "Selected event"), ("MoveBox", "0"), ("TrimBox", "5"), ("SourceOffsetText", "0.000 s"))):
            fail("long titles displaced ordinary event timing")
    first = captures["native-top-rows-long-names-visual.png"]
    last = captures["native-top-rows-wide-visual.png"]
    for name, group, control in (("project_text", "status_controls", "ProjectName"),
                                ("event_text", "event_controls", "SelectionName")):
        measured_text = next(item for item in first["layout"][group] if item["name"] == control)
        if any(abs(number(long[name].get(axis)) - number(measured_text.get(axis))) > 0.5 for axis in ("x", "y", "width", "height")):
            fail("long-name bounds differ from their captured controls")
        if abs(number(long[name].get("natural_width")) - number(measured_text.get("text_natural_width"))) > 0.5:
            fail("long-name text measurement differs from its captured control")
    resize = receipt.get("resize", {})
    if not isinstance(resize, dict) or sha(resize.get("before_sha256")) != sha(resize.get("after_sha256")):
        fail("resize changed the session")
    if (any(resize.get(key + "_before") != resize.get(key + "_after") for key in ("revision", "track", "clip"))
            or type(resize.get("revision_before")) is not int or resize["revision_before"] < 1
            or any(not isinstance(resize.get(key + "_before"), str) or not resize[key + "_before"] for key in ("track", "clip"))
            or resize.get("requested_outer_width") != 1400):
        fail("resize did not preserve revision and selection")
    before, after = (number(resize.get("outer_width_" + key)) for key in ("before", "after"))
    if (before <= 0 or after <= 0 or resize.get("wider_observed") is not (after > before + 0.5)
            or abs(before - number(first["window_bounds"].get("outer_width"))) > 0.5
            or abs(after - number(last["window_bounds"].get("outer_width"))) > 0.5
            or any(abs(number(first["window_bounds"].get(key)) - number(bounds.get(key))) > 0.5
                   for key in ("outer_width", "outer_height", "client_width", "client_height"))):
        fail("resize claim or restored bounds do not match actual captures")


def require_timeline_viewport(state, *, require_tracks_fit=True):
    """Check the actual content viewport, including legitimate tall timelines."""
    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise RuntimeError("Workspace viewport has missing or non-finite geometry")
        return value

    viewport, timeline = state.get("viewport", {}), state.get("timeline", {})
    for rectangle in (viewport, timeline):
        if not isinstance(rectangle, dict):
            raise RuntimeError("Workspace viewport rectangle is missing")
        for key in ("x", "y", "width", "height"):
            number(rectangle.get(key))
        if rectangle["width"] <= 0 or rectangle["height"] <= 0:
            raise RuntimeError("Workspace viewport rectangle is empty")
    if (viewport["x"] < timeline["x"] - 0.5 or viewport["y"] < timeline["y"] - 0.5
            or viewport["x"] + viewport["width"] > timeline["x"] + timeline["width"] + 0.5
            or viewport["y"] + viewport["height"] > timeline["y"] + timeline["height"] + 0.5
            or abs(viewport["width"] - number(state.get("viewport_width"))) > 0.5
            or abs(viewport["height"] - number(state.get("viewport_height"))) > 0.5):
        raise RuntimeError("Workspace viewport scalar and measured rectangle disagree")
    row_height = number(state.get("row_height"))
    headers = state.get("headers", [])
    tracks_bottom = number(state.get("tracks_bottom"))
    if (row_height not in (44, 68) or not isinstance(headers, list)
            or type(state.get("selected_density_index")) is not int
            or state["selected_density_index"] != (0 if row_height == 44 else 1)
            or abs(tracks_bottom - (26 + len(headers) * row_height)) > 0.5):
        raise RuntimeError("Workspace density does not match measured track extent")
    extent = number(state.get("extent_height"))
    scrolling = number(state.get("scrollable_height"))
    offset = number(state.get("vertical_offset"))
    expected_extent = max(viewport["height"], tracks_bottom)
    expected_scrolling = max(0, expected_extent - viewport["height"])
    if (abs(extent - expected_extent) > 0.5 or abs(scrolling - expected_scrolling) > 0.5
            or offset < 0 or offset > expected_scrolling + 0.5
            or (require_tracks_fit and (tracks_bottom > viewport["height"] or offset > 0.5))):
        raise RuntimeError("Workspace extent clips tracks or adds unnecessary vertical scrolling")
    return viewport


def require_source_selection_control(source, expected_source):
    """Bind the separate authored selection control to the unchanged fixture."""
    transition = source.get("auto_expand", {})
    derived = transition.get("derived_fixture", {})
    other_track = transition.get("other_track_id")
    if (transition.get("before_selection_id") != expected_source["eventID"]
            or transition.get("after_selection_id") != expected_source["eventID"]
            or "other_selection_id" not in transition or transition["other_selection_id"] is not None
            or not isinstance(other_track, str) or not other_track or other_track == expected_source["eventID"]
            or transition.get("source_sha256_before") != expected_source["sourceSHA256"]
            or transition.get("source_sha256_after") != expected_source["sourceSHA256"]
            or transition.get("canonical_source_restored") is not True):
        raise RuntimeError("Source auto-expansion did not exercise and restore a distinct selection")
    original, changed = derived.get("original_manifest_sha256"), derived.get("derived_manifest_sha256")
    if (derived.get("kind") != "authored scratch project with one empty selection-control track"
            or original != expected_source["manifestSHA256"] or not isinstance(changed, str)
            or len(changed) != 64 or set(changed) - set("0123456789abcdef") or changed == original
            or any(type(derived.get(key)) is not int or derived[key] != value for key, value in
                   (("original_track_count", 1), ("derived_track_count", 2), ("retained_event_count", 1)))):
        raise RuntimeError("Source selection control has an invalid authored derivative identity")
    sidecars = derived.get("sidecars", [])
    expected = {"Compatibility/CPR/Original.cpr": expected_source["sourceSHA256"],
                "Compatibility/CPR/ImportReport.json": expected_source["reportSHA256"]}
    if (not isinstance(sidecars, list) or len(sidecars) != len(expected)
            or {item.get("path") for item in sidecars} != set(expected)
            or any(item.get("original_sha256") != expected[item["path"]]
                   or item.get("copied_sha256") != expected[item["path"]] for item in sidecars)):
        raise RuntimeError("Source selection control changed preserved source or report bytes")


def require_workspace_layout(smoke, evidence, expected_source):
    """Require measured native geometry and session invariants, not only check labels."""
    receipt = smoke.get("workspace", {})
    bounds = smoke.get("window_bounds", {})

    def fail(message):
        raise RuntimeError("Workspace receipt: " + message)

    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            fail("non-finite geometry")
        return value

    def near(first, last):
        return abs(number(first) - number(last)) <= 0.5

    def sha(value):
        if not isinstance(value, str) or len(value) != 64 or set(value) - set("0123456789abcdef"):
            fail("invalid state SHA-256")
        return value

    def rectangle(value, *, visible=True):
        if not isinstance(value, dict):
            fail("missing measured rectangle")
        x, y, width, height = (number(value.get(key)) for key in ("x", "y", "width", "height"))
        if width < 0 or height < 0 or (visible and (width <= 0 or height <= 0)):
            fail("empty visible rectangle")
        if visible and (x < -0.5 or y < -0.5 or x + width > number(bounds.get("client_width")) + 0.5
                        or y + height > number(bounds.get("client_height")) + 0.5):
            fail("visible rectangle outside captured client")
        return value

    if not WORKSPACE_CHECKS.issubset(smoke.get("checks", [])):
        fail("missing native workspace checks")
    if receipt.get("input_evidence") != "UIA and injected routed keyboard events; no physical input":
        fail("input evidence boundary is missing")
    screenshots = receipt.get("screenshots", {})
    if screenshots != {"normal": "native-workspace-normal-visual.png", "expanded": "native-workspace-expanded-visual.png"}:
        fail("missing density and expanded workspace captures")
    for filename in screenshots.values():
        require_window_visual(evidence / filename, bounds)
    toolbar = receipt.get("toolbar_controls", [])
    if (not isinstance(toolbar, list) or len(toolbar) != 3
            or {control.get("name") for control in toolbar} != {"RowDensityBox", "LeftZoneToggle", "MixerZoneToggle"}):
        fail("workspace toolbar controls were not measured")
    for control in toolbar:
        rectangle(control)
        if control["height"] < 24 or control["width"] < 24:
            fail("workspace toolbar control has an unusable hit area")
    for first, second in zip(sorted(toolbar, key=lambda item: item["x"]), sorted(toolbar, key=lambda item: item["x"])[1:]):
        if first["x"] + first["width"] > second["x"] + 0.5:
            fail("workspace toolbar controls overlap")
    captures = receipt.get("capture_safety", [])
    if (not isinstance(captures, list) or len(captures) != 3
            or {entry.get("surface") for entry in captures} != {"inspector", "timeline", "mixer"}
            or any(entry.get(key) is not True for entry in captures
                   for key in ("capture_before", "capture_after", "layout_refused"))):
        fail("active inspector, timeline and mixer captures were not preserved")

    state_hash = sha(receipt.get("initial_state_sha256"))
    expected_names = {"compact", "normal", "left-hidden", "panes-hidden", "restored",
                      "splitter-minimum", "splitter-maximum", "splitter-restored"}
    records = receipt.get("states", [])
    if (not isinstance(records, list) or len(records) != len(expected_names)
            or any(not isinstance(item, dict) for item in records)
            or {item.get("name") for item in records} != expected_names):
        fail("missing or duplicated measured workspace states")
    states = {item["name"]: item for item in records}
    initial = states["compact"]
    if (type(initial.get("revision")) is not int or initial["revision"] < 1
            or any(not isinstance(initial.get(key), str) or not initial[key]
                   for key in ("selected_track_id", "selected_clip_id"))):
        fail("missing selected session identity")
    for state in records:
        if (sha(state.get("state_sha256")) != state_hash
                or any(state.get(key) != initial[key] for key in ("revision", "selected_track_id", "selected_clip_id"))
                or type(state.get("revision")) is not int):
            fail("layout changed project, history, transport or selection state")
        row_height = number(state.get("row_height"))
        if row_height not in (44, 68):
            fail("unsupported measured row density")
        viewport = require_timeline_viewport(state)
        if (type(state.get("left_visible")) is not bool or type(state.get("mixer_visible")) is not bool
                or not near(state.get("left_width"), 286 if state["left_visible"] else 0)
                or not near(state.get("horizontal_offset"), initial.get("horizontal_offset"))
                or number(state["horizontal_offset"]) < 0):
            fail("pane extent or timeline scroll changed unexpectedly")
        timeline = rectangle(state.get("timeline"))
        mixer = rectangle(state.get("mixer"), visible=state["mixer_visible"])
        if state["mixer_visible"]:
            if (not 195.5 <= mixer["height"] <= 376.5 or not near(mixer["x"], timeline["x"])
                    or not near(mixer["width"], timeline["width"])
                    or not near(mixer["y"], timeline["y"] + timeline["height"] + 5)):
                fail("mixer and arrangement geometry do not share a usable split")
        elif not near(mixer["height"], 0):
            fail("hidden mixer retained height")
        if number(timeline["height"]) < 219.5:
            fail("splitter collapsed the arrangement below its minimum")
        headers = state.get("headers", [])
        if not isinstance(headers, list) or len(headers) != 4:
            fail("four authored track rows were not measured")
        for index, header in enumerate(headers):
            rectangle(header)
            if (not near(header["width"], 198) or not near(header["height"], row_height)
                    or not near(header["x"], headers[0]["x"])
                    or not near(header["y"], headers[0]["y"] + index * row_height)
                    or header["x"] < viewport["x"] - 0.5 or header["x"] + header["width"] > viewport["x"] + viewport["width"] + 0.5
                    or header["y"] < viewport["y"] - 0.5 or header["y"] + header["height"] > viewport["y"] + viewport["height"] + 0.5):
                fail("track header dimensions do not follow row density")
        if not 24 <= headers[0]["y"] - viewport["y"] <= 29 or not -0.5 <= headers[0]["x"] - viewport["x"] <= 2:
            fail("track rows are detached from the visible timeline ruler")
    if initial["row_height"] != 44 or states["normal"]["row_height"] != 68:
        fail("compact default and normal density were not exercised")
    for name, state in states.items():
        if (state["left_visible"] != (name not in {"left-hidden", "panes-hidden"})
                or state["mixer_visible"] != (name != "panes-hidden")):
            fail("expected pane visibility transition was not observed")
    hidden, empty = states["left-hidden"], states["panes-hidden"]
    if (not near(hidden["timeline"]["width"] - initial["timeline"]["width"], initial["left_width"])
            or not near(initial["timeline"]["x"] - hidden["timeline"]["x"], initial["left_width"])
            or not near(empty["timeline"]["height"] - hidden["timeline"]["height"], hidden["mixer"]["height"] + 5)
            or not near(empty["timeline"]["width"], hidden["timeline"]["width"])):
        fail("hiding panes did not return their measured space to the timeline")
    for name in ("normal", "restored", "splitter-restored"):
        if any(not near(states[name][zone][key], initial[zone][key])
               for zone in ("timeline", "mixer") for key in ("x", "y", "width", "height")):
            fail("restored panes or density did not preserve workspace bounds")

    targets = receipt.get("event_targets", [])
    if (not isinstance(targets, list) or len(targets) != 2
            or {item.get("row_height") for item in targets} != {44, 68}):
        fail("both density hit targets were not measured")
    for item in targets:
        width, height, move, trim, trim_width = (number(item.get(key)) for key in
                                               ("event_width", "event_height", "move_x", "trim_x", "trim_width"))
        if (width < 16 or not near(height, 38 if item["row_height"] == 44 else 58)
                or not near(trim_width, 10) or not 0 <= move < width - trim_width < trim < width
                or item.get("move_hit") is not True or item.get("trim_hit") is not True):
            fail("event move and trim targets are not distinct native hit regions")
    if not near(targets[0]["event_width"], targets[1]["event_width"]):
        fail("row density changed event time geometry")

    split = receipt.get("splitter", {})
    minimum, maximum = number(split.get("minimum_height")), number(split.get("maximum_height"))
    total_height = initial["timeline"]["height"] + initial["mixer"]["height"] + 5
    if (not near(minimum, 196) or not near(maximum, max(196, min(376, total_height - 225)))
            or maximum - minimum < 10 or not near(split.get("minimum_actual"), minimum)
            or not near(split.get("maximum_actual"), maximum)
            or not near(states["splitter-minimum"]["mixer"]["height"], minimum)
            or not near(states["splitter-maximum"]["mixer"]["height"], maximum)
            or not near(split.get("arrangement_minimum_actual"), states["splitter-maximum"]["timeline"]["height"])
            or split.get("keyboard_focus_preserved") is not True):
        fail("splitter limits and keyboard focus were not exercised")
    faders = split.get("faders", [])
    if not isinstance(faders, list) or len(faders) != 2:
        fail("missing fader geometry at both splitter limits")
    for entry, height in zip(faders, (minimum, maximum)):
        fader_height = number(entry.get("fader_height"))
        value, tick, thumb = (number(entry.get(key)) for key in ("value", "tick_y", "thumb_y"))
        if (not near(entry.get("zone_height"), height) or not 60 <= fader_height <= 240
                or not -96 <= value <= 24 or not 0 <= tick <= fader_height
                or not 0 <= thumb <= fader_height or not near(tick, thumb)):
            fail("resized fader thumb and scale disagree")
    if number(faders[1]["fader_height"]) <= number(faders[0]["fader_height"]):
        fail("mixer fader height did not follow the splitter")
    source = receipt.get("source_only", {})
    if (sha(source.get("before_sha256")) != sha(source.get("after_sha256"))
            or source.get("ordinary_actions_disabled") is not True or source.get("source_expanded") is not True
            or source.get("auto_expand_input") != "Programmatic source-list SelectionChanged event through the shared session"):
        fail("source-only selection changed state or exposed ordinary event actions")
    require_source_selection_control(source, expected_source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = Path(__file__).resolve().parents[1]
    root = app.parent
    out = args.output.resolve()
    if out.exists():
        raise SystemExit("Use a new output directory")
    evidence = out / "evidence"
    evidence.mkdir(parents=True)
    stage = out / "package/Rebase"
    stage.mkdir(parents=True)
    env = dict(os.environ)
    env.update(REBASE_PORTABLE_ONLY="1", DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    env.pop("REBASE_RESEARCH_ROOT", None)
    resolved = app / "Package.resolved"
    original_resolved = resolved.read_bytes() if resolved.exists() else None
    report = {"schema": "rebase.windows-application-build.v1", "status": "failed",
              "commit": env.get("GITHUB_SHA"), "development_build": True, "signed": False,
              "playback_tested": False, "audible_output_measured": False, "commands": [],
              "toolchain": {"dotnet_sdk": SDK, "dotnet_runtime": DOTNET_RUNTIME, "swift": SWIFT},
              "runner_image": {key: os.environ.get(key) for key in ("ImageOS", "ImageVersion")}}
    replacements = []
    for path, label in ((root, "workspace"), (Path.home(), "home"), (out, "build-output")):
        for value in (str(path), str(path).replace("\\", "/"), str(path).replace("/", "\\")):
            replacements.append((value, "<" + label + ">"))

    def clean(value):
        if isinstance(value, str):
            for original, replacement in replacements:
                value = value.replace(original, replacement)
        elif isinstance(value, dict):
            value = {key: clean(item) for key, item in value.items()}
        elif isinstance(value, list):
            value = [clean(item) for item in value]
        return value

    def write(path, record):
        path.write_text(json.dumps(clean(record), indent=2) + "\n", encoding="utf-8")

    def run(command, name, custom_env=None, timeout=600, cwd=app):
        record = {"name": name, "argv": clean([str(item) for item in command])}
        report["commands"].append(record)
        started = time.monotonic()
        try:
            process = subprocess.run(command, cwd=cwd, env=custom_env or env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout)
            output, code = process.stdout, process.returncode
        except subprocess.TimeoutExpired as error:
            output, code = error.stdout or b"", None
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
        record.update(exit_code=code, elapsed_seconds=round(time.monotonic() - started, 3))
        (evidence / (name + ".log")).write_text(clean(output), encoding="utf-8")
        print(clean(output), end="", flush=True)
        if code != 0:
            raise RuntimeError(name + (" timed out" if code is None else " failed with exit " + str(code)))
        return output

    try:
        if os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("Packaging requires actual Windows x64")
        if run(["dotnet", "--version"], "dotnet-version", timeout=30).strip() != SDK:
            raise RuntimeError("Unexpected .NET SDK")
        if "Swift version " + SWIFT not in run(["swift", "--version"], "swift-version", timeout=30):
            raise RuntimeError("Unexpected Swift toolchain")
        run([sys.executable, str(app / "scripts/test_windows_native_audio_gate.py")], "native-receipt-controls")
        run([sys.executable, str(app / "scripts/test_windows_soxr_package.py"), "--output",
             str(evidence / "dependency-controls")], "dependency-package-controls")
        controls = run(["dotnet", "run", "--project", str(app / "Windows/RebaseWindows/Tests/RebaseWindows.Controls.csproj"),
                        "-c", "Release"], "host-controls")
        controls = json.loads(controls.strip().splitlines()[-1])
        if (controls.get("suite") != "windows-host-portable-controls" or controls.get("failures") != 0
                or type(controls.get("checks")) is not int or controls["checks"] <= 0):
            raise RuntimeError("Missing executed host controls")
        write(evidence / "host-controls.json", controls)
        run([sys.executable, str(app / "scripts/run-windows-native-audio-ci.py"), "--configuration", "Release",
             "--output", str(evidence / "native")], "native-audio-conformance")
        shutil.copyfile(evidence / "native/build/RebaseWindowsAudio.dll", stage / "RebaseWindowsAudio.dll")
        report["device_resampler"] = stage_soxr(app, evidence / "native/soxr", stage, env.get("GITHUB_SHA"))
        write(evidence / "device-resampler-package.json", report["device_resampler"])
        # Both explicit CPR mode 2 and the separate endpoint-rate adapter link
        # this same verified public library; their caller profiles stay distinct.
        env["REBASE_SOXR_LIBRARY_DIR"] = str(evidence / "native/soxr/install/lib")
        run(["dotnet", "publish", str(app / "Windows/RebaseWindows/RebaseWindows.csproj"), "-c", "Release",
             "-r", "win-x64", "--self-contained", "true", "-p:PublishTrimmed=false", "-p:PublishSingleFile=false",
             "-p:DebugType=None", "-p:DebugSymbols=false", "-p:ContinuousIntegrationBuild=true",
             "-p:PathMap=" + str(root) + "=/_/Rebase",
             "-p:RuntimeFrameworkVersion=" + DOTNET_RUNTIME, "-o", str(stage)], "publish-wpf")
        runtime_options = json.loads((stage / "Rebase.runtimeconfig.json").read_text(encoding="utf-8"))["runtimeOptions"]
        included = {item["name"]: item["version"] for item in runtime_options.get("includedFrameworks", [])}
        if (included.get("Microsoft.NETCore.App") != DOTNET_RUNTIME
                or included.get("Microsoft.WindowsDesktop.App") != DOTNET_RUNTIME):
            raise RuntimeError("Published desktop runtime is not the pinned self-contained version")
        scratch = out / "session-build"
        run(["swift", "build", "--scratch-path", str(scratch), "-c", "release", "--product", "rebase-session",
             "-Xswiftc", "-file-prefix-map", "-Xswiftc", str(root) + "=/_/Rebase",
             "-Xswiftc", "-debug-prefix-map", "-Xswiftc", str(root) + "=/_/Rebase",
             "-Xcc", "-ffile-prefix-map=" + str(root) + "=/_/Rebase"], "build-session")
        bin_path = Path(run(["swift", "build", "--scratch-path", str(scratch), "-c", "release", "--show-bin-path"],
                            "session-bin-path", timeout=60).strip().splitlines()[-1])
        shutil.copyfile(bin_path / "rebase-session.exe", stage / "rebase-session.exe")
        swiftc = Path(shutil.which("swiftc") or "missing").resolve()
        candidates = [parent / "Runtimes" / SWIFT / "usr/bin" for parent in swiftc.parents]
        candidates = [path for path in candidates if path.is_dir()]
        if len(candidates) != 1:
            raise RuntimeError("Cannot identify the pinned Swift runtime component")
        vc_root = Path(os.environ.get("VCToolsRedistDir", "missing"))
        vc_dirs = list((vc_root / "x64").glob("Microsoft.*.CRT"))
        if not vc_dirs:
            raise RuntimeError("Visual C++ x64 redistribution directory is unavailable")
        windows = Path(os.environ["SystemRoot"])
        closure = assemble_dependencies(stage, candidates[0], vc_dirs, windows / "System32")
        native_imports = next((row["imports"] for row in closure["images"]
                               if row["path"].lower() == "rebasewindowsaudio.dll"), [])
        if {"name": "soxr.dll", "source": "application"} not in native_imports:
            raise RuntimeError("Native device adapter does not import the packaged SoXR DLL")
        helper_imports = next((row["imports"] for row in closure["images"]
                               if row["path"].lower() == "rebase-session.exe"), [])
        if {"name": "soxr.dll", "source": "application"} not in helper_imports:
            raise RuntimeError("Shared CPR helper does not import the packaged SoXR DLL")
        write(evidence / "pe-dependency-closure.json", closure)
        example = copy_example(app, stage)
        licenses = stage / "ThirdPartyNotices"
        licenses.mkdir(exist_ok=True)
        license_sources = json.loads((app / "scripts/windows-runtime-license-sources.json").read_text(encoding="utf-8"))
        for source in license_sources:
            with urllib.request.urlopen(source["url"], timeout=60) as response:
                content = response.read(2_000_001)
            if hashlib.sha256(content).hexdigest() != source["sha256"]:
                raise RuntimeError("Pinned runtime notice changed: " + source["name"])
            (licenses / source["name"]).write_bytes(content)
        write(licenses / "sources.json", license_sources)
        (licenses / "Visual-Cpp-Runtime.txt").write_text(
            "The package includes Microsoft Visual C++ runtime DLLs from the x64 redistributable component.\n"
            "Microsoft runtime terms: https://visualstudio.microsoft.com/license-terms/\n", encoding="utf-8")
        (stage / "README.txt").write_text(
            "Rebase for Windows — unsigned development build\n\n"
            "Extract this entire folder before running Rebase.exe. Keep the DLLs and helper beside it.\n"
            "The authored example opens as a separate editable copy. Its audio permission is in Examples/README.md.\n"
            "This preview supports a bounded set of shared project editing and rendering workflows.\n"
            "Stereo Float32 playback adapts 8–192 kHz snapshots to the default endpoint using bundled SoXR.\n"
            "Source and converted snapshots are each limited to 32 million stereo frames.\n"
            "Source Audio exposes eight shared audition modes, including retained timeline and complete-track snapshots.\n"
            "Availability requires verified media, timing and saved-clock data; exports preserve full provenance.\n"
            "Recording, plugins, general project compatibility and streaming playback remain incomplete.\n"
            "CI window checks do not establish audio-device playback or complete application parity.\n"
            "Source and development notes: https://github.com/thatsmethen/rebase"
            "\n", encoding="utf-8")
        if any(stage.rglob("*.pdb")):
            raise RuntimeError("Development package must not include PDB/debug path records")
        # Exclude the installed Swift/.NET/VS search paths while testing these exact files.
        restricted = dict(env)
        for key in list(restricted):
            if key.upper().startswith(("SWIFT", "DOTNET_ROOT", "COREHOST", "COMPLUS_", "_NT_")):
                del restricted[key]
        restricted.update(PATH=os.pathsep.join((str(stage), str(windows / "System32"), str(windows))),
                          DOTNET_MULTILEVEL_LOOKUP="0")
        fixture = app / "Tests/Fixtures/SourceAudition"
        source_project = fixture / "AuthoredSource.rebaseproj"
        source_media = fixture / "SelectedSource.wav"
        source_lock = fixture / "expected.json"
        if (not source_project.is_dir() or not source_media.is_file() or not source_lock.is_file()
                or any(inside(path, stage) for path in (source_project, source_media, source_lock))):
            raise RuntimeError("The external authored source fixture is unavailable")
        expected_source = json.loads(source_lock.read_text(encoding="utf-8"))
        fixture_bytes = {path.relative_to(fixture).as_posix(): digest(path)
                         for path in fixture.rglob("*") if path.is_file()}
        modes_fixture = app / "Tests/Fixtures/SourceAuditionModes"
        if not (modes_fixture / "expected.json").is_file() or inside(modes_fixture, stage):
            raise RuntimeError("The external authored all-mode source fixture is unavailable")
        modes_fixture_bytes = {path.relative_to(modes_fixture).as_posix(): digest(path)
                               for path in modes_fixture.rglob("*") if path.is_file()}
        restricted["REBASE_SMOKE_SOURCE_MODES_FIXTURE"] = str(modes_fixture)
        run([sys.executable, str(app / "scripts/check-session-protocol.py"), "--helper", str(stage / "rebase-session.exe"),
             "--example", str(example), "--report", str(evidence / "packaged-session-protocol.json"),
             "--source-project", str(source_project), "--source-media", str(source_media), "--source-lock", str(source_lock)],
            "packaged-session-protocol", restricted, timeout=600, cwd=stage)
        session = json.loads((evidence / "packaged-session-protocol.json").read_text(encoding="utf-8"))
        if (session.get("status") != "passed" or session.get("source_journey_tested") is not True
                or session.get("waveform", {}).get("clips_checked") != 11
                or session.get("source", {}).get("playback_tested") is not False
                or session.get("ruler", {}).get("read_only") is not True
                or session.get("ruler", {}).get("stale_revision_rejected") is not True
                or session.get("ruler", {}).get("first_bar_seconds") != [0, 2.5, 5, 7.5]
                or session.get("ruler", {}).get("first_quarter_seconds") != [0, 0.625, 1.25, 1.875, 2.5]
                or any(session.get("source", {}).get(key) != expected_source[key]
                       for key in ("sourceSHA256", "mediaSHA256", "outputSHA256", "pcmSHA256", "frames", "sampleRate", "channels"))):
            raise RuntimeError("Packaged session protocol did not pass")
        imported = session.get("cpr_import", {})
        required_import_controls = (
            "tested", "review_read_only", "review_bounded", "cancellation_preserves_state",
            "superseded_review_rejected", "stale_revision_rejected", "changed_source_rejected",
            "explicit_partial_required", "dirty_replacement_guarded", "existing_destination_preserved",
            "import_published", "exact_source_and_report_preserved", "save_reopen_preserves_baseline",
            "historical_read_only", "tampered_report_rejected", "tampered_source_rejected")
        if (any(imported.get(key) is not True for key in required_import_controls)
                or imported.get("sourceSHA256") != expected_source["sourceSHA256"]
                or imported.get("reportSHA256") != expected_source["reportSHA256"]):
            raise RuntimeError("Packaged CPR import protocol checks did not pass")
        require_automation_protocol(session, json.loads((example / "Project.json").read_text(encoding="utf-8")),
                                    json.loads((app / "scripts/example-render-lock.json").read_text(encoding="utf-8")))
        modes_result_path = evidence / "packaged-cpr-audition-modes.json"
        run([sys.executable, str(app / "scripts/check-cpr-audition-modes.py"),
             "--helper", str(stage / "rebase-session.exe"), "--fixtures", str(modes_fixture),
             "--report", str(modes_result_path)], "packaged-cpr-audition-modes", restricted, timeout=600, cwd=stage)
        modes_lock = modes_fixture / "expected.json"
        report["cpr_audition_control"] = require_cpr_audition(
            json.loads(modes_result_path.read_text(encoding="utf-8")), json.loads(modes_lock.read_text(encoding="utf-8")),
            digest(modes_lock), digest(stage / "rebase-session.exe"))
        report["cpr_audition_control"]["receipt_sha256"] = digest(modes_result_path)
        smoke_path = evidence / "wpf-smoke.json"
        run([str(stage / "Rebase.exe"), "--smoke", "--smoke-json", str(smoke_path),
             "--smoke-source-project", str(source_project), "--smoke-source-media", str(source_media)],
            "packaged-window-smoke", restricted, timeout=300, cwd=stage)
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        if (smoke.get("suite") != "windows-wpf-shared-session-smoke" or smoke.get("outcome") != "passed"
                or smoke.get("stage") != "completed" or smoke.get("playback_tested") is not False
                or smoke.get("audible_output_measured") is not False or not smoke.get("checks")):
            raise RuntimeError("Window smoke receipt is incomplete")
        required_checks = {"real-waveforms-visible", "four-track-rows-fit", "source-package-copy", "source-event-ui-selection",
                           "source-media-ui-attachment", "source-attachment-undo", "source-attachment-redo",
                           "source-export-ui-verified", "source-provenance-matches", "source-window-visual-artifact",
                           "snap-control-fits-toolbar", "timeline-horizontal-scroll-performed", "track-headers-stay-anchored",
                           "timeline-events-scroll", "timeline-scroll-visual-artifact", "inspector-volume-shared-edit",
                           "inspector-volume-undo", "inspector-volume-redo", "inspector-focus-restored",
                           "inspector-pan-shared-edit", "inspector-mute-shared-edit", "inspector-solo-shared-edit",
                           "source-selection-labels", "mixer-mute-shared-edit", "track-solo-shared-edit",
                           "mixer-volume-shared-edit-and-undo",
                           "musical-ruler-shared-96bpm", "musical-ruler-seconds-toggle",
                           "selection-synchronized-across-panes", "channel-strip-bottom-aligned", "channel-volume-shared-edit", "channel-volume-undo",
                           "channel-pan-shared-edit", "channel-mute-shared-edit", "fader-scale-matches-value",
                           "mixer-numeric-volume-commit", "mixer-numeric-volume-invalid-preserved", "mixer-numeric-volume-cancel",
                           "numeric-event-enter-and-undo", "numeric-event-cancel", "numeric-event-invalid-preserved",
                           "numeric-trim-enter-and-undo", "numeric-tempo-enter-and-undo", "numeric-seek-and-cancel",
                           "cpr-review-window-visible", "cpr-review-all-pages-accessible", "cpr-review-cancel-preserves-session",
                           "cpr-changed-source-rejected", "cpr-dirty-cancel-preserves-session",
                           "cpr-destination-cancel-preserves-review", "cpr-import-supported-data", "cpr-import-source-preserved",
                           "cpr-historical-report-readonly", "cpr-review-visual-artifact",
                           "cpr-review-footer-visible", "cpr-review-capture-alpha-coverage", "cpr-review-minimum-error-layout"}
        if (smoke.get("source_journey_tested") is not True or not required_checks.issubset(smoke["checks"])
                or smoke.get("source_screenshot") != "native-source-visual.png"
                or smoke.get("source_output_sha256") != expected_source["outputSHA256"]
                or smoke.get("source_sha256") != expected_source["sourceSHA256"]
                or smoke.get("media_sha256") != expected_source["mediaSHA256"]):
            raise RuntimeError("Source-event or waveform window checks are incomplete")
        alignment = smoke.get("channel_alignment", {})
        if (any(type(alignment.get(key)) not in (int, float) or not math.isfinite(alignment[key]) for key in ("selected_nameplate_bottom", "mixer_nameplate_bottom")) or
                abs(alignment["selected_nameplate_bottom"] - alignment["mixer_nameplate_bottom"]) > 6):
            raise RuntimeError("Selected Channel strip is not aligned with the lower console")
        scale = smoke.get("fader_scale", [])
        if (len(scale) != 6 or {(entry.get("selected_channel"), entry.get("value")) for entry in scale} !=
                {(side, value) for side in (False, True) for value in (-96, 0, 24)} or
                any(type(entry.get(key)) not in (int, float) or not math.isfinite(entry[key]) for entry in scale for key in ("tick_y", "thumb_y")) or
                any(abs(entry["tick_y"] - entry["thumb_y"]) > 0.5 for entry in scale)):
            raise RuntimeError("Fader scale does not match observed native thumb geometry")
        require_pinned_header_scroll(smoke)
        require_musical_ruler(smoke)
        require_workspace_layout(smoke, evidence, expected_source)
        require_top_rows(smoke, evidence, digest(example / "Project.json"), expected_source)
        require_automation_window(smoke, evidence, json.loads((example / "Project.json").read_text(encoding="utf-8")),
                                  json.loads((app / "scripts/example-render-lock.json").read_text(encoding="utf-8")))
        report["source_modes_window_control"] = require_cpr_audition_window(smoke, evidence,
            json.loads(modes_lock.read_text(encoding="utf-8")), json.loads(modes_result_path.read_text(encoding="utf-8")))
        modules = {"process": validate_modules(smoke.pop("process_modules", None), stage, windows,
                                               {"rebase.exe", "coreclr.dll", "rebasewindowsaudio.dll", "soxr.dll"}),
                   "helper": validate_modules(smoke.pop("helper_modules", None), stage, windows,
                                              {"rebase-session.exe", "swiftcore.dll", "soxr.dll"})}
        write(evidence / "loaded-modules.json", modules)
        write(smoke_path, smoke)
        bounds = smoke.get("window_bounds", {})
        require_window_visual(evidence / "native-app-visual.png", bounds)
        require_window_visual(evidence / "native-source-visual.png", bounds)
        require_window_visual(evidence / "native-timeline-scroll-visual.png", bounds)
        cpr_review = smoke.get("cpr_review", {})
        if (any(cpr_review.get(key) is not True for key in (
                "reviewed", "cancelled_without_changes", "changed_source_rejected", "dirty_guard",
                "destination_cancel_preserved_review", "imported", "historical_read_only", "vertical_scroll_checked"))
                or cpr_review.get("preserved_source_sha256") != expected_source["sourceSHA256"]
                or cpr_review.get("native_file_pickers_tested") is not False
                or cpr_review.get("physical_input_tested") is not False
                or cpr_review.get("native_frame_visual_tested") is not False
                or cpr_review.get("review_screenshot") != "native-cpr-review-visual.png"
                or type(cpr_review.get("pages_checked")) is not int or cpr_review["pages_checked"] < 1
                or type(cpr_review.get("items_checked")) is not int or cpr_review["items_checked"] < 1):
            raise RuntimeError("Reviewed CPR import window checks are incomplete")
        require_cpr_review_layout(evidence / "native-cpr-review-visual.png", cpr_review.get("window_bounds", {}),
                                  cpr_review.get("capture_layout", {}))
        if cpr_review.get("minimum_error_screenshot") != "native-cpr-review-minimum-error-visual.png":
            raise RuntimeError("Missing minimum-size CPR error capture")
        require_cpr_review_layout(evidence / "native-cpr-review-minimum-error-visual.png", cpr_review.get("minimum_error_bounds", {}),
                                  cpr_review.get("minimum_error_layout", {}), minimum_error=True)
        # Recheck all bundled source bytes after both complete user journeys.
        example_manifest = json.loads((stage / "Examples/example.json").read_text(encoding="utf-8"))
        if any(digest(example / item["path"]) != item["sha256"] for item in example_manifest["files"]):
            raise RuntimeError("A package check changed the bundled example")
        if fixture_bytes != {path.relative_to(fixture).as_posix(): digest(path)
                             for path in fixture.rglob("*") if path.is_file()}:
            raise RuntimeError("A package check changed the authored source fixture")
        if modes_fixture_bytes != {path.relative_to(modes_fixture).as_posix(): digest(path)
                                   for path in modes_fixture.rglob("*") if path.is_file()}:
            raise RuntimeError("A package check changed the authored all-mode source fixture")
        # Keep this mandatory gate after window diagnostics, before any downloadable ZIP.
        # An application smoke pass cannot turn a failed/empty Release suite into success.
        run([sys.executable, str(app / "scripts/run-portable-ci.py"), "swift", "--configuration", "Release",
             "--output", str(evidence / "shared"), "--soxr-build", str(evidence / "native/soxr")],
             "shared-release-conformance", timeout=900)
        files = [{"path": path.relative_to(stage).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)}
                 for path in sorted(stage.rglob("*")) if path.is_file()]
        fixture_payload_hashes = {expected_source[key] for key in
                                  ("sourceSHA256", "mediaSHA256", "manifestSHA256", "reportSHA256", "outputSHA256")}
        fixture_payload_hashes.update(modes_fixture_bytes.values())
        if any(item["sha256"] in fixture_payload_hashes for item in files):
            raise RuntimeError("A source-audition test payload was copied into the application package")
        if any(path.is_symlink() for path in stage.rglob("*")):
            raise RuntimeError("Package contains a symbolic link")
        write(stage / "package-manifest.json", {"schema": "rebase.windows-package.v1", "commit": env.get("GITHUB_SHA"),
                                               "toolchain": report["toolchain"], "files": files})
        download = out / "download"
        download.mkdir()
        revision = env.get("GITHUB_SHA", "local")[:12]
        archive = download / ("Rebase-Windows-x64-development-" + revision + ".zip")
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    bundle.write(path, "Rebase/" + path.relative_to(stage).as_posix())
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:
                raise RuntimeError("Archive CRC verification failed")
        report.update(status="passed", package={"name": archive.name, "bytes": archive.stat().st_size,
                                                "sha256": digest(archive)}, window_smoke_tested=True,
                      dialogs_tested=False, dependency_closure_checked=True, app_local_modules_observed=True)
        report.update(source_journey_tested=True, source_fixture_shipped=False, real_waveform_checks_passed=True)
        report["source_modes_fixture_shipped"] = False
        report["pinned_track_headers_scroll_checked"] = True
        report["musical_ruler_placement_checked"] = True
    except Exception as error:
        report["error"] = clean(str(error))
        print(report["error"], file=sys.stderr)
        # A partial/failed package must never be mistaken for the checked download.
        shutil.rmtree(out / "download", ignore_errors=True)
    finally:
        if original_resolved is not None:
            resolved.write_bytes(original_resolved)
        # Raw module receipts are checked above, then paths are removed from public evidence.
        smoke_path = evidence / "wpf-smoke.json"
        if smoke_path.exists():
            try:
                smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
                for key in ("process_modules", "helper_modules"):
                    if key in smoke:
                        smoke[key] = [{"name": item.get("name")} for item in smoke[key]]
                write(smoke_path, smoke)
            except Exception:
                smoke_path.unlink()
        write(evidence / "application-build.json", report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
