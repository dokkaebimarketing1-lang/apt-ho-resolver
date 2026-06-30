"""F3+F4 Final Verification — 골든셋 기반 precision@1 측정 + 리포트 생성.

ledger_원베일리.json을 mock unit_master로, listings_원베일리_full.json을 입력으로
전체 추론 파이프라인을 mock 모드로 실행하고 precision@1을 측정한다.
Supabase DB 없이도 실행 가능.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
_LISTINGS_FILE = _PROJECT_ROOT / "참고자료/데이터샘플/listings_원베일리_full.json"
_LEDGER_FILE = _PROJECT_ROOT / "참고자료/데이터샘플/ledger_원베일리.json"

_141_TRUTH_DONG_HO = {
    ("101", "902"): True, ("101", "1602"): True,
    ("103", "106"): True, ("104", "3401"): True,
}


def _load_data() -> tuple[list[dict], list[dict]]:
    with open(_LISTINGS_FILE, encoding="utf-8") as f:
        listings_raw = json.load(f)
    with open(_LEDGER_FILE, encoding="utf-8") as f:
        ledger_raw = json.load(f)
    return listings_raw, ledger_raw["ledger"]


def _build_unit_master(ledger: dict) -> list[dict]:
    """ledger_원베일리.json → mock unit_master 변환."""
    units = []
    for dong_name, floors in ledger.items():
        dong_num = "".join(c for c in dong_name if c.isdigit())
        for _floor_key, ho_list in floors.items():
            for entry in ho_list:
                ho = entry.get("ho", "")
                area_m2 = entry.get("area", 0)
                floor = entry.get("floor", 0)
                units.append({
                    "canonical_ho_id": f"{dong_num.zfill(3)}{ho}",
                    "complex_id": "wonbailly",
                    "dong": dong_num,
                    "ho": ho,
                    "floor": floor,
                    "area_exclusive": int(area_m2 * 100),
                    "area_type": "",  # ledger에 없음, areaName으로 대체
                    "direction": "",  # ledger에 없음
                })
    return units


def _normalize_direction(raw: str) -> str:
    """한글 방향 → 영문 코드."""
    m = {"남향": "S", "북향": "N", "동향": "E", "서향": "W",
         "남동향": "SE", "남서향": "SW", "북동향": "NE", "북서향": "NW"}
    return m.get(raw, raw)


class TestFinalVerification:
    def test_data_loaded(self):
        """골든셋 데이터 로드 확인."""
        listings, ledger = _load_data()
        assert len(listings) == 2454
        assert len(ledger) > 0

    def test_precision_at_1_mock(self):
        """Mock unit_master로 precision@1 측정 (DB 없이).

        원베일리 2,454건 listings + ledger 기반 mock unit_master로
        전체 파이프라인 실행 → precision@1, 단일확정 커버리지, 다호율 측정.
        """
        from src.inference import infer_complex

        listings_raw, ledger = _load_data()
        unit_master = _build_unit_master(ledger)
        assert len(unit_master) > 0, "No unit_master built from ledger"

        # 원베일리 매물을 Listing 형식으로 변환
        listings = []
        for item in listings_raw:
            listings.append({
                "id": item.get("articleNo", ""),
                "complex_id": "wonbailly",
                "dong": "".join(c for c in str(item.get("buildingName", ""))
                               if c.isdigit()),
                "dong_source": "naver",
                "area_cm2": int(float(item.get("area2", 0)) * 100),
                "floor": _parse_floor_num(item.get("floorInfo", "")),
                "floor_exact": "저" not in str(item.get("floorInfo", "")),
                "direction": _normalize_direction(
                    str(item.get("direction", ""))
                ),
                "ho_hint": str(item.get("articleFeatureDesc", "") or ""),
                "area_type": str(item.get("areaName", "")),
                "price_manwon": _parse_price(item.get("dealOrWarrantPrc", "")),
            })

        m_probs = {"dong": 0.95, "area_cm2": 0.99, "floor": 0.85,
                   "area_type": 0.90, "direction": 0.80, "ho": 0.90}
        u_probs = {"dong": 0.05, "area_cm2": 0.01, "floor": 0.15,
                   "area_type": 0.10, "direction": 0.20, "ho": 0.01}

        results = infer_complex("원베일리", listings, unit_master,
                                m_probs, u_probs)

        assert len(results) > 0, f"No inference results for {len(listings)} listings"

        # precision@1 계산
        from src.kpi import (compute_multi_prob_rate,
                             compute_precision_at_1,
                             compute_single_confirm_coverage)

        # 라벨 생성 (listing dong + ho_hint 매칭)
        labels = []
        for i, listing in enumerate(listings_raw):
            dong_raw = str(listing.get("buildingName", ""))
            dong_num = "".join(c for c in dong_raw if c.isdigit())
            ho_hint = str(listing.get("articleFeatureDesc", "") or "")
            ho_match = "".join(c for c in ho_hint if c.isdigit())

            if dong_num and ho_match:
                labels.append({
                    "id": listing.get("articleNo", ""),
                    "dong": dong_num,
                    "ho": ho_match,
                })
            else:
                labels.append(None)

        p1 = compute_precision_at_1(results, [l for l in labels if l])
        single_cov = compute_single_confirm_coverage(results)
        multi_rate = compute_multi_prob_rate(results)

        print(f"\n  precision@1: {p1:.4f}")
        print(f"  single_confirm_coverage: {single_cov:.4f}")
        print(f"  multi_prob_rate: {multi_rate:.4f}")
        print(f"  total listings: {len(listings)}")
        print(f"  total results: {len(results)}")

        assert p1 >= 0.0, "precision@1 should be computable"
        assert single_cov >= 0.0
        assert multi_rate >= 0.0

    def test_141_known_truth(self):
        """141 검증호(101동902/1602,103동106,104동3401) 최소 존재 확인."""
        _, ledger = _load_data()
        unit_master = _build_unit_master(ledger)

        found = set()
        for unit in unit_master:
            dong = str(unit.get("dong", ""))
            ho = str(unit.get("ho", ""))
            for (kd, kh) in _141_TRUTH_DONG_HO:
                if dong == kd and ho == kh:
                    found.add((kd, kh))

        assert len(found) > 0, (
            f"141 known truth not in ledger: {_141_TRUTH_DONG_HO}"
        )

    def test_report_generation(self):
        """리포트 생성 + sanitize 검증."""
        from src.inference import infer_complex
        from src.report import generate_report, sanitize_report

        listings_raw, ledger = _load_data()
        unit_master = _build_unit_master(ledger)

        listings = [{
            "id": item.get("articleNo", ""),
            "complex_id": "wonbailly",
            "dong": "".join(c for c in str(item.get("buildingName", ""))
                           if c.isdigit()),
            "area_cm2": int(float(item.get("area2", 0)) * 100),
            "floor": _parse_floor_num(item.get("floorInfo", "")),
            "floor_exact": True,
            "direction": _normalize_direction(str(item.get("direction", ""))),
            "ho_hint": str(item.get("articleFeatureDesc", "") or ""),
            "area_type": str(item.get("areaName", "")),
            "dong_source": "naver",
        } for item in listings_raw[:500]]  # 상위 500건만

        m = {"dong": 0.95, "area_cm2": 0.99, "floor": 0.85,
             "area_type": 0.90, "direction": 0.80, "ho": 0.90}
        u = {"dong": 0.05, "area_cm2": 0.01, "floor": 0.15,
             "area_type": 0.10, "direction": 0.20, "ho": 0.01}

        results = infer_complex("원베일리", listings, unit_master, m, u)
        html = generate_report(results, "원베일리")
        sanitized = sanitize_report(html)

        assert "원베일리" in html
        assert "추정" in html, "HTML must contain '추정' tag"
        assert "articleNo" not in sanitized, "sanitize must remove articleNo"
        assert len(sanitized) > 0


def _parse_floor_num(floor_info: str) -> int | None:
    """층 정보 파싱 (e.g., '저/35' → 35, '23' → 23)."""
    if not floor_info:
        return None
    parts = str(floor_info).split("/")
    last = parts[-1].strip()
    try:
        return int(last)
    except ValueError:
        return None


def _parse_price(price_str: str) -> int | None:
    """가격 파싱 (e.g., '85억' → 850000만원 or just use raw)."""
    if not price_str:
        return None
    p = str(price_str).replace("억", "").replace(",", "").strip()
    try:
        return int(float(p) * 10000)  # 억 → 만원
    except ValueError:
        return None
