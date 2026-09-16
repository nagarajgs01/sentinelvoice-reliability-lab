from sentinelvoice.benchmark import (
    benchmark_transcript,
    keyword_coverage,
    normalize_text,
    real_time_factor,
    word_error_rate,
)


def test_normalization_ignores_case_and_punctuation() -> None:
    assert normalize_text("Hello, WORLD!") == ["hello", "world"]


def test_exact_transcript_has_zero_wer() -> None:
    assert word_error_rate("check order thirteen", "check order thirteen") == 0


def test_word_substitution_is_measured() -> None:
    assert word_error_rate("check order thirteen", "check order thirty") == 1 / 3


def test_benchmark_applies_quality_gate() -> None:
    result = benchmark_transcript("please cancel my order", "please cancel my order", 250)
    assert result["accuracy_percent"] == 100
    assert result["passed"] is True


def test_keyword_coverage_is_case_insensitive() -> None:
    assert keyword_coverage(["refund", "order number"], "Your REFUND for the order number is ready") == 1


def test_real_time_factor() -> None:
    assert real_time_factor(0.5, 2.0) == 0.25
