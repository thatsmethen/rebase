using System.Text;
using System.Text.Json.Serialization;

namespace Rebase.Windows;

/// Bounded presentation of a reviewed source. The original report and source
/// remain owned and verified by the shared session, never reconstructed here.
public sealed class CPRReviewSnapshot
{
    public const int MaximumBytes = 128 * 1024;
    [JsonRequired] public string ReviewID { get; set; } = "";
    [JsonRequired] public string SourceName { get; set; } = "";
    [JsonRequired] public string SourceSHA256 { get; set; } = "";
    [JsonRequired] public long SourceByteCount { get; set; }
    [JsonRequired] public string InterpretationProfile { get; set; } = "";
    [JsonRequired] public bool Historical { get; set; }
    [JsonRequired] public bool CanImport { get; set; }
    [JsonRequired] public int RecoveredTrackCount { get; set; }
    [JsonRequired] public int RecoveredClipCount { get; set; }
    [JsonRequired] public int UnresolvedEventCount { get; set; }
    [JsonRequired] public int TotalItems { get; set; }
    [JsonRequired] public int Offset { get; set; }
    public int? NextOffset { get; set; }
    [JsonRequired] public CPRReviewItem[] Items { get; set; } = [];

    public void Validate(string? expectedReviewID = null, int? expectedOffset = null)
    {
        if (!Guid.TryParseExact(ReviewID, "D", out _) || expectedReviewID is not null && ReviewID != expectedReviewID ||
            expectedOffset is not null && Offset != expectedOffset ||
            string.IsNullOrWhiteSpace(SourceName) || Encoding.UTF8.GetByteCount(SourceName) > 4096 ||
            SourceSHA256 is null || SourceSHA256.Length != 64 || SourceSHA256.Any(c => !char.IsAsciiHexDigit(c)) ||
            SourceByteCount is < 12 or > 268435456 ||
            string.IsNullOrWhiteSpace(InterpretationProfile) || Encoding.UTF8.GetByteCount(InterpretationProfile) > 128 ||
            Historical && CanImport || RecoveredTrackCount < 0 || RecoveredClipCount < 0 || UnresolvedEventCount < 0 ||
            TotalItems < 0 || Offset < 0 || Offset > TotalItems || Items is null || Items.Length > 32 ||
            Items.Length > TotalItems - Offset || (Items.Length == 0 && TotalItems != 0) ||
            (Offset + Items.Length < TotalItems ? NextOffset != Offset + Items.Length : NextOffset is not null))
            throw new InvalidDataException("The session returned an inconsistent CPR review page.");

        long contentBytes = Encoding.UTF8.GetByteCount(SourceName) + Encoding.UTF8.GetByteCount(InterpretationProfile);
        foreach (var item in Items)
        {
            if (item is null || item.Section is not ("recovered" or "tracks" or "unresolved" or "defaults" or "metadata") ||
                item.Label is null || item.Detail is null)
                throw new InvalidDataException("The session returned an invalid CPR review item.");
            contentBytes += Encoding.UTF8.GetByteCount(item.Label) + Encoding.UTF8.GetByteCount(item.Detail);
        }
        if (contentBytes > MaximumBytes) throw new InvalidDataException("The CPR review page exceeds 128 KiB.");
    }

    public void ValidateContinuation(CPRReviewSnapshot first, int expectedOffset)
    {
        Validate(first.ReviewID, expectedOffset);
        if (SourceName != first.SourceName || SourceSHA256 != first.SourceSHA256 || SourceByteCount != first.SourceByteCount ||
            InterpretationProfile != first.InterpretationProfile || Historical != first.Historical || CanImport != first.CanImport ||
            RecoveredTrackCount != first.RecoveredTrackCount || RecoveredClipCount != first.RecoveredClipCount ||
            UnresolvedEventCount != first.UnresolvedEventCount || TotalItems != first.TotalItems)
            throw new InvalidDataException("The CPR review changed between pages. Inspect the file again.");
    }
}

public sealed class CPRReviewItem
{
    [JsonRequired] public string Section { get; set; } = "";
    [JsonRequired] public string Label { get; set; } = "";
    [JsonRequired] public string Detail { get; set; } = "";
}
