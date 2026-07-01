"""DB 전체 재구축 — subprocess + PYTHONUNBUFFERED + 실시간 출력 relay"""
import os, time, subprocess, sys, sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB = ROOT / "local.db"
VENV = str(ROOT / ".venv" / "Scripts" / "python.exe")

# Clean
print("=" * 50)
print("[0/4] Cleaning...", flush=True)
for ext in ["", "-wal", "-shm"]:
    p = Path(str(DB) + ext)
    if p.exists(): p.unlink()

db = sqlite3.connect(str(DB))
db.execute("PRAGMA journal_mode=WAL")
db.execute("""CREATE TABLE IF NOT EXISTS unit_master (
    id INTEGER PRIMARY KEY AUTOINCREMENT, complex_id TEXT DEFAULT '', dong TEXT DEFAULT '',
    ho TEXT NOT NULL, canonical_ho_id TEXT, floor INTEGER, floor_kind TEXT DEFAULT 'exact',
    area_exclusive INTEGER, area_type TEXT DEFAULT '', direction TEXT DEFAULT '',
    public_price INTEGER, source TEXT DEFAULT '', bldg_pk TEXT DEFAULT NULL
)""")
db.execute("CREATE TABLE IF NOT EXISTS line_fact (complex_id TEXT, dong TEXT, line TEXT, direction TEXT, area_type TEXT, confidence REAL, observations INTEGER DEFAULT 1, revoked INTEGER DEFAULT 0)")
db.commit(); db.close()
print("  DB ready\n", flush=True)

steps = [
    ("[1/4] public_price", "load_public_price.py"),
    ("[2/4] housing_permit", "load_housing_permit.py"),
    ("[3/4] build_line_fact", "build_line_fact.py"),
    ("[4/4] indexes", "create_indexes.py"),
]

t0 = time.time()
for label, script in steps:
    print(f"{'='*50}\n{label}:", flush=True)
    ts = time.time()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    script_path = str(ROOT / "scripts" / script)
    proc = subprocess.Popen(
        [VENV, "-u", script_path],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        bufsize=1,
    )
    for line in proc.stdout:
        # 이미 flush=True 된 출력 그대로 relay
        sys.stdout.write(line)
        sys.stdout.flush()
    proc.wait()
    if proc.returncode != 0:
        print(f"  ❌ FAILED (code={proc.returncode})", flush=True)
        sys.exit(1)
    print(f"  ✅ Done ({time.time()-ts:.0f}s)", flush=True)

# Final stats
db = sqlite3.connect(str(DB))
t = db.execute("SELECT count(*) FROM unit_master").fetchone()[0]
lf = db.execute("SELECT count(*) FROM line_fact").fetchone()[0]
fl = db.execute("SELECT count(*) FROM unit_master WHERE floor IS NOT NULL").fetchone()[0]
db.close()
e = time.time()-t0
print(f"\n{'='*50}")
print(f"REBUILD DONE! {t:,} rows, {lf:,} line_fact, floor {100*fl//t}%")
print(f"Time: {e/60:.0f}min")
