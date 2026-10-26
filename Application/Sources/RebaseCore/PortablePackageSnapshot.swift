import Foundation

/// Bounded identities for regular package contents. Hashing and copying use
/// fixed chunks; neither operation allocates a whole large media asset.
struct PortablePackageSnapshot: Equatable {
    static let maximumEntries = 10_000
    static let maximumBytes = 536_870_912
    private static let chunkBytes = 1_048_576
    struct Entry: Equatable {
        let components: [String]
        let isDirectory: Bool
        let size: Int
        var chunks: [String] = []
        func url(in root: URL) -> URL {
            components.reduce(root) { $0.appendingPathComponent($1) }
        }
    }
    private(set) var entries: [Entry]

    func replacingManifest(with data: Data) throws -> Self {
        guard let index = entries.firstIndex(where: { $0.components == [ProjectStore.manifestName] && !$0.isDirectory }),
              data.count <= Self.maximumBytes - entries.reduce(0, { $0 + $1.size }) + entries[index].size else {
            throw Self.tooLarge()
        }
        var result = entries
        var chunks: [String] = []
        for start in stride(from: 0, to: data.count, by: Self.chunkBytes) {
            chunks.append(cprSHA256(data.subdata(in: start..<min(data.count, start + Self.chunkBytes))))
        }
        result[index] = Entry(components: [ProjectStore.manifestName], isDirectory: false, size: data.count, chunks: chunks)
        return Self(entries: result)
    }

    static func capture(in root: URL) throws -> Self {
        let inventory = try inventory(in: root)
        var result = inventory
        for index in result.indices where !result[index].isDirectory {
            var hashes: [String] = []
            try readChunks(result[index], in: root) { hashes.append(cprSHA256($0)) }
            result[index].chunks = hashes
        }
        guard try Self.inventory(in: root) == inventory else { throw changed() }
        return Self(entries: result)
    }

    /// Copies precisely the inventoried bytes, never a recursive copy of a tree
    /// that can grow after its size check. Both trees must match before return.
    func copy(from source: URL, to destination: URL) throws -> URL {
        let manager = FileManager.default
        let source = try ProjectFileIO.canonicalRoot(source)
        let parent = try ProjectFileIO.canonicalRoot(destination.deletingLastPathComponent())
        let destination = parent.appendingPathComponent(destination.lastPathComponent)
        try ProjectFileIO.requireRealDirectory(parent)
        guard !ProjectFileIO.samePath(source, destination),
              !ProjectFileIO.contains(destination, in: source) else {
            throw Self.invalid("Choose a new project folder outside the source package.")
        }
        try ProjectFileIO.createNewDirectory(destination)
        var complete = false
        defer { if !complete { try? manager.removeItem(at: destination) } }
        try ProjectFileIO.requireRealDirectory(destination)
        for entry in entries {
            let output = entry.url(in: destination)
            try ProjectFileIO.requireRealDirectory(output.deletingLastPathComponent())
            if entry.isDirectory {
                try ProjectFileIO.createNewDirectory(output)
            } else {
                try Data().write(to: output, options: .withoutOverwriting)
                let handle = try FileHandle(forWritingTo: output)
                do {
                    defer { try? handle.close() }
                    var index = 0
                    try Self.readChunks(entry, in: source) { data in
                        guard index < entry.chunks.count,
                              cprSHA256(data) == entry.chunks[index] else { throw Self.changed() }
                        try handle.write(contentsOf: data)
                        index += 1
                    }
                    guard index == entry.chunks.count else { throw Self.changed() }
                    try handle.synchronize()
                }
            }
        }
        guard try Self.capture(in: source) == self,
              try Self.capture(in: destination) == self else { throw Self.changed() }
        complete = true
        return destination
    }

