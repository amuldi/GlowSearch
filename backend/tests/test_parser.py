from app.parser.oliveyoung_html import parse_detail_page, parse_search_results


BASE_URL = "https://www.oliveyoung.co.kr"


def test_parse_search_results_from_oliveyoung_listing_markup() -> None:
    html = """
    <ul class="cate_prd_list">
      <li>
        <div class="prd_info">
          <a href="javascript:common.link.moveGoodsDetail('A000000113988');">
            <img src="//image.oliveyoung.co.kr/item.jpg" alt="상품명 이미지" />
          </a>
          <div class="prd_name">
            <a>
              <span class="tx_brand">BRTC</span>
              <p class="tx_name">BRTC V10 비타민 화이트닝 슬리핑팩 100ml</p>
            </a>
          </div>
          <p class="prd_price">
            <span class="tx_org"><span class="tx_num">24,000</span>원</span>
          </p>
        </div>
      </li>
    </ul>
    """

    records = parse_search_results(html, base_url=BASE_URL, limit=10)

    assert len(records) == 1
    assert records[0].source_brand_name == "BRTC"
    assert records[0].product_name_ko == "BRTC V10 비타민 화이트닝 슬리핑팩 100ml"
    assert records[0].regular_price == 24000
    assert records[0].image_url == "https://image.oliveyoung.co.kr/item.jpg"
    assert records[0].source_product_id == "A000000113988"
    assert records[0].source_url == (
        "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000113988"
    )


def test_parse_display_price_range_from_official_source() -> None:
    html = """
    <ul class="cate_prd_list">
      <li>
        <span class="tx_brand">브랜드</span>
        <p class="tx_name">옵션 가격 상품</p>
        <p class="prd_price"><span class="tx_cur">19,900 원 ~</span></p>
      </li>
    </ul>
    """

    records = parse_search_results(html, base_url=BASE_URL, limit=10)

    assert records[0].regular_price == 19900


def test_parse_original_and_sale_prices_from_oliveyoung_listing_markup() -> None:
    html = """
    <ul class="cate_prd_list">
      <li>
        <span class="tx_brand">라운드랩</span>
        <p class="tx_name">라운드랩 자작나무 수분 톤업 선크림</p>
        <p class="prd_price">
          <span class="tx_org"><span class="tx_num">25,000</span>원</span>
          <span class="tx_cur"><span class="tx_num">23,900</span>원</span>
        </p>
      </li>
    </ul>
    """

    records = parse_search_results(html, base_url=BASE_URL, limit=10)

    assert records[0].regular_price == 23900
    assert records[0].original_price == 25000
    assert records[0].sale_price == 23900


def test_parse_listing_without_discount_does_not_set_sale_price() -> None:
    html = """
    <ul class="cate_prd_list">
      <li>
        <span class="tx_brand">컬러그램</span>
        <p class="tx_name">컬러그램 무할인 상품</p>
        <p class="prd_price">
          <span class="tx_org"><span class="tx_num">17,000</span>원</span>
          <span class="tx_cur"><span class="tx_num">17,000</span>원</span>
        </p>
      </li>
    </ul>
    """

    records = parse_search_results(html, base_url=BASE_URL, limit=10)

    assert records[0].regular_price == 17000
    assert records[0].original_price == 17000
    assert records[0].sale_price is None


def test_parse_modern_oliveyoung_brand_name_markup() -> None:
    html = """
    <ul>
      <li data-ref-goodsno="A000000111111">
        <a href="/store/goods/getGoodsDetail.do?goodsNo=A000000111111">
          <img src="https://image.oliveyoung.co.kr/item.jpg" />
        </a>
        <p class="ProductCard_brand__abc">식물나라</p>
        <h3 data-qa-name="text-product-title">식물나라 가벼운 수분 선 젤 60ml 단품/2입 기획</h3>
        <span data-qa-name="text-product-original-price">25,800원</span>
      </li>
    </ul>
    """

    records = parse_search_results(html, base_url=BASE_URL, limit=10)

    assert records[0].source_brand_name == "식물나라"
    assert records[0].product_name_ko == "식물나라 가벼운 수분 선 젤 60ml 단품/2입 기획"
    assert records[0].regular_price == 25800


