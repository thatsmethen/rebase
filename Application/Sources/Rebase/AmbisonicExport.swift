import AppKit
import RebaseCore
import UniformTypeIdentifiers

@MainActor
enum AmbisonicExport {
    static func present() {
        let open = NSOpenPanel()
        open.title = "Convert Ambisonic Audio"
        open.allowedContentTypes = [.audio]
        guard open.runModal() == .OK, let source = open.url else { return }
        do {
            let info = try AmbisonicFileConverter.inspect(source: source)
            let direction = NSAlert()
            direction.messageText = "Choose the conversion direction"
            direction.informativeText = "\(info.channels) channels · \(info.precision)-bit floating-point WAV · \(Int(info.sampleRate)) Hz. The sample rate and channel count are preserved. Files with nonfinite or extremely small or large samples are rejected."
            direction.addButton(withTitle: "FuMa → AmbiX")
            direction.addButton(withTitle: "AmbiX → FuMa")
            direction.addButton(withTitle: "Cancel")
            let choice = direction.runModal()
            guard choice == .alertFirstButtonReturn || choice == .alertSecondButtonReturn else { return }
            let reverse = choice == .alertSecondButtonReturn
            let panel = NSSavePanel()
            panel.title = "Save Converted Audio"
            panel.allowedContentTypes = [.wav]
            panel.nameFieldStringValue = source.deletingPathExtension().lastPathComponent + (reverse ? "-FuMa.wav" : "-AmbiX.wav")
            guard panel.runModal() == .OK, let destination = panel.url else { return }
            try convert(source: source, destination: destination, reverse: reverse)
            NSWorkspace.shared.activateFileViewerSelecting([destination])
        } catch {
            NSAlert(error: error).runModal()
        }
    }

    static func convert(source: URL, destination: URL, reverse: Bool) throws {
        try AmbisonicFileConverter.convert(source: source, destination: destination,
                                           direction: reverse ? .ambixToFuma : .fumaToAmbix)
    }
}
