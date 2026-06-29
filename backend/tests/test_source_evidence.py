from app.ingestion.source_evidence import (
    classify_name_language,
    extract_product_image_evidence,
    extract_product_name_evidence,
    extract_product_price_evidence,
    product_name_en_candidate,
    product_name_en_rejection_reason,
)


def test_extract_product_name_evidence_reads_json_ld_product_names() -> None:
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Speedy Skinny Brow"
          }
        </script>
      </head>
    </html>
    """

    evidence = extract_product_name_evidence(html)

    assert evidence[0].source == "json_ld_product_name"
    assert evidence[0].name == "Speedy Skinny Brow"
    assert evidence[0].language == "latin"
    assert product_name_en_candidate(evidence).name == "Speedy Skinny Brow"


def test_extract_product_metadata_evidence_reads_json_ld_image_and_offer_price() -> None:
    html = """
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "SOFT FINISH LOOSE POWDER",
        "image": [
          "https://image.example/hera-powder.jpg"
        ],
        "offers": {
          "@type": "Offer",
          "price": "54000",
          "priceCurrency": "KRW"
        }
      }
    </script>
    """

    images = extract_product_image_evidence(html)
    prices = extract_product_price_evidence(html)

    assert images[0].source == "json_ld_product_image"
    assert images[0].url == "https://image.example/hera-powder.jpg"
    assert prices[0].source == "json_ld_offer_price"
    assert prices[0].price == "54000"
    assert prices[0].currency == "KRW"


def test_extract_product_metadata_evidence_reads_meta_image_and_price() -> None:
    html = """
    <meta property="og:image" content="https://image.example/kissme.png" />
    <meta property="product:price:amount" content="16000" />
    <meta property="product:price:currency" content="KRW" />
    """

    images = extract_product_image_evidence(html)
    prices = extract_product_price_evidence(html)

    assert images[0].source == "meta:og:image"
    assert images[0].url == "https://image.example/kissme.png"
    assert prices[0].source == "meta:product:price:amount"
    assert prices[0].price == "16000"
    assert prices[0].currency == "KRW"


def test_extract_product_name_evidence_does_not_use_korean_name_as_english_candidate() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="믹순 히알레배 포어 블러링 크림 50ml" />
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "믹순 히알레배 포어 블러링 크림 50ml"
          }
        </script>
      </head>
    </html>
    """

    evidence = extract_product_name_evidence(html)

    assert "latin" not in {item.language for item in evidence}
    assert product_name_en_candidate(evidence) is None
    assert product_name_en_rejection_reason(evidence) == "mixed_language_without_latin_product_name"


def test_product_name_en_candidate_rejects_mixed_retail_titles_with_brand_english_only() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="메디힐(MEDIHEAL) 더마 토너 패드 100매 8종 - 후기 | 무신사" />
        <meta name="title" content="에이오유(AOU) 에이오유 촘촘 아이브로우밤 - 후기 | 무신사" />
        <title>화홍엠(HWAHONGM) 258 컨실러 브러쉬 - 후기 | 무신사</title>
      </head>
    </html>
    """

    evidence = extract_product_name_evidence(html)

    assert {item.language for item in evidence} == {"mixed"}
    assert product_name_en_candidate(
        evidence,
        rejected_names={"MEDIHEAL", "AOU", "HWAHONGM", "musinsa"},
    ) is None
    assert (
        product_name_en_rejection_reason(
            evidence,
            rejected_names={"MEDIHEAL", "AOU", "HWAHONGM", "musinsa"},
        )
        == "mixed_language_without_latin_product_name"
    )


def test_extract_product_name_evidence_reads_product_from_json_ld_graph() -> None:
    html = """
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@graph": [
          {"@type": "BreadcrumbList", "name": "Home"},
          {"@type": ["Product"], "name": "Vanish Airbrush Concealer"}
        ]
      }
    </script>
    """

    evidence = extract_product_name_evidence(html)

    assert [item.name for item in evidence] == ["Vanish Airbrush Concealer"]
    assert product_name_en_candidate(evidence).source == "json_ld_product_name"


def test_product_name_en_candidate_rejects_brand_or_store_titles() -> None:
    html = """
    <html>
      <head>
        <title>This store is unavailable</title>
        <meta property="og:title" content="MERZY : Another me" />
        <meta name="title" content="MERZY" />
      </head>
    </html>
    """

    evidence = extract_product_name_evidence(html)

    assert product_name_en_candidate(evidence, rejected_names={"MERZY"}) is None
    assert (
        product_name_en_rejection_reason(evidence, rejected_names={"MERZY"})
        == "latin_evidence_rejected_low_confidence"
    )


def test_product_name_en_candidate_keeps_product_like_latin_name() -> None:
    html = """
    <meta property="og:title" content="Speedy Skinny Brow" />
    """

    evidence = extract_product_name_evidence(html)

    assert product_name_en_candidate(evidence, rejected_names={"peripera"}).name == "Speedy Skinny Brow"


def test_classify_name_language_splits_korean_latin_and_mixed_names() -> None:
    assert classify_name_language("SOFT FINISH LOOSE POWDER") == "latin"
    assert classify_name_language("소프트 피니시 루스 파우더") == "ko"
    assert classify_name_language("mude 인스파이어") == "mixed"
    assert classify_name_language("123") == "unknown"
