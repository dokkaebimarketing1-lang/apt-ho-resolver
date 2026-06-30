"""JusoChannel — 도로명주소 상세 API (data.go.kr 15096712).

API 문서: business.juso.go.kr/addrlink/addrLinkApi.do
searchType=floorho 로 동·호 정보를 포함한 상세 주소 조회.
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import BaseChannel


class JusoChannel(BaseChannel):
    """도로명주소 상세 API 채널.

    channel_name='juso', reliability=0.85
    """

    channel_name = "juso"
    reliability = 0.85

    BASE_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"

    def __init__(self, api_key: str | None = None,
                 client: httpx.Client | None = None) -> None:
        super().__init__(api_key=api_key, client=client)

    def _do_collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """도로명주소 상세 API 호출.

        Required query keys:
            keyword: 검색어 (도로명 주소 또는 건물명).
        Supported query keys:
            current_page: 페이지 번호 (기본 1).
            count_per_page: 페이지당 건수 (기본 100).

        Returns:
            API 응답의 results.juso 목록.
        """
        params: dict[str, Any] = {
            "confmKey": self._api_key,
            "currentPage": query.get("current_page", 1),
            "countPerPage": query.get("count_per_page", 100),
            "resultType": "json",
            "searchType": "floorho",
        }

        keyword = query.get("keyword", "")
        if keyword:
            params["keyword"] = keyword

        resp = self._client.get(self.BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", {}).get("juso", [])
