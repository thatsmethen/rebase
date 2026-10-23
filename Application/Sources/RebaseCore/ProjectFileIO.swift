import Foundation
#if os(Windows)
import WinSDK
#elseif canImport(Darwin)
import Darwin
#endif

/// Project manifests are bounded snapshots. Media and compatibility payloads
/// are never rewritten by this layer.
enum ProjectFileIO {
    static let maximumManifestBytes = 8_388_608

    static func canonicalRoot(_ root: URL) throws -> URL {
        guard root.isFileURL, !root.path.contains("\0"), !root.absoluteString.lowercased().contains("%00") else {
            throw invalid("Choose a local project folder without NUL characters.")
        }
        return root.standardizedFileURL.resolvingSymlinksInPath()
    }

    static func samePath(_ first: URL, _ second: URL) -> Bool {
        components(first) == components(second)
    }

    static func contains(_ url: URL, in directory: URL) -> Bool {
        let candidate = components(url), base = components(directory)
        return candidate.count > base.count && candidate.starts(with: base)
    }

    static func isLinkOrReparsePoint(_ url: URL) throws -> Bool {
        #if os(Windows)
        let path = try windowsPath(url)
        let result: (DWORD, DWORD) = path.withUnsafeBufferPointer { path in
            let attributes = GetFileAttributesW(path.baseAddress)
            return (attributes, attributes == INVALID_FILE_ATTRIBUTES ? GetLastError() : 0)
        }
        guard result.0 != INVALID_FILE_ATTRIBUTES else {
            throw invalid("The project path could not be inspected (Windows error \(result.1)).")
        }
        return result.0 & DWORD(FILE_ATTRIBUTE_REPARSE_POINT) != 0
        #else
        return try FileManager.default.attributesOfItem(atPath: url.path)[.type] as? FileAttributeType == .typeSymbolicLink
        #endif
    }

    static func requireRealDirectory(_ url: URL) throws {
        guard samePath(url.standardizedFileURL, try canonicalRoot(url)),
              try !isLinkOrReparsePoint(url),
              try FileManager.default.attributesOfItem(atPath: url.path)[.type] as? FileAttributeType == .typeDirectory else {
            throw invalid("The project copy must remain a real directory, not a link or reparse point.")
        }
    }

    /// Creates only a new directory, including when an empty directory already
    /// exists at the requested path. Used for private package-copy staging.
    static func createNewDirectory(_ url: URL) throws {
        #if os(Windows)
        let path = try windowsPath(url)
        let error: DWORD = path.withUnsafeBufferPointer { path in
            CreateDirectoryW(path.baseAddress, nil) ? 0 : GetLastError()
        }
        guard error == 0 else { throw invalid("A new project folder could not be created (Windows error \(error)).") }
        #elseif canImport(Darwin)
        let result = url.withUnsafeFileSystemRepresentation { mkdir($0, mode_t(S_IRWXU)) }
        guard result == 0 else { throw invalid("A new project folder could not be created at the requested path.") }
        #else
        throw invalid("Exclusive project-directory creation is not supported on this host.")
        #endif
    }

    private static func components(_ url: URL) -> [String] {
        #if os(Windows)
        url.pathComponents.map { $0.lowercased() }
        #else
        url.pathComponents
        #endif
    }

    static func manifestURL(in root: URL) throws -> URL {
        let url = root.appendingPathComponent(ProjectStore.manifestName)
        guard samePath(url, url.resolvingSymlinksInPath()) else {
            throw invalid("The project manifest must remain a regular file inside its project folder.")
        }
        if let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
           attributes[.type] as? FileAttributeType != .typeRegular {
            throw invalid("The project manifest must be a regular file, not a directory or link.")
        }
        return url
    }

    static func readManifest(in root: URL) throws -> Data {
        let url = try manifestURL(in: root)
        let manager = FileManager.default
        let before = try manager.attributesOfItem(atPath: url.path)
        guard before[.type] as? FileAttributeType == .typeRegular,
              let size = (before[.size] as? NSNumber)?.intValue,
              (1...maximumManifestBytes).contains(size) else {
            throw invalid("Project manifests must be regular files of at most 8 MiB.")
        }
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        let data = try file.read(upToCount: size + 1) ?? Data()
        let after = try manager.attributesOfItem(atPath: url.path)
        guard data.count == size, (after[.size] as? NSNumber)?.intValue == size,
              before[.systemFileNumber] as? NSNumber == after[.systemFileNumber] as? NSNumber,
              before[.modificationDate] as? Date == after[.modificationDate] as? Date else {
            throw invalid("The project manifest changed while it was being read.")
        }
        return data
    }

