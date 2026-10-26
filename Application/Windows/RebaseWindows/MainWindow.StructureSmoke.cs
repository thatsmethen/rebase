using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Automation.Peers;
using System.Windows.Automation.Provider;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace Rebase.Windows;

public partial class MainWindow
{
    private async Task<object> RunProjectStructureSmoke(string artifactRoot, string work, List<string> checks,
        Action<string> setStage, CancellationToken cancellation)
    {
        var fixtureRoot = Environment.GetEnvironmentVariable("REBASE_SMOKE_PROJECT_STRUCTURE_FIXTURE") ??
            throw new InvalidOperationException("The authored saved-structure fixture was not supplied.");
        var fixtureBytes = await File.ReadAllBytesAsync(Path.Combine(fixtureRoot, "expected.json"), cancellation);
        using var fixture = JsonDocument.Parse(fixtureBytes);
        if (fixture.RootElement.GetProperty("schema").GetString() != "rebase.project-structure-fixtures.v1")
            throw new InvalidDataException("Unexpected saved-structure fixture schema.");
        var cases = fixture.RootElement.GetProperty("cases").EnumerateArray().ToArray();
        if (cases.Length != 2 || !cases.Select(row => row.GetProperty("name").GetString()).SequenceEqual(new[] { "small", "large" }))
            throw new InvalidDataException("Saved-structure controls require both ordered small and large cases.");
        string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
        string StateHash() => Hash(JsonSerializer.SerializeToUtf8Bytes(model.State, ProtocolJson.Options));
        string ProjectHash() => Hash(JsonSerializer.SerializeToUtf8Bytes(model.Project, ProtocolJson.Options));
        var records = new List<object>(); var captures = new List<object>(); var custody = new List<object>();
        ProjectStructureWindow? dialog = null; object? afterUndo = null;
        void Check(bool okay, string label)
        {
            setStage(label);
            if (!okay) throw new InvalidOperationException(label + ": " + model.Status);
            checks.Add(label);
        }
        async Task Idle(Func<bool>? condition = null)
        {
            using var limit = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            limit.CancelAfter(TimeSpan.FromSeconds(120));
            do
            {
                await Dispatcher.InvokeAsync(() => { UpdateLayout(); activeProjectStructure?.UpdateLayout(); }, DispatcherPriority.ApplicationIdle);
                if (!model.Busy && (condition?.Invoke() ?? true)) return;
                await Task.Delay(20, limit.Token);
            } while (true);
        }
        Dictionary<string, ulong> Delta(IReadOnlyDictionary<string, ulong> before) =>
            new[] { "inspectProjectStructure", "projectStructurePage", "closeProjectStructure" }.ToDictionary(command => command,
                command => model.HelperRequestCounts().GetValueOrDefault(command) - before.GetValueOrDefault(command));
        async Task OpenViewer()
        {
            setStage("structure-menu-open");
            await Idle(() => IsEnabled && !openingProjectStructure);
            var parent = ItemsControl.ItemsControlFromItemContainer(ProjectStructureMenu) as MenuItem ??
                throw new InvalidOperationException("The saved-structure command has no Project menu.");
            parent.IsSubmenuOpen = true; await Dispatcher.InvokeAsync(UpdateLayout, DispatcherPriority.ApplicationIdle);
            if (!ProjectStructureMenu.IsEnabled || !ProjectStructureMenu.IsVisible)
                throw new InvalidOperationException("The saved-structure Project menu action is unavailable.");
            ((IInvokeProvider)new MenuItemAutomationPeer(ProjectStructureMenu).GetPattern(PatternInterface.Invoke)).Invoke();
            await Idle(() => activeProjectStructure is { IsVisible: true } || !openingProjectStructure && IsEnabled);
            dialog = activeProjectStructure ?? throw new InvalidOperationException("Saved structure did not open: " + model.Status);
            if (IsEnabled) throw new InvalidOperationException("The project owner remained editable while its structure view was open.");
        }
        async Task CloseViewer()
        {
            if (dialog is null || !dialog.CloseButton.IsVisible || !dialog.CloseButton.IsEnabled)
                throw new InvalidOperationException("The saved-structure Close action is unavailable.");
            ((IInvokeProvider)new ButtonAutomationPeer(dialog.CloseButton).GetPattern(PatternInterface.Invoke)).Invoke();
            await Idle(() => !openingProjectStructure && activeProjectStructure is null && IsEnabled);
            if (dialog.IsVisible) throw new InvalidOperationException("The saved-structure view did not close.");
            dialog = null;
        }
        async Task SelectTab(string name)
        {
            var tab = dialog!.Sections.Items.Cast<TabItem>().Single(item => Equals(item.Header, name));
            ((ISelectionItemProvider)new TabItemAutomationPeer(tab, new TabControlAutomationPeer(dialog.Sections)).GetPattern(PatternInterface.SelectionItem)).Select();
            await Idle();
            if (!ReferenceEquals(dialog.Sections.SelectedItem, tab) || tab.Content is not FrameworkElement { IsVisible: true })
                throw new InvalidOperationException("The saved-structure section did not become visible.");
        }
        void ValidateSnapshot(JsonElement expected)
        {
            var value = dialog!.Snapshot; var counts = expected.GetProperty("counts");
            if (!ProjectStructurePage.SameID(value.ProjectID, expected.GetProperty("projectID").GetString()) || value.Revision != model.State.Revision ||
                value.SourceSHA256 != expected.GetProperty("sourceSHA256").GetString() || value.SourceByteCount != expected.GetProperty("sourceBytes").GetInt32() ||
                value.ReportSHA256 != expected.GetProperty("reportSHA256").GetString() || value.ReportByteCount != expected.GetProperty("reportBytes").GetInt32() ||
                value.ProjectManifestSHA256 != expected.GetProperty("manifestSHA256").GetString() ||
                value.Hierarchy.Count != counts.GetProperty("entries").GetInt32() || value.Tracks.Count != counts.GetProperty("tracks").GetInt32() ||
                value.Issues.Count != counts.GetProperty("issues").GetInt32() || value.ListCount != counts.GetProperty("lists").GetInt32() ||
                value.ObjectCount != counts.GetProperty("nativeObjects").GetInt32() || value.ResourceAssociationCount != counts.GetProperty("resourceAssociations").GetInt32() ||
                Hash(Encoding.UTF8.GetBytes(dialog.CompleteJson.Text)) != value.ReportSHA256 || Encoding.UTF8.GetByteCount(dialog.CompleteJson.Text) != value.ReportByteCount)
                throw new InvalidDataException("The actual saved-structure report differs from its authored fixture lock.");
        }
        object SnapshotIdentity() => new { project_id = dialog!.Snapshot.ProjectID, revision = dialog.Snapshot.Revision,
            source_sha256 = dialog.Snapshot.SourceSHA256, source_bytes = dialog.Snapshot.SourceByteCount,
            manifest_sha256 = dialog.Snapshot.ProjectManifestSHA256, report_sha256 = dialog.Snapshot.ReportSHA256,
            report_bytes = dialog.Snapshot.ReportByteCount, entries = dialog.Snapshot.Hierarchy.Count, tracks = dialog.Snapshot.Tracks.Count,
            issues = dialog.Snapshot.Issues.Count, lists = dialog.Snapshot.ListCount, native_objects = dialog.Snapshot.ObjectCount,
            resource_associations = dialog.Snapshot.ResourceAssociationCount };
        object State() => new { state_sha256 = StateHash(), project_sha256 = ProjectHash(), revision = model.State.Revision,
            dirty = model.State.Dirty, needs_save_as = model.State.NeedsSaveAs, can_undo = model.State.CanUndo, can_redo = model.State.CanRedo,
            track_id = model.State.Selection.TrackID, clip_id = model.State.Selection.ClipID };
        async Task<object> Capture(string name)
        {
            await Idle(); var content = (FrameworkElement)dialog!.Content; var dpi = VisualTreeHelper.GetDpi(content);
            var width = checked((int)Math.Ceiling(content.ActualWidth * dpi.DpiScaleX));
            var height = checked((int)Math.Ceiling(content.ActualHeight * dpi.DpiScaleY));
            var bitmap = new RenderTargetBitmap(width, height, dpi.PixelsPerInchX, dpi.PixelsPerInchY, PixelFormats.Pbgra32); bitmap.Render(content);
            var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            var path = Path.Combine(artifactRoot, name); using (var output = File.Create(path)) encoder.Save(output);
            var alpha = MeasureClientAlpha(bitmap, content); var imageHash = Hash(await File.ReadAllBytesAsync(path, cancellation));
            await File.WriteAllTextAsync(Path.Combine(artifactRoot, name.Replace(".png", "-alpha.json", StringComparison.Ordinal)),
                JsonSerializer.Serialize(new { screenshot = name, png_sha256 = imageHash, alpha_coverage = alpha }), cancellation);
            var measured = new List<object>();
            foreach (var (label, element) in new (string, FrameworkElement)[] {
                ("sections", dialog.Sections), ("content", (FrameworkElement)((TabItem)dialog.Sections.SelectedItem).Content), ("close", dialog.CloseButton) }
                .Concat(dialog.Sections.Items.Cast<TabItem>().Select(tab => ("tab-" + (string)tab.Header, (FrameworkElement)tab))))
            {
                var point = element.TransformToAncestor(content).Transform(new Point());
                measured.Add(new { name = label, x = point.X, y = point.Y, width = element.ActualWidth, height = element.ActualHeight,
                    visible = element.IsVisible, enabled = element.IsEnabled });
                if (!element.IsVisible || element.ActualWidth <= 0 || element.ActualHeight <= 0 || point.X < -0.5 || point.Y < -0.5 ||
                    point.X + element.ActualWidth > content.ActualWidth + 0.5 || point.Y + element.ActualHeight > content.ActualHeight + 0.5)
                    throw new InvalidOperationException("A saved-structure control is outside its captured client: " + label);
            }
            if (alpha["root_background_alpha"] != 255 || alpha["alpha_below_254_pixels"] != 0)
                throw new InvalidOperationException("Saved-structure capture failed measured alpha coverage.");
            return new { file = name, sha256 = imageHash, alpha_coverage = alpha,
                bounds = new { outer_width_dip = dialog.ActualWidth, outer_height_dip = dialog.ActualHeight,
                    width_dip = content.ActualWidth, height_dip = content.ActualHeight, dpi_scale_x = dpi.DpiScaleX, dpi_scale_y = dpi.DpiScaleY,
                    pixel_width = width, pixel_height = height }, controls = measured,
                selected_section = ((TabItem)dialog.Sections.SelectedItem).Header, scope = ProjectStructureSnapshot.Scope,
                report_sha256 = dialog.Snapshot.ReportSHA256, report_bytes = dialog.Snapshot.ReportByteCount,
                frame_excluded = true };
        }
        try
        {
            foreach (var expected in cases)
            {
                var name = expected.GetProperty("name").GetString()!; var copiedRoot = Path.Combine(work, "Structure-" + name + ".rebaseproj");
                Directory.CreateDirectory(copiedRoot); var sourceRoot = Path.GetFullPath(Path.Combine(fixtureRoot, expected.GetProperty("root").GetString()!));
                if (!sourceRoot.StartsWith(Path.GetFullPath(fixtureRoot) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("The structure fixture escaped its root.");
                foreach (var file in expected.GetProperty("files").EnumerateArray())
                {
                    var relative = file.GetProperty("path").GetString()!;
                    if (relative is not ("Project.json" or "Compatibility/CPR/Original.cpr" or "Compatibility/CPR/ImportReport.json"))
                        throw new InvalidDataException("Unexpected saved-structure fixture payload.");
                    var originalPath = Path.Combine(sourceRoot, relative.Replace('/', Path.DirectorySeparatorChar));
                    var bytes = await File.ReadAllBytesAsync(originalPath, cancellation);
                    if (bytes.Length != file.GetProperty("bytes").GetInt32() || Hash(bytes) != file.GetProperty("sha256").GetString())
                        throw new InvalidDataException("A saved-structure fixture file differs from its lock.");
                    var destination = Path.Combine(copiedRoot, relative.Replace('/', Path.DirectorySeparatorChar)); Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                    await using (var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write)) await output.WriteAsync(bytes, cancellation);
                }
                await model.Open(Path.Combine(copiedRoot, "Project.json"), false, true); await Idle(() => IsEnabled);
                if (!ProjectStructurePage.SameID(model.Project?.Id, expected.GetProperty("projectID").GetString()) ||
                    !ProjectStructurePage.SameID(model.State.Selection.TrackID, expected.GetProperty("trackID").GetString()))
                    throw new InvalidDataException("The authored structure project did not open.");
                var original = State(); var originalState = StateHash(); var originalProject = ProjectHash(); var requests = model.HelperRequestCounts();
                await OpenViewer(); ValidateSnapshot(expected);
                var opened = State(); var snapshot = SnapshotIdentity(); var commands = Delta(requests); var pageCount = (dialog!.Snapshot.ReportByteCount + ProjectStructurePage.ChunkBytes - 1) / ProjectStructurePage.ChunkBytes;
                if (commands["inspectProjectStructure"] != 1 || commands["projectStructurePage"] != (ulong)(pageCount - 1) || commands["closeProjectStructure"] != 1)
                    throw new InvalidOperationException("The saved-structure page or cleanup command count differs.");
                if (name == "small")
                {
                    Check(StateHash() == originalState && !model.State.Dirty && !IsEnabled, "structure-clean-open-preserves-state");
                    var visited = new List<string>();
                    foreach (var section in new[] { "Overview", "Hierarchy", "Tracks", "Issues", "Complete JSON" })
                    { await SelectTab(section); visited.Add((string)((TabItem)dialog.Sections.SelectedItem).Header); }
                    Check(visited.Count == 5, "structure-all-tabs-accessible");
                    var provider = (IValueProvider)new TextBoxAutomationPeer(dialog.CompleteJson).GetPattern(PatternInterface.Value);
                    var rejected = false; var jsonBefore = Hash(Encoding.UTF8.GetBytes(dialog.CompleteJson.Text));
                    try { provider.SetValue("This report must remain read-only."); } catch (InvalidOperationException) { rejected = true; }
                    Check(provider.IsReadOnly && rejected && dialog.CompleteJson.Text == dialog.Snapshot.Json && StateHash() == originalState, "structure-json-readonly");
                    var readOnly = new { is_read_only = dialog.CompleteJson.IsReadOnly, provider_read_only = provider.IsReadOnly,
                        write_rejected = rejected, before_sha256 = jsonBefore, after_sha256 = Hash(Encoding.UTF8.GetBytes(dialog.CompleteJson.Text)) };
                    dialog.Width = dialog.MinWidth; dialog.Height = dialog.MinHeight; await SelectTab("Tracks");
                    captures.Add(await Capture("native-project-structure-minimum-visual.png")); Check(true, "structure-minimum-window-captured");
                    await CloseViewer(); Check(StateHash() == originalState, "structure-clean-close-preserves-state");
                    records.Add(new { name = "clean", before = original, opened, after = State(), commands, page_count = pageCount, snapshot, read_only = readOnly,
                        report_sha256 = expected.GetProperty("reportSHA256").GetString(), report_bytes = expected.GetProperty("reportBytes").GetInt32(), visited_sections = visited });
                    var gain = model.SelectedTrack?.GainDB ?? throw new InvalidOperationException("The authored structure track was not selected.");
                    var changedGain = gain == -6 ? -7 : -6;
                    ((IRangeValueProvider)(UIElementAutomationPeer.CreatePeerForElement(InspectorGainSlider) ??
                        throw new InvalidOperationException("The gain control has no automation peer.")).GetPattern(PatternInterface.RangeValue)).SetValue(changedGain);
                    await Idle(() => model.SelectedTrack?.GainDB == changedGain);
                    var dirty = State(); var dirtyHash = StateHash(); requests = model.HelperRequestCounts();
                    if (!model.State.Dirty || !model.State.CanUndo) throw new InvalidOperationException("The structure dirty-state control did not commit its gain edit.");
                    await OpenViewer(); ValidateSnapshot(expected);
                    Check(StateHash() == dirtyHash && model.State.Dirty && model.State.CanUndo, "structure-dirty-open-preserves-state");
                    Check(dialog!.Snapshot.ReportSHA256 == expected.GetProperty("reportSHA256").GetString(), "structure-dirty-source-report-stable");
                    var dirtyOpened = State(); var dirtySnapshot = SnapshotIdentity(); commands = Delta(requests);
                    if (commands["inspectProjectStructure"] != 1 || commands["projectStructurePage"] != (ulong)(pageCount - 1) || commands["closeProjectStructure"] != 1)
                        throw new InvalidOperationException("Dirty inspection changed the expected page or cleanup command count.");
                    await CloseViewer();
                    Check(StateHash() == dirtyHash && model.State.CanUndo, "structure-dirty-close-preserves-history");
                    records.Add(new { name = "dirty", before = dirty, opened = dirtyOpened, after = State(), commands, page_count = pageCount, snapshot = dirtySnapshot,
                        report_sha256 = expected.GetProperty("reportSHA256").GetString(), report_bytes = expected.GetProperty("reportBytes").GetInt32() });
                    ((IInvokeProvider)new ButtonAutomationPeer(UndoButton).GetPattern(PatternInterface.Invoke)).Invoke();
                    await Idle(() => model.SelectedTrack?.GainDB == gain);
                    Check(ProjectHash() == originalProject && !model.State.Dirty && model.State.CanRedo, "structure-undo-restores-project");
                    afterUndo = State();
                }
                else
                {
                    Check(StateHash() == originalState && pageCount > 1 && commands["projectStructurePage"] > 0, "structure-large-multipage-complete");
                    await SelectTab("Complete JSON"); dialog.Width = dialog.MinWidth; dialog.Height = dialog.MinHeight; await Idle();
                    var text = dialog.CompleteJson; var beforeOffset = text.VerticalOffset; text.ScrollToEnd(); await Idle();
                    var firstLine = text.GetFirstVisibleLineIndex(); var lastLine = text.GetLastVisibleLineIndex();
                    var lastSourceLine = text.GetLineIndexFromCharacterIndex(text.Text.Length - 1);
                    Check(text.IsReadOnly && text.VerticalOffset > beforeOffset && lastLine >= lastSourceLine && StateHash() == originalState,
                        "structure-large-json-end-accessible");
                    captures.Add(await Capture("native-project-structure-json-visual.png")); Check(true, "structure-json-window-captured");
                    var scroll = new { before_offset = beforeOffset, after_offset = text.VerticalOffset, viewport_height = text.ViewportHeight,
                        extent_height = text.ExtentHeight, first_visible_line = firstLine, last_visible_line = lastLine, last_source_line = lastSourceLine,
                        json_sha256 = Hash(Encoding.UTF8.GetBytes(text.Text)), json_bytes = Encoding.UTF8.GetByteCount(text.Text), read_only = text.IsReadOnly };
                    await CloseViewer(); Check(StateHash() == originalState, "structure-large-close-preserves-state");
                    records.Add(new { name = "large", before = original, opened, after = State(), commands, page_count = pageCount, snapshot, scroll,
                        report_sha256 = expected.GetProperty("reportSHA256").GetString(), report_bytes = expected.GetProperty("reportBytes").GetInt32() });
                }
                foreach (var file in expected.GetProperty("files").EnumerateArray())
                {
                    var relative = file.GetProperty("path").GetString()!; var originalBytes = await File.ReadAllBytesAsync(Path.Combine(sourceRoot, relative.Replace('/', Path.DirectorySeparatorChar)), cancellation);
                    var copyBytes = await File.ReadAllBytesAsync(Path.Combine(copiedRoot, relative.Replace('/', Path.DirectorySeparatorChar)), cancellation);
                    if (Hash(originalBytes) != file.GetProperty("sha256").GetString() || !copyBytes.AsSpan().SequenceEqual(originalBytes))
                        throw new InvalidDataException("Saved structure inspection changed its source fixture or working copy.");
                    custody.Add(new { name, path = relative, bytes = originalBytes.Length, original_sha256 = Hash(originalBytes), copy_sha256 = Hash(copyBytes) });
                }
            }
            Check(custody.Count == 6, "structure-source-files-unchanged");
            return new { tested = true, fixture_sha256 = Hash(fixtureBytes), cases = records, captures, custody, after_undo = afterUndo,
                helper_sha256 = Hash(await File.ReadAllBytesAsync(Path.Combine(AppContext.BaseDirectory, "rebase-session.exe"), cancellation)),
                physical_input_tested = false, native_file_pickers_tested = false, playback_tested = false,
                input_evidence = "Actual Project menu, tab, read-only value, gain, undo and Close UIA callbacks; WPF ScrollToEnd. No physical input." };
        }
        finally { if (dialog is { IsVisible: true }) { dialog.Close(); await Idle(() => !openingProjectStructure); } }
    }
}
