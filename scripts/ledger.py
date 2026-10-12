#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ledger.py — 成本台账（JSONL 追加制，币与真钱分列）

用法:
  python ledger.py add <ledger.jsonl> <action> <shot_id> <backend> <coins> <cash_cny> <duration_sec> [note]
  python ledger.py summary <ledger.jsonl>          # 总览三数 + 分后端明细

action ∈ submit|retry|salvage|fail_refund|fit|concat
fail_refund 传负数即冲账；汇总时自动净值。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

VALID_ACTIONS = {"submit", "retry", "salvage", "fail_refund", "fit", "concat"}


def add(args):
    path, action, shot_id, backend, coins, cash, dur = args[:7]
    note = args[7] if len(args) > 7 else ""
    if action not in VALID_ACTIONS:
        raise ValueError(f"非法 action: {action}（允许: {sorted(VALID_ACTIONS)}）")
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "action": action,
             "shot_id": shot_id, "backend": backend,
             "coins": float(coins), "cash_cny": float(cash),
             "duration_sec": float(dur), "note": note}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": True, "entry": entry}, ensure_ascii=False))


def summary(path):
    rows = []
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    by_backend = {}
    for r in rows:
        b = by_backend.setdefault(r["backend"], {"coins": 0.0, "cash_cny": 0.0, "calls": 0})
        b["coins"] += r["coins"]; b["cash_cny"] += r["cash_cny"]; b["calls"] += 1
    out = {
        "overview": {   # 总览三数
            "final_video_sec": round(sum(r["duration_sec"] for r in rows
                                         if r["action"] == "concat"), 3),
            "machine_sec": round(sum(r["duration_sec"] for r in rows), 3),
            "cash_cny_net": round(sum(r["cash_cny"] for r in rows), 2),
            "coins_net": round(sum(r["coins"] for r in rows), 2),
        },
        "by_backend": {k: {"coins": round(v["coins"], 2), "cash_cny": round(v["cash_cny"], 2),
                           "calls": v["calls"]} for k, v in by_backend.items()},
        "entries": len(rows),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    if sys.argv[1] == "add":
        add(sys.argv[2:])
    elif sys.argv[1] == "summary":
        summary(sys.argv[2])
    else:
        print(__doc__); sys.exit(2)


if __name__ == "__main__":
    main()
