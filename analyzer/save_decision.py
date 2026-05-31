#!/usr/bin/env python3
"""Tier 1 决策保存脚本 — 供 Agent 在 LLM 分析后调用

将 LLM 的主动对话决策写入数据库，供 Tier 2 调度器执行。

用法:
    python save_decision.py --time "14:30" --message "消息内容" --reason "原因"
    python save_decision.py --skip --reason "不适合主动对话的原因"
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
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.database import init_db, execute


def main():
    parser = argparse.ArgumentParser(description="保存主动对话决策")
    parser.add_argument("--time", help="目标发送时间 HH:MM")
    parser.add_argument("--message", help="要发送的消息内容")
    parser.add_argument("--reason", default="", help="决策原因")
    parser.add_argument("--skip", action="store_true", help="跳过（不发送）")
    args = parser.parse_args()
    
    init_db()
    
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    
    if args.skip:
        # 记录跳过原因（用于审计）
        execute(
            """INSERT INTO proactive_messages 
               (target_time, target_date, message, reason, status, created_at) 
               VALUES (?, ?, ?, ?, 'skipped', ?)""",
            ("00:00", today, f"[SKIP] {args.reason}", args.reason, now.isoformat())
        )
        result = {"status": "skipped", "reason": args.reason}
    elif args.time and args.message:
        # 验证时间格式
        try:
            target_h, target_m = map(int, args.time.split(":"))
            if not (0 <= target_h <= 23 and 0 <= target_m <= 59):
                raise ValueError("Invalid time")
        except ValueError:
            print(json.dumps({"error": f"无效时间格式: {args.time}，应为 HH:MM"}))
            sys.exit(1)
        
        # 如果目标时间已过，设为明天
        target_date = today
        target_dt = datetime.strptime(f"{today} {args.time}", "%Y-%m-%d %H:%M")
        if target_dt <= now:
            tomorrow = now + __import__('datetime').timedelta(days=1)
            target_date = tomorrow.strftime("%Y-%m-%d")
        
        execute(
            """INSERT INTO proactive_messages 
               (target_time, target_date, message, reason, status, created_at) 
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (args.time, target_date, args.message, args.reason, now.isoformat())
        )
        
        result = {
            "status": "saved",
            "target_time": args.time,
            "target_date": target_date,
            "message_preview": args.message[:50],
            "reason": args.reason,
        }
    else:
        print(json.dumps({"error": "需要 --time 和 --message 参数，或 --skip"}))
        sys.exit(1)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
