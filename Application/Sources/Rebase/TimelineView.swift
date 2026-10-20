import SwiftUI
import RebaseCore

struct TimelineView: View {
    let project: Project
    let selectedClipID: UUID?
    let selectedTrackID: UUID?
    let playhead: Double
    let sourceAudition: CPRSourceEventPlaybackInfo?
    let waveformPeaks: [UUID: [Float]]
    @Binding var musicalRuler: Bool
    @Binding var snapMode: SnapMode
    @Binding var gridRelative: Bool
    let onSelectClip: (UUID?) -> Void
    let onSelectTrack: (UUID) -> Void
    let onMoveClip: (UUID, Double) -> Void
    let onTrimEnd: (UUID, Double) -> Void
    let onSeek: (Double) -> Void

    @State private var pixelsPerSecond: Double = 42
    private let headerWidth: CGFloat = 174
    private let laneHeight: CGFloat = 94
    private let rulerHeight: CGFloat = 32

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            if !project.unresolvedAudioEvents.isEmpty { unresolvedNotice }
            GeometryReader { geometry in
                let availableWidth = max(240, geometry.size.width - headerWidth)
                let contentWidth = max(availableWidth, CGFloat(max(30, max(project.arrangementDuration, sourceAudition?.duration ?? 0) + 8) * pixelsPerSecond))
                ScrollView(.vertical) {
                    HStack(alignment: .top, spacing: 0) {
                        trackHeaders
                        ScrollView(.horizontal) {
                            VStack(spacing: 0) {
                                ruler(width: contentWidth)
                                if project.tracks.isEmpty {
                                    emptyArrangement(width: contentWidth, height: max(170, geometry.size.height - rulerHeight))
                                } else {
                                    ForEach(Array(project.tracks.enumerated()), id: \.element.id) { index, track in
                                        lane(track, index: index, width: contentWidth)
                                    }
                                    TimelineGrid(pixelsPerSecond: pixelsPerSecond, project: musicalRuler ? project : nil)
                                        .frame(width: contentWidth, height: max(60, geometry.size.height - rulerHeight - CGFloat(project.tracks.count) * laneHeight))
                                        .overlay(alignment: .leading) { playheadLine }
                                        .contentShape(Rectangle())
                                        .onSpatialTapGesture { location in seek(at: location.x) }
                                }
                            }
                            .frame(width: contentWidth)
                        }
                        .scrollIndicators(.visible)
                    }
                }
                .scrollIndicators(.visible)
            }
        }
        .background(TimelineColors.canvas)
    }

    private var unresolvedNotice: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("\(project.unresolvedAudioEvents.count) unresolved audio event\(project.unresolvedAudioEvents.count == 1 ? "" : "s") · \(project.unresolvedAudioEvents.filter { project.attachedMedia(for: $0) != nil }.count) media attached · playback pending",
                  systemImage: "exclamationmark.triangle")
                .font(.system(size: 11)).foregroundStyle(.orange)
            let unplaced = project.unresolvedAudioEvents.filter { eventRange($0) == nil }
            if !unplaced.isEmpty {
                ScrollView(.horizontal) {
                    HStack {
                        ForEach(unplaced) { event in
                            Button { onSelectClip(event.id) } label: {
                                Label("Timing unresolved · \(event.name)", systemImage: "clock.badge.questionmark")
                                    .font(.caption).lineLimit(1)
                            }
                            .buttonStyle(.bordered)
                            .tint(selectedClipID == event.id ? .orange : .gray)
                            .accessibilityLabel("Inspect unplaced audio event \(event.name)")
                        }
                    }
                }
            }
        }.padding(.horizontal, 14).padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.orange.opacity(0.06))
    }

    private var toolbar: some View {
        HStack(spacing: 12) {
            Text("ARRANGEMENT")
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .tracking(1.4)
                .foregroundStyle(TimelineColors.secondary)
            Spacer()
            Toggle("Bars", isOn: $musicalRuler).toggleStyle(.button).font(.caption)
            Picker("Snap", selection: $snapMode) {
                ForEach(SnapMode.allCases) { Text($0.rawValue).tag($0) }
            }.frame(width: 115).font(.caption)
            Toggle("Relative", isOn: $gridRelative).toggleStyle(.button).font(.caption).disabled(snapMode == .off)
            Text("Drag · Trim")
                .font(.system(size: 10))
                .foregroundStyle(TimelineColors.secondary)
                .lineLimit(1)
            HStack(spacing: 2) {
                Button { pixelsPerSecond = max(4, pixelsPerSecond / 1.5) } label: {
                    Image(systemName: "minus.magnifyingglass").frame(width: 27, height: 26)
                }
                .disabled(pixelsPerSecond <= 4)
                .help("Zoom out")
                .accessibilityLabel("Zoom out of arrangement")
                Button { pixelsPerSecond = min(420, pixelsPerSecond * 1.5) } label: {
                    Image(systemName: "plus.magnifyingglass").frame(width: 27, height: 26)
                }
                .disabled(pixelsPerSecond >= 420)
                .help("Zoom in")
                .accessibilityLabel("Zoom into arrangement")
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color.white.opacity(0.8))
        }
        .padding(.horizontal, 14)
        .frame(height: 34)
        .background(TimelineColors.panel)
        .overlay(alignment: .bottom) { TimelineColors.line.frame(height: 1) }
    }

    private var trackHeaders: some View {
        VStack(spacing: 0) {
            HStack {
                Text("TRACKS")
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .tracking(1)
                Spacer()
                Text(String(format: "%02d", project.tracks.count))
                    .font(.system(size: 10, design: .monospaced))
            }
            .foregroundStyle(TimelineColors.secondary)
            .padding(.horizontal, 14)
            .frame(height: rulerHeight)
            .overlay(alignment: .bottom) { TimelineColors.line.frame(height: 1) }
            ForEach(Array(project.tracks.enumerated()), id: \.element.id) { index, track in
                Button { onSelectTrack(track.id) } label: {
                    HStack(alignment: .top, spacing: 10) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(TimelineColors.track(index))
                            .frame(width: 3, height: 34)
                        VStack(alignment: .leading, spacing: 8) {
                            Text(track.name)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(Color.white.opacity(0.9))
                                .lineLimit(1)
                            HStack(spacing: 7) {
                                Image(systemName: "waveform")
                                Text(track.unresolvedAudioEvents.isEmpty
                                    ? "\(track.clips.count) \(track.clips.count == 1 ? "clip" : "clips")"
                                    : "\(track.clips.count) clips · \(track.unresolvedAudioEvents.count) unresolved")
                                Spacer(minLength: 0)
                                if track.isMuted { Text("M").foregroundStyle(Color.orange) }
                                if track.isSolo { Text("S").foregroundStyle(Color.cyan) }
                            }
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(TimelineColors.secondary)
                        }
                    }
                    .padding(.horizontal, 12)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .frame(height: laneHeight)
                .background(selectedTrackID == track.id ? Color.white.opacity(0.055) : Color.clear)
                .overlay(alignment: .bottom) { TimelineColors.line.frame(height: 1) }
                .help("Select \(track.name)")
                .accessibilityLabel("Select track \(index + 1), \(track.name)")
            }
            Spacer(minLength: 0)
        }
        .frame(width: headerWidth)
        .background(TimelineColors.panel)
        .overlay(alignment: .trailing) { TimelineColors.line.frame(width: 1) }
    }

    private func ruler(width: CGFloat) -> some View {
        TimelineRuler(pixelsPerSecond: pixelsPerSecond, project: musicalRuler ? project : nil)
            .frame(width: width, height: rulerHeight)
            .background(TimelineColors.panel)
            .overlay(alignment: .leading) {
                VStack(spacing: 0) {
                    Image(systemName: "arrowtriangle.down.fill")
                        .font(.system(size: 9))
                    Rectangle().frame(width: 1)
                }
                .foregroundStyle(TimelineColors.playhead)
                .frame(width: 9, height: rulerHeight)
                .offset(x: CGFloat(max(0, playhead) * pixelsPerSecond) - 4.5)
                .allowsHitTesting(false)
            }
            .clipped()
            .contentShape(Rectangle())
            .onSpatialTapGesture { location in seek(at: location.x) }
            .accessibilityLabel(musicalRuler ? "Timeline ruler in bars and beats" : "Timeline ruler in minutes and seconds")
    }

    private func lane(_ track: Track, index: Int, width: CGFloat) -> some View {
        ZStack(alignment: .leading) {
            TimelineGrid(pixelsPerSecond: pixelsPerSecond, project: musicalRuler ? project : nil)
                .background(selectedTrackID == track.id ? Color.white.opacity(0.025) : Color.clear)
                .contentShape(Rectangle())
                .onSpatialTapGesture { location in
                    onSelectTrack(track.id)
                    onSelectClip(nil)
                    seek(at: location.x)
                }
            ForEach(track.clips) { clip in
                TimelineClipView(
                    clip: clip, peaks: waveformPeaks[clip.id] ?? [],
                    color: TimelineColors.track(index), selected: selectedClipID == clip.id,
                    attenuated: track.isMuted || (project.tracks.contains(where: \.isSolo) && !track.isSolo),
                    pixelsPerSecond: pixelsPerSecond,
                    onSelect: { onSelectTrack(track.id); onSelectClip(clip.id) },
                    onMove: { onMoveClip(clip.id, $0) },
                    onTrim: { onTrimEnd(clip.id, $0) }
                )
                .padding(.vertical, 9)
                .zIndex(selectedClipID == clip.id ? 2 : 1)
            }
            ForEach(track.unresolvedAudioEvents) { event in
                if let placement = eventRange(event) {
                    Button { onSelectTrack(track.id); onSelectClip(event.id) } label: {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(event.name).font(.system(size: 11, weight: .semibold)).lineLimit(1)
                            Label("\(sourceAudition?.eventID == event.id ? "Source event audition" : "Unresolved audio") · \(placement.duration, specifier: "%.3f") s", systemImage: "waveform.slash")
                                .font(.system(size: 10)).lineLimit(1)
                        }
                        .padding(10).frame(width: max(24, placement.duration * pixelsPerSecond), height: laneHeight - 18, alignment: .topLeading)
                        .background(Color.orange.opacity(selectedClipID == event.id ? 0.16 : 0.07))
                        .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(Color.orange.opacity(0.75),
                            style: StrokeStyle(lineWidth: selectedClipID == event.id ? 2 : 1, dash: [5, 3])))
                        .foregroundStyle(Color.orange.opacity(0.95))
                    }
                    .buttonStyle(.plain)
                    .offset(x: placement.position * pixelsPerSecond)
                    .help(sourceAudition?.eventID == event.id && sourceAudition?.timelineRange != nil
                        ? "Source-clock placement for this audition. The original import remains unchanged."
                        : project.attachedMedia(for: event) == nil
                        ? "Saved source coordinates. Media and playback processing remain unresolved."
                        : "Saved source coordinates. Media attached; native playback processing remains unresolved.")
                    .accessibilityLabel("Inspect unresolved audio event \(event.name), start \(placement.position) seconds, duration \(placement.duration) seconds")
                    .zIndex(selectedClipID == event.id ? 3 : 1)
                }
            }
        }
        .frame(width: width, height: laneHeight)
        .overlay(alignment: .leading) { playheadLine }
        .overlay(alignment: .bottom) { TimelineColors.line.frame(height: 1) }
        .clipped()
    }

    private func eventRange(_ event: UnresolvedCPRAudioEvent) -> (position: Double, duration: Double)? {
        if sourceAudition?.eventID == event.id, let range = sourceAudition?.timelineRange {
            return (range.position, range.duration)
        }
        return event.placement.map { (position: $0.position, duration: $0.duration) }
    }

    private var playheadLine: some View {
        Rectangle()
            .fill(TimelineColors.playhead)
            .frame(width: 1)
            .offset(x: CGFloat(max(0, playhead) * pixelsPerSecond))
            .allowsHitTesting(false)
    }

    private func emptyArrangement(width: CGFloat, height: CGFloat) -> some View {
        TimelineGrid(pixelsPerSecond: pixelsPerSecond, project: musicalRuler ? project : nil)
            .frame(width: width, height: height)
            .overlay(alignment: .topLeading) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Your arrangement starts here")
                        .font(.system(size: 17, weight: .medium))
                        .foregroundStyle(Color.white.opacity(0.8))
                    Text("Import an audio file to see its waveform and place it in time.")
                        .font(.system(size: 12))
                        .foregroundStyle(TimelineColors.secondary)
                }
                .padding(30)
                .allowsHitTesting(false)
            }
            .overlay(alignment: .leading) { playheadLine }
            .contentShape(Rectangle())
            .onSpatialTapGesture { location in seek(at: location.x) }
    }

    private func seek(at x: CGFloat) {
        onSeek(max(0, Double(x) / pixelsPerSecond))
    }
}

