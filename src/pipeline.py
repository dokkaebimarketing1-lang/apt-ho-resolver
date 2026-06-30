"""Pipeline — F-S 매칭 → DS 충돌 해결 → [{ho, probability}] 출력 (A84, A81).

DS는 F-S(inference.py) 출력 위 충돌 해결용만. 단독 매칭 프레임워크 아님.
가중합 금지. 우선순위: P3 > CLOSURE_LABEL > ho_hint > 대장 대조.
"""

from __future__ import annotations

from typing import Any

from src.inference import (
    _block_candidates,
    _fellegi_sunter_weight,
    _weight_to_probability,
)

__all__ = ["combine_evidence", "resolve_cluster", "run_pipeline"]

_DEFAULT_MASS: dict[str, float] = {
    "p3": 0.95, "closure_label": 0.90, "ho_hint": 0.70, "ledger": 0.50,
    "vacancy": 0.90,
}


def combine_evidence(evidences: list[dict]) -> dict:
    """Dempster-Shafer 증거 결합. 믿음 질량, 충돌 K, "모름" 명시.

    각 증거: {"hypothesis": ho, "mass": float, "is_negative": bool}
    Returns: {"masses": {ho: mass}, "unknown": float, "conflict_k": float}
    """
    if not evidences:
        return {"masses": {}, "unknown": 1.0, "conflict_k": 0.0}

    state: dict[str, float] = {}
    unknown = 1.0
    k_acc = 0.0

    for ev in evidences:
        hyp = ev.get("hypothesis")
        mass = ev.get("mass", 0.0)
        is_neg = ev.get("is_negative", False)
        if mass <= 0 or hyp is None:
            continue
        mass = min(mass, 0.999)

        if is_neg:
            k = state.get(hyp, 0.0) * mass
        else:
            k = sum(m for h, m in state.items() if h != hyp) * mass

        norm = 1.0 - k
        if norm < 1e-10:
            return {"masses": {}, "unknown": 1.0, "conflict_k": 1.0}

        new_state: dict[str, float] = {}
        if is_neg:
            for h, m in state.items():
                new_state[h] = m * (1.0 - mass) / norm if h == hyp else m / norm
            new_unknown = unknown / norm
        else:
            for h, m in state.items():
                new_state[h] = (m + unknown * mass) / norm if h == hyp else m * (1.0 - mass) / norm
            if hyp not in state:
                new_state[hyp] = unknown * mass / norm
            new_unknown = unknown * (1.0 - mass) / norm

        state = new_state
        unknown = new_unknown
        k_acc = 1.0 - (1.0 - k_acc) * (1.0 - k)

    return {"masses": state, "unknown": unknown, "conflict_k": k_acc}


def resolve_cluster(cluster: list[dict]) -> dict:
    """클러스터 내 증거 우선순위 해결. P3 > CLOSURE_LABEL > ho_hint > 대장 대조.

    Returns: {"ho_final", "candidate_hos", "method", "is_estimate", "method_log"}
    """
    if not cluster:
        return {"ho_final": None, "candidate_hos": [], "method": "none",
                "is_estimate": True, "method_log": ["증거 부족"]}

    by_src: dict[str, list[dict]] = {}
    negatives: list[dict] = []
    for item in cluster:
        if item.get("is_negative"):
            negatives.append(item)
        else:
            by_src.setdefault(item.get("source", "ledger"), []).append(item)

    # P3: 정답 라벨 — immediate return
    p3 = by_src.get("p3", [])
    if p3:
        ho = p3[0]["ho"]
        return {"ho_final": ho, "candidate_hos": [{"ho": ho, "probability": 1.0}],
                "method": "p3", "is_estimate": False, "method_log": [f"P3 정답 라벨: {ho}"]}

    # Build DS evidence list
    ds_ev: list[dict] = []
    for src in ("closure_label", "ho_hint", "ledger"):
        for item in by_src.get(src, []):
            ds_ev.append({"hypothesis": item["ho"],
                          "mass": item.get("mass", _DEFAULT_MASS.get(src, 0.5)),
                          "is_negative": False})
    for item in negatives:
        if item.get("ho"):
            ds_ev.append({"hypothesis": item["ho"],
                          "mass": item.get("mass", _DEFAULT_MASS["vacancy"]),
                          "is_negative": True})

    if not ds_ev:
        return {"ho_final": None, "candidate_hos": [], "method": "none",
                "is_estimate": True, "method_log": ["양의 증거 없음"]}

    result = combine_evidence(ds_ev)
    masses = result["masses"]

    method = "closure_label" if "closure_label" in by_src else ("ho_hint" if "ho_hint" in by_src else "ledger")
    log = [f"DS 결합 (K={result['conflict_k']:.4f})", f"증거 수: {len(ds_ev)}"]

    cands = sorted(masses.items(), key=lambda x: x[1], reverse=True)
    candidate_hos = [{"ho": ho, "probability": round(m, 4)} for ho, m in cands if m > 0.001]
    total = sum(c["probability"] for c in candidate_hos)
    if total > 0:
        for c in candidate_hos:
            c["probability"] = round(c["probability"] / total, 4)

    ho_final = candidate_hos[0]["ho"] if candidate_hos else None
    is_estimate = method != "closure_label" or len(candidate_hos) > 1
    return {"ho_final": ho_final, "candidate_hos": candidate_hos,
            "method": method, "is_estimate": is_estimate, "method_log": log}


