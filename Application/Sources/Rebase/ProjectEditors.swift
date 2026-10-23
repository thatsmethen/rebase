import SwiftUI
import RebaseCore

struct TempoEditor: View {
    @ObservedObject var session: StudioSession
    @Environment(\.dismiss) private var dismiss
    @State private var tempo = TempoMap()
    @State private var signatures = SignatureMap()
    @State private var beat = 4.0
    @State private var bpm = 120.0
    @State private var numerator = 4
    @State private var denominator = 4
    @State private var message: String?
    @State private var convertNativeTiming = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("Tempo & Signature Tracks").font(.title2)
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Apply") {
                    do {
                        try tempo.validate(); try signatures.validate()
                        try session.applyMusicalMaps(tempo: tempo, signatures: signatures,
                            convertNativeTiming: convertNativeTiming)
                        dismiss()
                    } catch { message = error.localizedDescription }
                }.keyboardShortcut(.defaultAction)
            }
            Text("Positions use quarter-note beats from zero. Musical clip starts follow tempo changes; recorded audio keeps its length.")
                .foregroundStyle(.secondary)
            if tempo.nativeClock != nil {
                HStack(alignment: .top) {
                    Text("Recovered source timing is preserved. To edit tempo or export DAWproject, switch to Rebase timing. Musical clip starts may shift slightly.")
                        .font(.callout).fixedSize(horizontal: false, vertical: true)
                    Button("Use Rebase Timing") {
                        do {
                            tempo = try tempo.convertedToApplicationTiming()
                            convertNativeTiming = true
                            message = nil
                        } catch { message = error.localizedDescription }
                    }
                }.padding(12).background(Color.cyan.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
            } else if convertNativeTiming {
                Text("Rebase timing will take effect when you apply. Cancel keeps the recovered clock; Undo restores it after applying.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            HStack(alignment: .top, spacing: 24) {
                VStack(alignment: .leading, spacing: 12) {
                    Text("TEMPO · STEP").font(.caption).foregroundStyle(.secondary)
                    List {
                        ForEach(tempo.events) { event in
                            HStack {
                                Text(String(format: "Beat %.3f", event.beat)).frame(width: 110, alignment: .leading)
                                Text(String(format: "%.2f BPM", event.bpm)).monospacedDigit()
                                Spacer()
                                if event.beat != 0 {
                                    Button { tempo.events.removeAll { $0.id == event.id } } label: { Image(systemName: "minus.circle") }.buttonStyle(.borderless).accessibilityLabel("Remove tempo at beat \(event.beat)").disabled(tempo.nativeClock != nil)
                                }
                            }
                        }
                    }.frame(minHeight: 220)
                    LabeledContent("BPM") { TextField("BPM", value: $bpm, format: .number).frame(width: 90) }
                    Button("Set Tempo at Beat") {
                        tempo.events.removeAll { $0.beat == beat }
                        tempo.events.append(TempoEvent(beat: beat, bpm: bpm))
                        tempo.events.sort { $0.beat < $1.beat }
                    }.disabled(tempo.nativeClock != nil)
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text("TIME SIGNATURE").font(.caption).foregroundStyle(.secondary)
                    List {
                        ForEach(signatures.events) { event in
                            HStack {
                                Text(String(format: "Beat %.3f", event.beat)).frame(width: 110, alignment: .leading)
                                Text("\(event.numerator)/\(event.denominator)").monospacedDigit()
                                Spacer()
                                if event.beat != 0 {
                                    Button { signatures.events.removeAll { $0.id == event.id } } label: { Image(systemName: "minus.circle") }.buttonStyle(.borderless).accessibilityLabel("Remove signature at beat \(event.beat)")
                                }
                            }
                        }
                    }.frame(minHeight: 220)
                    HStack {
                        TextField("Numerator", value: $numerator, format: .number).frame(width: 60)
                        Text("/")
                        Picker("Denominator", selection: $denominator) {
                            ForEach([1, 2, 4, 8, 16], id: \.self) { Text("\($0)").tag($0) }
                        }.labelsHidden().frame(width: 75)
                    }
                    Button("Set Signature at Beat") {
                        signatures.events.removeAll { $0.beat == beat }
                        signatures.events.append(SignatureEvent(beat: beat, numerator: numerator, denominator: denominator))
                        signatures.events.sort { $0.beat < $1.beat }
                    }
                }
            }
            HStack {
                Text("Event position")
                TextField("Quarter-note beat", value: $beat, format: .number).frame(width: 100)
                Text("Signature changes must fall on a bar boundary.").foregroundStyle(.secondary)
            }
            if let message { Text(message).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true) }
        }
        .textFieldStyle(.roundedBorder).padding(24).frame(width: 820, height: 610)
        .onAppear {
            tempo = session.project.tempoMap
            signatures = session.project.signatureMap
            convertNativeTiming = false
        }
    }
}