    static func writeManifest(_ data: Data, in root: URL) throws {
        guard (1...maximumManifestBytes).contains(data.count) else {
            throw invalid("Project manifests must be at most 8 MiB.")
        }
        let destination = try manifestURL(in: root)
        #if os(Windows)
        // No cross-volume copy fallback: publish a completed sibling using one
        // rename. Foundation .atomic can fall back to COPY_ALLOWED on Windows.
        let manager = FileManager.default
        let staging = root.appendingPathComponent(".rebase-manifest-" + UUID().uuidString + ".tmp")
        defer { try? manager.removeItem(at: staging) }
        try data.write(to: staging, options: .withoutOverwriting)
        do {
            let check = try FileHandle(forReadingFrom: staging)
            defer { try? check.close() }
            guard try check.read(upToCount: data.count + 1) == data else {
                throw invalid("The staged project manifest changed before publication.")
            }
        }
        let sourcePath = try windowsPath(staging), destinationPath = try windowsPath(destination)
        let error: DWORD = sourcePath.withUnsafeBufferPointer { source in
            destinationPath.withUnsafeBufferPointer { destination in
                MoveFileExW(source.baseAddress, destination.baseAddress,
                    DWORD(MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) ? 0 : GetLastError()
            }
        }
        guard error == 0 else { throw invalid("The project could not be saved (Windows error \(error)). The previous manifest was retained.") }
        #else
        try data.write(to: destination, options: .atomic)
        #endif
    }

    /// Hard-links a completed sibling file without replacing an existing path.
    /// The caller removes staging after publication or failure.
    static func publishNewFile(_ staging: URL, to destination: URL) throws {
        guard samePath(try canonicalRoot(staging.deletingLastPathComponent()),
                       try canonicalRoot(destination.deletingLastPathComponent())) else {
            throw invalid("Publish files from completed sibling files.")
        }
        let manager = FileManager.default
        let before = try manager.attributesOfItem(atPath: staging.path)
        guard before[.type] as? FileAttributeType == .typeRegular,
              let size = (before[.size] as? NSNumber)?.uint64Value else {
            throw invalid("Only completed regular files can be published.")
        }
        #if os(Windows)
        let sourcePath = try windowsPath(staging), destinationPath = try windowsPath(destination)
        let error: DWORD = sourcePath.withUnsafeBufferPointer { source in
            destinationPath.withUnsafeBufferPointer { destination in
                CreateHardLinkW(destination.baseAddress, source.baseAddress, nil) ? 0 : GetLastError()
            }
        }
        guard error == 0 else { throw invalid("The new file could not be published (Windows error \(error)). Existing files are never replaced.") }
        #else
        try manager.linkItem(at: staging, to: destination)
        #endif
        do {
            let after = try manager.attributesOfItem(atPath: destination.path)
            guard after[.type] as? FileAttributeType == .typeRegular,
                  (after[.size] as? NSNumber)?.uint64Value == size else {
                throw invalid("The published file did not pass its file and size checks.")
            }
            let file = try FileHandle(forReadingFrom: destination)
            defer { try? file.close() }
            guard try file.seekToEnd() == size else { throw invalid("The published file is incomplete.") }
        } catch {
            try? manager.removeItem(at: destination)
            throw error
        }
    }

    /// Publishes a completed sibling project directory without replacing any
    /// existing destination. The caller owns staging cleanup on failure.
    static func publishNewDirectory(_ staging: URL, to destination: URL) throws {
        let sourceParent = try canonicalRoot(staging.deletingLastPathComponent())
        let destinationParent = try canonicalRoot(destination.deletingLastPathComponent())
        try requireRealDirectory(staging)
        guard samePath(sourceParent, destinationParent) else {
            throw invalid("Publish projects from a completed sibling directory.")
        }
        #if os(Windows)
        let sourcePath = try windowsPath(staging), destinationPath = try windowsPath(destination)
        let error: DWORD = sourcePath.withUnsafeBufferPointer { source in
            destinationPath.withUnsafeBufferPointer { destination in
                MoveFileExW(source.baseAddress, destination.baseAddress, 0) ? 0 : GetLastError()
            }
        }
        guard error == 0 else { throw invalid("The new project could not be published (Windows error \(error)). Existing destinations are never replaced.") }
        #elseif canImport(Darwin)
        let status = staging.withUnsafeFileSystemRepresentation { source in
            destination.withUnsafeFileSystemRepresentation { destination in
                renameatx_np(AT_FDCWD, source, AT_FDCWD, destination, UInt32(RENAME_EXCL))
            }
        }
        guard status == 0 else { throw invalid("The new project could not be published. Existing destinations are never replaced.") }
        #else
        throw invalid("Atomic publication of a new project directory is not supported on this host.")
        #endif
    }

    #if os(Windows)
    private static func windowsPath(_ url: URL) throws -> [WCHAR] {
        guard url.isFileURL, !url.path.contains("\0"), !url.absoluteString.lowercased().contains("%00") else {
            throw invalid("Choose a local project path without NUL characters.")
        }
        return try url.withUnsafeFileSystemRepresentation { representation in
            guard let representation else { throw invalid("The project path cannot be represented on Windows.") }
            var path = String(cString: representation)
            if !path.hasPrefix("\\\\?\\") {
                if path.hasPrefix("\\\\") { path = "\\\\?\\UNC\\" + path.dropFirst(2) }
                else { path = "\\\\?\\" + path }
            }
            return Array(path.utf16) + [0]
        }
    }
    #endif

    private static func invalid(_ message: String) -> RebaseCoreError { .invalidProject(message) }
}
