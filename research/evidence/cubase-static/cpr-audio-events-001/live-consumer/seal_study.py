"""Seal authored interpretation and custody; no target or test execution."""
from pathlib import Path
import datetime, hashlib, json, shutil, subprocess, sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(path):
    path = Path(path)
    return dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size,
                sha256=digest(path))


for filename in ["bind_source.py", "verify_evidence.py"]:
    subprocess.run([sys.executable, str(HERE / filename)], check=True, capture_output=True)
verification = json.loads((HERE / "verification.json").read_text())
imported = json.loads((HERE / "evidence-import.json").read_text())
assert not imported.get("isError", False)
assert imported["structuredContent"]["result"] == dict(imported=54, unknowns_added=0, total=54)
assert "CLOSED: evidence import session" in (HERE / "import-run.log").read_text()
check = json.loads((HERE / "candidate-ring-check.json").read_text())
assert check["status"] == "passed" and check["operation_count"] == 1200
assert check["target_execution_count"] == 0

candidate = HERE / "candidate"
candidate.mkdir(exist_ok=True)
source_paths = [
    ROOT / "Application/Sources/RebaseTimingDSP/cpr_live_stereo_ring.c",
    ROOT / "Application/Sources/RebaseTimingDSP/include/cpr_live_stereo_ring.h",
    ROOT / "Application/Tests/RebaseCoreTests/CPRLiveStereoRingTests.swift",
]
assert digest(source_paths[0]) == check["source_sha256"]
assert digest(source_paths[1]) == check["header_sha256"]
assert digest(HERE / "check_ring.py") == check["script_sha256"]
for path in source_paths:
    destination = candidate / path.name
    if destination.exists():
        assert destination.read_bytes() == path.read_bytes()
    else:
        shutil.copyfile(path, destination)