private struct TimelineClipView: View {
    let clip: Clip
    let peaks: [Float]
    let color: Color
    let selected: Bool
    let attenuated: Bool
    let pixelsPerSecond: Double
    let onSelect: () -> Void
    let onMove: (Double) -> Void
    let onTrim: (Double) -> Void
    @State private var moveOffset: Double = 0
    @State private var trimDuration: Double?
    @State private var moving = false

    private var duration: Double { trimDuration ?? clip.duration }
    private var width: CGFloat { max(14, CGFloat(duration * pixelsPerSecond)) }
    private var position: Double { max(0, clip.position + moveOffset) }

    var body: some View {
        ZStack(alignment: .trailing) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 5) {
                    Text(clip.name)
                        .font(.system(size: 10, weight: .semibold))
                        .lineLimit(1)
                    Spacer(minLength: 0)
                }
                .foregroundStyle(Color.white.opacity(0.94))
                .padding(.horizontal, 8)
                .frame(height: 24)
                .background(color.opacity(selected ? 0.34 : 0.2))
                WaveformShape(peaks: peaks, color: color.opacity(0.9))
                    .frame(width: max(14, CGFloat(clip.duration * pixelsPerSecond)))
                    .frame(maxHeight: .infinity)
                    .frame(width: width, alignment: .leading)
                    .clipped()
                    .padding(.vertical, 5)
            }
            .frame(width: width)
            .background(color.opacity(selected ? 0.19 : 0.105))
            .clipShape(RoundedRectangle(cornerRadius: 5))
            .overlay {
                RoundedRectangle(cornerRadius: 5)
                    .strokeBorder(selected ? color.opacity(0.95) : color.opacity(0.42), lineWidth: selected ? 1.5 : 1)
            }
            .contentShape(Rectangle())
            .onTapGesture(perform: onSelect)
            .gesture(DragGesture(minimumDistance: 3, coordinateSpace: .global)
                .onChanged { value in
                    if !moving { moving = true; onSelect() }
                    moveOffset = Double(value.translation.width) / pixelsPerSecond
                }
                .onEnded { _ in
                    let destination = position
                    moveOffset = 0
                    moving = false
                    onMove(destination)
                })

            if selected {
                RoundedRectangle(cornerRadius: 1)
                    .fill(color.opacity(0.95))
                    .frame(width: 3, height: 23)
                    .frame(width: 12, height: 70)
                    .contentShape(Rectangle())
                    .gesture(DragGesture(minimumDistance: 1, coordinateSpace: .global)
                        .onChanged { value in
                            trimDuration = max(0.02, clip.duration + Double(value.translation.width) / pixelsPerSecond)
                        }
                        .onEnded { _ in
                            let newDuration = duration
                            trimDuration = nil
                            onTrim(newDuration)
                        })
                    .help("Drag to trim the end of \(clip.name)")
                    .accessibilityLabel("Trim end of \(clip.name)")
                    .accessibilityAdjustableAction { direction in
                        if direction == .increment { onTrim(clip.duration + 0.1) }
                        if direction == .decrement { onTrim(max(0.02, clip.duration - 0.1)) }
                    }
            }
        }
        .opacity(attenuated ? 0.42 : 1)
        .offset(x: CGFloat(position * pixelsPerSecond))
        .help("\(clip.name) · \(String(format: "%.3f", position)) s · \(String(format: "%.3f", duration)) s long")
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(clip.name), starts at \(String(format: "%.2f", position)) seconds, duration \(String(format: "%.2f", duration)) seconds")
        .accessibilityAction(named: Text("Select clip"), onSelect)
        .accessibilityAction(named: Text("Move earlier")) { onMove(max(0, clip.position - 0.1)) }
        .accessibilityAction(named: Text("Move later")) { onMove(clip.position + 0.1) }
    }
}

