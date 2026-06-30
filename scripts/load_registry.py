"""전유부 CSV → DB 적재 (최적화: 100K배치, PRAGMA)"""
import sqlite3, time, sys
sys.path.insert(0, "D:/부동산호수알아내기")
from src.ho_key import normalize_ho, normalize_dong

CSV = r"D:\부동산호수알아내기\건축HUB_대용량데이터\건축물대장_전유부_2026-05.csv"
DB = "D:/부동산호수알아내기/local.db"

db = sqlite3.connect(DB)
t0 = time.time()
prev = db.execute("SELECT count(*) FROM unit_master WHERE source='building_registry'").fetchone()[0]
rows, valid, total = [], 0, 0

with open(CSV, encoding="utf-8") as f:
    for line in f:
        total += 1
        parts = line.split("|")
        if len(parts) < 26: continue
        try:
            ho = normalize_ho(parts[22].strip(), "building_registry")
            dong = normalize_dong(parts[21].strip(), "building_registry")
            fl = parts[25].strip()
            floor = int(fl) if fl.isdigit() else None
            rows.append(("", dong, ho, f"{dong.zfill(3)}{ho}", floor,
                         "exact" if floor else "mid", "building_registry", parts[0].strip()))
            valid += 1
        except (ValueError, IndexError): continue
        
        if len(rows) >= 100000:
            db.executemany("INSERT OR IGNORE INTO unit_master (complex_id,dong,ho,canonical_ho_id,floor,floor_kind,source,bldg_pk) VALUES (?,?,?,?,?,?,?,?)", rows)
            db.commit()
            rows = []
        if total % 3000000 == 0:
            cur = db.execute("SELECT count(*) FROM unit_master WHERE source='building_registry'").fetchone()[0]
            e = time.time() - t0
            print(f"  {total/1e6:.1f}M lines, +{cur-prev:,} reg, {total/e:.0f} l/s ({e/60:.0f}min)", flush=True)

if rows:
    db.executemany("INSERT OR IGNORE INTO unit_master (complex_id,dong,ho,canonical_ho_id,floor,floor_kind,source,bldg_pk) VALUES (?,?,?,?,?,?,?,?)", rows)
    db.commit()

cur = db.execute("SELECT count(*) FROM unit_master WHERE source='building_registry'").fetchone()[0]
e = time.time() - t0
print(f"\nDone: +{cur-prev:,} reg (total {cur:,}) in {e/60:.1f}min")
db.close()
