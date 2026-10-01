from signallens.domain.diffing import DiffHunk, PageDiff, diff_lines, drop_noise_hunks, render_diff

OLD = [
    "Pricing",
    "Start accepting payments at just 2%",
    "No setup fees.",
    "UPI | 0%",
    "Last updated: Sep 28, 2026 10:15 AM",
    "© 2025 Razorpay",
]


def test_identical_snapshots_have_no_hunks():
    diff = diff_lines(OLD, list(OLD))
    assert diff.is_empty
    assert diff.changed_ratio == 0
    assert render_diff(diff) == "(no changes)"


def test_price_change_is_a_kept_changed_hunk_with_context():
    new = list(OLD)
    new[1] = "Start accepting payments at just 1.8%"
    diff = diff_lines(OLD, new)
    assert len(diff.hunks) == 1
    hunk = diff.hunks[0]
    assert hunk.op == "changed"
    assert hunk.before == ["Start accepting payments at just 2%"]
    assert hunk.after == ["Start accepting payments at just 1.8%"]
    assert hunk.context_before == ["Pricing"]
    assert hunk.context_after == ["No setup fees.", "UPI | 0%"]
    kept, reasons = drop_noise_hunks(diff)
    assert len(kept.hunks) == 1 and reasons == []


def test_copyright_year_and_timestamp_changes_produce_no_hunks():
    new = list(OLD)
    new[4] = "Last updated: Oct 1, 2026 9:05 PM"
    new[5] = "© 2026 Razorpay"
    diff = diff_lines(OLD, new)
    assert diff.is_empty


def test_volatile_only_hunk_is_dropped_with_reason():
    # e.g. a diff built elsewhere (or a re-wrapped block) whose only difference is volatile
    diff = PageDiff(
        hunks=[DiffHunk("changed", ["© 2025 Razorpay"], ["© 2026 Razorpay"], [], [])],
        lines_added=1,
        lines_removed=1,
        old_line_count=6,
        new_line_count=6,
    )
    kept, reasons = drop_noise_hunks(diff)
    assert kept.is_empty
    assert kept.lines_added == 0 and kept.lines_removed == 0
    assert len(reasons) == 1 and reasons[0].startswith("volatile-only")


def test_rewrapped_and_punctuation_only_changes_are_dropped():
    old = ["Intro", "Start at 2%", "per transaction", "Plans: Standard"]
    new = ["Intro", "Start at 2% per transaction", "Plans — Standard"]
    kept, reasons = drop_noise_hunks(diff_lines(old, new))
    assert kept.is_empty
    assert all(r.startswith("formatting-only") for r in reasons)


def test_meaningful_punctuation_next_to_numbers_is_kept():
    for before, after in [("Fee 2.5%", "Fee 25%"), ("Fee 0%*", "Fee 0%"), ("-5% discount", "5% discount")]:
        kept, reasons = drop_noise_hunks(diff_lines(["x", before], ["x", after]))
        assert len(kept.hunks) == 1, (before, after, reasons)


def test_added_and_removed_hunks_and_counts():
    old = ["A", "B", "C"]
    new = ["A", "C", "D", "E"]
    diff = diff_lines(old, new)
    assert [h.op for h in diff.hunks] == ["removed", "added"]
    assert diff.lines_removed == 1 and diff.lines_added == 2
    assert diff.old_line_count == 3 and diff.new_line_count == 4
    assert diff.changed_ratio == 3 / 7
    assert not diff.is_restructure


def test_restructure_detection():
    diff = diff_lines(["a", "b", "c", "d"], ["w", "x", "y", "z"])
    assert diff.is_restructure


def test_context_never_overlaps_neighbouring_hunks():
    old = ["h", "a1", "same", "b1", "t"]
    new = ["h", "a2", "same", "b2", "t"]
    diff = diff_lines(old, new, context=2)
    assert len(diff.hunks) == 2
    assert diff.hunks[0].context_after == ["same"]
    assert diff.hunks[1].context_before == ["same"]


def test_suppression_patterns():
    old = ["Pricing", "Customer story: Acme grew 3x", "Fee 2%"]
    new = ["Pricing", "Customer story: Globex grew 5x", "Fee 2%"]
    kept, reasons = drop_noise_hunks(diff_lines(old, new), suppress_patterns=["^customer story", "[invalid("])
    assert kept.is_empty
    assert "suppression rule '^customer story'" in reasons[0]

    kept, _ = drop_noise_hunks(
        diff_lines(old, ["Pricing", "Customer story: Globex", "Fee 3%"]),
        suppress_patterns=["^customer story"],
    )
    assert len(kept.hunks) == 1  # the fee change is not covered by the rule


def test_render_format():
    new = list(OLD)
    new[1] = "Start accepting payments at just 1.8%"
    text = render_diff(diff_lines(OLD, new, context=1))
    assert text == (
        "@@ 1 changed\n"
        "  Pricing\n"
        "- Start accepting payments at just 2%\n"
        "+ Start accepting payments at just 1.8%\n"
        "  No setup fees."
    )


def test_render_truncates_cleanly_with_omission_note():
    old = [f"line {i} old value" for i in range(60)]
    new = [f"line {i} new value" if i % 4 == 0 else f"line {i} old value" for i in range(60)]
    diff = diff_lines(old, new)
    text = render_diff(diff, max_chars=300)
    assert len(text) <= 300
    assert text.startswith("@@ 1 changed")
    assert "more hunks omitted" in text
    # every rendered hunk is whole
    assert text.count("@@") + int(text.split("… ")[-1].split(" ")[0]) == len(diff.hunks)


def test_render_single_oversized_hunk():
    diff = diff_lines(["x"], [f"added line number {i}" for i in range(200)])
    text = render_diff(diff, max_chars=200)
    assert len(text) <= 200
    assert "hunk truncated" in text
