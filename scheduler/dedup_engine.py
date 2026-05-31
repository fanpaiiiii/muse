"""去重引擎 - 防止重复消息和任务"""
from datetime import datetime
from typing import Optional

from core.database import query, execute, now_iso


class DedupEngine:
    """消息和任务去重"""

    def __init__(self, window_hours: int = 24):
        self.window_hours = window_hours

    def is_duplicate(self, key: str, action_type: str = "proactive") -> bool:
        """检查是否重复"""
        if not key:
            return False
        rows = query(
            """SELECT COUNT(*) as cnt FROM dedup_log
               WHERE key = ? AND action_type = ?
               AND created_at > datetime('now', ?)""",
            (key, action_type, f"-{self.window_hours} hours")
        )
        return rows[0]["cnt"] > 0

    def record(self, key: str, action_type: str = "proactive"):
        """记录已执行的操作"""
        execute(
            "INSERT INTO dedup_log (key, action_type, created_at) VALUES (?, ?, datetime('now'))",
            (key, action_type)
        )

    def check_and_record(self, key: str, action_type: str = "proactive") -> bool:
        """检查并记录（原子操作）"""
        if self.is_duplicate(key, action_type):
            return True  # 是重复
        self.record(key, action_type)
        return False  # 不是重复

    def cleanup(self, days: int = 7):
        """清理过期记录"""
        execute(
            "DELETE FROM dedup_log WHERE created_at < datetime('now', ?)",
            (f"-{days} days",)
        )

    def get_stats(self) -> dict:
        """获取去重统计"""
        rows = query(
            """SELECT action_type, COUNT(*) as cnt
               FROM dedup_log
               WHERE created_at > datetime('now', '-24 hours')
               GROUP BY action_type"""
        )
        return {row["action_type"]: row["cnt"] for row in rows}
