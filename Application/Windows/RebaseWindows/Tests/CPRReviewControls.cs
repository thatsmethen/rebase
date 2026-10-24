using System.Text.Json;
using Rebase.Windows;

static class CPRReviewControls
{
    public static async Task<int> Run()
    {
        var checks = 0;
        void Check(bool value) { checks++; if (!value) throw new Exception("CPR review control " + checks + " failed."); }
        void Reject(Action action) { checks++; try { action(); } catch (InvalidDataException) { return; } throw new Exception("Invalid CPR review was accepted."); }
        var first = Page(); first.Validate(expectedOffset: 0); Check(true);
        var second = Page(offset: 2); second.ValidateContinuation(first, 2); Check(true);
        foreach (var mutate in new Action<CPRReviewSnapshot>[] {
            p => p.NextOffset = 1, p => p.TotalItems = 1, p => p.SourceSHA256 = "bad", p => p.ReviewID = "not-an-id",
            p => p.Historical = true, p => p.Items[0].Section = "unknown", p => p.SourceByteCount = 268435457,
            p => p.Items[0].Detail = new string('x', CPRReviewSnapshot.MaximumBytes + 1) })
        { var invalid = Page(); mutate(invalid); Reject(() => invalid.Validate()); }
        foreach (var mutate in new Action<CPRReviewSnapshot>[] {
            p => p.SourceName = "Different.cpr", p => p.SourceSHA256 = new string('b', 64), p => p.InterpretationProfile = "other",
            p => p.RecoveredTrackCount++, p => p.TotalItems++, p => p.ReviewID = Guid.NewGuid().ToString() })
        { var invalid = Page(offset: 2); mutate(invalid); Reject(() => invalid.ValidateContinuation(first, 2)); }
        var missing = "{\"reviewID\":\"00000000-0000-4000-8000-000000000001\"}";
        checks++; try { _ = JsonSerializer.Deserialize<CPRReviewSnapshot>(missing, ProtocolJson.Options); throw new Exception("Required review fields were omitted."); } catch (JsonException) { }
        var expanded = Page(); expanded.Items[0].Detail = "ESCAPED_CONTROL";
        var rawPage = JsonSerializer.Serialize(expanded, ProtocolJson.Options).Replace("ESCAPED_CONTROL", string.Concat(Enumerable.Repeat("\\u0061", 23000)), StringComparison.Ordinal);
        var decodedPage = JsonSerializer.Deserialize<CPRReviewSnapshot>(rawPage, ProtocolJson.Options)!;
        decodedPage.Validate(); Check(decodedPage.Items[0].Detail.Length == 23000);
        Reject(() => ProtocolJson.Decode("{\"protocol\":1,\"id\":17,\"ok\":true,\"state\":{},\"cprReview\":" + rawPage + "}", 17));
        foreach (var root in new[] { "[]", "null", "1", "\"text\"", "true" }) Reject(() => ProtocolJson.Decode(root, 17));
        foreach (var casing in new[] { "CprReview", "CPRREVIEW" })
            Reject(() => ProtocolJson.Decode("{\"protocol\":1,\"id\":17,\"ok\":true,\"state\":{},\"" + casing + "\":" + rawPage + "}", 17));
        Reject(() => ProtocolJson.Decode("{\"protocol\":1,\"id\":17,\"ID\":17,\"ok\":true,\"state\":{}}", 17));

        var client = new ReviewClient();
        await using var model = new StudioViewModel(client, new SilentAudio());
        await model.Open("current-project", false, false);
        string Identity() => JsonSerializer.Serialize(model.State, ProtocolJson.Options);
        var before = Identity(); var review = await model.InspectCPR("authored.cpr");
        Check(review is not null && Identity() == before && model.CPRReview == review);
        var token = review!.ReviewID;
        Check(await model.CPRReviewPage(review, 2) is { Offset: 2 } && Identity() == before);
        client.Drift = true;
        Check(await model.CPRReviewPage(review, 2) is null && Identity() == before && model.CPRReview == review);
        client.Drift = false;
        Check(await model.CancelCPRReview(token) && model.CPRReview is null && Identity() == before && client.CancelCalls == 1);
        Check(!await model.ImportCPR(review, "new.rebaseproj", false) && client.ImportCalls == 0);
        review = await model.InspectCPR("authored.cpr");
        // A destination picker cancellation sends no import command: the same
        // review remains valid for its next explicit user action.
        await Task.Yield(); Check(client.ImportCalls == 0 && model.CPRReview == review && Identity() == before);
        client.FailImport = true;
        Check(!await model.ImportCPR(review!, "failed.rebaseproj", false) && client.ImportCalls == 1 && Identity() == before && model.CPRReview == review);
        Check(model.Status == "Source changed after review.");
        client.FailImport = false;
        await model.Command("setGain", trackID: "track", value: 1); var dirty = Identity();
        Check(model.State.Dirty);
        Check(!await model.ImportCPR(review!, "dirty.rebaseproj", false) && Identity() == dirty && client.ImportCalls == 2);
        client.FailSave = true;
        var beforeFailedSaveImports = client.ImportCalls;
        var failedSave = await model.Save();
        Check(!failedSave && !model.State.Dirty && model.NeedsSaveDecision && model.CPRReview == review && model.Status == "Save verification failed.");
        // A clean state in an unsuccessful response cannot authorize the next
        // destructive workflow. MainWindow requires this explicit success result.
        if (failedSave && !model.State.Dirty) await model.ImportCPR(review!, "must-not-import.rebaseproj", false);
        Check(client.ImportCalls == beforeFailedSaveImports);
        var beforeBlockedReplacement = client.Requests.Count;
        Check(!await model.ImportCPR(review!, "next-manual-import.rebaseproj", false) && client.Requests.Count == beforeBlockedReplacement && model.NeedsSaveDecision);
        await model.Open("next-manual-open.rebaseproj", false, false);
        Check(client.Requests.Count == beforeBlockedReplacement && model.NeedsSaveDecision && model.Title.Contains('•'));
        Check(!await model.Save("failed-save-as.rebaseproj") && !model.State.Dirty && model.NeedsSaveDecision && model.CPRReview == review);
        client.FailSave = false;
        Check(await model.Save() && !model.State.Dirty && !model.NeedsSaveDecision && model.CPRReview == review);
        var imported = model.ImportCPR(review!, "imported.rebaseproj", false);
        var duplicate = model.ImportCPR(review!, "duplicate.rebaseproj", false);
        Check(await imported); Check(!await duplicate && client.ImportCalls == 3);
        Check(model.State.Path == "imported.rebaseproj" && model.CPRReview is null && !model.State.Dirty);
        var importedIdentity = Identity(); var report = await model.ImportReport();
        Check(report is { Historical: true, CanImport: false } && Identity() == importedIdentity);
        Check(!await model.ImportCPR(report!, "not-allowed.rebaseproj", false) && client.ImportCalls == 3);
        Check(await model.CancelCPRReview(report!.ReviewID) && Identity() == importedIdentity);
        var superseded = await model.InspectCPR("first.cpr"); var current = await model.InspectCPR("second.cpr");
        Check(superseded!.ReviewID != current!.ReviewID && !await model.ImportCPR(superseded, "old.rebaseproj", false) && client.ImportCalls == 3);
        Check(client.Requests.Where(r => r.Command == "importCPR").All(r => r.AllowPartial is true && r.SourceSHA256 == new string('a', 64)));
        Check(client.Requests.All(r => r.ExpectedRevision is not null));
        var beforeUnconfirmed = Identity(); var importCalls = client.ImportCalls; client.Unconfirmed = true;
        Check(!await model.ImportCPR(current, "uncertain.rebaseproj", false) && client.ImportCalls == importCalls + 1 &&
            Identity() == beforeUnconfirmed && model.CPRReview is null && model.Status == SessionProcess.ImportOutcomeUnconfirmed);
        Check(!await model.ImportCPR(current, "uncertain-retry.rebaseproj", false) && client.ImportCalls == importCalls + 1 &&
            model.Status == SessionProcess.ImportOutcomeUnconfirmed);
        var beforeTerminalCancel = client.Requests.Count;
        Check(await model.CancelCPRReview(current.ReviewID) && client.Requests.Count == beforeTerminalCancel &&
            model.Status == SessionProcess.ImportOutcomeUnconfirmed);
        client.Unconfirmed = false;
        current = await model.InspectCPR("published.cpr"); client.Published = true;
        importCalls = client.ImportCalls; var beforePublished = Identity();
        Check(!await model.ImportCPR(current!, "published.rebaseproj", false) && client.ImportCalls == importCalls + 1 &&
            Identity() == beforePublished && model.CPRReview is null && model.Status == ReviewClient.PublishedGuidance);
        Check(!await model.ImportCPR(current!, "published-retry.rebaseproj", false) && client.ImportCalls == importCalls + 1 &&
            model.Status == ReviewClient.PublishedGuidance);
        beforeTerminalCancel = client.Requests.Count;
        Check(await model.CancelCPRReview(current!.ReviewID) && client.Requests.Count == beforeTerminalCancel && model.Status == ReviewClient.PublishedGuidance);
        client.Published = false;
        current = await model.InspectCPR("timeout.cpr"); client.TimedOut = true;
        importCalls = client.ImportCalls;
        Check(!await model.ImportCPR(current!, "timeout.rebaseproj", false) && client.ImportCalls == importCalls + 1 && model.CPRReview is null);
        Check(!await model.ImportCPR(current!, "timeout-retry.rebaseproj", false) && client.ImportCalls == importCalls + 1);
        client.TimedOut = false; client.FailSave = true;
        Check(!await model.Save() && model.NeedsSaveDecision && !model.State.Dirty);
        current = await model.InspectCPR("explicit-discard.cpr");
        Check(await model.ImportCPR(current!, "explicit-discard.rebaseproj", true) && !model.NeedsSaveDecision);
        Check(!await model.Save() && model.NeedsSaveDecision);
        await model.Open("explicit-discard-open.rebaseproj", false, true);
        Check(!model.NeedsSaveDecision && !model.Title.Contains('•') && client.Requests.Last().Command == "open" && client.Requests.Last().DiscardChanges is true);
        return checks;
    }
    private static CPRReviewSnapshot Page(int offset = 0, string reviewID = "00000000-0000-4000-8000-000000000001", bool historical = false) => new()
    {
        ReviewID = reviewID, SourceName = "Authored.cpr", SourceSHA256 = new string('a', 64), SourceByteCount = 1024,
        InterpretationProfile = "cpr-static-subset-v5", Historical = historical, CanImport = !historical, RecoveredTrackCount = 1,
        RecoveredClipCount = 0, UnresolvedEventCount = 1, TotalItems = 3, Offset = offset, NextOffset = offset == 0 ? 2 : null,
        Items = offset == 0 ? [new() { Section = "tracks", Label = "Authored", Detail = "One recovered track" }, new() { Section = "unresolved", Label = "Source", Detail = "One retained source event" }]
            : [new() { Section = "defaults", Label = "Application", Detail = "Authored default" }]
    };
    private sealed class ReviewClient : ISessionClient
    {
        public readonly List<SessionRequest> Requests = [];
        public int CancelCalls, ImportCalls;
        public const string PublishedGuidance = "The imported project was published, but it could not be reopened. Reopen the destination; do not overwrite it.";
        public bool Drift, FailImport, Unconfirmed, FailSave, Published, TimedOut;
        private string? token;
        private bool historical;
        private SessionState state = new() { Revision = 1, Path = "current-project", Project = new() { Id = "project", Name = "Current", Tempo = 120, SampleRate = 48000,
            TempoMap = JsonSerializer.SerializeToElement(new { }), SignatureMap = JsonSerializer.SerializeToElement(new { }) } };
        public Task<SessionResponse> Send(SessionRequest request)
        {
            Requests.Add(request);
            var reply = new SessionResponse { Protocol = 1, Ok = true, Id = request.Id };
            switch (request.Command)
            {
                case "inspectCPR": case "cprImportReport":
                    token = Guid.NewGuid().ToString(); historical = request.Command == "cprImportReport";
                    reply.CprReview = Page(reviewID: token, historical: historical); break;
                case "cprReviewPage":
                    reply.CprReview = Page(request.ReviewOffset!.Value, token!, historical);
                    if (Drift) reply.CprReview.SourceName = "Changed.cpr"; break;
                case "cancelCPRReview": CancelCalls++; token = null; break;
                case "setGain": state.Dirty = true; state.Revision++; break;
                case "save": case "saveAs":
                    state.Dirty = false;
                    if (FailSave) { reply.Ok = false; reply.Error = new() { Code = "saveVerification", Message = "Save verification failed." }; }
                    break;
                case "importCPR":
                    ImportCalls++;
                    if (Unconfirmed) throw new IOException(SessionProcess.ImportOutcomeUnconfirmed);
                    if (TimedOut) throw new TimeoutException(SessionProcess.ImportOutcomeUnconfirmed);
                    if (Published) { token = null; reply.Ok = false; reply.Error = new() { Code = "importPublished", Message = PublishedGuidance }; }
                    else if (FailImport || state.Dirty && request.DiscardChanges is not true)
                    { reply.Ok = false; reply.Error = new() { Message = FailImport ? "Source changed after review." : "Unsaved changes require a decision." }; }
                    else { state.Path = request.Path; state.Revision++; state.Dirty = false; token = null; }
                    break;
            }
            reply.State = JsonSerializer.Deserialize<SessionState>(JsonSerializer.Serialize(state, ProtocolJson.Options), ProtocolJson.Options);
            return Task.FromResult(reply);
        }
        public object[] ModuleReceipt() => [];
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
    private sealed class SilentAudio : IAudioOutput
    {
        public Task<DeviceFormat> Format() => throw new Exception("Review must not open audio.");
        public Task<AudioRateInfo> RateInfo() => throw new Exception("Review must not query audio conversion.");
        public Task<AudioStatus> Status() => throw new Exception("Review must not poll audio.");
        public Task SetSource(LoadedSnapshot source) => throw new Exception("Review must not load audio.");
        public Task Play() => throw new Exception("Review must not play audio.");
        public Task Pause() => Task.CompletedTask;
        public Task Stop() => Task.CompletedTask;
        public Task Seek(ulong frame) => throw new Exception("Review must not seek audio.");
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
