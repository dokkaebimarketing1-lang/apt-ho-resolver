"""AuctionChannel 단위 테스트 — mock httpx.Client + mock PDF 기반.

테스트 전략:
- _extract_from_text: PDF 없는 순수 텍스트 → 정규식 추출 검증 (한글 포함)
- _parse_pdf: PyPDF2 로 생성한 mock PDF → 텍스트 추출 검증 (ASCII)
- _do_collect: mock httpx.Client 로 HTTP 호출 모킹 → 전체 흐름 검증
"""

from __future__ import annotations

from io import BytesIO
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from PyPDF2 import PdfReader

from src.channels.auction import (
    AuctionChannel,
    _extract_from_text,
)

# ============================================================
# Helpers
# ============================================================


def _make_search_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    """모의 경매 검색 API 응답."""
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "정상"},
            "body": {
                "items": {"item": items},
                "numOfRows": 20,
                "pageNo": 1,
                "totalCount": len(items),
            },
        }
    }


def _make_search_item(
    case_no: str = "2025타경12345",
    court_name: str = "서울중앙지방법원",
    goods_seq: str = "1",
) -> dict[str, Any]:
    """모의 경매 물건 항목."""
    return {
        "caseNo": case_no,
        "courtName": court_name,
        "goodsSeq": goods_seq,
        "sigunguCd": "11680",
        "addr": "서울특별시 강남구",
    }


def _make_pdf_with_text(text: str) -> bytes:
    """extract_text() 로 읽히는 텍스트를 포함한 PDF 생성.

    Args:
        text: 포함할 텍스트 (ASCII 만 안전 — 한글은 비권장).

    Returns:
        텍스트가 포함된 유효한 PDF 바이트.
    """
    text_bytes = text.encode("ascii", errors="replace")
    stream_data = b"BT /F1 12 Tf 50 700 Td (" + text_bytes + b") Tj ET"
    stream_length = len(stream_data)

    obj1 = b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj"
    obj2 = b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj"
    obj3 = (
        b"3 0 obj<</Type/Page/Parent 2 0 R"
        b"/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>endobj"
    )
    obj4 = (
        b"4 0 obj<</Length " + str(stream_length).encode() + b">>stream\n"
        + stream_data + b"\nendstream\nendobj"
    )
    obj5 = b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj"

    obj_parts = [obj1, obj2, obj3, obj4, obj5]
    body = b"\n".join(obj_parts)

    offsets = [0]
    for i in range(len(obj_parts) - 1):
        offsets.append(offsets[-1] + len(obj_parts[i]) + 1)

    xref_header = b"xref\n0 6\n"
    xref_entries = [b"0000000000 65535 f \n"]
    for off in offsets:
        xref_entries.append(f"{off:010d} 00000 n \n".encode())

    xref = xref_header + b"".join(xref_entries)

    pdf_header = b"%PDF-1.4\n"
    startxref_offset = len(pdf_header) + len(body) + len(xref)
    trailer = (
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n"
        + str(startxref_offset).encode() + b"\n%%EOF"
    )

    pdf = pdf_header + body + xref + trailer
    return pdf


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_client() -> MagicMock:
    """기본 mock httpx.Client."""
    client = MagicMock(spec=httpx.Client)

    search_resp = MagicMock(spec=httpx.Response)
    search_resp.json.return_value = _make_search_response([])
    search_resp.raise_for_status.return_value = None
    client.get.return_value = search_resp

    return client


@pytest.fixture
def channel(mock_client: MagicMock) -> AuctionChannel:
    """AuctionChannel with mock client."""
    return AuctionChannel(api_key="test-key", client=mock_client)


# ============================================================
# Test: _extract_from_text (순수 함수 — 한글 포함)
# ============================================================