private struct WaveformShape: View {
    let peaks: [Float]
    let color: Color

    var body: some View {
        Canvas { context, size in
            guard !peaks.isEmpty, size.width > 0, size.height > 0 else { return }
            let columns = max(1, Int(min(size.width / 2, CGFloat(peaks.count))))
            let middle = size.height / 2
            var waveform = Path()
            var upper: [CGPoint] = []
            var lower: [CGPoint] = []
            for column in 0..<columns {
                let start = column * peaks.count / columns
                let end = max(start + 1, (column + 1) * peaks.count / columns)
                var peak: Float = 0
                for sample in peaks[start..<min(end, peaks.count)] where sample.isFinite {
                    peak = max(peak, min(1, abs(sample)))
                }
                let x = (CGFloat(column) + 0.5) / CGFloat(columns) * size.width
                let amplitude = max(0.5, CGFloat(peak) * (middle - 1))
                upper.append(CGPoint(x: x, y: middle - amplitude))
                lower.append(CGPoint(x: x, y: middle + amplitude))
                waveform.move(to: CGPoint(x: x, y: middle - amplitude))
                waveform.addLine(to: CGPoint(x: x, y: middle + amplitude))
            }
            var envelope = Path()
            if let first = upper.first {
                envelope.move(to: CGPoint(x: 0, y: first.y))
                for point in upper { envelope.addLine(to: point) }
                for point in lower.reversed() { envelope.addLine(to: point) }
                envelope.closeSubpath()
                context.fill(envelope, with: .color(color.opacity(0.3)))
            }
            context.stroke(waveform, with: .color(color), lineWidth: 1)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct TimelineGrid: View {
    let pixelsPerSecond: Double
    var project: Project? = nil

    var body: some View {
        Canvas { context, size in
            if let project {
                for tick in musicalTicks(project, seconds: size.width / pixelsPerSecond, pixelsPerSecond: pixelsPerSecond) {
                    var line = Path(); let x = tick.seconds * pixelsPerSecond + 0.5
                    line.move(to: CGPoint(x: x, y: 0)); line.addLine(to: CGPoint(x: x, y: size.height))
                    context.stroke(line, with: .color(.white.opacity(tick.bar ? 0.09 : 0.035)), lineWidth: 1)
                }
                return
            }
            let major = timelineInterval(pixelsPerSecond)
            let spacing = CGFloat(major * pixelsPerSecond / 4)
            guard spacing > 0 else { return }
            for index in 0...Int(size.width / spacing) {
                let x = CGFloat(index) * spacing + 0.5
                var line = Path()
                line.move(to: CGPoint(x: x, y: 0))
                line.addLine(to: CGPoint(x: x, y: size.height))
                context.stroke(line, with: .color(Color.white.opacity(index % 4 == 0 ? 0.07 : 0.025)), lineWidth: 1)
            }
        }
    }
}

private struct TimelineRuler: View {
    let pixelsPerSecond: Double
    var project: Project? = nil

    var body: some View {
        Canvas { context, size in
            if let project {
                var lastLabelX = -100.0
                for tick in musicalTicks(project, seconds: size.width / pixelsPerSecond, pixelsPerSecond: pixelsPerSecond) {
                    let x = tick.seconds * pixelsPerSecond
                    if tick.bar, x - lastLabelX >= 55 {
                        context.draw(Text(tick.label).font(.system(size: 10, design: .monospaced)).foregroundColor(TimelineColors.secondary), at: CGPoint(x: x + 7, y: 12), anchor: .leading)
                        lastLabelX = x
                    }
                    var mark = Path(); mark.move(to: CGPoint(x: x + 0.5, y: size.height - (tick.bar ? 8 : 4)))
                    mark.addLine(to: CGPoint(x: x + 0.5, y: size.height))
                    context.stroke(mark, with: .color(.white.opacity(0.24)), lineWidth: 1)
                }
                return
            }
            let interval = timelineInterval(pixelsPerSecond)
            let spacing = CGFloat(interval * pixelsPerSecond)
            guard spacing > 0 else { return }
            for index in 0...Int(size.width / spacing) {
                let seconds = Double(index) * interval
                let label = interval < 1
                    ? String(format: "%d:%04.1f", Int(seconds) / 60, seconds.truncatingRemainder(dividingBy: 60))
                    : String(format: "%d:%02d", Int(seconds) / 60, Int(seconds) % 60)
                let text = Text(label).font(.system(size: 10, design: .monospaced)).foregroundColor(TimelineColors.secondary)
                context.draw(text, at: CGPoint(x: CGFloat(index) * spacing + 7, y: 12), anchor: .leading)
                var tick = Path()
                tick.move(to: CGPoint(x: CGFloat(index) * spacing + 0.5, y: size.height - 7))
                tick.addLine(to: CGPoint(x: CGFloat(index) * spacing + 0.5, y: size.height))
                context.stroke(tick, with: .color(Color.white.opacity(0.24)), lineWidth: 1)
            }
        }
        .overlay(alignment: .bottom) { TimelineColors.line.frame(height: 1) }
    }
}

private struct MusicalTick {
    let seconds: Double
    let bar: Bool
    let label: String
}
private func musicalTicks(_ project: Project, seconds: Double, pixelsPerSecond: Double) -> [MusicalTick] {
    guard let end = try? project.tempoMap.beat(atSeconds: min(86_400, seconds)) else { return [] }
    var ticks: [MusicalTick] = []
    for (index, signature) in project.signatureMap.events.enumerated() {
        let limit = min(end, index + 1 < project.signatureMap.events.count ? project.signatureMap.events[index + 1].beat : end)
        let beatSize = 4.0 / Double(signature.denominator)
        let barSize = Double(signature.numerator) * beatSize
        var beat = signature.beat
        // Zoom chooses visual density only; snap resolution remains independent.
        let minimumSpacing = 12.0 / pixelsPerSecond
        let fastest = project.tempoMap.events.map(\.bpm).max() ?? 120
        let showBeats = beatSize * 60 / fastest >= minimumSpacing
        let barStride = max(1, ceil(minimumSpacing * fastest / 60 / barSize))
        let step = showBeats ? beatSize : barSize * barStride
        while beat <= limit, ticks.count < 8192 {
            if index + 1 < project.signatureMap.events.count, beat >= limit { break }
            if let time = try? project.tempoMap.seconds(atBeat: beat), let position = try? project.signatureMap.position(atBeat: beat) {
                ticks.append(MusicalTick(seconds: time, bar: position.beat == 1 && position.sixteenth == 1 && position.tick == 0,
                                         label: "\(position.bar)"))
            }
            beat += step
        }
    }
    return ticks
}

private func timelineInterval(_ pixelsPerSecond: Double) -> Double {
    [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300].first(where: { $0 * pixelsPerSecond >= 80 }) ?? 300
}

private enum TimelineColors {
    static let canvas = Color(red: 0.063, green: 0.072, blue: 0.088)
    static let panel = Color(red: 0.087, green: 0.098, blue: 0.116)
    static let line = Color.white.opacity(0.075)
    static let secondary = Color(red: 0.53, green: 0.58, blue: 0.65)
    static let playhead = Color(red: 0.98, green: 0.57, blue: 0.38)
    static func track(_ index: Int) -> Color {
        let colors: [Color] = [
            Color(red: 0.36, green: 0.77, blue: 0.83),
            Color(red: 0.63, green: 0.61, blue: 0.88),
            Color(red: 0.78, green: 0.65, blue: 0.43),
            Color(red: 0.43, green: 0.76, blue: 0.61),
            Color(red: 0.85, green: 0.52, blue: 0.61),
            Color(red: 0.47, green: 0.63, blue: 0.88)
        ]
        return colors[index % colors.count]
    }
}

private extension View {
    func onSpatialTapGesture(perform action: @escaping (CGPoint) -> Void) -> some View {
        gesture(SpatialTapGesture().onEnded { action($0.location) })
    }
}
