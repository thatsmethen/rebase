import SwiftUI
import RebaseCore

struct CPRSourceAudioView: View {
    let inspection: CPRSourceAudioInspection
    let onRender: () -> Void
    let onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Source Audio").font(.title2.bold())
            Text(inspection.name).font(.headline).textSelection(.enabled)
            Text("Saved Reference event settings").font(.caption).foregroundStyle(.secondary)
            Grid(alignment: .leading, horizontalSpacing: 28, verticalSpacing: 10) {
                row("Event gain", String(format: "%.6g", Double(inspection.volume)))
                row("Phase inversion", inspection.inverted ? "Enabled" : "Off")
                row("Explicit fade in / out", "\(inspection.hasExplicitFadeIn ? "Present" : "None") / \(inspection.hasExplicitFadeOut ? "Present" : "None")")
                row("Warp state", inspection.hasWarpState ? "Present — processing unresolved" : "No saved Warpscale")
                row("Automatic fades", inspection.autoFadeFlags.map { $0 == 0 ? "Disabled · \(inspection.autoFadeOrigin) setting" : "Flags \($0) · \(inspection.autoFadeOrigin) setting" } ?? "Unresolved default")
                if let duration = inspection.autoFadeDuration {
                    row("Saved fade duration", String(format: "%.6g s", duration))
                }
            }.font(.callout)
            Divider()
            Text("Source-event render · Research").font(.headline)
            Text("Reconstructs the attached source and saved event gain at the source sample rate. It assumes fresh source state with no external pitch context. Track effects, mixer, automation and full project playback remain unresolved.")
                .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            if let reason = inspection.localRenderUnavailableReason {
                Label(reason, systemImage: "info.circle").font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("Exports a Float32 WAV from matching attached PCM24 WAV media. The event stays unresolved in the project.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text("Source SHA-256 \(inspection.sourceSHA256)\nEvent \(inspection.eventIdentity) · Track \(inspection.trackIdentity)")
                .font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary).textSelection(.enabled)
            HStack {
                Button("Close", action: onClose).keyboardShortcut(.cancelAction)
                Spacer()
                Button("Render Source Event…", action: onRender)
                    .disabled(inspection.localRenderUnavailableReason != nil)
                    .buttonStyle(.borderedProminent)
            }
        }.padding(28).frame(width: 600)
    }

    private func row(_ label: String, _ value: String) -> some View {
        GridRow {
            Text(label).foregroundStyle(.secondary)
            Text(value).textSelection(.enabled)
        }
    }
}
