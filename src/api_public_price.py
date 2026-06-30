"""data.go.kr 공동주택가격 API 클라이언트.

호별(동+호+면적+가격) 데이터 제공.
API 키 필요: PUBLIC_DATA_API_KEY 환경변수.

사용:
    from src.api_public_price import fetch_public_price
    rows = fetch_public_price(sigungu_cd="28177", bjdong_cd="10300")
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import unquote


API_URL = "https://apis.data.go.kr/1613000/AP01/getOdGdsPrc"
NUM_OF_ROWS = 99999  # API 호출당 최대 행


def _get_key() -> str:
    key = os.environ.get("PUBLIC_DATA_API_KEY", "")
    if not key:
        raise RuntimeError("PUBLIC_DATA_API_KEY not set in environment")
    return key


def fetch_public_price(
    sigungu_cd: str,
    bjdong_cd: str,
    *,
    year: int = 2026,
    num_of_rows: int = NUM_OF_ROWS,
) -> list[dict[str, Any]]:
    """공동주택가격 API 호출 (호별 데이터).

    Args:
        sigungu_cd: 시군구코드 (5자리, 예: "28177")
        bjdong_cd: 법정동코드 (5자리, 예: "10300")
        year: 기준년도 (기본: 2026)
        num_of_rows: 페이지당 행 수

    Returns:
        [{mgm_bldrgst_pk, dong_nm, ho_nm, area, price, ...}, ...]
    """
    import requests

    key = _get_key()
    params = {
        "serviceKey": unquote(key),
        "numOfRows": num_of_rows,
        "pageNo": 1,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "year": year,
    }

    resp = requests.get(API_URL, params=params, verify=False, timeout=60)
    resp.raise_for_status()

    data = resp.json()
    items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items


def to_unit_master_rows(items: list[dict]) -> list[dict[str, Any]]:
    """API 응답 → unit_master 형식 변환.

    Returns:
        [{complex_id, dong, ho, canonical_ho_id, floor,
          area_exclusive, public_price, source}, ...]
    """
    from src.ho_key import normalize_dong, normalize_ho

    rows = []
    for item in items:
        dong_raw = item.get("dongNm", "")
        ho_raw = item.get("hoNm", "")
        try:
            dong = normalize_dong(dong_raw, "public_price")
            ho = normalize_ho(ho_raw, "public_price")
        except ValueError:
            continue

        rows.append({
            "complex_id": "",
            "dong": dong,
            "ho": ho,
            "canonical_ho_id": f"{dong.zfill(3)}{ho}",
            "floor": None,
            "floor_kind": "mid",
            "area_exclusive": int(float(item.get("area", 0)) * 100),
            "area_type": "",
            "direction": "",
            "public_price": int(item.get("price", 0)),
            "source": "public_price",
        })
    return rows


__all__ = ["fetch_public_price", "to_unit_master_rows", "API_URL"]
