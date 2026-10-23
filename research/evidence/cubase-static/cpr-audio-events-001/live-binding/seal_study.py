"""Seal this bounded study exclusively; never execute proprietary code."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
def pin(path):
    return dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())
def put(path, value):
    with path.open("x") as f:
        f.write(json.dumps(value, indent=2) + "\n")

assert not (HERE / "artifact-manifest.json").exists()
verification = json.loads((HERE / "verification.json").read_text())
assert verification["passed"] and verification["totals"]["unique_evidence_records"] == 122
assert verification["totals"]["rea_dossiers"] == 61
imported = json.loads((HERE / "evidence-import.json").read_text())
assert imported["structuredContent"]["result"] == dict(imported=122, unknowns_added=0, total=122)
assert "CLOSED: evidence import session" in (HERE / "import-run.log").read_text()
for directory in HERE.glob("pass[0-9]*"):
    assert "CLOSED: isolated raw-slice MCP session" in (directory / "progress.log").read_text()
candidate = json.loads((HERE / "candidate-check.json").read_text())
assert candidate["status"] == "passed"
assert [candidate[k] for k in ["windows", "offsets", "planes", "prefixes"]] == [126, 45, 97, 48]
for key in ["source", "header", "oracle"]:
    assert pin(ROOT / candidate[key]["path"]) == candidate[key]

snapshots = []
for relative in [
    "Application/Sources/RebaseTimingDSP/native_callback_adapter.c",
    "Application/Sources/RebaseTimingDSP/include/native_callback_adapter.h",
    "Application/Tests/RebaseCoreTests/NativeCallbackAdapterTests.swift",
    "research/evidence/application/APP013/callback-adapter-oracle.py",
    "research/evidence/application/APP013/callback-adapter-oracle.json",
    "research/evidence/application/APP013/callback-instruction-verification.json",
    "research/evidence/application/APP013/verify-callback-instructions.py",
    "research/evidence/application/APP013/independent-kernels-final-02.log",
    "research/evidence/application/APP013/callback-independent-review.json",
]:
    source = ROOT / relative
    destination = HERE / "candidate" / source.name
    with destination.open("xb") as output:
        output.write(source.read_bytes())
    snapshots.append(dict(source=pin(source), snapshot=pin(destination)))

refs = {name: pin(HERE / filename) for name, filename in [
    ("original_bytes_and_readbacks", "verification.json"),
    ("dispatch_constants_imports", "original-bindings.json"),
    ("canonical_REA_records", "evidence-bundle.json"),
    ("canonical_import", "evidence-import.json"),
    ("optimized_candidate_controls", "candidate-check.json"),
    ("independent_review", "candidate/callback-independent-review.json"),
]}
claims = [
    dict(id="LIVEBIND-1", claim="The earlier registered callback is invoked by a concrete VstOpTrack Float32 adapter.",
         evidence=["pass1/native-101f2bbcc.txt", "pass1/native-101f2bf2c.txt",
                   "pass1/native-101f2c440.txt", "pass2/native-101f2cd84.txt",
                   "pass2/native-101f2d0dc.txt", "original-bindings.json"],
         details=[
             "Constructor101f2bbcc assigns vptr1047e7db8, callback+230 fromx3 and optional provider+238 fromx4. Primary slot80 reaches101f2bf2c, which invokes101f2c440 on its inspected branches.",
             "Engine configuration size4 selects adapter1047e7fb0; size8 selects1047e80c8. Float32 adapter+48 forwards callback slot0 with(receiver,start,end,signed16channels,planes). Alternate slot8 is not included in the Float32 candidate.",
             "Admission is callback!=null AND((transportResult&1)!=0 OR forcedField240!=0). A false callback result returns before every postprocessing step.",
             "The engine base constructor initializes format-size4; an actual hosted configuration is still dynamic. No universal runtime-default or whole-process identity claim."]),
    dict(id="LIVEBIND-2", claim="Callback window uses a fused biased offset conversion, with a separately rounded reciprocal offset setter.",
         evidence=["pass1/native-101f2c440.txt", "pass2/native-101ed1134.txt",
                   "pass2/native-101ed1184.txt", "pass4/native-101f17eb8.txt",
                   "pass4/native-101f17150.txt", "pass5/native-101ef386c.txt",
                   "pass5/native-101ef38c4.txt", "pass11/native-102fc7564.txt",
                   "pass12/native-102fc756c.txt", "pass12/native-102fc7494.txt"],
         equations=[
             "Positive engine rate r: reciprocal=RN64(1/r). offsetSeconds=RN64(Double(signed32OffsetFrames)*reciprocal).",
             "offsetFrames=FCVTZS_signed64(FMA64(offsetSeconds,r,0.5)); start=position+offsetFrames; end=start+signextend32(blockCount).",
             "Rate update: offsetSeconds=RN64(RN64(oldOffsetSeconds*Double(truncatedOldRate))*newReciprocal).",
             "Negative offsets use truncation toward zero after +0.5; this is not symmetric rounding."],
         details=[
             "IEngine/SequencerEngine slot98 returns engine+268; setter102fc756c stores r there and reciprocal at+270. Constructor initializes exact44100 and nearest1/44100.",
             "101ed1184 obtains position from the explicit engine override+8 when enabled, otherwise transport-provider slot18. 101ed1134 obtains the admission result from override-enabled1 or provider slot20.",
             "These are supplied-state value operations. Native provider lifecycle, latency compensation and AVAudioEngine block partition are not implemented by this helper."]),
    dict(id="LIVEBIND-3", claim="Float32 postprocessing is a first-channel terminal-sample predicate followed by an optional transport prefix.",
         evidence=["pass1/native-101f2c440.txt", "pass3/native-101f2cd44.txt",
                   "pass3/native-101f2cd68.txt", "pass3/native-101f2cc1c.txt",
                   "pass5/native-101f16534.txt", "pass5/native-1037dffcc.txt",
                   "pass3/native-101f2cc94.txt", "pass3/native-101f2ccb8.txt"],
         ordered_rules=[
             "Inspect raw bits of planes[0][N-1]. If exponent0 and magnitude!=0, apply Float32 +constant on even indices and -constant on odd indices in every channel; constant bits2edbe6ff. Each channel restarts at even0; an odd terminal sample receives addition.",
             "Otherwise if exponentallones, bzero every channel's firstN samples. This covers either-sign infinity and NaN, without general scanning.",
             "Otherwise preserve all sample bits. A nonfinite sample in another channel or another frame is not independently detected.",
             "Then, only if complete transportResult!=0, zero a capped positive prefix starting at buffer-wrapper signed frame offset+8. Whole-block predicate givesN; otherwise prefix=clamp(boundary-start,0,N).",
             "The prefix is applied AFTER correction/zeroing. It can start at a nonzero offset in a larger buffer."],
         details=[
             "The two CPU-selected correction bodies have the same inspected scalar/SIMD arithmetic rule. Native global CPU feature state does not change the recovered formula.",
             "This can depend on buffer boundaries and parity. Rebase's own partition is not asserted equal to Cubase's.",
             "Candidate arm64 IEEE nearest/FZ-off/DN-off domain is explicit. Correction cases containing other nonfinite samples are rejected rather than asserting NaN payload arithmetic."]),
    dict(id="LIVEBIND-4", claim="The previously identified source-event audition producer is connected to this callback stage.",
         evidence=["audition-callback-binding.json", "pass3/native-101980550.txt",
                   "pass8/native-1019807c8.txt", "pass10/native-10198069c.txt",
                   "original-bindings.json"],
         details=[
             "Prior immutable renderer-selection evidence binds AudioProcess::Audition::Manager10197f2b4, selected source stream, event volume and default StreamPlayer factory101955e44→10197fef4.",
             "The original constructor assigns primaryvptr1046b2f50 and callbackthis+38 vptr1046b32e0. Callbackslot0=1019807c8 adjusts receiver-38 and calls10198069c.",
             "101980550 obtains the receiver through105010970+508 and registers this+38 via101df4ea4, which checks VstOpTrack and stores+230 as proved in the prior live-consumer study.",
             "10198069c uses end-start and a separate ring, with stopped/not-ready silence and underflow/drain paths. This supports the role of the Float32 adapter after audition PCM; it does not equate the two player classes' entire lifecycles.",
             "Current app applies only the poststage after its previously derived stereo ring transfer, bufferOffset0/prefix0. Rebase scheduling, queue/refill and its chosen producer/backend remain explicit application composition."]),
]
next_work = dict(
    classification="Concrete next-work native consumer; not candidate implementation or general playback acceptance",
    connection=[
        "VSTAudioChannel constructor101d3b918 assigns primary1047ac688, callback+15e8 table1047ad0e0 and fill-provider+15f0 table1047ad100.",
        "Factory slot608→101d41b8c creates VstOpTrack with callbackowner+15e8 and optionalprovider0.",
        "Float32 callback101d40088→101d3fc3c reaches embeddedtimelinebuffer+1678→101d0d034→101d0d038 in its bounded non-varispeed branch.",
        "Constructor initializes buffer provider null, then explicitly assigns channel+15f0 at101d3bd00. Filling101d0cc58 calls that provider+8 with absolute position, count, channels and format/planar pointers.",
        "Provider+8=101d3f7d8 checks actualVstOpTrack and channel count then reaches101d3e704. That partitions a supplied interval using101d3ea38 and calls101d3eb24.",
        "101d3eb24 queries channel+1610 virtual+20/+18 for segments, uses source+38 and gainFloat32+68, calls segment timing getters+f8/+d8/+108, intersects frame windows, emits prefix silence, and constructs AudioAccessor10036e34c(flags0x25,policy1).",
        "It then sets accessor gain+160, seeks+178 and reads+168; a particular transient error can retry once at a segment boundary. These exact original ranges are retained."],
    unresolved=[
        "Bind assignment/actual interface of channel+1610. Syntactic store scan identifies setter101d3e5a0 as the next bounded anchor; no body/import was added after this study's capture cap.",
        "Bind actual segment type/getters and the global datum at1050105e0+388/+390, including narrowed reciprocal, before calling its local rounding a general placement contract.",
        "Resolve101d3ea38 mapping/loop partitions and ordinary channel varispeed branch before implementing nonzero, looped or multi-event playback.",
        "No current app promotion to ordinary track/project playback, event placement, routing, PDC, automations or hosted native state."])

finding = dict(schema_version=1, id="LIVEBIND-001",
               title="VstOpTrack callback windows and Float32 poststage, with source-event audition binding",
               created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               evidence_class="static original-image bytes plus REA; separately executed authored candidate",
               source_sha256=verification["source_sha256"], target_execution_count=0,
               target_runtime_comparison_count=0, full_fidelity_established=False,
               claims=claims, next_work=next_work, custody=verification["totals"],
               candidate=dict(
                   snapshots=snapshots,
                   domain="arm64 IEEE nearest, no FZ/DN/AH/FIZ; finite positive rate>=1; checked signed conversions/additions; 1...64 disjoint valid Float32 planes, positiveN and boundedprefix/capacity.",
                   deliberate_rejections=["Native conversion saturation/integer wrap", "Unestablished FP modes",
                                         "Aliased sample/descriptors/result storage",
                                         "Nonfinite arithmetic in alternating correction branch"],
                   controls=dict(windows=126, offset_conversions=45, plane_cases=97,
                                 prefix_cases=48, fma_discriminators=16,
                                 optimized_candidate="All316 independently generated oracle cases pass at-O3 with application strict FP flags.",
                                 Swift="Four peer tests pass; the retained coordinated10-test log also includes six independent mode1 tests.",
                                 scope="Own candidate/public application checks, never proprietary target execution or output comparison.")),
               sessions=dict(isolated_raw_clients=21, all_closed=True,
                             canonical_import_records=122, importer_closed=True),
               limitations=[
                   "Original instructions and exact bytes are authority. Raw Ghidra slices omit external code/data, imports, RTTI and unwind; C-like output is not compilable or bit-faithful original source.",
                   "Concrete constructed classes and interface roles do not prove which instance/configuration is active in an arbitrary running host.",
                   "VstOpTrack process contains additional optional-provider/transition processing outside this callback helper.",
                   "No device capture, native scheduling/block partition, general timeline reconstruction or full-project fidelity claim."],
               prospective_disconfirming_cases=[
                   "A runtime-configured size8 adapter or changed registered callback would select a different operation.",
                   "Changing block boundaries may change sentinel detection or alternating correction parity.",
                   "A nonzero native transport prefix/offset would differ from Rebase's explicitly supplied zero context.",
                   "Independent matching runtime output could contradict the bounded static interpretation; no such target run has occurred."],
               references=refs)
put(HERE / "finding.json", finding)
files = [p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts
         and p.name != "artifact-manifest.json"]
manifest = dict(schema_version=1, finding_sha256=pin(HERE / "finding.json")["sha256"],
                files=[pin(p) for p in sorted(files)],
                external_references=list(refs.values()) +
                json.loads((HERE / "original-bindings.json").read_text())["prior_immutable_evidence"])
put(HERE / "artifact-manifest.json", manifest)
assert all(pin(ROOT / item["path"]) == item for item in manifest["files"])
print(json.dumps(dict(finding=pin(HERE / "finding.json"),
                     manifest=pin(HERE / "artifact-manifest.json"), files=len(files))))