def _gt_to_source(gt: Any) -> str:
    """GroundTruth → 소스 우선순위 분류."""
    if not gt.is_ground_truth():
        return "ledger"
    return "p3" if getattr(gt, "source", "") == "auction" else "closure_label"


def _add_ev(cluster: list[dict], ho: str, source: str, mass: float, neg: bool = False) -> None:
    """클러스터에 증거 추가 (헬퍼)."""
    cluster.append({"ho": ho, "source": source, "mass": mass,
                    "confidence": mass, "is_negative": neg})


def run_pipeline(
    listings: list[dict],
    unit_master: list[dict],
    ground_truths: list[Any] | None = None,
    m_probs: dict[str, float] | None = None,
    u_probs: dict[str, float] | None = None,
) -> list[dict]:
    """전체 파이프라인: F-S 매칭 → DS 충돌 해결 → [{ho, probability}].

    DS는 F-S 출력 위 충돌 해결용만. 가중합 사용 금지.
    """
    ground_truths = ground_truths or []
    m_probs = m_probs or {}
    u_probs = u_probs or {}
    results: list[dict] = []

    for listing in listings:
        cid = str(listing.get("complex_id", ""))
        dong = str(listing.get("dong", ""))

        # 1. F-S matching (대장 대조)
        candidates = _block_candidates(listing, unit_master)
        scored = sorted(
            ((_fellegi_sunter_weight(listing, u, m_probs, u_probs), u) for u in candidates),
            key=lambda x: x[0], reverse=True,
        )
        max_w = scored[0][0] if scored else 0.0
        cluster: list[dict] = []
        seen: set[str] = set()
        for weight, unit in scored:
            ho = str(unit.get("ho", ""))
            if not ho or ho in seen:
                continue
            seen.add(ho)
            _add_ev(cluster, ho, "ledger", _weight_to_probability(weight, max_w))

        # 2. Ground truth matching
        for gt in ground_truths:
            if str(getattr(gt, "complex_id", "") or "") != cid:
                continue
            if str(getattr(gt, "dong", "") or "") != dong:
                continue
            gt_ho = getattr(gt, "ho", None)
            if gt_ho is None:
                continue
            _add_ev(cluster, str(gt_ho), _gt_to_source(gt), getattr(gt, "confidence", 0.5))

        # 3. ho_hint from listing
        ho_hint = listing.get("ho_hint") or listing.get("ho")
        if ho_hint:
            _add_ev(cluster, str(ho_hint), "ho_hint", _DEFAULT_MASS["ho_hint"])

        # 4. Negative evidence: vacancy
        for vho in listing.get("vacancy_hos", []):
            _add_ev(cluster, str(vho), "vacancy", _DEFAULT_MASS["vacancy"], neg=True)

        # 5. Resolve
        r = resolve_cluster(cluster)
        results.append({"complex_id": cid, "dong": dong, **r})

    return results
