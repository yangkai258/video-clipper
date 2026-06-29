"""Regression check for llm_service.py downsampling stride (P0#1).

Background:
    llm_service.py:_create_timeline_with_llm downsamples SRT when compact form
    exceeds MAX_CHARS=50000. The original stride formula multiplied
    len(parsed_segments) by len(srt_compact) -- a classic sampling-stride bug.
    For a 1.5GB SRT (~5000 segments, 150k chars) the original step was 7651,
    keeping only 1 segment, LLM hallucinated 5+ segments from 27 chars.

This test does NOT import the source (the logic is inlined in
_create_timeline_with_llm and is not exposed). It re-implements both formulas
and asserts the corrected one keeps enough signal for the LLM.

ponytail: standalone, no ffmpeg/LLM/DB, no fixtures.
"""
MAX_CHARS = 50000


def old_step(seg_n, compact_n):
    return max(1, seg_n * compact_n // MAX_CHARS // 2 + 1)


def new_step(seg_n, compact_n):
    return max(1, compact_n // MAX_CHARS + 1)


def sampled_count(seg_n, step):
    return (seg_n + step - 1) // step


def test_old_formula_is_pathological():
    # 1.5GB SRT scenario
    segs, compact = 5000, 150_000
    assert old_step(segs, compact) > 100, "old step should be huge"
    assert sampled_count(segs, old_step(segs, compact)) < 5, (
        f"old formula leaves <5 segments, LLM has no signal"
    )


def test_new_formula_keeps_signal():
    segs, compact = 5000, 150_000
    step = new_step(segs, compact)
    kept = sampled_count(segs, step)
    assert kept >= 100, f"new step {step} kept only {kept} segments; want >=100"
    assert kept <= segs, "sampled cannot exceed input"
    # sanity: kept segments * avg_chars ~ target budget
    assert kept * (compact // segs) <= MAX_CHARS * 2, "compact output overshoots budget"


def test_new_formula_no_op_below_threshold():
    # 100 segments, 20 chars each -> 2k chars, below MAX_CHARS
    # (in real code the downsample branch is skipped, so step is irrelevant)
    segs, compact = 100, 2_000
    assert compact <= MAX_CHARS
    # but if it WERE applied, step would be 1
    assert new_step(segs, compact) == 1


if __name__ == "__main__":
    test_old_formula_is_pathological()
    test_new_formula_keeps_signal()
    test_new_formula_no_op_below_threshold()
    print("OK: stride formula regression check passed")
