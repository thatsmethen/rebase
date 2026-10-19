// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Rebase",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "Rebase", targets: ["Rebase"])],
    dependencies: [.package(url: "https://github.com/weichsel/ZIPFoundation.git", exact: "0.9.20")],
    targets: [
        .target(name: "RebaseDSP", publicHeadersPath: "include", cSettings: [
            .unsafeFlags(["-fno-fast-math", "-ffp-contract=off", "-frounding-math"])
        ]),
        .target(name: "RebaseAmbiDSP", publicHeadersPath: "include", cSettings: [
            .unsafeFlags(["-fno-fast-math", "-ffp-contract=off", "-frounding-math"])
        ]),
        .target(name: "RebaseTimingDSP", publicHeadersPath: "include", cSettings: [
            .unsafeFlags(["-fno-fast-math", "-ffp-contract=off", "-frounding-math"])
        ]),
        .target(name: "RebaseCore", dependencies: ["ZIPFoundation", "RebaseAmbiDSP", "RebaseTimingDSP"]),
        .executableTarget(name: "Rebase", dependencies: ["RebaseCore", "RebaseDSP"]),
        .testTarget(name: "RebaseCoreTests", dependencies: ["RebaseCore", "RebaseDSP"])
    ],
    swiftLanguageModes: [.v5]
)