class TestExtractFromText:
    """_extract_from_text — 정규식 기반 텍스트 추출."""

    def test_full_match(self) -> None:
        """Given 모든 필드 포함 PDF 텍스트 When 추출 Then 모든 값 반환"""
        text = (
            "아파트 감정평가서\n"
            "101동 203호\n"
            "15층\n"
            "전용면적 84.12㎡\n"
            "공급면적 109.84㎡\n"
            "남향\n"
            "감정가 500,000,000원\n"
        )
        result = _extract_from_text(text)
        assert result["dong"] == "101동"
        assert result["ho"] == "203호"
        assert result["floor"] == 15
        assert result["area_m2"] == 84.12
        assert result["supply_area_m2"] == 109.84
        assert result["direction"] == "S"
        assert result["direction_kr"] == "남향"
        assert result["appraised_price_won"] == 500_000_000

    def test_no_space_between_dong_ho(self) -> None:
        """Given 동호 사이 공백 없음 When 추출 Then 정상 파싱"""
        result = _extract_from_text("101동203호")
        assert result["dong"] == "101동"
        assert result["ho"] == "203호"

    def test_single_digit_dong(self) -> None:
        """Given 1자리 동 When 추출 Then 정상"""
        result = _extract_from_text("1동 101호")
        assert result["dong"] == "1동"
        assert result["ho"] == "101호"

    def test_three_digit_dong(self) -> None:
        """Given 3자리 동 When 추출 Then 정상"""
        result = _extract_from_text("101동 1204호")
        assert result["dong"] == "101동"
        assert result["ho"] == "1204호"

    def test_four_digit_ho(self) -> None:
        """Given 4자리 호 When 추출 Then 정상"""
        result = _extract_from_text("101동 1503호")
        assert result["ho"] == "1503호"

    def test_floor_extraction(self) -> None:
        """Given 층 정보 When 추출 Then 정수 반환"""
        result = _extract_from_text("아파트 23층")
        assert result["floor"] == 23

    def test_area_decimal(self) -> None:
        """Given 소수점 면적 When 추출 Then float 반환"""
        result = _extract_from_text("전용면적 59.99㎡")
        assert result["area_m2"] == 59.99

    def test_area_integer(self) -> None:
        """Given 정수 면적 When 추출 Then float 반환"""
        result = _extract_from_text("84㎡")
        assert result["area_m2"] == 84.0

    def test_area_no_decimal_space(self) -> None:
        """Given 면적 숫자와 ㎡ 사이 공백 없음 When 추출 Then 정상"""
        result = _extract_from_text("84.12㎡")
        assert result["area_m2"] == 84.12

    def test_all_directions(self) -> None:
        """Given 8개 방향 When 추출 Then 영문 코드 매핑"""
        cases = [
            ("남향", "S"),
            ("북향", "N"),
            ("동향", "E"),
            ("서향", "W"),
            ("남동향", "SE"),
            ("남서향", "SW"),
            ("북동향", "NE"),
            ("북서향", "NW"),
        ]
        for kr, en in cases:
            result = _extract_from_text(f"방향: {kr}")
            assert result["direction"] == en, f"Failed for {kr} -> {en}"
            assert result["direction_kr"] == kr

    def test_appraised_price_with_comma(self) -> None:
        """Given 콤마 포함 감정가 When 추출 Then 정수"""
        result = _extract_from_text("감정가 1,234,567,890원")
        assert result["appraised_price_won"] == 1_234_567_890

    def test_appraised_price_alt_wording(self) -> None:
        """Given '감정평가액' 표기 When 추출 Then 정상"""
        result = _extract_from_text("감정평가액 500,000,000")
        assert result["appraised_price_won"] == 500_000_000

    def test_no_dong_ho(self) -> None:
        """Given 동호 없음 When 추출 Then None"""
        result = _extract_from_text("단지 정보 없음")
        assert result["dong"] is None
        assert result["ho"] is None

    def test_no_floor(self) -> None:
        """Given 층 정보 없음 When 추출 Then None"""
        result = _extract_from_text("101동 203호 남향")
        assert result["floor"] is None

    def test_no_area(self) -> None:
        """Given 면적 정보 없음 When 추출 Then None"""
        result = _extract_from_text("101동 203호 15층")
        assert result["area_m2"] is None

    def test_no_direction(self) -> None:
        """Given 방향 정보 없음 When 추출 Then None"""
        result = _extract_from_text("101동 203호 15층 84.12㎡")
        assert result["direction"] is None
        assert result["direction_kr"] is None

    def test_no_appraised_price(self) -> None:
        """Given 감정가 정보 없음 When 추출 Then None"""
        result = _extract_from_text("101동 203호 15층")
        assert result["appraised_price_won"] is None

    def test_empty_text(self) -> None:
        """Given 빈 텍스트 When 추출 Then 모든 값 None"""
        result = _extract_from_text("")
        assert all(v is None for v in result.values())

    def test_multiline_noise(self) -> None:
        """Given 잡음 많은 텍스트 When 추출 Then 정상 추출"""
        text = (
            "감정평가서\n"
            "===========\n"
            "사건번호: 2025타경12345\n"
            "물건: 서울 강남구 역삼동\n"
            "101동 203호\n"
            "건물 구조: 철근콘크리트\n"
            "15층/지하2층\n"
            "전용면적 84.12㎡\n"
            "대지권면적 32.45㎡\n"
            "남향\n"
            "감정평가액 950,000,000원\n"
            "비고: 현황 미상\n"
        )
        result = _extract_from_text(text)
        assert result["dong"] == "101동"
        assert result["ho"] == "203호"
        assert result["floor"] == 15
        assert result["area_m2"] == 84.12
        assert result["direction"] == "S"
        assert result["appraised_price_won"] == 950_000_000

    def test_keyword_in_appraised_wording(self) -> None:
        """Given 다양한 감정가 표기법 When 추출 Then 정상"""
        cases = [
            "감정가 300,000,000원",
            "감정평가액 1,500,000,000",
            "감정평가금액 200,000,000원",
        ]
        for text in cases:
            result = _extract_from_text(text)
            assert result["appraised_price_won"] is not None


