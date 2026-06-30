"""AuctionChannel — 법원경매 채널 (PDF 파싱).

courtauction.go.kr 경매 물건 검색 → 감정평가서/매각물건명세서 PDF 다운로드
→ PDF 텍스트 추출 → 정규식 파싱 → (동, 호, 층, 면적, 향, 감정가).

경매 동·호는 100% 공개 (결정론적 정답).
GroundTruth 정답 라벨 생성용 채널.

Usage:
    ch = AuctionChannel(api_key="...", client=httpx.Client())
    results = ch.collect({"keyword": "래미안", "sigungu_cd": "11680"})
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import httpx
from PyPDF2 import PdfReader

from .base import BaseChannel

# 경매 물건 검색 URL (courtauction.go.kr)
_SEARCH_URL = "https://www.courtauction.go.kr/retrieveAuctionGoodsList.do"

# 감정평가서 PDF 다운로드 URL
_APPRAISAL_URL = "https://www.courtauction.go.kr/downloadAppraisal.do"

# 매각물건명세서 PDF 다운로드 URL
_STATEMENT_URL = "https://www.courtauction.go.kr/downloadStatement.do"

# --- 정규식 패턴 ---
# 동 호: "101동 203호", "101동203호"
_RE_DONG_HO = re.compile(r"(\d{1,3}동)\s*(\d{1,4}호)")

# 층: "15층", "지하1층"
_RE_FLOOR = re.compile(r"(\d+)층")

# 전용면적 (㎡): "84.12㎡", "59.99㎡ "
_RE_AREA = re.compile(r"(\d+\.?\d*)\s*㎡")

# 공급면적 (㎡) — "공급면적 84.12㎡"
_RE_SUPPLY_AREA = re.compile(r"공급[면적]*\s*(\d+\.?\d*)\s*㎡")

# 감정가: "감정가 500,000,000원", "감정평가액 500,000,000", "감정평가금액"
_RE_APPRAISED_PRICE = re.compile(
    r"감정(?:가|평가액|평가금액)\s*([\d,]+)\s*원?"
)

# 향 (방향): 한글 8방위
_RE_DIRECTION = re.compile(
    r"(남향|북향|동향|서향|남동향|남서향|북동향|북서향)"
)

# --- 방향 매핑 (domain.normalize_direction 과 동일) ---
_DIRECTION_MAP: dict[str, str] = {
    "남향": "S",
    "북향": "N",
    "동향": "E",
    "서향": "W",
    "남동향": "SE",
    "남서향": "SW",
    "북동향": "NE",
    "북서향": "NW",
}


def _extract_from_text(text: str) -> dict[str, Any]:
    """PDF 텍스트에서 동·호·층·면적·향·감정가 추출.

    Args:
        text: PDF 에서 추출한 raw 텍스트.

    Returns:
        파싱된 정보 dict. 찾지 못한 필드는 None.
        Keys: dong, ho, floor, area_m2, supply_area_m2, direction,
              direction_kr, appraised_price_won.
    """
    result: dict[str, Any] = {
        "dong": None,
        "ho": None,
        "floor": None,
        "area_m2": None,
        "supply_area_m2": None,
        "direction": None,
        "direction_kr": None,
        "appraised_price_won": None,
    }

    # 동·호
    m = _RE_DONG_HO.search(text)
    if m:
        result["dong"] = m.group(1)
        result["ho"] = m.group(2)

    # 층
    m = _RE_FLOOR.search(text)
    if m:
        result["floor"] = int(m.group(1))

    # 전용면적 (㎡) — 공급면적보다 구체적이므로 우선
    m = _RE_AREA.search(text)
    if m:
        result["area_m2"] = float(m.group(1))

    # 공급면적
    m = _RE_SUPPLY_AREA.search(text)
    if m:
        result["supply_area_m2"] = float(m.group(1))

    # 감정가
    m = _RE_APPRAISED_PRICE.search(text)
    if m:
        price_str = m.group(1).replace(",", "")
        try:
            result["appraised_price_won"] = int(price_str)
        except ValueError:
            pass

    # 향
    m = _RE_DIRECTION.search(text)
    if m:
        kr = m.group(1)
        result["direction_kr"] = kr
        result["direction"] = _DIRECTION_MAP.get(kr)

    return result


class AuctionChannel(BaseChannel):
    """법원경매 채널 — courtauction.go.kr PDF 기반.

    channel_name='auction', reliability=0.95
    경매 동·호는 100% 공개이므로 GroundTruth 정답 라벨 생성에 사용.
    """

    channel_name = "auction"
    reliability = 0.95

    def __init__(self, api_key: str | None = None,
                 client: httpx.Client | None = None) -> None:
        super().__init__(api_key=api_key, client=client)

    def _do_collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """법원경매 물건 검색 → PDF 파싱.

        Step 1: courtauction.go.kr 검색 API 호출 → 물건 목록.
        Step 2: 각 물건의 감정평가서 PDF 다운로드.
        Step 3: PDF 텍스트 추출 → 정규식 파싱.

        Supported query keys:
            keyword: 검색어 (단지명 등).
            sigungu_cd: 시군구 코드.
            case_no: 사건번호 (직접 지정).
            num_of_rows: 페이지당 건수 (기본 20).
            page_no: 페이지 번호 (기본 1).

        Returns:
            파싱된 물건 정보 리스트. 각 항목:
                dong: str or None
                ho: str or None
                floor: int or None
                area_m2: float or None
                supply_area_m2: float or None
                direction: str or None (영문 코드)
                direction_kr: str or None (한글)
                appraised_price_won: int or None
                case_no: str
                court_name: str
                goods_seq: str
                pdf_url: str
        """
        # Step 1: 검색
        params: dict[str, Any] = {
            "numOfRows": query.get("num_of_rows", 20),
            "pageNo": query.get("page_no", 1),
        }
        if "keyword" in query:
            params["keyword"] = query["keyword"]
        if "sigungu_cd" in query:
            params["sigunguCd"] = query["sigungu_cd"]
        if "case_no" in query:
            params["caseNo"] = query["case_no"]

        search_resp = self._client.get(_SEARCH_URL, params=params)
        search_resp.raise_for_status()
        search_data = search_resp.json()

        raw_items = (
            search_data.get("response", {})
            .get("body", {})
            .get("items", {})
            .get("item", [])
        )
        if isinstance(raw_items, dict):
            raw_items = [raw_items]

        # Step 2 & 3: PDF 다운로드 + 파싱
        _PARSED_KEYS = [
            "dong", "ho", "floor", "area_m2", "supply_area_m2",
            "direction", "direction_kr", "appraised_price_won",
        ]
        results: list[dict[str, Any]] = []
        for item in raw_items:
            case_no = item.get("caseNo", "")
            court_name = item.get("courtName", "")
            goods_seq = item.get("goodsSeq", "")

            # 감정평가서 PDF 다운로드 (1차 시도)
            pdf_bytes = self._try_download_pdf(case_no, goods_seq)
            if pdf_bytes is None:
                # 매각물건명세서 PDF 다운로드 (2차 시도)
                pdf_bytes = self._try_download_pdf(
                    case_no, goods_seq, use_statement=True
                )

            parsed: dict[str, Any] = (
                self._parse_pdf(pdf_bytes)
                if pdf_bytes
                else {k: None for k in _PARSED_KEYS}
            )
            parsed["case_no"] = case_no
            parsed["court_name"] = court_name
            parsed["goods_seq"] = goods_seq
            results.append(parsed)

        return results

    def _try_download_pdf(
        self, case_no: str, goods_seq: str, use_statement: bool = False
    ) -> bytes | None:
        """감정평가서 또는 매각물건명세서 PDF 다운로드 시도.

        Args:
            case_no: 사건번호.
            goods_seq: 물건 일련번호.
            use_statement: True 면 매각물건명세서, False 면 감정평가서.

        Returns:
            PDF 바이트. 실패 시 None.
        """
        url = _STATEMENT_URL if use_statement else _APPRAISAL_URL
        params = {"caseNo": case_no, "goodsSeq": goods_seq}
        try:
            pdf_resp = self._client.get(url, params=params)
            pdf_resp.raise_for_status()
            content_type = pdf_resp.headers.get("content-type", "")
            if "application/pdf" not in content_type and not content_type.startswith("application/octet"):
                return None
            return pdf_resp.content
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError):
            return None

    def _parse_pdf(self, pdf_bytes: bytes) -> dict[str, Any]:
        """PDF 바이트에서 텍스트 추출 후 파싱.

        Args:
            pdf_bytes: PDF 파일 바이트.

        Returns:
            _extract_from_text() 결과 dict. 파싱 실패 시 빈 dict.
        """
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            text_parts: list[str] = []
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_parts.append(extracted)
            full_text = "\n".join(text_parts)
            return _extract_from_text(full_text)
        except Exception:
            return {}
