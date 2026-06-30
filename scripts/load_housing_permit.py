"""주택인허가 → unit_master 적재 (별도 행, source='housing_permit', area_type=확정)"""
import sqlite3, time, sys
sys.path.insert(0, "D:/부동산호수알아내기")
from src.ho_key import normalize_ho, normalize_dong

CSV = r"D:\부동산호수알아내기\건축HUB_대용량데이터\주택인허가_호별개요_2026-05.csv"
SEP, DB = "|", "D:/부동산호수알아내기/local.db"

db = sqlite3.connect(DB)
t0, rows, inserted = time.time(), [], 0

with open(CSV, encoding="utf-8") as f:
    for cnt, line in enumerate(f):
        parts = line.split(SEP)
        if len(parts) < 19: continue
        try:
            ho = normalize_ho(parts[17].strip(), "housing_permit")
            dong = normalize_dong(parts[12].strip(), "housing_permit")
            at = parts[18].strip()  # pngtypGbNm (확정!)
            fl_str = parts[13].strip()
            fl = int(fl_str) if fl_str.isdigit() else None
            cn = parts[3].strip() if len(parts) > 3 else ""
            mgm = parts[0].strip()
            if not ho or not at: continue
        except (ValueError, IndexError): continue
        
        rows.append((cn[:50], dong, ho, f"{dong.zfill(3)}{ho}", fl, "exact" if fl else "mid", at, "housing_permit", mgm))
        if len(rows) >= 50000:
            db.executemany(
                "INSERT OR IGNORE INTO unit_master (complex_id,dong,ho,canonical_ho_id,floor,floor_kind,area_type,source,bldg_pk) VALUES (?,?,?,?,?,?,?,?,?)",
                rows)
            rows = []
            if cnt % 500000 == 0:
                print(f"  {cnt/1e6:.1f}M lines parsed ({time.time()-t0:.0f}s)", flush=True)

if rows:
    print(f"  Inserting {len(rows)} rows...")
    db.executemany(
        "INSERT OR IGNORE INTO unit_master (complex_id,dong,ho,canonical_ho_id,floor,floor_kind,area_type,source,bldg_pk) VALUES (?,?,?,?,?,?,?,?,?)",
        rows)
    print(f"  Done")

db.commit()
t = db.execute("SELECT count(*) FROM unit_master").fetchone()[0]
hp = db.execute("SELECT count(*) FROM unit_master WHERE source='housing_permit'").fetchone()[0]
elapsed = time.time()-t0
print(f"New housing_permit: {hp:,} rows (total: {t:,}) in {elapsed:.0f}s")
print(f"area_type confirmed: {hp:,} rows with pngtypGbNm (100% 확정)")
db.close()
