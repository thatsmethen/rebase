import AppKit
import SwiftUI
import RebaseCore

struct CPRProjectStructurePreview: Identifiable {
    let id = UUID()
    let snapshot: CPRProjectStructureSnapshot
}

struct CPRProjectStructureView: View {
    let preview: CPRProjectStructurePreview
    let onClose: () -> Void
    private var report: CPRNativeProjectBindingReport { preview.snapshot.report }
    private enum Section: String, CaseIterable {
        case overview = "Overview", hierarchy = "Track order", bindings = "Saved bindings", issues = "Unresolved", json = "Complete JSON"
    }
    @State private var section = Section.overview

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Saved Project Structure").font(.title2.weight(.semibold))
            Text("Decoded from the preserved CPR source. This snapshot excludes later Rebase edits. Saved routing and level values remain unresolved for whole-project playback.")
                .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 4) {
                ForEach(Section.allCases, id: \.self) { item in
                    Button { section = item } label: {
                        Text(item.rawValue).font(.system(size: 12, weight: .medium))
                            .frame(maxWidth: .infinity).padding(.vertical, 8)
                            .background(section == item ? Color.accentColor.opacity(0.22) : .clear,
                                        in: RoundedRectangle(cornerRadius: 6))
                    }.buttonStyle(.plain).accessibilityValue(section == item ? "Selected" : "")
                }
            }.padding(4).background(.black.opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
            Group {
                switch section {
                case .overview: overview
                case .hierarchy: hierarchy
                case .bindings: bindings
                case .issues: issues
                case .json: StructureJSONView(text: String(decoding: preview.snapshot.reportBytes, as: UTF8.self))
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
            HStack {
                Text("Read-only source snapshot").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Close", action: onClose).keyboardShortcut(.cancelAction)
            }
        }.padding(20).frame(width: 840, height: 640)
    }

    private var overview: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("\(report.entries.count) counted entries · \(report.tracks.count) audio resource bindings · \(report.resourceAssociations.count) other resource associations")
                    .font(.headline)
                Text("Track order includes repeated references, unknown objects and empty slots. Saved bus candidates do not establish a working output route; the complete report retains the underlying object identities, byte ranges and raw numeric values.")
                field("Preserved source SHA-256", report.sourceSHA256)
                field("Report SHA-256", preview.snapshot.reportSHA256)
                field("Saved project manifest SHA-256", preview.snapshot.projectManifestSHA256)
                field("Size", "\(report.sourceByteCount) source bytes · \(preview.snapshot.reportBytes.count) report bytes")
            }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
        }.textSelection(.enabled)
    }

    private var hierarchy: some View {
        List(Array(report.entries.enumerated()), id: \.offset) { _, entry in
            VStack(alignment: .leading, spacing: 5) {
                Text(entry.path.map(String.init).joined(separator: " / ") + " · " + (entry.object?.className ?? "Empty slot"))
                    .font(.headline)
                Text(entry.role + (entry.repeatedIdentity ? " · repeated reference" : ""))
                    .foregroundStyle(.secondary)
                if let object = entry.object {
                    Text("Source object \(object.identityOffset) · version \(object.version)").font(.caption.monospaced())
                }
            }.padding(.vertical, 4)
        }.textSelection(.enabled)
    }

    private var bindings: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 18) {
                if report.tracks.isEmpty { Text("No audio resource bindings were decoded from this source.") }
                ForEach(Array(report.tracks.enumerated()), id: \.offset) { _, track in
                    VStack(alignment: .leading, spacing: 7) {
                        Text("Audio track · source object \(track.track.identityOffset)").font(.headline)
                        field("Saved provider", track.providerName ?? "Not decoded")
                        field("Saved association", "tag \(track.tag.map(String.init) ?? "unknown") · index \(track.providerIndex.map(String.init) ?? "unknown")")
                        field("Retained state", track.stateRepresentation + (track.stateExtentKnown ? " · complete extent" : " · extent unresolved"))
                        field("Saved output bus value", number(track.outputBusValue))
                        field("Saved Volume value", number(track.volumeValue))
                        Text("\(track.busCandidates.count) bus descriptions · \(track.savedDestinationCandidates.count) saved destination candidates")
                        Text("Effective routing and processing unresolved").foregroundStyle(.orange)
                    }
                    Divider()
                }
                if !report.resourceAssociations.isEmpty {
                    Text("Other resource associations").font(.headline)
                    ForEach(Array(report.resourceAssociations.enumerated()), id: \.offset) { _, association in
                        Text("\(association.track.className) @ \(association.track.identityOffset) → \(association.resource?.className ?? "empty resource")\n\(association.scope)")
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
        }.textSelection(.enabled)
    }

    private var issues: some View {
        List(Array(report.issues.enumerated()), id: \.offset) { _, issue in
            VStack(alignment: .leading, spacing: 5) {
                Text(issue.code).font(.headline)
                Text(issue.detail)
                Text("Source bytes \(issue.span.offset)…\(issue.span.offset + issue.span.byteCount)").font(.caption.monospaced()).foregroundStyle(.secondary)
            }.padding(.vertical, 4)
        }.textSelection(.enabled)
    }

    private func field(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.system(size: 12, design: .monospaced)).fixedSize(horizontal: false, vertical: true)
        }
    }
    private func number(_ value: CPRNativeSavedNumber?) -> String {
        guard let value else { return "Not decoded" }
        return value.encoding + " · " + (value.integer ?? value.floatingPointBits.map { "raw bits 0x" + $0 } ?? "unknown")
    }
}

/// AppKit keeps selection and scrolling responsive for the bounded full report.
private struct StructureJSONView: NSViewRepresentable {
    let text: String
    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true; scroll.hasHorizontalScroller = true
        let view = NSTextView()
        view.isEditable = false; view.isSelectable = true; view.isRichText = false
        view.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        view.textColor = .labelColor; view.backgroundColor = .textBackgroundColor
        view.isVerticallyResizable = true; view.isHorizontallyResizable = true
        view.autoresizingMask = [.width]
        view.textContainer?.widthTracksTextView = false
        view.textContainer?.containerSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        view.textContainerInset = NSSize(width: 12, height: 12)
        view.string = text; scroll.documentView = view
        return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) {
        if let view = scroll.documentView as? NSTextView, view.string != text { view.string = text }
    }
}