    private static func inventory(in root: URL) throws -> [Entry] {
        try ProjectFileIO.requireRealDirectory(root)
        let manager = FileManager.default
        var enumerationError: Error?
        guard let enumerator = manager.enumerator(at: root, includingPropertiesForKeys: nil,
            errorHandler: { _, error in enumerationError = error; return false }) else {
            throw invalid("The project directory could not be read completely.")
        }
        var result: [Entry] = [], totalBytes = 0
        for case let enumerated as URL in enumerator {
            // Foundation's macOS enumerator may expand /var to /private/var
            // even when its input URL uses the standardized spelling.
            let item = enumerated.standardizedFileURL
            guard result.count < maximumEntries else { throw tooLarge() }
            guard ProjectFileIO.contains(item, in: root),
                  ProjectFileIO.samePath(item.standardizedFileURL, try ProjectFileIO.canonicalRoot(item)),
                  try !ProjectFileIO.isLinkOrReparsePoint(item) else {
                throw invalid("Project copies require regular files and directories without links or reparse points.")
            }
            let components = Array(item.pathComponents.dropFirst(root.pathComponents.count))
            guard !components.isEmpty, components.allSatisfy({
                !$0.isEmpty && $0 != "." && $0 != ".." && !$0.contains("\0") && !$0.contains(":") && !$0.contains("\\")
            }) else { throw invalid("A package filename cannot be copied safely between hosts.") }
            let attributes = try manager.attributesOfItem(atPath: item.path)
            let kind = attributes[.type] as? FileAttributeType
            guard kind == .typeRegular || kind == .typeDirectory else {
                throw invalid("Project copies require only regular files and directories.")
            }
            var size = 0
            if kind == .typeRegular {
                guard let bytes = (attributes[.size] as? NSNumber)?.int64Value,
                      bytes >= 0, bytes <= Int64(maximumBytes - totalBytes) else { throw tooLarge() }
                size = Int(bytes); totalBytes += size
            }
            result.append(Entry(components: components, isDirectory: kind == .typeDirectory, size: size))
        }
        if let enumerationError { throw enumerationError }
        try ProjectFileIO.requireRealDirectory(root)
        return result.sorted {
            if $0.components.count != $1.components.count { return $0.components.count < $1.components.count }
            return $0.components.joined(separator: "/") < $1.components.joined(separator: "/")
        }
    }

    private static func readChunks(_ entry: Entry, in root: URL, consume: (Data) throws -> Void) throws {
        try ProjectFileIO.requireRealDirectory(root)
        let item = entry.url(in: root)
        guard ProjectFileIO.samePath(item, try ProjectFileIO.canonicalRoot(item)),
              try !ProjectFileIO.isLinkOrReparsePoint(item) else { throw changed() }
        let manager = FileManager.default
        let before = try manager.attributesOfItem(atPath: item.path)
        guard before[.type] as? FileAttributeType == .typeRegular,
              (before[.size] as? NSNumber)?.int64Value == Int64(entry.size) else { throw changed() }
        let file = try FileHandle(forReadingFrom: item)
        defer { try? file.close() }
        var remaining = entry.size
        while remaining > 0 {
            let count = min(chunkBytes, remaining)
            var data = Data()
            while data.count < count {
                guard let part = try file.read(upToCount: count - data.count), !part.isEmpty else { throw changed() }
                data.append(part)
            }
            try consume(data)
            remaining -= count
        }
        guard (try file.read(upToCount: 1) ?? Data()).isEmpty else { throw changed() }
        let after = try manager.attributesOfItem(atPath: item.path)
        guard after[.type] as? FileAttributeType == .typeRegular,
              (after[.size] as? NSNumber)?.int64Value == Int64(entry.size),
              before[.systemFileNumber] as? NSNumber == after[.systemFileNumber] as? NSNumber,
              before[.modificationDate] as? Date == after[.modificationDate] as? Date,
              ProjectFileIO.samePath(item, try ProjectFileIO.canonicalRoot(item)),
              try !ProjectFileIO.isLinkOrReparsePoint(item) else { throw changed() }
    }

    private static func invalid(_ message: String) -> RebaseCoreError { .invalidProject(message) }
    private static func changed() -> RebaseCoreError { invalid("The project package changed while it was being copied or verified. Reopen it and try again.") }
    private static func tooLarge() -> RebaseCoreError { invalid("Project copying is currently bounded to 10,000 entries and 512 MiB.") }
}
