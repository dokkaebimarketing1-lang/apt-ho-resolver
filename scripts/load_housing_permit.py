"""주택인허가 → unit_master — raw sqlite3 + 실시간 진행률"""
import sqlite3, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
CSV = ROOT / "건축HUB_대용량데이터/주택인허가_호별개요_2026-05.csv"
DB_PATH = ROOT / "local.db"
TOTAL_ESTIMATE = 6_700_000

db = sqlite3.connect(str(DB_PATH))
db.execute("PRAGMA journal_mode=WAL")
rows, cnt, inserted, t0 = [], 0, 0, time.time()
last_pct = 0

with open(CSV, encoding="utf-8") as f:
    for line in f:
        parts = line.split("|")
        if len(parts) < 19: continue
        ho_raw = parts[17].strip()
        dong_raw = parts[12].strip()
        if not ho_raw: continue
        ho = ho_raw.lstrip("0").zfill(4)
        dong = dong_raw.lstrip("0")[:10]
        if not dong:
            continue
        if not dong.isdigit():
            dong = f"{ord(dong_raw[0])%100:02d}"
        at = parts[18].strip()
        if not at: continue
        fl_str = parts[13].strip()
        fl = int(fl_str) if fl_str.isdigit() else None
        cn = parts[3].strip()[:50] if len(parts) > 3 else ""
        mgm = parts[0].strip()
        rows.append((cn, dong, ho, f"{dong.zfill(3)}{ho}", fl, "exact" if fl else "mid", None, at, "", None, "housing_permit", mgm))
        cnt += 1
        
        if len(rows) >= 50000:
            db.executemany("INSERT OR IGNORE INTO unit_master (complex_id,dong,ho,canonical_ho_id,floor,floor_kind,area_exclusive,area_type,direction,public_price,source,bldg_pk) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            inserted += len(rows); rows = []
            db.commit()
            elapsed = time.time() - t0
            pct = min(100, cnt * 100 // TOTAL_ESTIMATE)
            if pct > last_pct:
                rate = cnt / elapsed if elapsed > 0 else 0
                eta_m = int((TOTAL_ESTIMATE - cnt) / rate / 60) if rate > 0 else 0
                print(f"  [2/4] housing   {pct:>3}%  {cnt//10000:>4}만행  {rate:>.0f}行/s  ETA {eta_m}분", flush=True)
                last_pct = pct

if rows:
    db.executemany("INSERT OR IGNORE INTO unit_master (complex_id,dong,ho,canonical_ho_id,floor,floor_kind,area_exclusive,area_type,direction,public_price,source,bldg_pk) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()

t = db.execute("SELECT count(*) FROM unit_master").fetchone()[0]
hp = db.execute("SELECT count(*) FROM unit_master WHERE source='housing_permit'").fetchone()[0]
elapsed = time.time() - t0
print(f"  [2/4] housing   ✅ {hp:>12,} housing_permit rows (total {t:,}) in {elapsed/60:.1f}min", flush=True)
db.close()
