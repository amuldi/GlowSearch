from app.service.source_policy import SourcePolicy


def test_source_policy_labels_and_allows_configured_prefixes() -> None:
    policy = SourcePolicy(
        allowed_prefixes=("oliveyoung", "oliveyoung-global", "musinsa", "barcode", "hwahae")
    )

    assert policy.allows("oliveyoung:public-api") is True
    assert policy.allows("oliveyoung-global") is True
    assert policy.allows("musinsa") is True
    assert policy.allows("hwahae") is True
    assert policy.allows("official") is False
    assert policy.label("oliveyoung-global") == "Olive Young Global"
    assert policy.label("barcode:lookup") == "Barcode/GTIN"
    assert policy.label("hwahae") == "Hwahae"
    assert policy.priority("oliveyoung:public-api") < policy.priority("musinsa")
    assert policy.priority("oliveyoung:public-api") < policy.priority("oliveyoung-global")
    assert policy.priority("oliveyoung-global") < policy.priority("musinsa")
