from app.worker.automation import _find_matching_card_index


def test_find_matching_card_index_prefers_company_and_title_match():
    card_texts = [
        "Other Co - Backend Engineer\nBangalore",
        "Acme Corp - Backend Engineer\nRemote",
    ]

    assert _find_matching_card_index(card_texts, "Backend Engineer", "Acme Corp") == 1


def test_find_matching_card_index_falls_back_to_title_only():
    card_texts = [
        "Platform Labs - Site Reliability Engineer\nRemote",
        "DataWorks - Backend Engineer\nPune",
    ]

    assert _find_matching_card_index(card_texts, "Backend Engineer", "") == 1


def test_find_matching_card_index_falls_back_to_company_only():
    card_texts = [
        "Platform Labs - Site Reliability Engineer\nRemote",
        "DataWorks - Backend Engineer\nPune",
    ]

    assert _find_matching_card_index(card_texts, "", "Platform Labs") == 0
