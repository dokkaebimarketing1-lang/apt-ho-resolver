"""건축HUB 전유부 CSV → unit_master_v2 전체 적재 (전국 보존, 서울 필터 가능)

CSV 포맷 (pipe-delimited, 27 fields):
  [0]  mgmBldrgstPk
  [5]  지번주소
  [6]  도로명주소
  [7]  건물명 (complex_name)
  [8]  sigungu_cd ⭐
  [9]  bjdong_cd
  [22] 동 (예: "102동")
  [23] 호 (예: "624호")
  [24] 층 (예: "20")
  [25] 층구분 (예: "지상")
"""
import sys, sqlite3, csv, re, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
CSV_PATH = ROOT / "건축HUB_대용량데이터" / "건축물대장_전유부_2026-05.csv"
DB_PATH = ROOT / "local.db"

if not CSV_PATH.exists():
    print(f"CSV not found: {CSV_PATH}")
    sys.exit(1)

db = sqlite3.connect(str(DB_PATH))
db.execute("PRAGMA journal_mode=OFF")  # fastest for bulk insert
db.execute("PRAGMA synchronous=OFF")
db.execute("PRAGMA cache_size=-1000000")  # 1GB cache

# Drop UNIQUE constraint for bulk load speed — dedup after
db.execute("DROP TABLE IF EXISTS unit_master_v2")
db.execute("""CREATE TABLE unit_master_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sigungu_cd TEXT NOT NULL,
    bjdong_cd TEXT NOT NULL,
    address_jibun TEXT,
    address_road TEXT,
    complex_name TEXT NOT NULL,
    bldg_pk TEXT NOT NULL,
    dong TEXT NOT NULL,
    ho TEXT NOT NULL,
    canonical_ho_id TEXT NOT NULL,
    line TEXT NOT NULL,
    floor INTEGER,
    floor_kind TEXT,
    area_exclusive INTEGER,
    area_type TEXT,
    direction TEXT,
    public_price INTEGER,
    source TEXT,
    is_verified INTEGER DEFAULT 0
)""")

# ── 정규화 함수 ──
def norm_dong(raw: str) -> str:
    """'102동' → '102'"""
    d = re.sub(r'[^0-9]', '', raw.strip())
    return d.lstrip('0') or '0'

def norm_ho(raw: str) -> str:
    """'624호' → '0624'"""
    h = re.sub(r'[^0-9]', '', raw.strip())
    return h.zfill(4)

def extract_line(ho: str) -> str:
    """'0624' → '24'"""
    if len(ho) >= 2:
        return ho[-2:]
    return '00'

def norm_floor(raw: str) -> int | None:
    """'20' → 20, '지하1' → -1"""
    s = raw.strip()
    if not s:
        return None
    neg = -1 if '지하' in s or s.startswith('B') else 1
    n = re.sub(r'[^0-9]', '', s)
    if not n:
        return None
    return int(n) * neg

def norm_floor_kind(raw: str) -> str | None:
    """'지상' → 'above', '지하' → 'below'"""
    s = raw.strip()
    if '지하' in s:
        return 'below'
    if '지상' in s:
        return 'above'
    return s if s else None

# ── 적재 ──
BATCH_SIZE = 100_000
rows: list[tuple] = []
total = 0
t0 = time.time()

