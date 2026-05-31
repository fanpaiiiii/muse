"""感知数据收集器 — 从各数据源聚合当前上下文

输出结构化 JSON，供 Tier 1 LLM 分析使用。
"""
import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.database import init_db, query, now_iso


def get_time_context():
    """时间上下文"""
    now = datetime.now()
    return {
        "timestamp": now.isoformat(),
        "hour": now.hour,
        "minute": now.minute,
        "day_of_week": now.strftime("%A"),
        "day_of_week_cn": ["周一","周二","周三","周四","周五","周六","周日"][now.weekday()],
        "is_weekend": now.weekday() >= 5,
        "date": now.strftime("%Y-%m-%d"),
    }


def get_user_activity():
    """用户活跃状态"""
    # 最后活跃时间
    rows = query(
        "SELECT created_at FROM behavior_log WHERE event_type IN ('message_received', 'message_sent') ORDER BY id DESC LIMIT 1"
    );
    last_active = rows[0]["created_at"] if rows else None
    minutes_since = None
    status = "unknown"
    
    if last_active:
        diff = (datetime.now() - datetime.fromisoformat(last_active)).total_seconds() / 60
        minutes_since = round(diff, 1)
        if diff < 5:
            status = "active"
        elif diff < 30:
            status = "recent"
        elif diff < 120:
            status = "idle"
        else:
            status = "away"
    
    # 今日消息统计
    today = datetime.now().strftime("%Y-%m-%d")
    msg_rows = query(
        "SELECT COUNT(*) as cnt FROM behavior_log WHERE DATE(created_at) = ? AND event_type IN ('message_received', 'message_sent')",
        (today,)
    );
    today_messages = msg_rows[0]["cnt"] if msg_rows else 0
    
    # 今日主动消息
    proactive_rows = query(
        "SELECT COUNT(*) as cnt FROM proactive_messages WHERE target_date = ? AND status = 'sent'",
        (today,)
    )
    today_proactive = proactive_rows[0]["cnt"] if proactive_rows else 0
    
    return {
        "last_active": last_active,
        "minutes_since_active": minutes_since,
        "status": status,
        "today_user_messages": today_messages,
        "today_proactive_messages": today_proactive,
    }


def get_recent_messages(limit=20):
    """最近的对话记录（从 activity_logs）"""
    rows = query(
        """SELECT event_type, content as text, created_at as time, source as role
           FROM behavior_log 
           WHERE event_type IN ('message_received', 'message_sent')
           ORDER BY id DESC LIMIT ?""",
        (limit,)
    )
    messages = []
    for row in reversed(rows):  # 按时间正序
        role = "user" if row["role"] == "message_received" else "assistant"
        messages.append({
            "role": role,
            "text": row["text"][:500] if row["text"] else "",
            "time": row["time"],
        })
    return messages


def get_tasks():
    """任务状态"""
    try:
        pending = query(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status IN ('pending', 'in_progress')"
        )
        overdue = query(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status IN ('pending', 'in_progress') AND due_time < datetime('now')"
        )
        completed_today = query(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'completed' AND DATE(completed_at) = DATE('now')"
        )
        
        # 最近的任务详情
        recent_tasks = query(
            """SELECT content as title, status, priority, due_time as due_date 
               FROM tasks 
               WHERE status IN ('pending', 'in_progress') 
               ORDER BY 
                 priority DESC,
                 due_time ASC
               LIMIT 5"""
        )
        
        return {
            "pending": pending[0]["cnt"] if pending else 0,
            "overdue": overdue[0]["cnt"] if overdue else 0,
            "completed_today": completed_today[0]["cnt"] if completed_today else 0,
            "upcoming": [
                {
                    "title": t["title"],
                    "status": t["status"],
                    "priority": t["priority"],
                    "due_date": t["due_date"],
                }
                for t in recent_tasks
            ],
        }
    except Exception:
        return {
            "pending": 0,
            "overdue": 0,
            "completed_today": 0,
            "upcoming": [],
        }


def get_proactive_history():
    """主动消息历史"""
    # 今日已发
    today = datetime.now().strftime("%Y-%m-%d")
    today_msgs = query(
        """SELECT target_time, message, reason, sent_at 
           FROM proactive_messages 
           WHERE target_date = ? AND status = 'sent'
           ORDER BY sent_at""",
        (today,)
    )
    
    # 最近7天统计
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    week_stats = query(
        """SELECT target_date, COUNT(*) as cnt 
           FROM proactive_messages 
           WHERE target_date >= ? AND status = 'sent'
           GROUP BY target_date ORDER BY target_date""",
        (week_ago,)
    )
    
    return {
        "today": [
            {"time": m["target_time"], "message": m["message"][:100], "reason": m["reason"]}
            for m in today_msgs
        ],
        "today_count": len(today_msgs),
        "week_stats": [
            {"date": s["target_date"], "count": s["cnt"]}
            for s in week_stats
        ],
    }


def collect_all():
    """收集全部感知数据"""
    time_ctx = get_time_context()
    activity = get_user_activity()
    messages = get_recent_messages()
    tasks = get_tasks()
    history = get_proactive_history()
    
    return {
        "time": time_ctx,
        "user_activity": activity,
        "recent_messages": messages,
        "tasks": tasks,
        "proactive_history": history,
    }


if __name__ == "__main__":
    init_db()
    data = collect_all()
    print(json.dumps(data, ensure_ascii=False, indent=2))