struct AutomationEditor: View {
    @ObservedObject var session: StudioSession
    let trackID: UUID
    @Environment(\.dismiss) private var dismiss
    @State private var parameter: AutomationParameter = .gainDB
    @State private var lanes: [AutomationLane] = []
    @State private var selectedID: UUID?
    @State private var pointTime = 0.0
    @State private var pointValue = 0.0
    @State private var interpolation: AutomationInterpolation = .linear
    @State private var message: String?
    private var track: Track? { session.project.tracks.first { $0.id == trackID } }
    private var lane: AutomationLane { lanes.first { $0.parameter == parameter } ?? AutomationLane(parameter: parameter) }
    private var span: Double { max(1, session.project.duration, lane.points.last?.time ?? 0, session.playhead) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Automation · \(track?.name ?? "Track")").font(.title2)
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Apply") {
                    do {
                        for value in lanes { try value.validate() }
                        session.applyAutomation(trackID, lanes: lanes)
                        dismiss()
                    } catch { message = error.localizedDescription }
                }.keyboardShortcut(.defaultAction)
            }
            HStack(spacing: 20) {
                Picker("Parameter", selection: $parameter) {
                    Text("Volume (dB)").tag(AutomationParameter.gainDB)
                    Text("Pan").tag(AutomationParameter.pan)
                }.frame(width: 220).onChange(of: parameter) { _, _ in selectedID = nil; pointValue = parameter == .gainDB ? (track?.gainDB ?? 0) : (track?.pan ?? 0) }
                Toggle("Read automation", isOn: Binding(get: { lane.isReadEnabled }, set: { var edited = lane; edited.isReadEnabled = $0; replace(edited) }))
                Spacer()
                Text("Click the curve area to place a point").font(.caption).foregroundStyle(.secondary)
            }
            AutomationGraph(lane: lane, span: span, playhead: session.playhead)
                .frame(height: 170)
                .gesture(SpatialTapGesture().onEnded { value in
                    pointTime = max(0, min(span, value.location.x / 772 * span))
                    let range = parameter.valueRange
                    pointValue = range.upperBound - min(1, max(0, value.location.y / 170)) * (range.upperBound - range.lowerBound)
                    selectedID = nil
                    putPoint()
                })
                .accessibilityLabel("\(parameter == .gainDB ? "Volume" : "Pan") automation curve with \(lane.points.count) points")
            HStack(spacing: 14) {
                VStack(alignment: .leading) { Text("Time (seconds)").font(.caption); TextField("Point time", value: $pointTime, format: .number).frame(width: 110) }
                VStack(alignment: .leading) { Text(parameter == .gainDB ? "Level (dB)" : "Pan (−1…1)").font(.caption); TextField("Point value", value: $pointValue, format: .number).frame(width: 110) }
                VStack(alignment: .leading) {
                    Text("Following segment").font(.caption)
                    Picker("Interpolation", selection: $interpolation) { Text("Linear").tag(AutomationInterpolation.linear); Text("Hold").tag(AutomationInterpolation.step) }.labelsHidden().frame(width: 120)
                }
                Button(selectedID == nil ? "Add Point" : "Update Point") { putPoint() }
                Button("At Playhead") { pointTime = session.playhead; selectedID = nil }
                Button("Delete") { var edited = lane; if let id = selectedID { edited.removePoint(id: id); replace(edited); selectedID = nil } }.disabled(selectedID == nil)
            }
            List {
                ForEach(lane.points) { point in
                    Button {
                        selectedID = point.id; pointTime = point.time; pointValue = point.value; interpolation = point.interpolation
                    } label: {
                        HStack {
                            Text(String(format: "%8.3f s", point.time)).frame(width: 110, alignment: .leading)
                            Text(String(format: "%+.3f", point.value)).frame(width: 100, alignment: .leading)
                            Text(point.interpolation == .linear ? "Linear" : "Hold")
                            Spacer()
                            if selectedID == point.id { Image(systemName: "pencil") }
                        }.monospacedDigit().contentShape(Rectangle())
                    }.buttonStyle(.plain).listRowBackground(selectedID == point.id ? Color.cyan.opacity(0.12) : Color.clear)
                }
            }.frame(minHeight: 100)
            Text(message ?? "The first and last values hold outside the curve. Volume segments interpolate in dB. Read off restores the manual fader value.")
                .font(.caption).foregroundStyle(message == nil ? Color.secondary : Color.orange)
        }
        .textFieldStyle(.roundedBorder).padding(24).frame(width: 820, height: 610)
        .onAppear { lanes = track?.automation ?? []; pointTime = session.playhead; pointValue = track?.gainDB ?? 0 }
    }
    private func replace(_ edited: AutomationLane) {
        if let index = lanes.firstIndex(where: { $0.parameter == edited.parameter }) { lanes[index] = edited }
        else { lanes.append(edited) }
    }
    private func putPoint() {
        do {
            var edited = lane
            let point = AutomationPoint(id: selectedID ?? UUID(), time: pointTime, value: pointValue, interpolation: interpolation)
            try edited.upsert(point); replace(edited); selectedID = point.id; message = nil
        } catch { message = error.localizedDescription }
    }
}

