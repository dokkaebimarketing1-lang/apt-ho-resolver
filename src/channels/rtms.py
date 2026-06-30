"""RtmsChannel — 국토부 아파트 매매 실거래 API (data.go.kr 15126468).

API 문서: data.go.kr/15126468
국토교통부 아파트 매매 실거래가 자료(getRTMSDataSvcAptTrade)를 호출하여
Transaction 형태의 dict 리스트로 반환한다.

합법선: 소유자·중개사 등 개인정보 필드는 수집하지 않는다.
        dict 에 없는 필드는 모두 버린다.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .base import BaseChannel


class RtmsChannel(BaseChannel):
    """국토부 아파트 매매 실거래 API 채널.

    channel_name='rtms', reliability=0.8
    """

    channel_name = "rtms"
    reliability = 0.8

    BASE_URL = (
        "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade"
        "/getRTMSDataSvcAptTrade"
    )

    def __init__(self, api_key: str | None = None,
                 client: httpx.Client | None = None) -> None:
        super().__init__(api_key=api_key, client=client)

    def _do_collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """RTMS 실거래 API 호출.

        Supported query keys:
            sigungu_cd: 시군구 코드 5자리 (필수, 예: "11650").
            deal_ymd:   거래년월 YYYYMM (필수, 예: "202406").
            complex_name: 단지명 (선택 — 제공 시 이 단지만 필터).
            complex_id:  단지 식별자 (선택 — 결과 dict에 포함).
            num_of_rows: 페이지당 건수 (선택, 기본 100).
            page_no:     페이지 번호 (선택, 기본 1).

        Returns:
            Transaction 형태 dict 리스트. 각 dict:
                complex_id:    str — query 의 complex_id (없으면 "").
                floor:         int — 층.
                area2:         float — 전용면적(m²).
                price:         int — 거래금액(만원).
                contract_date: str — 계약일 "YYYY-MM-DD".
                dong:          str — 동 (빈 값이면 "").
                source_id:     str — "rtms_{index}".
        """
        sigungu_cd = query.get("sigungu_cd")
        if not sigungu_cd:
            return []

        deal_ymd = query.get("deal_ymd")
        if not deal_ymd:
            return []

        complex_id = query.get("complex_id", "")
        complex_name = query.get("complex_name", "")

        params: dict[str, Any] = {
            "serviceKey": self._api_key,
            "LAWD_CD": sigungu_cd,
            "DEAL_YMD": deal_ymd,
            "numOfRows": query.get("num_of_rows", 100),
            "pageNo": query.get("page_no", 1),
            "_type": "json",
        }

        resp = self._client.get(self.BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        items = (
            data.get("response", {})
            .get("body", {})
            .get("items", {})
            .get("item", [])
        )
        if isinstance(items, dict):
            items = [items]

        return self._to_transactions(items, complex_name, complex_id)

    @staticmethod
    def _to_transactions(
        rows: list[dict[str, Any]],
        complex_name: str,
        complex_id: str,
    ) -> list[dict[str, Any]]:
        """원시 API 행 리스트 → Transaction 형태 dict 리스트.

        - complex_name 이 제공되면 단지명 불일치 행 제외.
        - aptDong 빈값 → "" (동 정보 없음).
        - aptDong 숫자만 → "N동" 보정.
        - 전용면적 float 유지.
        - 거래금액 콤마·공백 제거 후 int.
        - 계약년/월/일 → "YYYY-MM-DD".
        """
        target = complex_name.replace(" ", "") if complex_name else ""
        out: list[dict[str, Any]] = []

        for i, row in enumerate(rows):
            # 단지명 필터
            if target:
                apt = str(row.get("aptNm", "") or "").strip()
                if target not in apt.replace(" ", ""):
                    continue

            try:
                # 동 처리: 숫자만 → "N동", 빈값 → ""
                dong_raw = str(row.get("aptDong", "") or "").strip()
                if dong_raw.isdigit():
                    dong = dong_raw + "동"
                else:
                    dong = dong_raw  # "" 포함 그대로

                floor = int(str(row.get("floor", "0")).strip())
                area2 = float(str(row.get("excluUseAr", "0")).strip())
                amount_raw = str(row.get("dealAmount", "0") or "0")
                price = int(re.sub(r"[,\s]", "", amount_raw))
                contract_date = _build_date(row)
            except (ValueError, TypeError):
                continue

            out.append({
                "complex_id": complex_id,
                "floor": floor,
                "area2": area2,
                "price": price,
                "contract_date": contract_date,
                "dong": dong,
                "source_id": f"rtms_{i}",
            })

        return out


def _build_date(row: dict[str, Any]) -> str:
    """dealYear/dealMonth/dealDay → 'YYYY-MM-DD'."""
    year = str(row.get("dealYear", "")).strip().zfill(4)
    month = str(row.get("dealMonth", "")).strip().zfill(2)
    day = str(row.get("dealDay", "")).strip().zfill(2)
    return f"{year}-{month}-{day}"
