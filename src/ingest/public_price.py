"""공동주택가격(공시가격) 벌크 CSV 파서 (Todo 6).

건축HUB 공동주택가격 CSV (pipe-delimited, UTF-8, no header, 25 columns).

컬럼 매핑:
    0: mgm_bldrgst_pk
    7: 건물명 (복합단지명, 예: "동아,풍림아파트")
    23: 공동주택가격 (원)
"""

from __future__ import annotations

from typing import Any

# 컬럼 인덱스
COL_MGM_PK = 0
COL_BUILDING_NAME = 7  # 건물명 (단지명)
COL_PUBLIC_PRICE = 23  # 공동주택가격 (원)

SEPARATOR = "|"
ENCODING = "utf-8"


def parse_row(line: str) -> dict[str, Any] | None:
    """pipe-delimited 행 파싱.

    Returns:
        {"mgm_bldrgst_pk": str, "building_name": str, "public_price": int | None}
    """
    parts = line.split(SEPARATOR)
    if len(parts) < 24:
        return None

    try:
        mgm_pk = parts[COL_MGM_PK].strip()
        building_name = parts[COL_BUILDING_NAME].strip()
        price_str = parts[COL_PUBLIC_PRICE].strip()

        if not mgm_pk:
            return None

        price_val: int | None = None
        if price_str:
            try:
                price_val = int(price_str)
            except ValueError:
                pass

        return {
            "mgm_bldrgst_pk": mgm_pk,
            "building_name": building_name,
            "public_price": price_val,
        }
    except (IndexError, ValueError):
        return None


def parse_file(filepath: str, *, max_rows: int = 0) -> list[dict[str, Any]]:
    """파일 전체 파싱."""
    results: list[dict[str, Any]] = []
    count = 0
    with open(filepath, encoding=ENCODING) as f:
        for line in f:
            row = parse_row(line)
            if row:
                results.append(row)
                count += 1
                if max_rows > 0 and count >= max_rows:
                    break
    return results


__all__ = ["COL_MGM_PK", "COL_BUILDING_NAME", "COL_PUBLIC_PRICE",
           "SEPARATOR", "ENCODING", "parse_row", "parse_file"]
