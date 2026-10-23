import Foundation
import Testing

/// Optional, read-only inputs owned by the researcher, never by this checkout.
/// An unset variable disables only explicitly marked tests. A configured but
/// incomplete fixture set fails its reads and existing digest checks normally.
enum PrivateResearchFixtures {
    static let environmentName = "REBASE_RESEARCH_ROOT"
    static let reason: Comment = "Requires external private fixtures; set REBASE_RESEARCH_ROOT to an absolute directory outside this checkout."
    static let checkout = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()

    enum ConfigurationError: Error, LocalizedError {
        case notAbsolute, insideCheckout, notDirectory, invalidTemplateName

        var errorDescription: String? {
            switch self {
            case .notAbsolute: "REBASE_RESEARCH_ROOT must be an absolute path, or unset for the public test run."
            case .insideCheckout: "REBASE_RESEARCH_ROOT must resolve outside the source checkout."
            case .notDirectory: "REBASE_RESEARCH_ROOT must identify an existing directory."
            case .invalidTemplateName: "Recorded template source must end in a named .cpr file."
            }
        }
    }

    static func resolveRoot(_ value: String?, checkout: URL) throws -> URL? {
        guard let value else { return nil }
        guard value.hasPrefix("/") else { throw ConfigurationError.notAbsolute }
        let directory = URL(fileURLWithPath: value, isDirectory: true).standardizedFileURL.resolvingSymlinksInPath()
        let source = checkout.standardizedFileURL.resolvingSymlinksInPath()
        guard directory.path != source.path, !directory.path.hasPrefix(source.path + "/") else {
            throw ConfigurationError.insideCheckout
        }
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: directory.path, isDirectory: &isDirectory), isDirectory.boolValue else {
            throw ConfigurationError.notDirectory
        }
        return directory
    }

    private static let configuration: Result<URL?, Error> = Result {
        try resolveRoot(ProcessInfo.processInfo.environment[environmentName], checkout: checkout)
    }

    static var isConfigured: Bool {
        if case .success(.some) = configuration { return true }
        return false
    }

    static var root: URL {
        if case .success(.some(let directory)) = configuration { return directory }
        // Disabled tests can initialize URL properties without touching disk.
        // The always-run configuration test reports invalid explicit settings.
        return URL(fileURLWithPath: "/__rebase_private_fixtures_unconfigured__", isDirectory: true)
    }

    static func validateEnvironment() throws { _ = try configuration.get() }

    static func templateFilename(recordedPath: String) throws -> String {
        let name = (recordedPath as NSString).lastPathComponent
        guard !recordedPath.hasSuffix("/"), !name.isEmpty,
              (name as NSString).pathExtension == "cpr",
              !(name as NSString).deletingPathExtension.isEmpty else {
            throw ConfigurationError.invalidTemplateName
        }
        return name
    }

    /// Retained records keep their original bytes and digest. Their machine-
    /// specific directory prefix is not interpreted as a local filesystem path.
    static func template(recordedPath: String) throws -> URL {
        root.appendingPathComponent("templates", isDirectory: true)
            .appendingPathComponent(try templateFilename(recordedPath: recordedPath))
    }
}

struct PrivateResearchFixtureConfigurationTests {
    @Test func explicitlyConfiguredResearchRootMustBeValid() throws {
        try PrivateResearchFixtures.validateEnvironment()
    }

    @Test func absentRelativeMissingAndCheckoutLocalRootsHaveDistinctOutcomes() throws {
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let checkout = temporary.appendingPathComponent("source", isDirectory: true)
        let outside = temporary.appendingPathComponent("fixtures", isDirectory: true)
        try FileManager.default.createDirectory(at: checkout, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outside, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporary) }
        #expect(try PrivateResearchFixtures.resolveRoot(nil, checkout: checkout) == nil)
        #expect(try PrivateResearchFixtures.resolveRoot(outside.path, checkout: checkout) == outside.resolvingSymlinksInPath())
        for bad in ["", "relative", "~/fixtures", checkout.path, checkout.appendingPathComponent("fixtures").path,
                    temporary.appendingPathComponent("missing").path] {
            #expect(throws: PrivateResearchFixtures.ConfigurationError.self) {
                try PrivateResearchFixtures.resolveRoot(bad, checkout: checkout)
            }
        }
        let link = temporary.appendingPathComponent("source-alias")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: checkout)
        #expect(throws: PrivateResearchFixtures.ConfigurationError.self) {
            try PrivateResearchFixtures.resolveRoot(link.path, checkout: checkout)
        }
        let file = temporary.appendingPathComponent("file")
        try Data([1]).write(to: file)
        #expect(throws: PrivateResearchFixtures.ConfigurationError.self) {
            try PrivateResearchFixtures.resolveRoot(file.path, checkout: checkout)
        }
    }

    @Test func recordedSourcePrefixesCannotRedirectTemplateResolution() throws {
        for recorded in ["Example.cpr", "original/machine/Example.cpr", "/outside/Example.cpr", "../../Example.cpr"] {
            #expect(try PrivateResearchFixtures.templateFilename(recordedPath: recorded) == "Example.cpr")
            #expect(try PrivateResearchFixtures.template(recordedPath: recorded) ==
                PrivateResearchFixtures.root.appendingPathComponent("templates/Example.cpr"))
        }
        for bad in ["", ".", "..", "Example.cpr/", "Example.json", ".cpr"] {
            #expect(throws: PrivateResearchFixtures.ConfigurationError.self) {
                try PrivateResearchFixtures.templateFilename(recordedPath: bad)
            }
        }
    }
}