references = {
    name: reference(path) for name, path in [
        ("source_custody", HERE / "verification.json"),
        ("original_dispatch_and_imports", HERE / "original-bindings.json"),
        ("canonical_evidence", HERE / "evidence-bundle.json"),
        ("canonical_import", HERE / "evidence-import.json"),
        ("independent_FIFO_control", HERE / "candidate-ring-check.json"),
        ("independent_FIFO_generator", HERE / "check_ring.py"),
        ("prior_selector_study", HERE.parent / "timeline-playback/finding.json"),
        ("prior_renderer_selection", HERE.parent / "renderer-selection/finding.json"),
        ("IID_initializer", HERE / "selector-iid-constant.json"),
    ]
}
claims = [
    dict(id="LIVE1", classification="concrete native receiver and registration",
         claim="The captured stereo transfer belongs to VSTAudioStreamPlayer, with a callback registered on a VstOpTrack receiver.",
         addresses=["1003838f0", "104467eb0", "104468148", "104468198",
                    "1003841a0", "101df4ea4"],
         details=[
             "Factory 1003838f0 allocates 0x68 bytes and assigns the primary vptr plus writer interface at this+0x20 and callback interface at this+0x50. Original RTTI names VSTAudioStreamPlayer.",
             "Successful open allocates one 32-byte ring record per channel. Each owns 32768 four-byte samples, capacity at ring+0x10, write index at +0x14 and read index at +0x18, initially zero.",
             "Open requires flag bit 1 and inactive state. Its direct-ready branch obtains a receiver through global105010970 virtual+0x508, then calls 101df4ea4 with this+0x50. That helper checks literal VstOpTrack and stores the callback at receiver+0x230.",
             "Callback slot0 is 1003849e8, which subtracts 0x50 and invokes 100384638. Writer interface slot0x18 is 100384ce4, which subtracts 0x20 and tails to 100384ac4.",
             "Format-property getters return 32 bits and kind2, consistent with the separately established Float32 descriptor. The transfer itself uses four-byte loads/stores. Sample rate is queried dynamically by 10038509c and is not assumed to be 44100.",
         ]),
    dict(id="LIVE2", classification="bounded native producer value operation",
         claim="Active, non-stopped stereo writes scatter interleaved frames into separate left/right rings without sample arithmetic.",
         addresses=["100384ac4", "100384b24..100384bb0", "100384c28..100384c90"],
         equation=[
             "C=32768. Available=(W-R+C)%C; empty W==R means available0. Free=C-Available.",
             "Before each frame, native requires Free>=trunc(Float32(C)*0.5)=16384.",
             "For each admitted frame: left[W]=input[2*i], right[W]=input[2*i+1], each as an exact 32-bit copy; W=(W+1)%C.",
             "A complete successful positive request increments submitted counter this+0x38 by the requested count.",
         ],
         details=[
             "The inclusive pre-frame threshold allows 16385 frames from empty: the final accepted frame begins with exactly16384 free slots.",
             "Native full-space handling polls/sleeps and can return after partial work or an asynchronous stop. Those behaviors are outside the candidate's atomic nonblocking request contract.",
             "Native entry stop returns INT32_MIN. An inactive player can return the requested count without enqueueing. Candidate write explicitly represents only the active/non-stopped branch.",
             "The mono producer multiplies by this+0x60; stereo does not. Mono and channel-count mismatch are excluded.",
         ]),
    dict(id="LIVE3", classification="bounded native consumer value operation",
         claim="The callback uses only end-start to request frames; it does not use the absolute start to seek.",
         addresses=["100384638", "100384650..1003846f8", "1003847b0..1003848c8",
                    "1003849bc..1003849e8", "103881008"],
         equation=[
             "N is the native signed32 interpretation of end-start; the admitted domain requires the difference to be representable and 0<=N<=32768.",
             "Stopped: zero all N output frames, advance timeline counter this+0x40 by N, leave read indices unchanged.",
             "Available>=N: copy N left/right words from matching ring read indices with wrap, advance R by N and timeline by N.",
             "Available<N and drain==0: zero the complete output block; leave R and timeline unchanged.",
             "Available<N and drain!=0: zero the block, overwrite the available prefix with queued stereo samples, advance R by Available and timeline by requested N.",
         ],
         details=[
             "Original Mach-O indirect symbols bind stub103881008 to _bzero. Zero-filled samples are positive-zero bits.",
             "For coherent stereo rings, both channels preserve their exact sample words and order. No gain, clipping or conversion occurs in these branches.",
             "Drain byte this+0x49 is set/cleared by 100383688 while waiting on submitted/timeline counters plus a separate latency query. That waiting policy and latency are not reconstructed.",
             "Alternate callback100384a64/primary+0x1f8 applies external postprocessing102fd9e40 after the transfer; it is excluded.",
         ]),
    dict(id="LIVE4", classification="original-image correction and remaining linkage",
         claim="The earlier AXt accessor argument5 is an open-flags argument; it does not itself establish Float32 format.",
         addresses=["10046e60c", "10036e458", "1004705b0", "10036eff0",
                    "1001ffef0..1001fff0c", "104feb498", "103927150"],
         details=[
             "Renderer-selection claimR7 described argument5 to10036e458 as format5. The captured constructor instead inspects argument>>1 and forwards the same argument to the source's open slot+0xf8. The earlier sealed artifact is preserved; this statement corrects that inference.",
             "The AXt-derived read thunk reaches10036eff0, but this does not tie its output to this VSTAudioStreamPlayer or to ordinary MAudioTrack playback.",
             "The unresolved selector IID now has exact initializer-bound bytes77b644ae362b4a198c9d3164152e968f at103927150 copied into104feb498. Additional concrete QI sites are retained, but no default timeline-to-player route is claimed.",
         ]),
]
finding = dict(
    schema_version=1, finding_id="CPR-LIVE-STEREO-RING-001",
    created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    status="sealed bounded static contract and independently tested reconstruction",
    source_sha256=verification["source_sha256"], target_execution=False,
    cubase_runtime_comparisons=0, claims=claims,
    admitted_domain=[
        "Successful initialized player state with exactly two source/output channels and coherent per-channel indices/capacities.",
        "Serial value operations with stable state and source buffers throughout each call; no concurrent native producer/consumer mutation.",
        "Fixed32768 capacity; counts0...32768; nonnegative counters and checked signed64 arithmetic; disjoint valid arrays/state/result.",
        "Candidate accepts arbitrary four-byte sample words because this stereo branch only transfers bits. Finite-audio admission remains the separate application preparation responsibility.",
    ],
    reconstruction=dict(
        api=["rb_cpr_live_ring_init", "rb_cpr_live_ring_reset",
             "rb_cpr_live_ring_write", "rb_cpr_live_ring_consume"],
        files=[reference(path) for path in source_paths],
        atomic_write="Whole request must satisfy frames<=Free-16384+1. Otherwise return WOULD_BLOCK with all state/storage untouched. This conservative admission replaces native blocking/retry.",
        reset="Indices and counters become zero; storage remains unchanged. Fresh-state application operation, not a proved native seek lifecycle.",
        errors="Input/range/alignment/overlap/counter checks precede writes. Failure preserves state/storage/output/result.",
        application_composition="Root integrates this normal stereo transfer after a separately selected rate/sample producer, splitting converted output into chunks<=8192. The AVAudioPlayerNode queue, four-buffer policy, reset/preroll and device path are explicit application choices."),
    controls=dict(
        optimized_C="Passed1200 independently modeled raw-word FIFO operations; 401 writes,399 whole-request rejections,290 normal reads,39 holding underruns,23 draining underruns,48 stopped reads and68 zero-length operations.",
        data="Every output word compared, including signed zero, subnormal, infinity and NaN bit patterns; no floating arithmetic is expected.",
        discriminators=["16385 accepted vs16386 rejected from empty", "multiple capacity wraps",
                        "absolute callback start independent of ring read position",
                        "hold vs drain vs stopped index/timeline behavior",
                        "distinct left/right patterns", "pre-write range/alias/overflow rejection"],
        Swift="Five focused test methods authored. Coordinated application suite result belongs to APP010 and is not asserted by this study.",
        independent_review="Peer source/integer review found no actionable candidate defect in the declared domain. That review did not independently verify the original native instruction evidence.",
        scope="Execution of authored reconstruction only; no proprietary code, hardware capture or runtime conformance comparison."),
    custody=verification["totals"],
    sessions=dict(raw_capture_clients=5, isolated_clients_closed=True,
                  imported_records=54, import_client_closed=True,
                  duplicate_capture="100384624 appears twice. Canonical bundle retains first record; verification proves only local_path differs and raw bytes are identical."),
    limitations=[
        "The actual upstream invocation of VstOpTrack+0x230, engine scheduling/threading and connection from MAudioTrack selector to this player remain unresolved.",
        "No native seek, exact device block size, asynchronous stop lifecycle, driver latency, real-time safety or default-engine route claim.",
        "No native blocking/retry/partial-write emulation, mono gain, mismatched channel counts or alternate postprocessing path.",
        "Raw Ghidra slices omit globals/imported code/RTTI/unwind. Original-image bindings are authority; C-like pseudocode is not bit-faithful compilable source.",
        "No complete DAW routing, plugins, PDC, automation or full-project playback fidelity claim.",
    ],
    prospective_disconfirming_cases=[
        "A verified upstream caller selects only alternate callback+8 or uses a different class/receiver; the plain callback composition would need revision.",
        "Divergent channel indices or live mutation during a request would invalidate the coherent serial value-operation domain.",
        "An exact corresponding runtime test disagrees at threshold, wrap, underflow or stop boundaries; runtime comparison remains prospective.",
    ],
    references=references)
(HERE / "finding.json").write_text(json.dumps(finding, indent=2) + "\n")
files = [path for path in HERE.rglob("*") if path.is_file()
         and path.name != "artifact-manifest.json" and "__pycache__" not in path.parts]
manifest = dict(schema_version=1, finding_sha256=digest(HERE / "finding.json"),
                files=[reference(path) for path in sorted(files)],
                external_references=list(references.values()))
(HERE / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
for item in manifest["files"]:
    path = ROOT / item["path"]
    assert path.stat().st_size == item["bytes"] and digest(path) == item["sha256"]
print(json.dumps(dict(finding_sha256=digest(HERE / "finding.json"),
                     manifest_sha256=digest(HERE / "artifact-manifest.json"),
                     files=len(files))))
