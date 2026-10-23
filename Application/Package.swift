// swift-tools-version: 6.0
import PackageDescription
import Foundation

let soxrLibraryDirectory = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().appendingPathComponent(".build-soxr/install/lib").path

#if os(Windows)
let portableOnly = true
#else
let portableOnly = ProcessInfo.processInfo.environment["REBASE_PORTABLE_ONLY"] == "1"
#endif

// The portable target compiles these same semantic sources. Its document store
// uses bounded WAV media; device transport and macOS framework APIs stay outside.
let portableSources = [
    "Automation.swift", "CPRAudioEventArchive.swift", "CPRAudioMediaAttachmentModel.swift",
    "CPRAutoFadeArchive.swift", "CPRClockRoles.swift", "CPRContractMigration.swift",
    "CPRProject.swift", "CPRProjectAudioSetup.swift", "CPRRecoveryV1.swift",
    "CPRRecoveryV2.swift", "CPRRecoveryV3.swift", "CPRRecoveryV4.swift", "CPRRecoveryV5.swift",
    "CPRSegmentReadPlan.swift", "CPRSignatureRecovery.swift", "CPRTrackContributorArchive.swift",
    "MusicalTime.swift", "NativeTempoClock.swift", "PCMRendering.swift", "PortableSHA256.swift", "Project.swift", "ProjectEditing.swift",
    "PortablePackageSnapshot.swift", "PortableSession.swift", "ProjectFileIO.swift", "ProjectStore.swift", "ProjectStorePortableAudio.swift",
    "UnresolvedCPRAudioEvent.swift", "WAVPCMSource.swift"
]
let coreDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    .appendingPathComponent("Sources/RebaseCore")
let portableExcludes = (try? FileManager.default.contentsOfDirectory(atPath: coreDirectory.path))?
    .filter { !portableSources.contains($0) } ?? []
let timingTarget = Target.target(name: "RebaseTimingDSP", publicHeadersPath: "include", cSettings: [
    .unsafeFlags(["-fno-fast-math", "-ffp-contract=off", "-frounding-math"])
])
let portableTargets: [Target] = [
    timingTarget,
    .target(name: "RebasePortable", dependencies: ["RebaseTimingDSP"], path: "Sources/RebaseCore",
            exclude: portableExcludes, sources: portableSources,
            swiftSettings: [.define("REBASE_PORTABLE")]),
    .executableTarget(name: "RebaseInspectCLI", dependencies: ["RebasePortable"]),
    .executableTarget(name: "RebaseSessionCLI", dependencies: ["RebasePortable"]),
    .testTarget(name: "RebasePortableTests", dependencies: ["RebasePortable", "RebaseTimingDSP"],
                path: "Tests", exclude: ["RebaseCoreTests", "PortableDSP", "run-tests.sh", "README.md"],
                sources: ["RebasePortableTests", "SharedEditingTests", "SharedDocumentTests"])
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
        .target(name: "RebaseSoXR", dependencies: ["RebaseTimingDSP"],
                publicHeadersPath: "include", cSettings: [
            .unsafeFlags(["-fno-fast-math", "-ffp-contract=off", "-frounding-math"])
        ], linkerSettings: [
            .linkedLibrary("soxr"),
            .unsafeFlags(["-L", soxrLibraryDirectory,
                          "-Xlinker", "-rpath", "-Xlinker", "@executable_path/../Frameworks",
                          "-Xlinker", "-rpath", "-Xlinker", soxrLibraryDirectory])
        ]),
        .target(name: "RebaseCore", dependencies: ["ZIPFoundation", "RebaseAmbiDSP", "RebaseTimingDSP", "RebaseSoXR"]),
        .executableTarget(name: "Rebase", dependencies: ["RebaseCore", "RebaseDSP"]),
        .testTarget(name: "RebaseCoreTests", dependencies: ["RebaseCore", "RebaseDSP"],
                    path: "Tests", exclude: ["RebasePortableTests", "PortableDSP", "run-tests.sh", "README.md"],
                    sources: ["RebaseCoreTests", "SharedEditingTests", "SharedDocumentTests"])
    ],
    swiftLanguageModes: [.v5]
)
