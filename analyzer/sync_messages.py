#!/usr/bin/env python3
"""消息同步器 — 从 Hermes state.db 拉取对话到 Muse behavior_log

这是 Muse 的「耳朵」。没有它，感知层完全是瞎的。

用法:
    python sync_messages.py                # 同步最近1小时的消息
    python sync_messages.py --hours 24     # 同步最近24小时
    python sync_messages.py --full         # 全量同步（首次使用）
    python sync_messages.py --stats        # 查看同步统计
"""
import os
os.environ["TZ"] = "Asia/Shanghai"
try:
    import time
    time.tzset()
except (ImportError, AttributeError):
    pass

import json
import os
import sys
import sqlite3
import hashlib
from datetime import datetime, timedelta
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.database import init_db, query, execute, get_db_path

# Hermes 状态数据库路径
HERMES_STATE_DB = os.path.expanduser("~/.hermes/state.db")


def get_hermes_conn():
    """连接 Hermes 状态数据库"""
    if not os.path.exists(HERMES_STATE_DB):
        print(json.dumps({"error": f"Hermes state.db 不存在: {HERMES_STATE_DB}"}))
        sys.exit(1)
    conn = sqlite3.connect(HERMES_STATE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_last_sync_time():
    """获取上次同步时间"""
    rows = query(
        "SELECT content FROM behavior_log WHERE event_type = 'sync_marker' ORDER BY id DESC LIMIT 1"
    )
    if rows:
        try:
            return datetime.fromisoformat(rows[0]["content"])
        except (ValueError, TypeError):
            pass
    # 默认同步最近24小时
    return datetime.now() - timedelta(hours=24)


def save_sync_time(dt):
    """保存同步时间标记"""
    execute(
        """INSERT INTO behavior_log (event_type, source, content, metadata, created_at) 
           VALUES ('sync_marker', 'system', ?, '{}', datetime('now'))""",
        (dt.isoformat(),)
    )


def sync_messages(hours=1, full=False):
    """从 Hermes state.db 同步消息到 Muse behavior_log

    Returns:
        dict: {"synced": int, "skipped": int, "errors": int}
    """
    hermes_conn = get_hermes_conn()
    init_db()

    # 确定同步起始时间
    if full:
        start_time = 0  # 从最早开始
    else:
        last_sync = get_last_sync_time()
        start_time = last_sync.timestamp()

    # 从 Hermes 拉取用户和助手消息
    cursor = hermes_conn.cursor()
    cursor.execute(
        """SELECT id, session_id, role, content, timestamp 
           FROM messages 
           WHERE role IN ('user', 'assistant') 
             AND timestamp > ?
             AND content IS NOT NULL
             AND content != ''
           ORDER BY timestamp ASC""",
        (start_time,)
    )
    messages = cursor.fetchall()
    hermes_conn.close()

    synced = 0
    skipped = 0
    errors = 0
    last_timestamp = start_time

    for msg in messages:
        try:
            ts_float = msg["timestamp"]
            ts_dt = datetime.fromtimestamp(ts_float)
            ts_iso = ts_dt.isoformat()

            # 去重：检查是否已存在（通过内容哈希 + 时间）
            content_hash = hashlib.md5(
                (msg["content"][:200] + ts_iso).encode()
            ).hexdigest()

            existing = query(
                "SELECT id FROM behavior_log WHERE content LIKE ? AND created_at = ? LIMIT 1",
                (f"%{content_hash[:16]}%", ts_iso)
            )
            if existing:
                skipped += 1
                continue

            # 映射角色
            role = "message_received" if msg["role"] == "user" else "message_sent"
            source = "hermes_sync"

            # 截断过长内容
            content = msg["content"][:2000]

            execute(
                """INSERT INTO behavior_log 
                   (event_type, source, content, metadata, created_at) 
                   VALUES (?, ?, ?, ?, ?)""",
                (role, source, content, 
                 json.dumps({"hermes_msg_id": msg["id"], "session_id": msg["session_id"], "hash": content_hash[:16]}),
                 ts_iso)
            )
            synced += 1
            last_timestamp = max(last_timestamp, ts_float)

        except Exception as e:
            errors += 1

    # 保存同步时间戳
    if last_timestamp > start_time:
        save_sync_time(datetime.fromtimestamp(last_timestamp))

    result = {
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
        "total_fetched": len(messages),
        "sync_from": datetime.fromtimestamp(start_time).isoformat(),
        "sync_to": datetime.fromtimestamp(last_timestamp).isoformat() if last_timestamp > start_time else "no change",
    }

    return result


def get_stats():
    """同步统计"""
    init_db()

    total = query("SELECT COUNT(*) as cnt FROM behavior_log WHERE event_type != 'sync_marker'")
    today = query(
        "SELECT COUNT(*) as cnt FROM behavior_log WHERE DATE(created_at) = DATE('now') AND event_type != 'sync_marker'"
    )
    last_sync = query(
        "SELECT content FROM behavior_log WHERE event_type = 'sync_marker' ORDER BY id DESC LIMIT 1"
    )

    return {
        "total_records": total[0]["cnt"] if total else 0,
        "today_records": today[0]["cnt"] if today else 0,
        "last_sync": last_sync[0]["content"] if last_sync else "never",
    }


def detect_feedback():
    """检测用户对 Muse 主动消息的反馈
    
    逻辑：如果用户在 Muse 发送消息后 30 分钟内回复了，
    记录为「已回复」；否则记录为「已忽略」。
    """
    from analyzer.persona_state import record_proactive_response
    
    # 获取最近的 Muse 主动消息
    muse_msgs = query(
        """SELECT id, sent_at FROM proactive_messages 
           WHERE status = 'sent' AND sent_at IS NOT NULL
           ORDER BY sent_at DESC LIMIT 5"""
    )
    
    if not muse_msgs:
        return
    
    # 获取用户最近的消息
    user_msgs = query(
        """SELECT created_at FROM behavior_log 
           WHERE event_type = 'message_received'
           ORDER BY created_at DESC LIMIT 5"""
    )
    
    if not user_msgs:
        return
    
    # 检查每条 Muse 消息是否有用户回复
    for muse_msg in muse_msgs:
        muse_time = datetime.fromisoformat(muse_msg["sent_at"])
        msg_id = muse_msg["id"]
        
        # 检查用户是否在 30 分钟内回复
        responded = False
        for user_msg in user_msgs:
            user_time = datetime.fromisoformat(user_msg["created_at"])
            diff_minutes = (user_time - muse_time).total_seconds() / 60
            if 0 < diff_minutes <= 30:
                responded = True
                break
        
        # 记录反馈
        record_proactive_response(msg_id, responded)


def main():
    parser = argparse.ArgumentParser(description="Muse 消息同步器")
    parser.add_argument("--hours", type=int, default=1, help="同步最近N小时")
    parser.add_argument("--full", action="store_true", help="全量同步")
    parser.add_argument("--stats", action="store_true", help="查看统计")
    args = parser.parse_args()

    if args.stats:
        result = get_stats()
    else:
        result = sync_messages(hours=args.hours, full=args.full)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
