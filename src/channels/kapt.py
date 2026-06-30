"""KaptChannel — K-apt 단지 기본정보 API (data.go.kr 15058453).

API 문서: data.go.kr/15058453 (AptListService1)
단지 메타데이터(kaptCode, 단지명, 주소 등) 조회.
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import BaseChannel


class KaptChannel(BaseChannel):
    """K-apt 단지 기본정보 API 채널.

    channel_name='kapt', reliability=0.9
    """

    channel_name = "kapt"
    reliability = 0.9

    BASE_URL = "http://apis.data.go.kr/1613000/AptListService1/getAptList"

    def __init__(self, api_key: str | None = None,
                 client: httpx.Client | None = None) -> None:
        super().__init__(api_key=api_key, client=client)

    def _do_collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """K-apt 단지 목록 API 호출.

        Supported query keys:
            sigungu_cd: 시군구 코드 (5자리).
            bjdong_cd: 법정동 코드 (5자리).
            complex_name: 단지명 검색어 (searchAptNm).
            num_of_rows: 페이지당 건수 (기본 100).
            page_no: 페이지 번호 (기본 1).

        Returns:
            API 응답의 response.body.items.item 목록.
        """
        params: dict[str, Any] = {
            "serviceKey": self._api_key,
            "numOfRows": query.get("num_of_rows", 100),
            "pageNo": query.get("page_no", 1),
            "_type": "json",
        }

        if "sigungu_cd" in query:
            params["sigunguCd"] = query["sigungu_cd"]
        if "bjdong_cd" in query:
            params["bjdongCd"] = query["bjdong_cd"]
        if "complex_name" in query:
            params["searchAptNm"] = query["complex_name"]

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
        return items
