import AppKit
import SwiftUI
import RebaseCore

@main
struct RebaseApp: App {
    @NSApplicationDelegateAdaptor(RebaseAppDelegate.self) private var appDelegate
    @StateObject private var session = StudioSession()

    var body: some Scene {
        WindowGroup {
            StudioView(session: session)
                .frame(minWidth: 1040, minHeight: 650)
                .preferredColorScheme(.dark)
                .onOpenURL { session.openURL($0) }
                .onAppear {
                    appDelegate.session = session
                    NSApplication.shared.setActivationPolicy(.regular)
                    NSApplication.shared.activate(ignoringOtherApps: true)
                }
        }
        .defaultSize(width: 1380, height: 860)
        .windowStyle(.hiddenTitleBar)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("New Project") { session.newProject() }.keyboardShortcut("n")
                Button("Open Project…") { session.openProject() }.keyboardShortcut("o")
            }
            CommandGroup(replacing: .saveItem) {
                Button("Save Project") { session.saveProject() }.keyboardShortcut("s")
                Button("Save Project As…") { session.saveProjectAs() }.keyboardShortcut("s", modifiers: [.command, .shift])
            }
            CommandGroup(after: .saveItem) {
                Button("Import Audio…") { session.importAudio() }.keyboardShortcut("i")
                Button("Export Mixdown…") { session.exportMix() }.keyboardShortcut("e")
                Divider()
                Button("Import DAWproject…") { session.importDAWProject() }
                Button("Export DAWproject…") { session.exportDAWProject() }
                Button("Import Reference Project…") { session.importCPRProject() }
                Button("Reference Import Report…") { session.showCPRCompatibility() }
                    .disabled(session.cprCompatibility == nil)
                Divider()
                Button("Convert Ambisonics…") { AmbisonicExport.present() }
            }
            CommandMenu("Transport") {
                Button(session.isPlaying ? "Pause" : (session.sourceEventPlaybackInfo == nil ? "Play" : "Play Source Event")) { session.togglePlayback() }.keyboardShortcut(.space, modifiers: [])
                if session.sourceEventPlaybackInfo != nil {
                    Button("Exit Source Event Audition") { session.exitSourceEventAudition() }
                }
                Button("Return to Start") { session.returnToStart() }.keyboardShortcut(.home, modifiers: [])
                Button("Split Selected Clip at Playhead") { session.splitSelected() }.keyboardShortcut("t")
                Button("Delete Selected Clip") { session.deleteSelected() }.keyboardShortcut(.delete, modifiers: [])
            }
            CommandGroup(replacing: .undoRedo) {
                Button("Undo") { session.undo() }.keyboardShortcut("z").disabled(!session.canUndo)
                Button("Redo") { session.redo() }.keyboardShortcut("z", modifiers: [.command, .shift]).disabled(!session.canRedo)
            }
        }
    }
}

@MainActor
final class RebaseAppDelegate: NSObject, NSApplicationDelegate {
    weak var session: StudioSession?
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        session?.confirmProjectReplacement() == false ? .terminateCancel : .terminateNow
    }
}

struct StudioView: View {
    @ObservedObject var session: StudioSession
    private let line = Color.white.opacity(0.08)

