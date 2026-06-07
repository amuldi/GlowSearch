from app.service.source_policy import SourcePolicy


def test_source_policy_labels_and_allows_configured_prefixes() -> None:
    policy = SourcePolicy(allowed_prefixes=("oliveyoung", "musinsa", "barcode"))

    assert policy.allows("oliveyoung:public-api") is True
    assert policy.allows("musinsa") is True
    assert policy.allows("official") is False
    assert policy.label("barcode:lookup") == "Barcode/GTIN"
    assert policy.priority("oliveyoung:public-api") < policy.priority("musinsa")
