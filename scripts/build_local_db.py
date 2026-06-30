"""로컬 DB 구축 — building_registry + housing_permit 융합.

두 소스에서 동/호/층/평형구분명을 모두 확보한 unit_master 생성.
공시가격(public_price)은 data.go.kr/3073746 파일 필요 (별도 다운로드).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).parent.parent  # project root
sys.path.insert(0, str(PROJECT))

from src.local_db import LocalDB
from src.ho_key import normalize_ho, normalize_dong

CSV_HOUSING = PROJECT / "건축HUB_대용량데이터/주택인허가_호별개요_2026-05.csv"
CSV_REGISTRY = PROJECT / "건축HUB_대용량데이터/건축물대장_전유부_2026-05.csv"
SAMPLE = 200000


def load_housing(db, max_rows=SAMPLE):
    from src.ingest.housing_permit import parse_row
    print(f"  [housing] {max_rows:,} rows...")
    rows, cnt = [], 0
    with open(CSV_HOUSING, encoding="utf-8") as f:
        for line in f:
            r = parse_row(line)
            if r is None: continue
            try:
                ho = normalize_ho(r["ho_name"], "housing_permit")
                dong = normalize_dong(r["dong_name"], "housing_permit")
            except ValueError: continue
            rows.append({"complex_id":"","dong":dong,"ho":ho,
                "canonical_ho_id":f"{dong.zfill(3)}{ho}",
                "floor":r.get("floor"),"floor_kind":"exact" if r.get("floor") else "mid",
                "area_exclusive":None,"area_type":r.get("area_type",""),
                "direction":"","public_price":None,"source":"housing_permit"})
            cnt += 1
            if cnt >= max_rows: break
    n = db.insert_unit_master(rows)
    print(f"    {n:,} rows (area_type)")
    return n


def load_registry(db, max_rows=SAMPLE):
    from src.ingest.building_registry import parse_row
    print(f"  [registry] {max_rows:,} rows...")
    rows, cnt = [], 0
    with open(CSV_REGISTRY, encoding="utf-8") as f:
        for line in f:
            r = parse_row(line)
            if r is None: continue
            try:
                ho = normalize_ho(r["ho_name"], "building_registry")
                dong = normalize_dong(r["dong_name"], "building_registry")
            except ValueError: continue
            rows.append({"complex_id":"","dong":dong,"ho":ho,
                "canonical_ho_id":f"{dong.zfill(3)}{ho}",
                "floor":r.get("floor"),"floor_kind":"exact" if r.get("floor") else "mid",
                "area_exclusive":None,"area_type":"",
                "direction":"","public_price":None,"source":"building_registry"})
            cnt += 1
            if cnt >= max_rows: break
    n = db.insert_unit_master(rows)
    print(f"    {n:,} rows (dong/ho/floor)")
    return n


def show(db):
    t = db.count()
    c = db.conn
    print(f"\n  unit_master: {t:,} rows")
    for l, w in [("area_type","area_type!=''"),("floor","floor IS NOT NULL"),("canonical_ho_id","LENGTH(canonical_ho_id)>0")]:
        n = c.execute(f"SELECT count(*) FROM unit_master WHERE {w}").fetchone()[0]
        print(f"    {l:25s}: {n:>8,} ({100*n//t}%)")
    for s in ["housing_permit","building_registry"]:
        n = c.execute("SELECT count(*) FROM unit_master WHERE source=?",(s,)).fetchone()[0]
        print(f"    source={s:20s}: {n:>8,}")
    print("\n  area_type top 10:")
    for a,n in c.execute("SELECT area_type,count(*) FROM unit_master WHERE area_type!='' GROUP BY area_type ORDER BY count(*) DESC LIMIT 10"):
        print(f"      {a:>10s}: {n:>8,}")


if __name__ == "__main__":
    db = LocalDB(PROJECT / "local.db")
    db.create_schema()
    load_housing(db)
    load_registry(db)
    show(db)
    db.close()
    print(f"\n  {PROJECT/'local.db'} ({(PROJECT/'local.db').stat().st_size//1024//1024} MB)")
