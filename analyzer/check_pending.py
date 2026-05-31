#!/usr/bin/env python3
"""Tier 2 调度器 — 检查到期的主动消息

供 Tier 2 Cron Job 调用（每5分钟）。
输出到期的消息列表，Agent 通过 send_message 发送。

用法:
    python check_pending.py              # 检查并输出到期消息
    python check_pending.py --mark-sent ID  # 标记消息已发送
    python check_pending.py --mark-cancel ID # 标记消息取消
    python check_pending.py --stats      # 输出统计信息
"""
import json
import sys
import os
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.database import init_db, query, execute


def check_due_messages():
    """检查当前到期的 pending 消息"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")
    
    # 查找今天到期且状态为 pending 的消息
    # 允许5分钟的窗口（当前时间 ± 5分钟）
    rows = query(
        """SELECT id, target_time, target_date, message, reason, created_at 
           FROM proactive_messages 
           WHERE status = 'pending' 
             AND target_date = ?
             AND target_time <= ?
           ORDER BY target_time""",
        (today, current_time)
    )
    
    due = []
    for row in rows:
        # 检查是否在5分钟窗口内
        target_dt = datetime.strptime(f"{row['target_date']} {row['target_time']}", "%Y-%m-%d %H:%M")
        diff_minutes = (now - target_dt).total_seconds() / 60
        
        if diff_minutes <= 5:
            due.append({
                "id": row["id"],
                "target_time": row["target_time"],
                "message": row["message"],
                "reason": row["reason"],
                "delay_minutes": round(diff_minutes, 1),
            })
    
    return due


def mark_sent(message_id):
    """标记消息已发送"""
    now = datetime.now().isoformat()
    execute(
        "UPDATE proactive_messages SET status = 'sent', sent_at = ? WHERE id = ?",
        (now, message_id)
    )
    return {"id": message_id, "status": "sent", "sent_at": now}


def mark_cancelled(message_id):
    """标记消息已取消"""
    execute(
        "UPDATE proactive_messages SET status = 'cancelled' WHERE id = ?",
        (message_id,)
    )
    return {"id": message_id, "status": "cancelled"}


def get_stats():
    """获取统计信息"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    sent_today = query(
        "SELECT COUNT(*) as cnt FROM proactive_messages WHERE target_date = ? AND status = 'sent'",
        (today,)
    )
    pending_today = query(
        "SELECT COUNT(*) as cnt FROM proactive_messages WHERE target_date = ? AND status = 'pending'",
        (today,)
    )
    skipped_today = query(
        "SELECT COUNT(*) as cnt FROM proactive_messages WHERE target_date = ? AND status = 'skipped'",
        (today,)
    )
    
    # 最近7天
    week_ago = (datetime.now() - __import__('datetime').timedelta(days=7)).strftime("%Y-%m-%d")
    week_stats = query(
        """SELECT target_date, status, COUNT(*) as cnt 
           FROM proactive_messages 
           WHERE target_date >= ?
           GROUP BY target_date, status
           ORDER BY target_date""",
        (week_ago,)
    )
    
    return {
        "today": {
            "sent": sent_today[0]["cnt"] if sent_today else 0,
            "pending": pending_today[0]["cnt"] if pending_today else 0,
            "skipped": skipped_today[0]["cnt"] if skipped_today else 0,
        },
        "week": [
            {"date": s["target_date"], "status": s["status"], "count": s["cnt"]}
            for s in week_stats
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Tier 2 调度器")
    parser.add_argument("--mark-sent", type=int, help="标记消息 ID 已发送")
    parser.add_argument("--mark-cancel", type=int, help="标记消息 ID 已取消")
    parser.add_argument("--stats", action="store_true", help="输出统计")
    args = parser.parse_args()
    
    init_db()
    
    if args.mark_sent:
        result = mark_sent(args.mark_sent)
    elif args.mark_cancel:
        result = mark_cancelled(args.mark_cancel)
    elif args.stats:
        result = get_stats()
    else:
        due = check_due_messages()
        result = {
            "due_count": len(due),
            "due_messages": due,
            "current_time": datetime.now().strftime("%H:%M"),
        }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
