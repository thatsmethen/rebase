namespace Rebase.Windows;

public sealed partial class StudioViewModel
{
    public CPRReviewSnapshot? CPRReview { get; private set; }

    public async Task<CPRReviewSnapshot?> InspectCPR(string path) => await BeginCPRReview(new() { Command = "inspectCPR", Path = path });
    public async Task<CPRReviewSnapshot?> ImportReport() => await BeginCPRReview(new() { Command = "cprImportReport" });
    private async Task<CPRReviewSnapshot?> BeginCPRReview(SessionRequest request)
    {
        CPRReviewSnapshot? result = null;
        await Execute(async () =>
        {
            CPRReview = null;
            var reply = await Send(request);
            var page = reply.CprReview ?? throw new InvalidDataException("The session omitted the CPR review.");
            page.Validate(expectedOffset: 0);
            if (page.Historical != (request.Command == "cprImportReport")) throw new InvalidDataException("The CPR review has the wrong source context.");
            CPRReview = result = page;
            Status = page.Historical ? "Showing the preserved import baseline." : "Review the supported and unresolved CPR data before importing.";
        });
        return result;
    }
    public async Task<CPRReviewSnapshot?> CPRReviewPage(CPRReviewSnapshot first, int offset)
    {
        CPRReviewSnapshot? result = null;
        await Execute(async () =>
        {
            RequireCPRReview(first);
            var reply = await Send(new() { Command = "cprReviewPage", ReviewID = first.ReviewID, ReviewOffset = offset });
            var page = reply.CprReview ?? throw new InvalidDataException("The session omitted the next CPR review page.");
            page.ValidateContinuation(first, offset);
            result = page;
        });
        return result;
    }
    public async Task<bool> CancelCPRReview(string reviewID)
    {
        if (CPRReview is null) return true;
        var succeeded = false;
        await Execute(async () =>
        {
            await Send(new() { Command = "cancelCPRReview", ReviewID = reviewID });
            if (CPRReview?.ReviewID == reviewID) CPRReview = null;
            succeeded = true;
        });
        return succeeded;
    }
    public async Task<bool> ImportCPR(CPRReviewSnapshot review, string path, bool discardChanges)
    {
        if (CPRReview is null) return false;
        var succeeded = false;
        await Execute(async () =>
        {
            RequireCPRReview(review);
            if (!review.CanImport || review.Historical) throw new InvalidOperationException("This review cannot import supported data.");
            RequireSaveDecision(discardChanges);
            try
            {
                await Send(new() { Command = "importCPR", ReviewID = review.ReviewID, SourceSHA256 = review.SourceSHA256,
                    Path = path, AllowPartial = true, DiscardChanges = discardChanges });
            }
            catch (Exception error) when (error is IOException or TimeoutException)
            { CPRReview = null; throw; }
            CPRReview = null; UseProjectContext(); Position = 0;
            Status = "Imported supported CPR data. The original source and import report are preserved in the project.";
            succeeded = true;
        });
        return succeeded;
    }
    private void RequireCPRReview(CPRReviewSnapshot review)
    {
        review.Validate(expectedOffset: 0);
        if (CPRReview?.ReviewID != review.ReviewID || CPRReview.SourceSHA256 != review.SourceSHA256)
            throw new InvalidOperationException("This review is no longer active. Inspect the source again.");
    }
}
