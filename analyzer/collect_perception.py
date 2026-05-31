#!/usr/bin/env python3
"""Tier 1 感知收集 + 决策脚本 — 供 Cron Job 调用

输出：结构化 JSON（感知数据 + 条件评分 + 决策结果 + 拟发送消息）

用法:
    python collect_perception.py                # 完整输出
    python collect_perception.py --compact      # 紧凑格式
    python collect_perception.py --json         # 纯 JSON（无额外文本）
"""
import os
os.environ["TZ"] = "Asia/Shanghai"
try:
    import time
    time.tzset()
except (ImportError, AttributeError):
    pass

import json
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.database import init_db
from analyzer.decision_engine import analyze


def main():
    init_db()

    result = analyze()

    # 输出给 LLM 的格式
    output = {
        "decision": {
            "should_act": result["should_act"],
            "score": result["score"],
            "condition": result["condition_summary"],
            "scene": result["scene"],
            "proposed_message": result["message"],
            "send_time": result["send_time"],
            "reason": result["reason"],
        },
    }

    # 仅在应该行动时包含原始数据
    if result["should_act"]:
        raw = result.get("raw_data", {})
        output["perception_summary"] = {
            "time": raw.get("perception", {}).get("time", {}).get("timestamp", ""),
            "user_status": raw.get("perception", {}).get("user_activity", {}).get("status", ""),
            "pending_tasks": raw.get("perception", {}).get("tasks", {}).get("pending", 0),
            "overdue_tasks": raw.get("perception", {}).get("tasks", {}).get("overdue", 0),
            "today_proactive": raw.get("perception", {}).get("proactive_history", {}).get("today_count", 0),
        }

    if "--compact" in sys.argv:
        print(json.dumps(output, ensure_ascii=False, separators=(',', ':')))
    elif "--json" in sys.argv:
        print(json.dumps(output, ensure_ascii=False))
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
