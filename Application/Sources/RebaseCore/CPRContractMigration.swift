import Foundation

/// Recognizes an exact historical descriptor identity without changing its
/// arithmetic or source provenance. Unknown identities remain unknown so the
/// descriptor's existing validation and replay checks continue to reject them.
enum CPRContractMigration {
    static func normalize(_ stored: String, to canonical: String, legacySHA256: String) -> String {
        guard stored != canonical,
              cprSHA256(Data(stored.utf8)) == legacySHA256 else { return stored }
        return canonical
    }
}