struct AutomationGraph: View {
    let lane: AutomationLane
    let span: Double
    let playhead: Double
    var body: some View {
        Canvas { context, size in
            let range = lane.parameter.valueRange
            func position(_ time: Double, _ value: Double) -> CGPoint {
                CGPoint(x: time / span * size.width, y: (range.upperBound - value) / (range.upperBound - range.lowerBound) * size.height)
            }
            var grid = Path()
            for i in 0...4 { let y = Double(i) / 4 * size.height; grid.move(to: CGPoint(x: 0, y: y)); grid.addLine(to: CGPoint(x: size.width, y: y)) }
            context.stroke(grid, with: .color(.white.opacity(0.1)), lineWidth: 1)
            if let first = lane.points.first, let last = lane.points.last {
                var curve = Path(); curve.move(to: position(0, first.value))
                var previous = first
                for point in lane.points {
                    if previous.interpolation == .step { curve.addLine(to: position(point.time, previous.value)) }
                    curve.addLine(to: position(point.time, point.value)); previous = point
                }
                curve.addLine(to: position(span, last.value))
                context.stroke(curve, with: .color(lane.isReadEnabled ? .cyan : .gray), lineWidth: 2)
                for point in lane.points {
                    let p = position(point.time, point.value)
                    context.fill(Path(ellipseIn: CGRect(x: p.x - 3, y: p.y - 3, width: 6, height: 6)), with: .color(.white))
                }
            }
            var head = Path(); let x = playhead / span * size.width
            head.move(to: CGPoint(x: x, y: 0)); head.addLine(to: CGPoint(x: x, y: size.height))
            context.stroke(head, with: .color(.orange), lineWidth: 1)
        }.background(Color.black.opacity(0.3)).clipped()
    }
}
