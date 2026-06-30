"""공시가격 호별 CSV → unit_master 적재.

국토교통부_주택 공시가격 정보(2025).csv (3.3 GB, comma-separated, header 있음).
컬럼: 기준연도,기준월,법정동코드,...단지명,동명,호명,전용면적,공시가격,...,건축물대장PK
"""

from __future__ import annotations

import csv
import sys
import zipfile
from pathlib import Path

PROJECT = Path(__file__).parent.parent  # project root (scripts/ → project/)
sys.path.insert(0, str(PROJECT))

from src.local_db import LocalDB
from src.ho_key import normalize_ho, normalize_dong

ZIP_PATH = PROJECT / "참고자료/데이터샘플/원본데이터/국토교통부-주택-공시가격-정보-20250626.zip"
CSV_NAME = "국토교통부_주택 공시가격 정보(2025).csv"
MAX_ROWS = 15_600_000  # 전체 (약 1,558만행)


def load(db: LocalDB, max_rows: int = MAX_ROWS):
    print(f"Extracting from {ZIP_PATH.name}...")
    with zipfile.ZipFile(ZIP_PATH) as zf:
        with zf.open(CSV_NAME) as f:
            reader = csv.DictReader(
                (line.decode("utf-8-sig") for line in f)
            )
            rows = []
            cnt = 0
            for row in reader:
                dong_raw = row.get("동명", "").strip()
                ho_raw = row.get("호명", "").strip()
                area_str = row.get("전용면적", "").strip()
                price_str = row.get("공시가격", "").strip()
                complex_name = row.get("단지명", "").strip()

                if not dong_raw or not ho_raw:
                    continue

                try:
                    dong = normalize_dong(dong_raw, "public_price")
                    ho = normalize_ho(ho_raw, "public_price")
                except ValueError:
                    continue

                area = None
                if area_str:
                    try: area = int(float(area_str) * 100)
                    except ValueError: pass

                price = None
                if price_str:
                    try: price = int(price_str)
                    except ValueError: pass

                rows.append({
                    "complex_id": complex_name[:50] if complex_name else "",
                    "dong": dong, "ho": ho,
                    "canonical_ho_id": f"{dong.zfill(3)}{ho}",
                    "floor": None, "floor_kind": "mid",
                    "area_exclusive": area,
                    "area_type": "", "direction": "",
                    "public_price": price,
                    "source": "public_price",
                })
                cnt += 1
                if cnt >= max_rows:
                    break

    n = db.insert_unit_master(rows)
    area_cnt = db.conn.execute(
        "SELECT count(*) FROM unit_master WHERE area_exclusive IS NOT NULL"
    ).fetchone()[0]
    price_cnt = db.conn.execute(
        "SELECT count(*) FROM unit_master WHERE public_price IS NOT NULL"
    ).fetchone()[0]
    print(f"  Inserted: {n:,} rows")
    print(f"    with area: {area_cnt:,}, with price: {price_cnt:,}")
    return n


if __name__ == "__main__":
    db = LocalDB(PROJECT / "local.db")
    db.create_schema()
    n = load(db)
    total = db.count()
    print(f"\n  unit_master total: {total:,} rows ({(PROJECT/'local.db').stat().st_size//1024//1024} MB)")
    for s in ["public_price"]:
        cnt = db.conn.execute("SELECT count(*) FROM unit_master WHERE source=?", (s,)).fetchone()[0]
        print(f"    source={s}: {cnt:,}")
    db.close()
