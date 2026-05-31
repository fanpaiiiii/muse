"""消息投递器 - 带重试的消息发送"""
import json
import time
from datetime import datetime
from typing import Dict, Optional

from core.database import query, execute, now_iso
from core.config_loader import get_config


class MessageDeliverer:
    """消息投递器 - 管理消息队列和投递"""

    def __init__(self):
        self.max_retries = get_config("delivery.max_retries", 3)
        self.retry_delay = get_config("delivery.retry_delay_seconds", 30)

    def queue_message(self, target: str, message: str, priority: int = 5,
                      scheduled_at: str = None) -> int:
        """加入消息队列"""
        return execute(
            """INSERT INTO message_queue (target, message, priority, scheduled_at, status)
               VALUES (?, ?, ?, ?, 'queued')""",
            (target, message, priority, scheduled_at)
        )

    def get_pending_messages(self, limit: int = 10) -> list:
        """获取待发送消息"""
        return query(
            """SELECT * FROM message_queue
               WHERE status = 'queued'
               AND (scheduled_at IS NULL OR scheduled_at <= datetime('now'))
               ORDER BY priority DESC, created_at ASC
               LIMIT ?""",
            (limit,)
        )

    def mark_sending(self, msg_id: int):
        """标记为发送中"""
        execute("UPDATE message_queue SET status = 'sending' WHERE id = ?", (msg_id,))

    def mark_sent(self, msg_id: int):
        """标记为已发送"""
        execute(
            "UPDATE message_queue SET status = 'sent', sent_at = datetime('now') WHERE id = ?",
            (msg_id,)
        )

    def mark_failed(self, msg_id: int):
        """标记为失败并检查是否需要重试"""
        row = query("SELECT retry_count, max_retries FROM message_queue WHERE id = ?", (msg_id,))
        if not row:
            return

        retry_count = row[0]["retry_count"] + 1
        if retry_count >= row[0]["max_retries"]:
            execute(
                "UPDATE message_queue SET status = 'failed', retry_count = ? WHERE id = ?",
                (retry_count, msg_id)
            )
        else:
            execute(
                "UPDATE message_queue SET status = 'queued', retry_count = ? WHERE id = ?",
                (retry_count, msg_id)
            )

    def deliver_message(self, target: str, message: str, platform: str = "telegram") -> bool:
        """直接发送消息（同步）"""
        # 记录到 proactive_log
        log_id = execute(
            """INSERT INTO proactive_log (node_id, message, status, platform, sent_at)
               VALUES ('direct', ?, 'sent', ?, datetime('now'))""",
            (message, platform)
        )

        # 实际发送（这里只做记录，真正发送由外部集成层完成）
        # 在独立运行模式下，将消息写入 stdout 供外部读取
        print(f"[DELIVER:{platform}] {message}")
        return True

    def deliver_with_retry(self, target: str, message: str, platform: str = "telegram") -> Dict:
        """带重试的发送"""
        msg_id = self.queue_message(target, message)
        last_error = None

        for attempt in range(self.max_retries):
            self.mark_sending(msg_id)
            try:
                success = self.deliver_message(target, message, platform)
                if success:
                    self.mark_sent(msg_id)
                    return {"success": True, "msg_id": msg_id, "attempts": attempt + 1}
            except Exception as e:
                last_error = str(e)

            self.mark_failed(msg_id)
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)

        return {"success": False, "msg_id": msg_id, "error": last_error, "attempts": self.max_retries}

    def record_proactive(self, node_id: str, message: str, status: str = "sent") -> int:
        """记录主动消息"""
        return execute(
            """INSERT INTO proactive_log (node_id, message, status, platform, sent_at)
               VALUES (?, ?, ?, 'system', datetime('now'))""",
            (node_id, message, status)
        )

    def get_today_stats(self) -> Dict:
        """获取今日投递统计"""
        rows = query(
            """SELECT status, COUNT(*) as cnt
               FROM message_queue
               WHERE date(created_at) = date('now')
               GROUP BY status"""
        )
        stats = {"queued": 0, "sending": 0, "sent": 0, "failed": 0}
        for row in rows:
            stats[row["status"]] = row["cnt"]
        return stats

    def cleanup_old_messages(self, days: int = 7):
        """清理旧消息"""
        execute(
            "DELETE FROM message_queue WHERE status IN ('sent', 'failed') AND created_at < datetime('now', ?)",
            (f"-{days} days",)
        )
