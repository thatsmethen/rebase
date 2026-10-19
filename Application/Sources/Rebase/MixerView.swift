import SwiftUI
import RebaseCore

struct MixerView: View {
    let project: Project
    let selectedTrackID: UUID?
    let onSelectTrack: (UUID) -> Void
    let onGainChange: (UUID, Double) -> Void
    let onPanChange: (UUID, Double) -> Void
    let onMuteToggle: (UUID) -> Void
    let onSoloToggle: (UUID) -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("MIXER")
                    .font(.system(size: 9, weight: .semibold, design: .monospaced))
                    .tracking(1.4)
                Spacer()
                Text("\(project.tracks.count) \(project.tracks.count == 1 ? "channel" : "channels")")
                    .font(.system(size: 10, design: .monospaced))
            }
            .foregroundStyle(MixerColors.secondary)
            .padding(.horizontal, 14)
            .frame(height: 32)
            .overlay(alignment: .bottom) { MixerColors.line.frame(height: 1) }

            if project.tracks.isEmpty {
                HStack(spacing: 12) {
                    Image(systemName: "slider.vertical.3").font(.system(size: 25, weight: .light))
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Make room for your mix").font(.system(size: 13, weight: .medium))
                        Text("Each imported track gets its own gain, pan, mute and solo controls.")
                            .font(.system(size: 11))
                    }
                }
                .foregroundStyle(MixerColors.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                GeometryReader { geometry in
                    ScrollView(.horizontal) {
                        HStack(spacing: 8) {
                            ForEach(Array(project.tracks.enumerated()), id: \.element.id) { index, track in
                                channel(track, index: index)
                                    .frame(width: 166, height: max(174, geometry.size.height - 20))
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                    }
                    .scrollIndicators(.visible)
                }
            }
        }
        .background(MixerColors.background)
    }

    private func channel(_ track: Track, index: Int) -> some View {
        let color = MixerColors.track(index)
        let selected = selectedTrackID == track.id
        return VStack(spacing: 10) {
            Button { onSelectTrack(track.id) } label: {
                HStack(spacing: 8) {
                    Text(String(format: "%02d", index + 1))
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .foregroundStyle(color)
                    Text(track.name)
                        .font(.system(size: 11, weight: .medium))
                        .lineLimit(1)
                        .foregroundStyle(Color.white.opacity(0.9))
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
                .frame(height: 20)
            }
            .buttonStyle(.plain)
            .help("Select \(track.name)")

            HStack(alignment: .center, spacing: 10) {
                MixerFader(value: track.gainDB, color: color, name: track.name) { value in
                    onSelectTrack(track.id)
                    onGainChange(track.id, value)
                }
                .frame(width: 61)

                VStack(spacing: 12) {
                    VStack(spacing: 5) {
                        Text("PAN")
                            .font(.system(size: 8, weight: .semibold, design: .monospaced))
                            .tracking(1)
                            .foregroundStyle(MixerColors.secondary)
                        Text(panText(track.pan))
                            .font(.system(size: 10, weight: .medium, design: .monospaced))
                            .monospacedDigit()
                            .foregroundStyle(Color.white.opacity(0.85))
                        Slider(value: Binding(
                            get: { track.pan },
                            set: { onSelectTrack(track.id); onPanChange(track.id, $0) }
                        ), in: -1...1)
                        .controlSize(.mini)
                        .tint(color)
                        .accessibilityLabel("\(track.name) pan")
                        .help("Pan left or right")
                        Button("Center") { onPanChange(track.id, 0) }
                            .font(.system(size: 9))
                            .buttonStyle(.plain)
                            .foregroundStyle(MixerColors.secondary)
                            .disabled(abs(track.pan) < 0.001)
                            .help("Reset pan to center")
                    }
                    HStack(spacing: 5) {
                        stateButton("M", active: track.isMuted, color: Color.orange, label: "Mute \(track.name)") {
                            onSelectTrack(track.id)
                            onMuteToggle(track.id)
                        }
                        stateButton("S", active: track.isSolo, color: color, label: "Solo \(track.name)") {
                            onSelectTrack(track.id)
                            onSoloToggle(track.id)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
            }
            .frame(maxHeight: .infinity)

            HStack(spacing: 4) {
                Text(String(format: "%+.1f", track.gainDB))
                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                    .monospacedDigit()
                    .foregroundStyle(Color.white.opacity(0.9))
                Text("dB").font(.system(size: 9)).foregroundStyle(MixerColors.secondary)
                Spacer()
                Button("Unity") { onGainChange(track.id, 0) }
                    .buttonStyle(.plain)
                    .font(.system(size: 9))
                    .foregroundStyle(MixerColors.secondary)
                    .disabled(abs(track.gainDB) < 0.001)
                    .help("Reset gain to 0 dB")
            }
            .frame(height: 18)
        }
        .padding(10)
        .background(selected ? Color.white.opacity(0.045) : Color.white.opacity(0.018), in: RoundedRectangle(cornerRadius: 6))
        .overlay {
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(selected ? color.opacity(0.48) : MixerColors.line, lineWidth: 1)
        }
        .overlay(alignment: .top) {
            Capsule().fill(color.opacity(selected ? 1 : 0.55)).frame(height: 2).padding(.horizontal, 9)
        }
    }

    private func stateButton(_ title: String, active: Bool, color: Color, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(active ? Color.black.opacity(0.85) : MixerColors.secondary)
                .frame(maxWidth: .infinity)
                .frame(height: 25)
                .background(active ? color : Color.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 4))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityValue(active ? "On" : "Off")
        .help(label)
    }

    private func panText(_ pan: Double) -> String {
        abs(pan) < 0.005 ? "C" : String(format: "%@ %.0f", pan < 0 ? "L" : "R", abs(pan) * 100)
    }
}

private struct MixerFader: View {
    let value: Double
    let color: Color
    let name: String
    let onChange: (Double) -> Void
    private let range: ClosedRange<Double> = -96...24
    @FocusState private var focused: Bool

    var body: some View {
        GeometryReader { geometry in
            let travel = max(1, geometry.size.height - 16)
            let normalized = faderPosition(value)
            let thumbY = 8 + travel * CGFloat(1 - normalized)
            ZStack(alignment: .topLeading) {
                Capsule()
                    .fill(Color.black.opacity(0.4))
                    .frame(width: 5, height: travel)
                    .offset(x: 20, y: 8)
                Capsule()
                    .fill(color.opacity(0.3))
                    .frame(width: 2, height: max(0, geometry.size.height - 8 - thumbY))
                    .offset(x: 21.5, y: thumbY)
                ForEach([24, 0, -12, -24, -48, -96], id: \.self) { tick in
                    let fraction = faderPosition(Double(tick))
                    HStack(spacing: 4) {
                        Rectangle().fill(Color.white.opacity(tick == 0 ? 0.5 : 0.14)).frame(width: 5, height: 1)
                        Text(tick > 0 ? "+\(tick)" : "\(tick)")
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundStyle(MixerColors.secondary)
                    }
                    .offset(x: 33, y: 8 + travel * CGFloat(1 - fraction) - 4)
                }
                RoundedRectangle(cornerRadius: 3)
                    .fill(LinearGradient(colors: [Color(white: 0.71), Color(white: 0.43)], startPoint: .top, endPoint: .bottom))
                    .overlay {
                        RoundedRectangle(cornerRadius: 3).strokeBorder(focused ? color : Color.white.opacity(0.3), lineWidth: 1)
                    }
                    .overlay {
                        Rectangle().fill(Color.black.opacity(0.55)).frame(height: 1).padding(.horizontal, 4)
                    }
                    .frame(width: 30, height: 15)
                    .shadow(color: .black.opacity(0.35), radius: 2, y: 2)
                    .offset(x: 7.5, y: thumbY - 7.5)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance: 0).onChanged { gesture in
                focused = true
                let fraction = min(1, max(0, 1 - Double((gesture.location.y - 8) / travel)))
                let gain = range.lowerBound + fraction.squareRoot() * (range.upperBound - range.lowerBound)
                onChange((gain * 10).rounded() / 10)
            })
        }
        .focusable()
        .focused($focused)
        .onMoveCommand { direction in
            if direction == .up || direction == .right { adjust(0.5) }
            if direction == .down || direction == .left { adjust(-0.5) }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(name) gain")
        .accessibilityValue(String(format: "%.1f decibels", value))
        .accessibilityAdjustableAction { direction in
            if direction == .increment { adjust(0.5) }
            if direction == .decrement { adjust(-0.5) }
        }
        .help("\(name) gain · Drag or use arrow keys")
    }

    private func adjust(_ amount: Double) {
        onChange(min(range.upperBound, max(range.lowerBound, value + amount)))
    }

    private func faderPosition(_ gain: Double) -> Double {
        let fraction = (min(range.upperBound, max(range.lowerBound, gain)) - range.lowerBound) / (range.upperBound - range.lowerBound)
        return fraction * fraction
    }
}

private enum MixerColors {
    static let background = Color(red: 0.075, green: 0.085, blue: 0.102)
    static let secondary = Color(red: 0.53, green: 0.58, blue: 0.65)
    static let line = Color.white.opacity(0.075)
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
