"""Read-only scoped native-contract review record; does not execute either app."""
from pathlib import Path
import hashlib,json,shutil
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pin(name):
 p=ROOT/name
 return {'path':name,'sha256':sha(p),'bytes':p.stat().st_size}
log=Path('/tmp/rebase-cpr-tests-reviewed-final.txt')
assert sha(log)=='71a917a9d53b7a2240fa8c9063958052293fa47e7a5d6af67430d113b24b8e05'
shutil.copyfile(log,HERE/'cpr-tests-reviewed-final.log')
core='Application/Sources/RebaseCore/CPRProject.swift';tests='Application/Tests/RebaseCoreTests/CPRProjectTests.swift';shell='Application/Sources/Rebase/StudioSession.swift'
assert sha(ROOT/core)=='75b82b2d3e0afadff279284d6f2872685fb2a3146ead0d7a08709eefe089e940'
assert sha(ROOT/tests)=='a043bfe9d53fbcd3f0e95c1c26f34c676ed8a6ef62f584acca59b0cee3ed51cd'
for p in [core,tests,shell]:shutil.copyfile(ROOT/p,HERE/('final-'+Path(p).name))
r={
 'review_id':'APP003-CPR-NATIVE-REVIEW-001','created_utc':datetime.now(timezone.utc).isoformat(),
 'scope':'Independent read-only review of CPR decoder/tests and import/report/Save As integration against pinned native archive/tempo contracts and structurally decoded shipped fixtures. No app source modification by reviewer, no target execution, no new broad test run.',
 'status':'Three actionable findings corrected and final source reviewed; no remaining actionable defect found within this scoped review',
 'source_files':[pin(p)for p in [core,tests,shell,'Application/Sources/RebaseCore/ProjectStore.swift']],
 'evidence':[pin(p)for p in [
 'research/evidence/cubase-static/cpr-objects-001/native/finding.json',
 'research/evidence/cubase-static/cpr-objects-001/native/validation.json',
 'research/evidence/cubase-static/cpr-objects-001/native/function-1022137ec.json',
 'research/evidence/cubase-static/cpr-objects-001/native/function-10221eb28.json',
 'research/evidence/cubase-static/cpr-objects-001/audio-native/finding.json',
 'research/evidence/cubase-static/cpr-objects-001/fixtures/structural-contract-v2.json',
 'research/evidence/cubase-static/cpr-objects-001/fixtures/tempo-modes-v1.json',
 'research/evidence/cubase-static/cpr-objects-001/fixtures/classic-house-v08.json',
 'research/evidence/cubase-static/cpr-objects-001/fixtures/lofi-hip-hop-v08.json',
 'research/evidence/application/APP003/cpr-native-review-support/class-name-comparator-provenance.json']],
 'resolved_findings':[
  {'id':'R1','priority':'P2','location':'CPRProject.swift tempo() count guard, final line652','problem':'Zero serialized tempo records were accepted and could be followed directly by a valid fixed float and enabled u16, allowing a native-rejected tempo object to produce a recovery claim. Native0x10173bdac returns false when signed count<1.','resolution':'Guard now requires count>0 as well as byte/count bounds.','test':'zeroRecordTempoCannotBecomeRecoveredFixedTempo uses an exact self-authored zero-record payload, with a positive one-record control and no-destination assertion.'},
  {'id':'R2','priority':'P2','location':'CPRProject.swift className()/declaration(), final lines295/353','problem':'Class registry declarations reused BOM-aware user-string normalization. A leading EFBBBF could be removed from a class name, promoting otherwise distinct native registry bytes to a supported class. Native class helper0x10221eb28 returns raw bytes; registry0x1022137ec uses strcmp, independently bound to original stub0x103881bcc.','resolution':'Separate className reader requires unchanged bounded ASCII and exactly one terminal NUL; user-visible names retain their separate BOM-aware decoder. This is a deliberately strict ASCII subset, not a full native string policy.','test':'classRegistryKeysDoNotNormalizeUserStringBOMs has ordinary-class positive control, leading BOM, suffix/embedded NUL controls.'},
  {'id':'R3','priority':'P2','location':'CPRProject.swift importProject(), final lines157-179; compatibilityReport() bound','problem':'Import report writes had no matching8MiB read limit, so an input within source/object/string limits could publish a package later refused by the app loader.','resolution':'Both paths use maximumReportBytes; encoded report checked before staging creation; staging compatibilityReport validated before final move.','test':'oversizedReportCannotPublishAnUnopenableProject constructs100 distinct audio skeletons with49,000-byte names: source<5MB, report>8MiB. Import refuses with source unchanged, no destination and no staging leftovers.'}
 ],
 'open_findings':[],
 'reviewed_contracts':[
  {'area':'Class/object identity','assessment':'32-bit sign-bit class references use ARCH-relative class declaration offsets. Positive object references use registered payload-length-field offsets. Each -2 declaration records its own class/version. Missing class fallback is bounded to earlier explicit -1 declarations, intentionally excluding native state-dependent -2 fallback. No scan recovery.'},
  {'area':'Bounds and cycles','assessment':'Byte cursors enforce enclosing extents. Class/object counts and recursive depth are bounded. Unknown positive references throw. Active list identities and globally encountered track identities reject recursive/shared-track duplication. Concrete class versions are checked on interpreted paths; unknown event kinds/tails remain opaque and do not become playable clips.'},
  {'area':'Fixed tempo','assessment':'22-byte records and complete u16 boolean agree with original reader. Nonzero selects fixedf32 directly; map mode does not substitute inactive fixed value. Nonfinite/out-of-range fixed values reject. Map coordinates and ramps remain unsupported.'},
  {'area':'Metadata','assessment':'Metadata BPM/rate/signature remain descriptive facts. Imported name/rate/signature/mixer/timebase defaults are explicit. Metadata does not silently set timing maps.'},
  {'area':'Media','assessment':'Current path reads produce dependency diagnostics only; no filesystem resolution, implicit media extraction or playable clip is invented. Root-native evidence supports field framing; timeline/source units remain unbound.'},
  {'area':'Persistence and Save As','assessment':'Import writes exact source and baseline report toCompatibility/CPR, verifies bytes, reloads project and report before destination publication. compatibilityReport verifies source/hash/sections and recomputed interpretation, rejects symlink redirection. StudioSession Save As copies all original children exceptProject.json, therefore includesCompatibility; only edited Project.json/name changes. cprCompatibility remains a historical baseline, not a claim about later edits. This Save As assessment is static source review, not a GUI execution.'}
 ],
 'test_evidence':{'log':pin('research/evidence/application/APP003/cpr-native-review-support/cpr-tests-reviewed-final.log'),'reported_result':'13 tests in1suite passed after0.279seconds','origin':'Implementation agent ran focused CPRProjectTests; reviewer checked retained log, final exact source hashes and targeted control bodies without rerunning the suite.','scope':'Self-authored malformed/bounded controls plus read-only exact shipped-template parsing and candidate package persistence. No Cubase runtime acceptance or conformance test.'},
 'snapshot_note':'initial-* snapshots were captured after R1/R2 were already patched and before R3. They are intermediate reviewed snapshots, not the original defective revision. final-* snapshots pin the completed revision.',
 'limits':['No claim of complete native CPR validity: uninterpreted native tails and missing compatibility/lifecycle context may still make a file unacceptable to Cubase.','No full adversarial fuzzing, reference-graph exhaustive proof, or GUI Save As exercise by this reviewer. Root owns GUI verification.','Imported project contains audio track skeletons and a bounded active-fixed-tempo subset only; clips, MIDI, instruments, routing, automation, plugin state, tempo-map coordinates and signatures remain preserved or unsupported.','Native runtime comparison count remains zero; all native observations are static.']
}
(ROOT/'research/evidence/application/APP003/cpr-native-review.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'review_sha256':sha(ROOT/'research/evidence/application/APP003/cpr-native-review.json'),'open_findings':0,'resolved':3}))