# ============================================================
# Test: _parse_pdf (PDF 파싱 — ASCII 텍스트)
# ============================================================


class TestParsePdf:
    """_parse_pdf — pdf_bytes -> dict 변환."""

    def test_parse_valid_pdf(self) -> None:
        """Given 유효한 PDF When _parse_pdf Then 텍스트 추출"""
        ch = AuctionChannel(
            api_key="test-key", client=MagicMock(spec=httpx.Client)
        )
        pdf = _make_pdf_with_text("101dong 203ho 15FLOOR 84.12m2 SOUTH")
        result = ch._parse_pdf(pdf)
        assert isinstance(result, dict)

    def test_parse_invalid_bytes(self) -> None:
        """Given 무효한 바이트 When _parse_pdf Then 빈 dict"""
        ch = AuctionChannel(
            api_key="test-key", client=MagicMock(spec=httpx.Client)
        )
        result = ch._parse_pdf(b"not a pdf at all")
        assert result == {}

    def test_parse_empty_bytes(self) -> None:
        """Given 빈 바이트 When _parse_pdf Then 빈 dict"""
        ch = AuctionChannel(
            api_key="test-key", client=MagicMock(spec=httpx.Client)
        )
        result = ch._parse_pdf(b"")
        assert result == {}


# ============================================================
# Test: AuctionChannel collect()
# ============================================================


