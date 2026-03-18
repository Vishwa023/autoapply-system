from app.services.instahyre_source import extract_job_links_from_html


def test_extract_job_links_filters_and_dedupes():
    links = [
        "https://www.instahyre.com/candidate/opportunities/123/",
        "/candidate/opportunities/123/",
        "https://www.instahyre.com/job/swe/",
        "https://www.google.com/jobs/1",
        "",
    ]

    out = extract_job_links_from_html("https://www.instahyre.com", links)
    assert "https://www.instahyre.com/candidate/opportunities/123" in out
    assert "https://www.instahyre.com/job/swe" in out
    assert len(out) == 2