def test_parse_oliveyoung_card_data_attributes() -> None:
    html = """
    <ul>
      <li
        data-goods-no="A000000238408"
        data-brand-nm="믹순"
        data-goods-nm="믹순 히알레배 포어 블러링 크림 50ml"
        data-normal-price="14,900"
        data-img-url="//image.oliveyoung.co.kr/item.jpg"
      ></li>
    </ul>
    """

    records = parse_search_results(html, base_url=BASE_URL, limit=10)

    assert records[0].source_brand_name == "믹순"
    assert records[0].product_name_ko == "믹순 히알레배 포어 블러링 크림 50ml"
    assert records[0].regular_price == 14900
    assert records[0].image_url == "https://image.oliveyoung.co.kr/item.jpg"
    assert records[0].source_url == (
        "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000238408"
    )


def test_parse_oliveyoung_embedded_product_literal() -> None:
    html = """
    <script>
      window.searchGoods = [{
        goodsNo: 'A000000238408',
        onlBrndNm: '믹순',
        goodsNm: '믹순 히알레배 포어 블러링 크림 50ml',
        nrmlAmt: '14900',
        mainImgUrl: '//image.oliveyoung.co.kr/item.jpg'
      }];
    </script>
    """

    records = parse_search_results(html, base_url=BASE_URL, limit=10)

    assert records[0].source_brand_name == "믹순"
    assert records[0].product_name_ko == "믹순 히알레배 포어 블러링 크림 50ml"
    assert records[0].regular_price == 14900
    assert records[0].source_product_id == "A000000238408"


def test_parse_structured_product_fields() -> None:
    html = """
    <script type="application/ld+json">
      {
        "@type": "Product",
        "goodsNo": "A000000238409",
        "brandName": "롬앤",
        "goodsName": "롬앤 글래스팅 컬러 글로스",
        "categoryName": "메이크업 > 립",
        "originalPrice": "13000",
        "priceToPay": "9900",
        "discountRate": "23",
        "ratingValue": "4.7",
        "reviewCount": "321",
        "description": "원본 설명",
        "options": ["01 피오니 발레"],
        "stockStatus": "in_stock",
        "imageUrl": "//image.oliveyoung.co.kr/item.jpg"
      }
    </script>
    """

    records = parse_search_results(html, base_url=BASE_URL, limit=10)

    assert records[0].category == "메이크업 > 립"
    assert records[0].sale_price == 9900
    assert records[0].discount_rate == 23
    assert records[0].rating == 4.7
    assert records[0].review_count == 321
    assert records[0].description == "원본 설명"
    assert records[0].options == ["01 피오니 발레"]
    assert records[0].sold_out is False


def test_parse_next_detail_page_price_and_name() -> None:
    html = """
    <div class="GoodsDetailInfo_title-area__unu7g" data-qa-name="text-product-title">
      <h3 class="GoodsDetailInfo_title__Vl_IP">[NEW] 공식 제품명</h3>
    </div>
    <span class="GoodsDetailInfo_price__AoTh8" data-qa-name="text-product-discount-price">
      <span>13,000</span><span>원 ~</span>
    </span>
    """

    record = parse_detail_page(html, base_url=BASE_URL)

    assert record.product_name_ko == "[NEW] 공식 제품명"
    assert record.regular_price == 13000
    assert record.sale_price == 13000


def test_parse_detail_shades_from_option_markup() -> None:
    html = """
    <html>
      <head><meta property="og:title" content="컬러 립 틴트 | 올리브영" /></head>
      <body>
        <button class="prd_brand">fwee</button>
        <ul class="prd_option_box">
          <li>01. 베이비 핑크</li>
          <li>02. 로지 코랄</li>
        </ul>
      </body>
    </html>
    """

    record = parse_detail_page(html, base_url=BASE_URL)

    assert record.product_name_ko == "컬러 립 틴트"
    assert record.source_brand_name == "fwee"
    assert record.shade == "01. 베이비 핑크, 02. 로지 코랄"
