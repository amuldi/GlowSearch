from app.core.config import Settings
from app.service.factory import _build_collectors


def test_build_collectors_adds_source_specific_json_providers(tmp_path) -> None:
    settings = Settings(
        verified_catalog_path=tmp_path / "verified_products.json",
        oliveyoung_public_api_enabled=False,
        musinsa_api_enabled=True,
        musinsa_api_base_url="https://provider.example/musinsa",
        oliveyoung_global_api_enabled=True,
        oliveyoung_global_api_base_url="https://provider.example/oliveyoung-global",
        official_brand_api_enabled=True,
        official_brand_api_base_url="https://provider.example/official",
    )

    collectors = _build_collectors(settings)

    assert [collector.name for collector in collectors] == [
        "oliveyoung:verified-cache",
        "musinsa",
        "oliveyoung-global",
        "official",
    ]