with open(CSV_PATH, encoding='utf-8') as f:
    reader = csv.reader(f, delimiter='|')
    for fields in reader:
        if len(fields) < 26:
            continue  # malformed row

        bldg_pk = fields[0].strip()
        sigungu_cd = fields[8].strip()
        bjdong_cd = fields[9].strip()

        if not bldg_pk or not sigungu_cd:
            continue

        dong = norm_dong(fields[22])
        ho = norm_ho(fields[23])

        if not dong or ho == '0000':
            continue

        canonical = f"{dong.zfill(3)}{ho}"
        line = extract_line(ho)

        # 두 필드 중 어느 것이 층이고 어느 것이 층구분인지 자동 판별
        f24, f25 = fields[24].strip(), fields[25].strip()
        f24_has_kind = '지상' in f24 or '지하' in f24
        f25_has_kind = '지상' in f25 or '지하' in f25

        if f24_has_kind and not f25_has_kind:
            floor_kind = norm_floor_kind(f24)
            floor_val = norm_floor(f25)
        elif f25_has_kind and not f24_has_kind:
            floor_kind = norm_floor_kind(f25)
            floor_val = norm_floor(f24)
        elif norm_floor(f24) is not None and norm_floor(f25) is None:
            floor_val = norm_floor(f24)
            floor_kind = norm_floor_kind(f25)
        elif norm_floor(f25) is not None and norm_floor(f24) is None:
            floor_val = norm_floor(f25)
            floor_kind = norm_floor_kind(f24)
        else:
            # 둘 다 층이거나 둘 다 구분이면 [24]=층, [25]=구분으로 가정
            floor_val = norm_floor(f24)
            floor_kind = norm_floor_kind(f25)

        rows.append((
            sigungu_cd,
            bjdong_cd,
            fields[5].strip() if len(fields) > 5 else None,
            fields[6].strip() if len(fields) > 6 else None,
            (fields[7].strip() or bldg_pk)[:100],
            bldg_pk,
            dong,
            ho,
            canonical,
            line,
            floor_val,
            floor_kind,
            None,  # area_exclusive (공동주택가격에서 backfill)
            None,  # area_type
            None,  # direction
            None,  # public_price
            "expos",  # source: 전유부
            0,      # is_verified
        ))
        total += 1

        if len(rows) >= BATCH_SIZE:
            db.executemany(
                """INSERT INTO unit_master_v2
                   (sigungu_cd, bjdong_cd, address_jibun, address_road,
                    complex_name, bldg_pk, dong, ho, canonical_ho_id, line,
                    floor, floor_kind, area_exclusive, area_type,
                    direction, public_price, source, is_verified)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            db.commit()
            elapsed = time.time() - t0
            rate = total / elapsed if elapsed > 0 else 0
            print(f"  {total//10000:>4}만행  {rate:>7.0f}行/s  {elapsed:.0f}s", flush=True)
            rows = []

# 마지막 배치
if rows:
    db.executemany(
        """INSERT INTO unit_master_v2
           (sigungu_cd, bjdong_cd, address_jibun, address_road,
            complex_name, bldg_pk, dong, ho, canonical_ho_id, line,
            floor, floor_kind, area_exclusive, area_type,
            direction, public_price, source, is_verified)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    db.commit()

total_raw = total
elapsed = time.time() - t0

# ── 중복 제거 & 인덱스 생성 ──
print(f"\nRaw insert: {total_raw:,}행 ({elapsed/60:.1f}min). Dedup & indexing...", flush=True)

# Create temp table with dedup
db.execute("""
    CREATE TABLE unit_master_v2_dedup AS
    SELECT MIN(id) as id, sigungu_cd, bjdong_cd, address_jibun, address_road,
           complex_name, bldg_pk, dong, ho, canonical_ho_id, line,
           floor, floor_kind, area_exclusive, area_type,
           direction, public_price, source, is_verified
    FROM unit_master_v2
    GROUP BY bldg_pk, canonical_ho_id, source
""")
db.execute("DROP TABLE unit_master_v2")
db.execute("ALTER TABLE unit_master_v2_dedup RENAME TO unit_master_v2")

# Create indexes
db.execute("CREATE INDEX IF NOT EXISTS idx_um_v2_sigungu ON unit_master_v2(sigungu_cd)")
db.execute("CREATE INDEX IF NOT EXISTS idx_um_v2_complex ON unit_master_v2(complex_name)")
db.execute("CREATE INDEX IF NOT EXISTS idx_um_v2_bldg_pk ON unit_master_v2(bldg_pk)")
db.execute("CREATE INDEX IF NOT EXISTS idx_um_v2_dong_line ON unit_master_v2(complex_name, dong, line)")
db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_um_v2_unique ON unit_master_v2(bldg_pk, canonical_ho_id, source)")

db.execute("PRAGMA journal_mode=WAL")
db.commit()

final_count = db.execute("SELECT count(*) FROM unit_master_v2").fetchone()[0]
seoul_count = db.execute(
    "SELECT count(*) FROM unit_master_v2 WHERE sigungu_cd LIKE '11%'"
).fetchone()[0]
seoul_complexes = db.execute(
    "SELECT count(DISTINCT complex_name) FROM unit_master_v2 WHERE sigungu_cd LIKE '11%'"
).fetchone()[0]

print(f"\n{'='*60}")
print(f"unit_master_v2 적재 완료")
print(f"  원본: {total_raw:,}행")
print(f"  중복제거: {final_count:,}행 ({elapsed/60:.1f}min)")
print(f"  서울: {seoul_count:,}행 ({seoul_count/final_count*100:.1f}%)")
print(f"  서울 단지: {seoul_complexes:,}개")
print(f"{'='*60}")

db.close()
