"""OnbidChannel — 온비드 OpenAPI (data.go.kr 15157207).

API 문서: data.go.kr/15157207
한국자산관리공사(온비드) 공매 물건 정보 조회.
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import BaseChannel


class OnbidChannel(BaseChannel):
    """온비드 공매 물건 API 채널.

    channel_name='onbid', reliability=0.85
    """

    channel_name = "onbid"
    reliability = 0.85

    BASE_URL = "http://api.onsale.go.kr/OpenAPI/goodsInfo.do"

    def __init__(self, api_key: str | None = None,
                 client: httpx.Client | None = None) -> None:
        super().__init__(api_key=api_key, client=client)

    def _do_collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """온비드 공매 물건 API 호출.

        Supported query keys:
            sigungu_cd: 시군구 코드 (5자리).
            keyword: 검색어.
            num_of_rows: 페이지당 건수 (기본 100).
            page_no: 페이지 번호 (기본 1).

        Returns:
            API 응답의 body.items.item 목록.
        """
        params: dict[str, Any] = {
            "ServiceKey": self._api_key,
            "numOfRows": query.get("num_of_rows", 100),
            "pageNo": query.get("page_no", 1),
            "_type": "json",
        }

        if "sigungu_cd" in query:
            params["sigunguCd"] = query["sigungu_cd"]
        if "keyword" in query:
            params["keyword"] = query["keyword"]

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
