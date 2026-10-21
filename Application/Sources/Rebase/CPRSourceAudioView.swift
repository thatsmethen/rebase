import SwiftUI
import RebaseCore

struct CPRSourceAudioView: View {
    let inspection: CPRSourceAudioInspection
    let onPlay: (CPRSourceEventPlaybackMode) -> Void
    @State private var playbackMode: CPRSourceEventPlaybackMode = .sourceRate

    private var playbackUnavailableReason: String? {
        switch playbackMode {
        case .sourceRate: return inspection.timelinePlaybackUnavailableReason
        case .nativeTimelineSourceRate: return inspection.nativeTimelinePlaybackUnavailableReason
        case .nativeTimelineProjectClock: return inspection.nativeProjectClockPlaybackUnavailableReason
        case .nativeTimelineSavedProjectClock: return inspection.nativeSavedProjectClockPlaybackUnavailableReason
        case .nativeMode0ProjectRate: return inspection.rateConvertedPlaybackUnavailableReason
        case .nativeMode2ProjectRate: return inspection.mode2PlaybackUnavailableReason
        case .nativeMode1ProjectRate: return inspection.mode1PlaybackUnavailableReason
        }
    }
    let onRender: () -> Void
    let onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Source Audio").font(.title2.bold())
            Text(inspection.name).font(.headline).textSelection(.enabled)
            Text("Saved Reference event settings").font(.caption).foregroundStyle(.secondary)
            Grid(alignment: .leading, horizontalSpacing: 28, verticalSpacing: 10) {
                if let setup = inspection.savedProjectAudioSetup {
                    row("Saved project rate", String(format: "%.9g Hz · factor %.9g",
                        Double(Float(bitPattern: setup.baseRateBits)), Double(bitPattern: setup.factorBits)))
                }
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
            Text("Source-event audio · Research").font(.headline)
            Text("Reconstructs this attached source and saved event gain with fresh source state and no external pitch context. Original-rate audition preserves the source sample rate. Timeline audition plays only this event, bypassing project effects, mixer, routing and automation. Full project playback remains unresolved.")
                .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            if let reason = inspection.localRenderUnavailableReason {
                Label(reason, systemImage: "info.circle").font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("Exports a Float32 WAV from matching attached PCM24 WAV media. The event stays unresolved in the project.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Picker("Audition rate", selection: $playbackMode) {
                Text("Original source rate").tag(CPRSourceEventPlaybackMode.sourceRate)
                Text("Native timeline reader · original rate").tag(CPRSourceEventPlaybackMode.nativeTimelineSourceRate)
                Text("Native timeline reader · Rebase clock, unconverted").tag(CPRSourceEventPlaybackMode.nativeTimelineProjectClock)
                Text("Native timeline reader · saved CPR clock, unconverted").tag(CPRSourceEventPlaybackMode.nativeTimelineSavedProjectClock)
                Text("Project rate · native linear mode 0").tag(CPRSourceEventPlaybackMode.nativeMode0ProjectRate)
                Text("Project rate · native sinc mode 1").tag(CPRSourceEventPlaybackMode.nativeMode1ProjectRate)
                Text("Project rate · SoXR mode 2").tag(CPRSourceEventPlaybackMode.nativeMode2ProjectRate)
            }.pickerStyle(.menu).accessibilityLabel("Source event audition rate")
            if playbackMode == .nativeTimelineSourceRate, playbackUnavailableReason == nil {
                Text("Reconstructs this event’s saved start, trim and source offset using the preserved source clock, then reads absolute timeline windows at the source rate. Project tempo edits do not alter this audition. Track effects, mixing and routing remain bypassed.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            if playbackMode == .nativeTimelineSourceRate, let range = inspection.nativeTimelineRange {
                Text(String(format: "Source timeline · start %.6f s · duration %.6f s · media offset %.6f s", range.position, range.duration, range.offset))
                    .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if playbackMode == .nativeTimelineProjectClock {
                Text("Reads source frames at this Rebase project’s \(Int(inspection.projectSampleRate)) Hz clock without conversion. A different source rate changes speed and pitch. Saved source timing is preserved; this option uses the current Rebase rate, including any edits since import.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                if let range = inspection.nativeProjectClockRange {
                    Text(String(format: "Project clock · start %.6f s · duration %.6f s · saved offset %.6f s", range.position, range.duration, range.offset))
                        .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if playbackMode == .nativeTimelineSavedProjectClock {
                Text("Uses the project rate saved in the original CPR. Rebase rate and tempo edits do not alter this audition. Source frames remain unconverted, so a different source rate changes speed and pitch. Live Reference device settings are not reconstructed.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                if let range = inspection.nativeSavedProjectClockRange {
                    Text(String(format: "Saved CPR clock · start %.6f s · duration %.6f s · saved offset %.6f s", range.position, range.duration, range.offset))
                        .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if playbackMode == .nativeMode0ProjectRate, playbackUnavailableReason == nil {
                Text("Converts \(Int(inspection.sourceSampleRate ?? 0)) → \(Int(inspection.projectSampleRate)) Hz in blocks with the reconstructed stereo mode 0 converter. This is an explicit mode choice; Reference’s default converter is unverified. Seeking restores conversion state from the event’s start. No extra tail samples are added.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            if playbackMode == .nativeMode2ProjectRate, playbackUnavailableReason == nil {
                Text("Reconstructs the native mode 2 wrapper using public SoXR 0.1.3 at \(Int(inspection.projectSampleRate)) Hz. Seeking rebuilds state from the event’s start. Reference sample equivalence remains unverified.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            if playbackMode == .nativeMode1ProjectRate, playbackUnavailableReason == nil {
                Text("Reconstructs the native mode 1 filter at \(Int(inspection.projectSampleRate)) Hz. This is an explicit mode choice. Seeking recreates state and replays from the event’s start. Reference sample equivalence remains unverified.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            if let reason = playbackUnavailableReason,
               reason != inspection.localRenderUnavailableReason {
                Label(reason, systemImage: "info.circle").font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text("Source SHA-256 \(inspection.sourceSHA256)\nEvent \(inspection.eventIdentity) · Track \(inspection.trackIdentity)")
                .font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary).textSelection(.enabled)
            HStack {
                Button("Close", action: onClose).keyboardShortcut(.cancelAction)
                Spacer()
                Button("Render Source Event…", action: onRender)
                    .disabled(inspection.localRenderUnavailableReason != nil)
                    .buttonStyle(.bordered)
                Button("Play Event on Timeline") { onPlay(playbackMode) }
                    .disabled(playbackUnavailableReason != nil)
                    .help(playbackUnavailableReason ?? "Audition only this source event using the timeline transport. Source and media are verified again before playback.")
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
