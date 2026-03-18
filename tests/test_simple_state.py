from app.worker.simple_state import SimpleStateStore


def test_state_records_attempts_and_blocks_applied(tmp_path):
    store = SimpleStateStore(str(tmp_path / "state.json"))

    assert store.should_attempt("job-1", max_attempts=2) is True

    record = store.record(
        key="job-1",
        title="Backend Engineer",
        company="Acme",
        apply_url="https://example.com/jobs/1",
        status="applied",
        details="Submitted by automation",
        screenshot_path=None,
    )

    assert record["attempts"] == 1
    assert store.should_attempt("job-1", max_attempts=2) is False


def test_state_limits_failed_retries(tmp_path):
    store = SimpleStateStore(str(tmp_path / "state.json"))

    store.record(
        key="job-2",
        title="Platform Engineer",
        company="Acme",
        apply_url="https://example.com/jobs/2",
        status="failed",
        details="Page timeout",
        screenshot_path=None,
    )
    assert store.should_attempt("job-2", max_attempts=2) is True

    store.record(
        key="job-2",
        title="Platform Engineer",
        company="Acme",
        apply_url="https://example.com/jobs/2",
        status="failed",
        details="Page timeout",
        screenshot_path=None,
    )
    assert store.should_attempt("job-2", max_attempts=2) is False
