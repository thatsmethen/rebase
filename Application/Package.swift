// swift-tools-version: 6.0
import PackageDescription
import Foundation

let soxrLibraryDirectory = ProcessInfo.processInfo.environment["REBASE_SOXR_LIBRARY_DIR"] ??
    URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appendingPathComponent(".build-soxr/install/lib").path

#if os(Windows)
let portableOnly = true
#else
let portableOnly = ProcessInfo.processInfo.environment["REBASE_PORTABLE_ONLY"] == "1"
#endif

// The portable target compiles these same semantic sources. Its document store
// uses bounded WAV media; device transport and macOS framework APIs stay outside.
let portableSources = [
    "Automation.swift", "CPRAudioEventArchive.swift", "CPRAudioMediaAttachmentModel.swift",
    "CPRAudioMediaAttachment.swift", "CPRAudioMediaValidationPortable.swift",
    "CPRSourceEventRenderPlan.swift", "CPRSourceEventRenderer.swift", "ProjectStoreCPRAudio.swift",
    "CPRAutoFadeArchive.swift", "CPRClockRoles.swift", "CPRContractMigration.swift",
    "CPRProject.swift", "CPRProjectAudioSetup.swift", "CPRRecoveryV1.swift",
    "CPRRecoveryV2.swift", "CPRRecoveryV3.swift", "CPRRecoveryV4.swift", "CPRRecoveryV5.swift",
    "CPRSegmentReadPlan.swift", "CPRSignatureRecovery.swift", "CPRTrackContributorArchive.swift",
    "CPRSourceAudition.swift", "StereoPCMBlock.swift", "CPRSourceTrackPlayback.swift",
    "CPRNativeTimelineStream.swift", "CPRRateConvertedStream.swift", "CPRLiveStereoTransfer.swift",
    "CPRLiveCallbackAdapter.swift", "CPRNativeAudioAccessor.swift", "CPRPlacedSourceEventPlan.swift",
    "CPRSourceTrackPlan.swift", "CPRTrackOverlapNormalizer.swift", "CPRTimelineSelection.swift",
    "CPRSourceAudioInspection.swift",
    "MusicalTime.swift", "MusicalRuler.swift", "NativeTempoClock.swift", "PCMRendering.swift", "PortableSHA256.swift", "Project.swift", "ProjectEditing.swift",
    "PortablePackageSnapshot.swift", "PortableSession.swift", "PortableCPRReview.swift", "ProjectFileIO.swift", "ProjectStore.swift", "ProjectStorePortableAudio.swift",
    "UnresolvedCPRAudioEvent.swift", "WAVPCMSource.swift", "WaveformPeaks.swift"
]
let coreDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    .appendingPathComponent("Sources/RebaseCore")
let portableExcludes = (try? FileManager.default.contentsOfDirectory(atPath: coreDirectory.path))?
    .filter { !portableSources.contains($0) } ?? []
let timingTarget = Target.target(name: "RebaseTimingDSP", publicHeadersPath: "include", cSettings: [
    .unsafeFlags(["-fno-fast-math", "-ffp-contract=off", "-frounding-math"])
])
#if os(Windows)
let soxrLinkerSettings: [LinkerSetting] = [
    .linkedLibrary("soxr"), .unsafeFlags(["-L", soxrLibraryDirectory])
]
#else
let soxrLinkerSettings: [LinkerSetting] = [
    .linkedLibrary("soxr"),
    .unsafeFlags(["-L", soxrLibraryDirectory,
                  "-Xlinker", "-rpath", "-Xlinker", "@executable_path/../Frameworks",
                  "-Xlinker", "-rpath", "-Xlinker", soxrLibraryDirectory])
]
#endif
let soxrTarget = Target.target(name: "RebaseSoXR", dependencies: ["RebaseTimingDSP"],
    publicHeadersPath: "include", cSettings: [
        .define("SOXR_DLL", .when(platforms: [.windows])),
        .unsafeFlags(["-fno-fast-math", "-ffp-contract=off", "-frounding-math"])
    ], linkerSettings: soxrLinkerSettings)
let portableTargets: [Target] = [
    timingTarget, soxrTarget,
    .target(name: "RebasePortable", dependencies: ["RebaseTimingDSP", "RebaseSoXR"], path: "Sources/RebaseCore",
            exclude: portableExcludes, sources: portableSources,
            swiftSettings: [.define("REBASE_PORTABLE")]),
    .executableTarget(name: "RebaseInspectCLI", dependencies: ["RebasePortable"]),
    .executableTarget(name: "RebaseSessionCLI", dependencies: ["RebasePortable"]),
    .testTarget(name: "RebasePortableTests", dependencies: ["RebasePortable", "RebaseTimingDSP"],
                path: "Tests", exclude: ["RebaseCoreTests", "PortableDSP", "Fixtures", "run-tests.sh", "README.md"],
                sources: ["RebasePortableTests", "SharedEditingTests", "SharedDocumentTests", "SharedCPRAudioTests", "SharedCPRAuditionOutputTests", "SharedCPRImportTests", "SharedWaveformTests", "SharedMusicalRulerTests"])
]

let package = Package(
    name: "Rebase",
    platforms: [.macOS(.v14)],
    products: portableOnly ? [.library(name: "RebasePortable", targets: ["RebasePortable"]),
        .executable(name: "rebase-inspect", targets: ["RebaseInspectCLI"]),
        .executable(name: "rebase-session", targets: ["RebaseSessionCLI"])] :
        [.executable(name: "Rebase", targets: ["Rebase"])],
    dependencies: portableOnly ? [] : [.package(url: "https://github.com/weichsel/ZIPFoundation.git", exact: "0.9.20")],
    targets: portableOnly ? portableTargets : [
        .target(name: "RebaseDSP", publicHeadersPath: "include", cSettings: [
            .unsafeFlags(["-fno-fast-math", "-ffp-contract=off", "-frounding-math"])
        ]),
        .target(name: "RebaseAmbiDSP", publicHeadersPath: "include", cSettings: [
            .unsafeFlags(["-fno-fast-math", "-ffp-contract=off", "-frounding-math"])
        ]),
        timingTarget,
        soxrTarget,
        .target(name: "RebaseCore", dependencies: ["ZIPFoundation", "RebaseAmbiDSP", "RebaseTimingDSP", "RebaseSoXR"]),
        .executableTarget(name: "Rebase", dependencies: ["RebaseCore", "RebaseDSP"]),
        .testTarget(name: "RebaseCoreTests", dependencies: ["RebaseCore", "RebaseDSP"],
                    path: "Tests", exclude: ["RebasePortableTests", "PortableDSP", "Fixtures", "run-tests.sh", "README.md"],
                    sources: ["RebaseCoreTests", "SharedEditingTests", "SharedDocumentTests", "SharedCPRAudioTests", "SharedCPRAuditionOutputTests", "SharedCPRImportTests", "SharedWaveformTests", "SharedMusicalRulerTests"])
    ],
    swiftLanguageModes: [.v5]
)
