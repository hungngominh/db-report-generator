from scripts.lib.schema import validation_errors


def test_fixture_valid_against_schema(sample_report):
    assert validation_errors(sample_report) == []


def test_fixture_is_multi_target(sample_report):
    ids = {t["target_id"] for t in sample_report["targets"]}
    assert {"t-main", "t-analytics"} <= ids


def test_fixture_has_error_target(sample_report):
    err = [t for t in sample_report["targets"] if t["collection_status"] == "error"]
    assert err and err[0]["diagnostics"] == {}


def test_fixture_has_skipped_and_invalid_sampling(sample_report):
    main = next(t for t in sample_report["targets"] if t["target_id"] == "t-main")
    diags = main["diagnostics"]
    assert diags["wait_events"]["status"] == "skipped"
    assert diags["wraparound"]["quality"]["sampling_valid"] is False
