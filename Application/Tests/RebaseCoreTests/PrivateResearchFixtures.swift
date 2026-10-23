import Foundation
import Testing

/// Optional, read-only inputs owned by the researcher. They may live outside
/// the checkout or inside its ignored .local directory, never in tracked source.
/// An unset variable disables only explicitly marked tests. A configured but
/// incomplete fixture set fails its reads and existing digest checks normally.
enum PrivateResearchFixtures {
    static let environmentName = "REBASE_RESEARCH_ROOT"
    static let reason: Comment = "Requires private fixtures; set REBASE_RESEARCH_ROOT to an absolute directory inside this checkout's ignored .local directory or outside the checkout."
    static let checkout = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()

    enum ConfigurationError: Error, LocalizedError {
        case notAbsolute, insideCheckout, notDirectory, invalidTemplateName

        var errorDescription: String? {
            switch self {
            case .notAbsolute: "REBASE_RESEARCH_ROOT must be an absolute path, or unset for the public test run."
            case .insideCheckout: "REBASE_RESEARCH_ROOT must resolve inside the checkout's ignored .local directory or outside the checkout; other source-checkout directories are not allowed."
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
        // Resolve the selected root first. Do not resolve the allowed .local
        // prefix separately: a .local symlink into tracked source must not make
        // that source directory an allowed research location.
        let local = source.appendingPathComponent(".local", isDirectory: true)
        let insideSource = directory.path == source.path || directory.path.hasPrefix(source.path + "/")
        let insideLocal = directory.path == local.path || directory.path.hasPrefix(local.path + "/")
        guard !insideSource || insideLocal else {
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
    private func scratchDirectory() throws -> URL {
        let directory = PrivateResearchFixtures.checkout.appendingPathComponent(".local/work/private-fixture-controls", isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }

    @Test func explicitlyConfiguredResearchRootMustBeValid() throws {
        try PrivateResearchFixtures.validateEnvironment()
    }

    @Test func absentRelativeMissingAndCheckoutLocalRootsHaveDistinctOutcomes() throws {
        let temporary = try scratchDirectory()
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

    @Test func ignoredLocalResearchAllowsResolvedPrivateRootsButNotSourceAliases() throws {
        let temporary = try scratchDirectory()
        defer { try? FileManager.default.removeItem(at: temporary) }
        let checkout = temporary.appendingPathComponent("source", isDirectory: true)
        let local = checkout.appendingPathComponent(".local", isDirectory: true)
        let fixtures = local.appendingPathComponent("fixtures", isDirectory: true)
        let tracked = checkout.appendingPathComponent("Application", isDirectory: true)
        let sibling = checkout.appendingPathComponent(".local-other", isDirectory: true)
        let outside = temporary.appendingPathComponent("outside", isDirectory: true)
        for directory in [fixtures, tracked, sibling, outside] {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        for allowed in [local, fixtures, outside] {
            #expect(try PrivateResearchFixtures.resolveRoot(allowed.path, checkout: checkout) == allowed.resolvingSymlinksInPath())
        }
        let sourceAlias = local.appendingPathComponent("source-alias")
        try FileManager.default.createSymbolicLink(at: sourceAlias, withDestinationURL: tracked)
        for rejected in [tracked, sibling, sourceAlias] {
            #expect(throws: PrivateResearchFixtures.ConfigurationError.self) {
                try PrivateResearchFixtures.resolveRoot(rejected.path, checkout: checkout)
            }
        }
        for (name, destination) in [("private-alias", fixtures), ("outside-alias", outside)] {
            let alias = local.appendingPathComponent(name)
            try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: destination)
            #expect(try PrivateResearchFixtures.resolveRoot(alias.path, checkout: checkout) == destination.resolvingSymlinksInPath())
        }

        let redirectedCheckout = temporary.appendingPathComponent("redirected-source", isDirectory: true)
        let redirectedTarget = redirectedCheckout.appendingPathComponent("Application", isDirectory: true)
        try FileManager.default.createDirectory(at: redirectedTarget, withIntermediateDirectories: true)
        let redirectedLocal = redirectedCheckout.appendingPathComponent(".local")
        try FileManager.default.createSymbolicLink(at: redirectedLocal, withDestinationURL: redirectedTarget)
        #expect(throws: PrivateResearchFixtures.ConfigurationError.self) {
            try PrivateResearchFixtures.resolveRoot(redirectedLocal.path, checkout: redirectedCheckout)
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
