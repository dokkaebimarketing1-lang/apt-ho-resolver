"""참조 테이블 ETL — 법정동코드 + kaptCode 매핑 (Todo 33).

법정동코드 CSV (EUC-KR, comma, header 있음, 3 columns).
kaptCode XLSX (Sheet1, row 2 header, row 3+ data, 92,164 rows).
"""

from __future__ import annotations

import csv
from typing import Any


def parse_legal_dong(filepath: str, *, max_rows: int = 0) -> list[dict[str, str]]:
    """법정동코드 CSV 파싱 (EUC-KR/CP949).

    컬럼: 법정동코드, 법정동명, 폐지여부
    """
    results: list[dict[str, str]] = []
    count = 0
    with open(filepath, encoding="cp949") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append({
                "code": row.get("법정동코드", "").strip(),
                "name": row.get("법정동명", "").strip(),
                "status": row.get("폐지여부", "").strip(),
            })
            count += 1
            if max_rows > 0 and count >= max_rows:
                break
    return results


def parse_kapt_complex_xlsx(filepath: str, *, max_rows: int = 0) -> list[dict[str, Any]]:
    """kaptCode 매핑 XLSX 파싱 (header는 2행, 데이터는 3행부터).

    컬럼: 시도, 시군구, 읍면, 동리, 단지코드(kaptCode), 단지명, 동수,
           관리비부과면적, 주거전용면적(단지합계), 주거전용면적(세부), 세대수
    """
    try:
        import openpyxl
    except ImportError:
        return []

    wb = openpyxl.load_workbook(filepath, read_only=True)
    ws = wb.active

    results: list[dict[str, Any]] = []
    count = 0
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if i <= 2:  # skip row 1 (notice) and row 2 (header)
            continue
        if len(row) < 5:
            continue
        kapt_code = str(row[4]).strip() if row[4] else ""
        if kapt_code and kapt_code.startswith("A"):
            results.append({
                "sido": str(row[0] or "").strip(),
                "sigungu": str(row[1] or "").strip(),
                "eupmyeon": str(row[2] or "").strip(),
                "dongri": str(row[3] or "").strip(),
                "kapt_code": kapt_code,
                "complex_name": str(row[5] or "").strip(),
                "dong_count": row[6] if len(row) > 6 else None,
                "total_units": row[10] if len(row) > 10 else None,
            })
            count += 1
            if max_rows > 0 and count >= max_rows:
                break

    wb.close()
    return results


__all__ = ["parse_legal_dong", "parse_kapt_complex_xlsx"]
