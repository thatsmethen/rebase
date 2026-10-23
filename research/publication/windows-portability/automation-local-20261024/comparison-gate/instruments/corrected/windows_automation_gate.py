"""Validate source-bound automation journey receipts before packaging Windows."""
import math
import re
import uuid


PROTOCOL_GATES = (
    "tested", "existing_volume_projected", "edits_revision_bound", "stale_rejected",
    "invalid_rejected", "other_automation_preserved", "read_off_preserves_points",
    "read_off_uses_manual_gain", "pan_edit_read_roundtrip", "undo_restores_project",
    "undo_restores_locked_render", "redo_restores_edits", "save_reopen_preserves_edits",
    "source_unchanged",
)


def require_automation_protocol(session, example, lock):
    """Bind reported operations to the unchanged authored project/render locks."""
    record = session.get("automation")
    if not isinstance(record, dict) or any(record.get(key) is not True for key in PROTOCOL_GATES):
        raise RuntimeError("Packaged automation commands did not complete every required control")
    if (record.get("evidence_class") != "authored-shared-session-control"
            or record.get("playback_tested") is not False
            or type(record.get("original_point_count")) is not int or record["original_point_count"] != 5
            or type(record.get("mutation_count")) is not int or record["mutation_count"] < 10
            or type(record.get("invalid_requests_checked")) is not int or record["invalid_requests_checked"] < 15):
        raise RuntimeError("Automation protocol receipt has incomplete counts or an unsupported evidence claim")
    tracks = example.get("tracks", [])
    if len(tracks) < 2:
        raise RuntimeError("Automation control example is missing its authored pad track")
    track = tracks[1]
    lanes = [lane for lane in track.get("automation", []) if lane.get("parameter") == "gainDB"]
    if (len(lanes) != 1 or track.get("name") != "Warm pad"
            or record.get("original_track_id") != track.get("id")
            or record.get("original_lane_id") != lanes[0].get("id")
            or len(lanes[0].get("points", [])) != record["original_point_count"]):
        raise RuntimeError("Automation receipt is not bound to the authored track and lane")
    for key in ("original_track_id", "original_lane_id"):
        try:
            if not isinstance(record[key], str):
                raise ValueError()
            uuid.UUID(record[key])
        except (ValueError, AttributeError):
            raise RuntimeError("Automation control identity is malformed") from None
    for key in ("restored_wav_sha256", "restored_pcm_sha256", "edited_wav_sha256", "edited_pcm_sha256"):
        if not isinstance(record.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", record[key]):
            raise RuntimeError("Automation render identity is missing or malformed")
    if (record["restored_wav_sha256"] != lock["wav_sha256"]
            or record["restored_pcm_sha256"] != lock["pcm_sha256"]
            or record["edited_wav_sha256"] == record["restored_wav_sha256"]
            or record["edited_pcm_sha256"] == record["restored_pcm_sha256"]):
        raise RuntimeError("Automation render did not change and then restore the locked original bytes")


WINDOW_GATES = (
    "tested", "editor_open_preserves_state", "volume_five_points_projected", "shared_edit",
    "invalid_preserved", "stale_preserved", "read_off_preserves_points", "undo_restores_project",
    "undo_restores_render", "pan_edit", "parameter_switch", "curve_point_added", "delete_undo_redo",
    "close_preserves_edits", "selection_preserved",
)
WINDOW_CHECKS = {
    "automation-editor-open-preserves-state", "automation-volume-five-points-projected",
    "automation-shared-edit", "automation-read-off-preserves-points", "automation-undo-restores-project",
    "automation-undo-restores-render", "automation-invalid-preserved", "automation-stale-preserved",
    "automation-pan-edit", "automation-parameter-switch", "automation-curve-point-added",
    "automation-delete-undo-redo", "automation-close-preserves-edits", "automation-selection-preserved",
    "automation-minimum-layout-captured",
}
CAPTURE_NAMES = {
    "native-automation-read-off-visual.png", "native-automation-invalid-visual.png",
    "native-automation-minimum-visual.png",
}


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise RuntimeError("Automation geometry is missing or non-finite")
    return value


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _box(value, width, height):
    if not isinstance(value, dict):
        raise RuntimeError("Automation control geometry is missing")
    x, y, w, h = (_number(value.get(key)) for key in ("x", "y", "width", "height"))
    if x < -0.5 or y < -0.5 or w <= 0 or h <= 0 or x + w > width + 0.5 or y + h > height + 0.5:
        raise RuntimeError("Automation control lies outside the captured client")
    return x, y, w, h


def require_automation_window(smoke, evidence, example, lock):
    import hashlib
    import struct

    record = smoke.get("automation")
    if (not isinstance(record, dict) or any(record.get(key) is not True for key in WINDOW_GATES)
            or not WINDOW_CHECKS.issubset(smoke.get("checks", []))
            or any(record.get(key) is not False for key in
                   ("playback_invalidation_tested", "physical_input_tested", "native_frame_visual_tested"))):
        raise RuntimeError("Native automation journey did not complete its scoped controls")
    if (record.get("original_render_sha256") != lock["wav_sha256"]
            or record.get("restored_render_sha256") != lock["wav_sha256"]
            or not _hash(record.get("edited_render_sha256"))
            or record["edited_render_sha256"] == lock["wav_sha256"]):
        raise RuntimeError("Native automation did not change then restore the locked example WAV")
    phase_names = ("original", "opening", "after_edit", "read_off", "after_undo_restored", "pan", "curve", "after_close")
    rows = record.get("phases")
    if not isinstance(rows, list) or len(rows) != len(phase_names) or [p.get("name") for p in rows] != list(phase_names):
        raise RuntimeError("Native automation phase record is incomplete")
    phases = dict(zip(phase_names, rows))
    for p in rows:
        if (any(not _hash(p.get(key)) for key in ("project_sha256", "volume_sha256", "pan_sha256"))
                or type(p.get("revision")) is not int or p["revision"] <= 0
                or p.get("track_id") != example["tracks"][1]["id"]
                or p.get("clip_id") != rows[0].get("clip_id")):
            raise RuntimeError("Automation phases lost source identity, selection or revision")
    if rows[0]["revision"] != rows[1]["revision"] or any(rows[i]["revision"] <= rows[i - 1]["revision"] for i in range(2, len(rows))):
        raise RuntimeError("Automation phase revisions do not match the exercised edit sequence")
    for key in ("project_sha256", "volume_sha256", "pan_sha256"):
        if not phases["original"][key] == phases["opening"][key] == phases["after_undo_restored"][key]:
            raise RuntimeError("Opening or undoing automation changed the original project")
        if phases["curve"][key] != phases["after_close"][key]:
            raise RuntimeError("Closing automation failed to retain the final edits")
    if (phases["original"]["project_sha256"] == phases["after_edit"]["project_sha256"]
            or phases["original"]["pan_sha256"] == phases["pan"]["pan_sha256"]
            or phases["pan"]["pan_sha256"] == phases["curve"]["pan_sha256"]):
        raise RuntimeError("Native automation edits did not produce distinct parameter states")
    if any(phases[name]["pan_sha256"] != phases["original"]["pan_sha256"] for name in ("after_edit", "read_off")):
        raise RuntimeError("Volume edits changed the pan lane")
    if any(phases[name]["volume_sha256"] != phases["original"]["volume_sha256"] for name in ("pan", "curve", "after_close")):
        raise RuntimeError("Pan edits changed the restored volume lane")
    captures = record.get("captures")
    if (not isinstance(captures, list) or len(captures) != 3
            or {c.get("file") for c in captures} != CAPTURE_NAMES):
        raise RuntimeError("Automation capture set is incomplete")
    controls_expected = {"parameter", "read", "curve", "points", "time", "value", "interpolation",
                         "add", "update", "delete", "reset", "undo", "redo", "close"}
    for capture in captures:
        name = capture["file"]
        data = (evidence / name).read_bytes()
        if (data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 33
                or hashlib.sha256(data).hexdigest() != capture.get("sha256")
                or capture.get("frame_excluded") is not True):
            raise RuntimeError("Automation image differs from its original capture receipt")
        bounds = capture.get("bounds", {})
        width, height, dx, dy, outer_width, outer_height = (_number(bounds.get(key)) for key in
            ("width_dip", "height_dip", "dpi_scale_x", "dpi_scale_y", "outer_width_dip", "outer_height_dip"))
        pixels = struct.unpack(">II", data[16:24])
        if (width <= 0 or height <= 0 or dx <= 0 or dy <= 0
                or outer_width > 680.5 or outer_height > 560.5
                or width > outer_width or height > outer_height
                or pixels != (bounds.get("pixel_width"), bounds.get("pixel_height"))
                or pixels != (math.ceil(width * dx), math.ceil(height * dy))):
            raise RuntimeError("Automation image was not measured at its minimum window geometry")
        controls = capture.get("controls")
        if (not isinstance(controls, list) or len(controls) != len(controls_expected)
                or {c.get("name") for c in controls} != controls_expected):
            raise RuntimeError("Automation editor control geometry is incomplete")
        boxes = {c["name"]: _box(c, width, height) for c in controls}
        if boxes["points"][3] < 140:
            raise RuntimeError("Automation point list has no usable minimum viewport")
        plot = _box(capture.get("curve_plot"), boxes["curve"][2], boxes["curve"][3])
        x, y, w, h = plot
        if w < 300 or h < 80:
            raise RuntimeError("Automation curve has no usable minimum viewport")
        duration = _number(capture.get("curve_duration"))
        points = capture.get("points")
        if (capture.get("parameter") != "gainDB" or capture.get("point_count") != 5
                or not isinstance(points, list) or len(points) != 5 or duration != 20):
            raise RuntimeError("Automation capture does not show the authored five-point volume lane")
        previous = -1
        identities = set()
        for point in points:
            time, value = _number(point.get("time")), _number(point.get("value"))
            try:
                identity = uuid.UUID(point["id"])
            except (ValueError, TypeError, KeyError, AttributeError):
                raise RuntimeError("Automation captured point identity is malformed") from None
            if (identity in identities or time <= previous or not 0 <= time <= duration
                    or not -96 <= value <= 24 or point.get("interpolation") not in ("linear", "step")):
                raise RuntimeError("Automation captured points are invalid or truncated")
            identities.add(identity); previous = time
        authored = next(lane for lane in example["tracks"][1]["automation"] if lane["parameter"] == "gainDB")["points"]
        for index, (point, original) in enumerate(zip(points, authored)):
            expected_point = dict(original)
            if name == "native-automation-read-off-visual.png" and index == 1:
                expected_point.update(value=-4, interpolation="step")
            if point != expected_point:
                raise RuntimeError("Captured automation points differ from the exercised authored edits")
        def position(time, value): return (x + time / duration * w, y + h - (value + 96) / 120 * h)
        expected = [position(0, points[0]["value"])]
        for index, point in enumerate(points):
            if index and points[index - 1]["interpolation"] == "step":
                expected.append(position(point["time"], points[index - 1]["value"]))
            expected.append(position(point["time"], point["value"]))
        expected.append(position(duration, points[-1]["value"]))
        vertices = capture.get("curve_vertices")
        if not isinstance(vertices, list) or len(vertices) != len(expected):
            raise RuntimeError("Automation visual curve omits its endpoints or outgoing Hold transition")
        for vertex, target in zip(vertices, expected):
            if abs(_number(vertex.get("x")) - target[0]) > 0.5 or abs(_number(vertex.get("y")) - target[1]) > 0.5:
                raise RuntimeError("Automation curve does not project the recorded points")
        if capture.get("read_enabled") is not (name != "native-automation-read-off-visual.png"):
            raise RuntimeError("Automation capture has the wrong Read state")
        if name == "native-automation-invalid-visual.png" and "finite" not in str(capture.get("message", "")):
            raise RuntimeError("Automation invalid-input capture has no visible validation feedback")
