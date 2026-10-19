import Foundation
import SwiftUI

/// A review of one inspected file, kept separate from the active project.
struct CPRImportPreview: Identifiable {
    let id = UUID()
    let source: URL
    let sourceName: String
    let sourceSHA256: String
    let byteCount: Int
    let recovered: [String]
    let metadata: [String]
    let tracks: [CPRPreviewFact]
    let unresolved: [String]
    let defaults: [String]
    let canImport: Bool
    let recoveryDescription: String
    var isImportReport = false
}

struct CPRPreviewFact: Identifiable {
    let id = UUID()
    let label: String
    let value: String
}

struct CPRImportReviewView: View {
    let preview: CPRImportPreview
    let onImport: () -> Void
    let onCancel: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 8) {
                Text(preview.isImportReport ? "Reference Import Report" : "Import Reference Project").font(.title2.weight(.semibold))
                Text(preview.sourceName).font(.headline).textSelection(.enabled)
                Text(preview.recoveryDescription).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }.padding(24)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    if !preview.recovered.isEmpty {
                        notes("Recovered project data", preview.recovered)
                    }
                    if !preview.tracks.isEmpty {
                        facts("Tracks in the source", preview.tracks)
                    }
                    if !preview.unresolved.isEmpty {
                        notes("Not restored", preview.unresolved)
                    }
                    if !preview.defaults.isEmpty {
                        notes("Settings for the recovered project", preview.defaults)
                    }
                    if !preview.metadata.isEmpty {
                        DisclosureGroup("Descriptive source metadata") {
                            notes("These tags describe the source; they may differ from its active arrangement settings.", preview.metadata)
                                .padding(.top, 8)
                        }
                    }
                    VStack(alignment: .leading, spacing: 7) {
                        Label("Original project retained", systemImage: "doc.on.doc")
                            .font(.headline)
                        Text(preview.isImportReport
                             ? "This report records the import baseline. Your Rebase edits may differ from it. The original CPR file is retained in this project; edits in Rebase do not update it."
                             : "The new Rebase project keeps an exact copy of this CPR file and its compatibility report. Edits in Rebase do not update the original Reference project.")
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        DisclosureGroup("Source details") {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(ByteCountFormatter.string(fromByteCount: Int64(preview.byteCount), countStyle: .file))
                                Text("SHA-256: \(preview.sourceSHA256)")
                                    .font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                            }.padding(.top, 5).frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider()
            HStack {
                Text(preview.isImportReport ? "Original file integrity checked." : preview.canImport ? "Creates a new project with the supported data." : "This file has no supported project data to restore yet.")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button(preview.isImportReport ? "Done" : "Cancel", action: onCancel).keyboardShortcut(.cancelAction)
                if !preview.isImportReport {
                    Button("Import Supported Data…", action: onImport)
                        .keyboardShortcut(.defaultAction).disabled(!preview.canImport)
                }
            }.padding(18)
        }
        .frame(width: 760, height: 650)
    }

    private func facts(_ title: String, _ values: [CPRPreviewFact]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            ForEach(values) { fact in
                HStack(alignment: .firstTextBaseline, spacing: 16) {
                    Text(fact.label).foregroundStyle(.secondary).frame(width: 185, alignment: .leading)
                    Text(fact.value).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }.font(.callout)
            }
        }
    }

    private func notes(_ title: String, _ values: [String]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            ForEach(Array(values.enumerated()), id: \.offset) { _, value in
                HStack(alignment: .top, spacing: 9) {
                    Text("•").foregroundStyle(.secondary)
                    Text(value).fixedSize(horizontal: false, vertical: true)
                }.font(.callout)
            }
        }
    }
}