    var body: some View {
        VStack(spacing: 0) {
            transport
            if let info = session.sourceEventPlaybackInfo { sourceAuditionBanner(info) }
            Divider().overlay(line)
            HStack(spacing: 0) {
                inspector.frame(width: 218)
                Rectangle().fill(line).frame(width: 1)
                VStack(spacing: 0) {
                    HStack {
                        Text("PROJECT").font(.system(size: 10, weight: .semibold, design: .monospaced)).tracking(1.7).foregroundStyle(.secondary)
                        Text(session.project.name).font(.system(size: 13, weight: .medium))
                        if session.isDirty { Circle().fill(Color.orange).frame(width: 5, height: 5) }
                        if session.cprCompatibility != nil {
                            Button("CPR · Partial import") { session.showCPRCompatibility() }
                                .font(.caption).foregroundStyle(.orange)
                                .help("Review recovered data and native features not restored")
                        }
                        Spacer()
                        Button { session.splitSelected() } label: { Label("Split", systemImage: "scissors") }.disabled(session.selectedClip == nil)
                        Button { session.deleteSelected() } label: { Image(systemName: "trash") }.disabled(session.selectedClipID == nil)
                            .help(session.selectedUnresolvedEvent == nil ? "Delete selected clip" : "Remove selected unresolved event; original CPR retained")
                            .accessibilityLabel(session.selectedUnresolvedEvent == nil ? "Delete selected clip" : "Remove selected unresolved event")
                        Button { session.importAudio() } label: { Label("Import Audio", systemImage: "plus") }
                    }.buttonStyle(.borderless).font(.system(size: 12)).padding(.horizontal, 18).frame(height: 46)
                    Divider().overlay(line)
                    TimelineView(project: session.project, selectedClipID: session.selectedClipID,
                                 selectedTrackID: session.selectedTrackID, playhead: session.playhead,
                                 waveformPeaks: session.waveformPeaks, musicalRuler: $session.musicalRuler,
                                 snapMode: $session.snapMode, gridRelative: $session.gridRelative,
                                 onSelectClip: { session.selectClip($0) },
                                 onSelectTrack: { session.selectTrack($0) },
                                 onMoveClip: { session.moveClip($0, to: $1) },
                                 onTrimEnd: { session.trimClip($0, duration: $1) },
                                 onSeek: { session.seek($0) })
                    Divider().overlay(line)
                    MixerView(project: session.project, selectedTrackID: session.selectedTrackID,
                              onSelectTrack: { session.selectTrack($0) },
                              onGainChange: { session.setGain($0, $1) },
                              onPanChange: { session.setPan($0, $1) },
                              onMuteToggle: { session.toggleMute($0) },
                              onSoloToggle: { session.toggleSolo($0) })
                        .frame(height: 252)
                }
            }
            Divider().overlay(line)
            HStack {
                Circle().fill(session.isPlaying ? Color.green : Color.gray).frame(width: 5, height: 5)
                Text(session.status).lineLimit(1)
                Spacer()
                if let info = session.sourceEventPlaybackInfo {
                    Text("1 source event   ·   \(Int(info.sampleRate)) Hz   ·   \(info.mode.displayName)")
                } else {
                    Text("\(session.project.tracks.count) tracks   ·   \(Int(session.project.sampleRate)) Hz   ·   Stereo out")
                }
            }.font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary).padding(.horizontal, 16).frame(height: 28)
        }
        .sheet(isPresented: $session.showTempoEditor) { TempoEditor(session: session) }
        .sheet(isPresented: $session.showAutomationEditor) {
            if let id = session.selectedTrackID { AutomationEditor(session: session, trackID: id) }
        }
        .sheet(item: $session.cprImportPreview) { preview in
            CPRImportReviewView(preview: preview,
                onImport: { session.confirmCPRImport(preview) },
                onCancel: { session.cprImportPreview = nil })
        }
        .sheet(item: $session.cprSourceAudioInspection, onDismiss: session.completeCPRSourceInspectionDismissal) { inspection in
            CPRSourceAudioView(inspection: inspection,
                onPlay: { session.playCPRSourceEvent(inspection.eventID, mode: $0) },
                onRender: { session.renderCPRSourceEvent(inspection.eventID) },
                onClose: { session.cprSourceAudioInspection = nil })
        }
        .background(Color(red: 0.075, green: 0.085, blue: 0.10))
        .tint(Color(red: 0.32, green: 0.75, blue: 0.83))
        .alert("Rebase", isPresented: Binding(get: { session.errorMessage != nil }, set: { if !$0 { session.errorMessage = nil } })) {
            Button("OK") { session.errorMessage = nil }
        } message: { Text(session.errorMessage ?? "") }
    }

    private func sourceAuditionBanner(_ info: CPRSourceEventPlaybackInfo) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "headphones").font(.system(size: 17))
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 8) {
                    Text("SOURCE EVENT AUDITION").font(.system(size: 10, weight: .bold, design: .monospaced)).tracking(1)
                    Text(info.name).font(.system(size: 12, weight: .semibold)).lineLimit(1)
                }
                if info.mode == .nativeMode0ProjectRate {
                    Text("Native linear mode 0 · \(Int(info.sourceSampleRate)) → \(Int(info.sampleRate)) Hz · streamed stereo")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                } else if info.mode == .nativeMode1ProjectRate {
                    Text("Native sinc mode 1 · \(Int(info.sourceSampleRate)) → \(Int(info.sampleRate)) Hz · reconstructed filter")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                } else if info.mode == .nativeMode2ProjectRate {
                    Text("SoXR mode 2 · \(Int(info.sourceSampleRate)) → \(Int(info.sampleRate)) Hz · reconstructed wrapper")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                }
                Text("Only this event · fresh source state · project effects, mixer, routing and automation bypassed")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Button("Exit Audition") { session.exitSourceEventAudition() }
                .accessibilityLabel("Exit source event audition")
                .help("Stop this event and return the transport to project playback")
                .buttonStyle(.bordered)
        }
        .foregroundStyle(Color.cyan)
        .padding(.horizontal, 20).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cyan.opacity(0.09))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Source event audition mode")
    }

    private var transport: some View {
        HStack(spacing: 18) {
            HStack(spacing: 9) {
                Image(systemName: "waveform.path").font(.system(size: 23, weight: .medium)).foregroundStyle(Color.cyan.opacity(0.85))
                Text("REBASE").font(.system(size: 12, weight: .bold, design: .monospaced)).tracking(3)
            }.frame(width: 180, alignment: .leading)
            HStack(spacing: 4) {
                Button { session.returnToStart() } label: { Image(systemName: "backward.end.fill").frame(width: 30, height: 30) }
                    .help("Return to start").accessibilityLabel("Return to start")
                Button { session.stop() } label: { Image(systemName: "stop.fill").frame(width: 30, height: 30) }
                    .help("Stop").accessibilityLabel("Stop")
                Button { session.togglePlayback() } label: {
                    Image(systemName: session.isPlaying ? "pause.fill" : "play.fill")
                        .foregroundStyle(session.isPlaying ? Color.black : Color.white)
                        .frame(width: 43, height: 32)
                        .background(session.isPlaying ? Color.cyan : Color.white.opacity(0.09), in: RoundedRectangle(cornerRadius: 5))
                }
                .help(session.sourceEventPlaybackInfo == nil ? "Play / pause · Space" : "Play / pause this source event · Space")
                .accessibilityLabel(session.isPlaying ? "Pause" : (session.sourceEventPlaybackInfo == nil ? "Play" : "Play source event"))
            }.buttonStyle(.plain)
            Text(Self.timecode(session.playhead)).font(.system(size: 23, weight: .medium, design: .monospaced)).monospacedDigit().frame(width: 188)
            Divider().frame(height: 29)
            VStack(alignment: .leading, spacing: 3) {
                Text("TEMPO").font(.system(size: 9, weight: .semibold)).foregroundStyle(.secondary)
                HStack(spacing: 4) {
                    TextField("120", value: Binding(get: { session.project.tempo }, set: { session.setTempo($0) }), format: .number.precision(.fractionLength(0...1)))
                        .textFieldStyle(.plain).frame(width: 45).font(.system(size: 14, design: .monospaced))
                        .disabled(session.project.tempoMap.nativeClock != nil)
                        .help(session.project.tempoMap.nativeClock == nil ? "Project tempo" : "Recovered Reference timing. Open Tempo Track to change timing mode before editing.")
                    Text("BPM").font(.system(size: 9)).foregroundStyle(.secondary)
                }
            }
            Button("Tempo Track") { session.showTempoEditor = true }
            Text(session.musicalPositionText).font(.system(size: 12, design: .monospaced)).monospacedDigit().accessibilityLabel("Musical position").accessibilityValue(session.musicalPositionText)
            Spacer()
            outputMeter
            Button { session.saveProject() } label: { Image(systemName: "square.and.arrow.down") }.help("Save project")
            Button("Export Mixdown") { session.exportMix() }.buttonStyle(.bordered)
        }.padding(.horizontal, 20).frame(height: 74)
    }

    private var outputMeter: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(session.sourceEventPlaybackInfo == nil ? "STEREO OUT" : "EVENT OUT")
                .font(.system(size: 9, weight: .semibold)).foregroundStyle(.secondary)
            ForEach(0..<2, id: \.self) { channel in
                let peak = session.outputPeaks[channel]
                let decibels = peak > 0 ? 20 * log10(Double(peak)) : -96
                HStack(spacing: 5) {
                    Text(channel == 0 ? "L" : "R").font(.system(size: 8, design: .monospaced)).foregroundStyle(.secondary)
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.white.opacity(0.08))
                        Capsule().fill(peak > 1 ? Color.red : Color.green.opacity(0.8))
                            .frame(width: 76 * min(1, max(0, (decibels + 60) / 60)))
                    }.frame(width: 76, height: 4)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Stereo output peaks")
        .accessibilityValue("Left \(session.outputPeaks[0]), right \(session.outputPeaks[1])")
        .help("Peak levels measured at the audio engine's stereo output")
    }

    private var inspector: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 18) {
            Text("INSPECTOR").font(.system(size: 10, weight: .semibold, design: .monospaced)).tracking(1.6).foregroundStyle(.secondary)
            if let track = session.selectedTrack {
                Text(track.name).font(.system(size: 18, weight: .medium)).lineLimit(2)
                Label("Audio track", systemImage: "waveform").font(.system(size: 11)).foregroundStyle(.secondary)
                Divider()
                field("LEVEL", String(format: "%+.1f dB", track.gainDB))
                field("PAN", abs(track.pan) < 0.01 ? "Center" : String(format: "%.0f %@", abs(track.pan) * 100, track.pan < 0 ? "L" : "R"))
                Picker("Time base", selection: Binding(get: { track.timeBase }, set: { session.setTrackTimeBase(track.id, $0) })) {
                    Text("Linear").tag(ClipTimeBase.seconds)
                    Text("Musical").tag(ClipTimeBase.musical)
                }.font(.caption).help("Set the time base for playable clips on this track")
                Button("Edit Automation…") { session.showAutomationEditor = true }
                if !track.automation.isEmpty {
                    let readingLanes = track.automation.filter { $0.isReadEnabled }.count
                    Text("\(readingLanes) automation \(readingLanes == 1 ? "lane" : "lanes") reading").font(.caption).foregroundStyle(.secondary)
                }
                if let clip = session.selectedClip {
                    Divider()
                    Text("SELECTED CLIP").font(.system(size: 9, weight: .semibold)).tracking(1.2).foregroundStyle(.secondary)
                    Text(clip.name).font(.system(size: 12, weight: .medium)).lineLimit(2)
                    field("START", Self.timecode(clip.position))
                    field("LENGTH", String(format: "%.3f s", clip.duration))
                    field("SOURCE OFFSET", String(format: "%.3f s", clip.sourceOffset))
                }
                if let event = session.selectedUnresolvedEvent {
                    Divider()
                    Label("UNRESOLVED AUDIO", systemImage: "exclamationmark.triangle")
                        .font(.system(size: 9, weight: .semibold)).foregroundStyle(.orange)
                    Text(event.name).font(.system(size: 12, weight: .medium)).lineLimit(3)
                    if let placement = event.placement {
                        field("SAVED START", Self.timecode(placement.position))
                        field("SAVED LENGTH", String(format: "%.3f s", placement.duration))
                    }
                    Text(session.project.attachedMedia(for: event) == nil ? event.placementStatus :
                        (event.placement == nil ? "Saved timing remains unresolved." : "Saved source coordinates recovered."))
                        .font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let file = event.files.first {
                        Text(file.filename).font(.caption).textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("\(file.channels) channels · \(file.sampleRate, specifier: "%.0f") Hz\n\(file.frameCount) declared frames")
                            .font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary)
                    }
                    if let attachment = session.project.attachedMedia(for: event) {
                        Label("Media attached", systemImage: "paperclip").font(.caption)
                        Text(attachment.selectedFilename).font(.caption).textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("User-selected file · \(attachment.bitsPerSample)-bit PCM\nSHA-256 \(attachment.mediaSHA256.prefix(12))…")
                            .font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary)
                    }
                    Button(session.project.attachedMedia(for: event) == nil ? "Attach Media…" : "Replace Attached Media…") {
                        session.attachSelectedCPRMedia()
                    }.font(.caption).disabled(event.files.count != 1 || event.segments.count != 1)
                    Button("Inspect Source Audio…") { session.inspectSelectedCPRSourceAudio() }.font(.caption)
                    Text("Attachment checks the file format and source bounds. Native playback processing remains unresolved.")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    Button("Remove Unresolved Event") { session.deleteSelected() }.font(.caption)
                    Text("Undo is available. The original CPR stays preserved.")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
            } else {
                Image(systemName: "waveform").font(.system(size: 34)).foregroundStyle(.secondary).padding(.top, 18)
                Text("Start with sound.").font(.system(size: 19, weight: .medium))
                Text("Import audio to create your first track. Arrange clips, shape the mix, then export.").font(.system(size: 12)).foregroundStyle(.secondary).lineSpacing(4)
                Button("Import Audio…") { session.importAudio() }.buttonStyle(.borderedProminent)
            }
            Spacer()
            Text("Space  Play / pause\n⌘T  Split at playhead\n⌘I  Import audio").font(.system(size: 10, design: .monospaced)).lineSpacing(6).foregroundStyle(.tertiary)
        }.padding(20).frame(maxWidth: .infinity, alignment: .topLeading)
        }.frame(maxHeight: .infinity, alignment: .topLeading).background(Color.black.opacity(0.12))
    }

    private func field(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label).font(.system(size: 9, weight: .semibold)).tracking(1).foregroundStyle(.secondary)
            Text(value).font(.system(size: 12, design: .monospaced)).monospacedDigit()
        }
    }

    static func timecode(_ seconds: Double) -> String {
        let millis = Int(max(0, seconds) * 1000)
        return String(format: "%02d:%02d:%02d.%03d", millis / 3_600_000, (millis / 60_000) % 60, (millis / 1000) % 60, millis % 1000)
    }
}
