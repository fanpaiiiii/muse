"""状态锁 - 防止对话打断"""
import json
from datetime import datetime, timedelta
from typing import Optional

from core.database import query, execute, now_iso


class StateLock:
    """分布式状态锁，防止多个 Cron Job 同时发送消息"""

    def __init__(self, lock_timeout_minutes: int = 10):
        self.lock_timeout = lock_timeout_minutes

    def acquire(self, node_id: str, reason: str = "") -> bool:
        """获取锁"""
        # 检查是否有未过期的锁
        existing = query(
            """SELECT * FROM state_lock WHERE expires_at > datetime('now') AND id = 1"""
        )
        if existing:
            return False  # 已被锁定

        # 清理过期锁并插入新锁
        execute("DELETE FROM state_lock WHERE id = 1")
        execute(
            """INSERT INTO state_lock (id, locked_by, locked_at, expires_at, reason)
               VALUES (1, ?, datetime('now'), datetime('now', ?), ?)""",
            (node_id, f"+{self.lock_timeout} minutes", reason)
        )
        return True

    def release(self, node_id: str = None):
        """释放锁"""
        if node_id:
            execute("DELETE FROM state_lock WHERE id = 1 AND locked_by = ?", (node_id,))
        else:
            execute("DELETE FROM state_lock WHERE id = 1")

    def is_locked(self) -> bool:
        """检查是否被锁定"""
        rows = query(
            "SELECT * FROM state_lock WHERE id = 1 AND expires_at > datetime('now')"
        )
        return len(rows) > 0

    def get_lock_info(self) -> Optional[dict]:
        """获取锁信息"""
        rows = query(
            "SELECT * FROM state_lock WHERE id = 1 AND expires_at > datetime('now')"
        )
        return dict(rows[0]) if rows else None
