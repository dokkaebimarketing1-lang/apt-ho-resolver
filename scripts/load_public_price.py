"""공시가격 ZIP → DB 적재 — raw sqlite3 + 실시간 진행률"""
import sqlite3, time, zipfile, csv
from pathlib import Path

ROOT = Path(__file__).parent.parent
ZIP_PATH = ROOT / "참고자료/데이터샘플/원본데이터/국토교통부-주택-공시가격-정보-20250626.zip"
CSV_NAME = "국토교통부_주택 공시가격 정보(2025).csv"
DB_PATH = ROOT / "local.db"
TOTAL_ESTIMATE = 13_000_000

db = sqlite3.connect(str(DB_PATH))
db.execute("PRAGMA journal_mode=WAL")
rows, cnt, t0 = [], 0, time.time()
last_pct = 0

def safe_int(s):
    try: return int(float(s))
    except: return None

with zipfile.ZipFile(ZIP_PATH) as zf:
    with zf.open(CSV_NAME) as f:
        reader = csv.DictReader((line.decode("utf-8-sig") for line in f))
        for r in reader:
            dr = (r.get("동명") or "").strip()
            hr = (r.get("호명") or "").strip()
            if not dr or not hr: continue
            dong = dr.lstrip("0")[:10]
            if not dong.isdigit(): dong = f"{ord(dr[0])%100:02d}"
            ho = hr.lstrip("0").zfill(4)
            area = safe_int(r.get("전용면적"))
            if area: area = int(area * 100) if area < 5000 else area
            else: area = None
            price = safe_int(r.get("공시가격"))
            cn = (r.get("단지명") or "")[:50]
            rows.append((cn, dong, ho, f"{dong.zfill(3)}{ho}", None, "mid", area, "", "", price, "public_price", None))
            cnt += 1
            
            if len(rows) >= 50000:
                db.executemany("INSERT OR IGNORE INTO unit_master (complex_id,dong,ho,canonical_ho_id,floor,floor_kind,area_exclusive,area_type,direction,public_price,source,bldg_pk) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                rows = []
                db.commit()
                elapsed = time.time() - t0
                pct = min(100, cnt * 100 // TOTAL_ESTIMATE)
                if pct > last_pct:
                    rate = cnt / elapsed if elapsed > 0 else 0
                    eta_m = int((TOTAL_ESTIMATE - cnt) / rate / 60) if rate > 0 else 0
                    print(f"  [1/4] public_price {pct:>3}%  {cnt//10000:>4}만행  {rate:>.0f}行/s  ETA {eta_m}분", flush=True)
                    last_pct = pct

if rows:
    db.executemany("INSERT OR IGNORE INTO unit_master (complex_id,dong,ho,canonical_ho_id,floor,floor_kind,area_exclusive,area_type,direction,public_price,source,bldg_pk) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()

t = db.execute("SELECT count(*) FROM unit_master").fetchone()[0]
elapsed = time.time() - t0
print(f"  [1/4] public_price ✅ {t:>12,} rows ({elapsed/60:.1f}min)", flush=True)
db.close()
