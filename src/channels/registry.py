"""RegistryChannel — 등기부등본 열람 채널 (iros.go.kr / 정부24).

설계 의도:
- 등기부등본(iros.go.kr 열람, 700원)에서 동·호·소유자주소 추출.
- 소유자 주소가 대상 단지 주소와 다르면 → 미거주 신호(비어있음/임대 가능성).
- 채널 신뢰도 0.98 (가장 신뢰할 수 있는 단일 채널 — 등기부는 법적 효력).
- 소수 검증 자본 모델: 유료+캡차로 대량 자동화 불가 → 제한적 검증용.

참고:
- 집합건물법 제1조: 집합건물의 동·호는 등기부에 필수 기재.
- A3: 등기부 VERIFIED (가장 정확한 채널).
- A53: 소유자 주소 간접 신호 — 소유자 주소 ≠ 등기부상 건물 주소 → 미거주.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .base import BaseChannel

# 두 주소 간 유사도 임계값
# 이 값 이하이면 소유자가 건물에 거주하지 않는 것으로 추정
_ADDRESS_SIMILARITY_MIN_SCORE = 0.6


class RegistryChannel(BaseChannel):
    """등기부등본 채널 — 등기부에서 동·호·소유자주소를 추출.

    channel_name='registry', reliability=0.98
    """

    channel_name = "registry"
    reliability = 0.98

    # 등기부 API 엔드포인트 (mock 전용 URL — 실제 iros.go.kr API 스펙 확인 필요)
    BASE_URL = "https://api.iros.go.kr/registry/v1/inquiry"

    def __init__(self, api_key: str | None = None,
                 client: httpx.Client | None = None) -> None:
        super().__init__(api_key=api_key, client=client)

    def _do_collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """등기부등본 조회.

        Required query keys:
            dong: 동 번호 (예: "101").
            ho: 호 번호 (예: "1503").
        Supported query keys:
            complex_id: 단지 고유 ID.
            complex_address: 단지 전체 주소 (미거주 판별용).

        Returns:
            파싱된 등기부 데이터 리스트. 각 항목:
                - dong (str): 동 번호
                - ho (str): 호 번호
                - owner_address (str): 소유자 주소
                - is_non_resident (bool): 소유자 미거주 추정 여부
        """
        dong = query.get("dong", "")
        ho = query.get("ho", "")

        if not dong or not ho:
            return []

        params: dict[str, Any] = {
            "serviceKey": self._api_key,
            "dong": dong,
            "ho": ho,
            "format": "json",
        }
        if "complex_id" in query:
            params["complex_id"] = query["complex_id"]

        resp = self._client.get(self.BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        return self._parse_registry_response(
            data, query.get("complex_address", ""),
        )

    # ------------------------------------------------------------------
    # 파싱
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_registry_response(
        data: dict[str, Any],
        complex_address: str,
    ) -> list[dict[str, Any]]:
        """등기부등본 JSON 응답을 파싱하여 동·호·소유자주소 추출.

        Args:
            data: 원본 응답 dict.
            complex_address: 단지 주소 (미거주 판별 비교용).

        Returns:
            파싱된 데이터 리스트.
        """
        results: list[dict[str, Any]] = []

        # 건물표시 목록 (등기부의 '갑구' 건물표시 항목)
        buildings = data.get("building_description", [])
        if isinstance(buildings, dict):
            buildings = [buildings]

        for building in buildings:
            dong = building.get("dong", "")
            ho = building.get("ho", "")
            owner_address = building.get("owner_address", "")

            is_non_resident = RegistryChannel._check_non_resident(
                owner_address, complex_address,
            )

            results.append({
                "dong": str(dong) if dong is not None else "",
                "ho": str(ho) if ho is not None else "",
                "owner_address": str(owner_address) if owner_address is not None else "",
                "is_non_resident": is_non_resident,
            })

        return results

    # ------------------------------------------------------------------
    # 미거주 신호
    # ------------------------------------------------------------------

    @staticmethod
    def _check_non_resident(
        owner_address: str,
        complex_address: str,
    ) -> bool:
        """소유자 주소와 단지 주소를 비교하여 미거주 여부 판단.

        전략 (우선순위):
        1. 두 주소 중 하나라도 빈 문자열 → 알 수 없음 → False
        2. 정확히 일치 → 거주 중 → False
        3. 단지 주소가 소유자 주소에 포함됨 → 거주 중 → False
        4. 유사도 임계값 미만 → 미거주 → True

        Args:
            owner_address: 등기부상 소유자 주소.
            complex_address: 대상 단지의 주소.

        Returns:
            미거주로 추정되면 True.
        """
        if not owner_address or not complex_address:
            return False

        oa = owner_address.strip()
        ca = complex_address.strip()

        # 정확한 일치
        if oa == ca:
            return False

        # 포함 관계: 단지 주소가 소유자 주소에 포함되면 같은 건물
        if ca in oa:
            return False

        # 유사도 기반 판단
        score = RegistryChannel._address_similarity(oa, ca)
        return score < _ADDRESS_SIMILARITY_MIN_SCORE

    @staticmethod
    def _address_similarity(addr1: str, addr2: str) -> float:
        """두 주소 문자열의 유사도 (공통 접두사 기반).

        Args:
            addr1: 첫 번째 주소.
            addr2: 두 번째 주소.

        Returns:
            0.0~1.0 유사도 점수.
        """
        a1 = re.sub(r"\s+", " ", addr1.strip())
        a2 = re.sub(r"\s+", " ", addr2.strip())

        if not a1 or not a2:
            return 0.0

        min_len = min(len(a1), len(a2))
        common = 0
        for i in range(min_len):
            if a1[i] == a2[i]:
                common += 1
            else:
                break

        max_len = max(len(a1), len(a2))
        return common / max_len if max_len > 0 else 0.0