class TestAuctionChannel:
    """AuctionChannel collect() 기본 동작."""

    def test_channel_attrs(self) -> None:
        """Given AuctionChannel class Then channel_name/reliability 설정됨"""
        assert AuctionChannel.channel_name == "auction"
        assert AuctionChannel.reliability == 0.95

    def test_collect_empty(self, channel: AuctionChannel,
                          mock_client: MagicMock) -> None:
        """Given 검색 결과 없음 When collect Then 빈 리스트"""
        result = channel.collect({"keyword": "없는단지"})
        assert result == []

    def test_collect_one_item(self, channel: AuctionChannel,
                              mock_client: MagicMock) -> None:
        """Given 1개 검색 결과 When collect Then 파싱 결과 반환"""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.json.return_value = _make_search_response([
            _make_search_item("2025타경12345", "서울중앙지방법원", "1"),
        ])
        search_resp.raise_for_status.return_value = None

        pdf = _make_pdf_with_text("101dong 203ho 15 floor 84.12 m2")
        pdf_resp = MagicMock(spec=httpx.Response)
        pdf_resp.content = pdf
        pdf_resp.headers = {"content-type": "application/pdf"}
        pdf_resp.raise_for_status.return_value = None

        mock_client.get.side_effect = [search_resp, pdf_resp]

        result = channel.collect({"keyword": "래미안"})
        assert len(result) == 1
        item = result[0]
        assert item["case_no"] == "2025타경12345"
        assert item["court_name"] == "서울중앙지방법원"
        assert item["goods_seq"] == "1"

    def test_collect_korean_pdf_text(self, channel: AuctionChannel,
                                      mock_client: MagicMock) -> None:
        """Given 검색 결과 When collect Then 메타데이터 채워짐"""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.json.return_value = _make_search_response([
            _make_search_item("CASE1", "수원지방법원", "3"),
        ])
        search_resp.raise_for_status.return_value = None

        pdf = _make_pdf_with_text("test content")
        pdf_resp = MagicMock(spec=httpx.Response)
        pdf_resp.content = pdf
        pdf_resp.headers = {"content-type": "application/pdf"}
        pdf_resp.raise_for_status.return_value = None

        mock_client.get.side_effect = [search_resp, pdf_resp]

        result = channel.collect({"keyword": "test"})
        assert len(result) == 1
        assert result[0]["case_no"] == "CASE1"
        assert result[0]["court_name"] == "수원지방법원"
        assert result[0]["goods_seq"] == "3"

    def test_collect_multiple_items(self, channel: AuctionChannel,
                                    mock_client: MagicMock) -> None:
        """Given 2개 검색 결과 When collect Then 각각 파싱 완료"""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.json.return_value = _make_search_response([
            _make_search_item("CASE1", "서울중앙지방법원", "1"),
            _make_search_item("CASE2", "수원지방법원", "2"),
        ])
        search_resp.raise_for_status.return_value = None

        pdf1 = _make_pdf_with_text("101 DONG 101 HO 10F")
        pdf_resp1 = MagicMock(spec=httpx.Response)
        pdf_resp1.content = pdf1
        pdf_resp1.headers = {"content-type": "application/pdf"}
        pdf_resp1.raise_for_status.return_value = None

        pdf2 = _make_pdf_with_text("102 DONG 202 HO 15F")
        pdf_resp2 = MagicMock(spec=httpx.Response)
        pdf_resp2.content = pdf2
        pdf_resp2.headers = {"content-type": "application/pdf"}
        pdf_resp2.raise_for_status.return_value = None

        mock_client.get.side_effect = [search_resp, pdf_resp1, pdf_resp2]

        result = channel.collect({"keyword": "아파트"})
        assert len(result) == 2

    def test_pdf_download_fails_fallback_to_statement(
        self, channel: AuctionChannel, mock_client: MagicMock
    ) -> None:
        """Given 감정평가서 PDF 실패 When collect Then 매각물건명세서 시도"""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.json.return_value = _make_search_response([
            _make_search_item("CASE1", "서울중앙지방법원", "1"),
        ])
        search_resp.raise_for_status.return_value = None

        err_resp = httpx.HTTPStatusError(
            "404", request=MagicMock(),
            response=MagicMock(spec=httpx.Response, status_code=404)
        )
        pdf2 = _make_pdf_with_text("test content")
        pdf_resp2 = MagicMock(spec=httpx.Response)
        pdf_resp2.content = pdf2
        pdf_resp2.headers = {"content-type": "application/pdf"}
        pdf_resp2.raise_for_status.return_value = None

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            mock_client.get.side_effect = [search_resp, err_resp, pdf_resp2]
            result = channel.collect({"keyword": "래미안"})

        assert len(result) == 1
        assert result[0]["case_no"] == "CASE1"

    def test_both_pdfs_fail(self, channel: AuctionChannel,
                            mock_client: MagicMock) -> None:
        """Given 두 PDF 모두 실패 When collect Then 메타데이터만 채워짐"""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.json.return_value = _make_search_response([
            _make_search_item("CASE1", "서울중앙지방법원", "1"),
        ])
        search_resp.raise_for_status.return_value = None

        err_resp = httpx.HTTPStatusError(
            "404", request=MagicMock(),
            response=MagicMock(spec=httpx.Response, status_code=404)
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            mock_client.get.side_effect = [search_resp, err_resp, err_resp]
            result = channel.collect({"keyword": "래미안"})

        assert len(result) == 1
        item = result[0]
        assert item["case_no"] == "CASE1"
        assert item["dong"] is None

    def test_single_item_as_dict(self, channel: AuctionChannel,
                                 mock_client: MagicMock) -> None:
        """Given item 이 dict (list 아님) When collect Then 리스트 변환"""
        raw = _make_search_response([])
        raw["response"]["body"]["items"]["item"] = _make_search_item("CASE1")
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.json.return_value = raw
        search_resp.raise_for_status.return_value = None

        pdf = _make_pdf_with_text("test")
        pdf_resp = MagicMock(spec=httpx.Response)
        pdf_resp.content = pdf
        pdf_resp.headers = {"content-type": "application/pdf"}
        pdf_resp.raise_for_status.return_value = None

        mock_client.get.side_effect = [search_resp, pdf_resp]

        result = channel.collect({"keyword": "테스트"})
        assert len(result) == 1

    def test_http_error_fallback(self, channel: AuctionChannel,
                                  mock_client: MagicMock) -> None:
        """Given HTTP 오류 When collect Then 빈 리스트 (재시도 후 폴백)"""
        err_resp = MagicMock(spec=httpx.Response, status_code=500)
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=err_resp
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = channel.collect({"keyword": "래미안"})
        assert result == []

    def test_timeout_fallback(self, channel: AuctionChannel,
                               mock_client: MagicMock) -> None:
        """Given 타임아웃 When collect Then 빈 리스트"""
        mock_client.get.side_effect = httpx.TimeoutException(
            "timeout", request=MagicMock()
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = channel.collect({"keyword": "래미안"})
        assert result == []

    def test_search_params_keyword(self, channel: AuctionChannel,
                                    mock_client: MagicMock) -> None:
        """Given keyword 검색 When collect Then params 에 keyword 포함"""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.json.return_value = _make_search_response([])
        search_resp.raise_for_status.return_value = None
        mock_client.get.return_value = search_resp

        channel.collect({"keyword": "래미안"})
        called_params = mock_client.get.call_args[1]["params"]
        assert called_params["keyword"] == "래미안"

    def test_search_params_sigungu(self, channel: AuctionChannel,
                                    mock_client: MagicMock) -> None:
        """Given sigungu_cd When collect Then params 에 sigunguCd 포함"""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.json.return_value = _make_search_response([])
        search_resp.raise_for_status.return_value = None
        mock_client.get.return_value = search_resp

        channel.collect({"sigungu_cd": "11680"})
        called_params = mock_client.get.call_args[1]["params"]
        assert called_params["sigunguCd"] == "11680"

    def test_search_params_case_no(self, channel: AuctionChannel,
                                    mock_client: MagicMock) -> None:
        """Given case_no When collect Then params 에 caseNo 포함"""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.json.return_value = _make_search_response([])
        search_resp.raise_for_status.return_value = None
        mock_client.get.return_value = search_resp

        channel.collect({"case_no": "2025타경12345"})
        called_params = mock_client.get.call_args[1]["params"]
        assert called_params["caseNo"] == "2025타경12345"

    def test_no_pdf_content_type(self, channel: AuctionChannel,
                                  mock_client: MagicMock) -> None:
        """Given PDF content-type 이 아님 When collect Then 건너뜀"""
        search_resp = MagicMock(spec=httpx.Response)
        search_resp.json.return_value = _make_search_response([
            _make_search_item("CASE1"),
        ])
        search_resp.raise_for_status.return_value = None

        # 감정평가서 PDF 응답이지만 content-type 이 text/html
        html_resp1 = MagicMock(spec=httpx.Response)
        html_resp1.content = b"<html>error</html>"
        html_resp1.headers = {"content-type": "text/html"}
        html_resp1.raise_for_status.return_value = None

        # 매각물건명세서 PDF 도 text/html
        html_resp2 = MagicMock(spec=httpx.Response)
        html_resp2.content = b"<html>error</html>"
        html_resp2.headers = {"content-type": "text/html"}
        html_resp2.raise_for_status.return_value = None

        mock_client.get.side_effect = [search_resp, html_resp1, html_resp2]

        result = channel.collect({"keyword": "테스트"})
        assert len(result) == 1
        assert result[0]["dong"] is None


# ============================================================
# Test: ChannelCollector Protocol
# ============================================================


class TestChannelProtocol:
    """AuctionChannel 이 ChannelCollector Protocol 을 만족하는지 검증."""

    def test_protocol_isinstance(self) -> None:
        """Given AuctionChannel instance When isinstance 검사 Then True"""
        from src.channels.base import ChannelCollector
        ch = AuctionChannel(
            api_key="test-key", client=MagicMock(spec=httpx.Client)
        )
        assert isinstance(ch, ChannelCollector)

    def test_protocol_attributes(self) -> None:
        """Given AuctionChannel instance Then channel_name/reliability 존재"""
        from src.channels.base import ChannelCollector
        ch = AuctionChannel(
            api_key="test-key", client=MagicMock(spec=httpx.Client)
        )
        assert hasattr(ch, "channel_name")
        assert hasattr(ch, "reliability")
        assert hasattr(ch, "collect")


# ============================================================
# Test: Mock PDF helper
# ============================================================


class TestMakePdfHelper:
    """_make_pdf_with_text 가 유효한 PDF 를 생성하는지 검증."""

    def test_pdf_is_valid(self) -> None:
        """Given 텍스트 When _make_pdf_with_text Then 유효한 PDF 반환"""
        pdf = _make_pdf_with_text("Hello World Test PDF")
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 1
        text = reader.pages[0].extract_text()
        assert "Hello" in text

    def test_pdf_empty(self) -> None:
        """Given 빈 텍스트 When PDF 생성 Then 유효한 PDF"""
        pdf = _make_pdf_with_text("")
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 1
