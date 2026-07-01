"""방향(direction) 수동 입력 도구

동 단위로 방향을 설정하거나, 라인:방향 쌍으로 개별 지정 가능.

사용법:
    # 동 전체에 방향 설정 (모든 라인에 동일 방향)
    python scripts/update_direction.py "헬리오시티" "S" --dong 1001

    # 라인별 방향 세부 지정
    python scripts/update_direction.py "헬리오시티" "10:S,20:S" --dong 1001
"""
import sys, sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "local.db"

def parse_line_dirs(spec: str) -> dict[str, str]:
    """'10:S,20:S' → {10: S, 20: S} | 'S' → {*: S} (wildcard)"""
    spec = spec.strip().upper()
    if "," not in spec and ":" not in spec and len(spec) <= 3:
        return {"*": spec}  # 단일 방향 → 모든 라인에 적용
    result = {}
    for pair in spec.split(","):
        pair = pair.strip()
        if ":" in pair:
            line, direction = pair.split(":", 1)
            result[line.strip()] = direction.strip().upper()
    return result

def update_direction(complex_name: str, line_dirs: dict[str, str],
                     dong: str | None = None):
    db = sqlite3.connect(str(DB))

    complex_match = db.execute(
        "SELECT DISTINCT complex_name FROM line_fact_apt WHERE complex_name LIKE ? LIMIT 1",
        (f"%{complex_name}%",)
    ).fetchone()
    if not complex_match:
        print(f"Not found: {complex_name}")
        db.close()
        return
    actual_name = complex_match[0]
    print(f"[{actual_name}]")

    dongs = [dong] if dong else [r[0] for r in db.execute(
        "SELECT DISTINCT dong FROM line_fact_apt WHERE complex_name=?", (actual_name,)
    ).fetchall()]

    updated = 0
    for d in dongs:
        if "*" in line_dirs:
            db.execute("UPDATE line_fact_apt SET direction=?, confidence=1.0 WHERE complex_name=? AND dong=?",
                       (line_dirs["*"], actual_name, d))
            updated += db.total_changes
        else:
            for line, direction in line_dirs.items():
                db.execute("UPDATE line_fact_apt SET direction=?, confidence=1.0 WHERE complex_name=? AND dong=? AND line=?",
                           (direction, actual_name, d, line))
                updated += db.total_changes
    db.commit()

    # Show results
    for d in dongs[:5]:
        rows = db.execute("SELECT line, direction FROM line_fact_apt WHERE complex_name=? AND dong=? ORDER BY line",
                          (actual_name, d)).fetchall()
        if rows:
            dirs = " | ".join(f"L{r[0]}={r[1] or '?'}" for r in rows)
            print(f"  {d}동: {dirs}")
    if len(dongs) > 5:
        print(f"  ... and {len(dongs)-5} more dongs")
    print(f"Updated: {updated} rows")
    db.close()

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Update direction for apartment complexes")
    p.add_argument("complex", help="Complex name (e.g., 헬리오시티)")
    p.add_argument("direction", help="Direction spec: 'S' for all, or '10:S,20:N' per line")
    p.add_argument("--dong", "-d", help="Specific dong (default: all)")
    args = p.parse_args()

    line_dirs = parse_line_dirs(args.direction)
    if not line_dirs:
        print("Usage: python update_direction.py <complex> <direction> [--dong N]")
        sys.exit(1)
    update_direction(args.complex, line_dirs, args.dong)
