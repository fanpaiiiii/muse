"""任务管理器 - 任务的增删改查和状态管理"""
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from core.database import query, execute, now_iso


class TaskManager:
    """任务全生命周期管理"""

    def add_task(self, content: str, source: str = "extracted",
                 priority: int = 5, due_time: str = None,
                 dedup_key: str = None, metadata: dict = None) -> int:
        """添加任务"""
        return execute(
            """INSERT INTO tasks (content, source, priority, due_time, dedup_key, metadata, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (content, source, priority, due_time, dedup_key, json.dumps(metadata or {}))
        )

    def get_task(self, task_id: int) -> Optional[Dict]:
        """获取单个任务"""
        rows = query("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return rows[0] if rows else None

    def get_pending_tasks(self, limit: int = 20) -> List[Dict]:
        """获取所有待处理任务"""
        return query(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY priority DESC, due_time ASC LIMIT ?",
            (limit,)
        )

    def get_overdue_tasks(self) -> List[Dict]:
        """获取逾期任务"""
        return query(
            "SELECT * FROM tasks WHERE status = 'pending' AND due_time < datetime('now') ORDER BY due_time ASC"
        )

    def get_upcoming_tasks(self, hours: int = 2) -> List[Dict]:
        """获取即将到期的任务"""
        cutoff = (datetime.now() + timedelta(hours=hours)).isoformat()
        return query(
            """SELECT * FROM tasks
               WHERE status = 'pending'
               AND due_time IS NOT NULL
               AND due_time <= ?
               AND due_time > datetime('now')
               ORDER BY due_time ASC""",
            (cutoff,)
        )

    def get_tasks_by_priority(self, min_priority: int = 7) -> List[Dict]:
        """获取高优先级任务"""
        return query(
            "SELECT * FROM tasks WHERE status = 'pending' AND priority >= ? ORDER BY priority DESC",
            (min_priority,)
        )

    def complete_task(self, task_id: int) -> bool:
        """完成任务"""
        result = execute(
            "UPDATE tasks SET status = 'completed', completed_at = datetime('now'), updated_at = datetime('now') WHERE id = ? AND status = 'pending'",
            (task_id,)
        )
        return result > 0

    def cancel_task(self, task_id: int) -> bool:
        """取消任务"""
        result = execute(
            "UPDATE tasks SET status = 'cancelled', updated_at = datetime('now') WHERE id = ? AND status IN ('pending', 'in_progress')",
            (task_id,)
        )
        return result > 0

    def update_task(self, task_id: int, **kwargs) -> bool:
        """更新任务属性"""
        allowed = {"content", "priority", "due_time", "status", "metadata"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        set_clauses = []
        values = []
        for k, v in updates.items():
            if k == "metadata":
                v = json.dumps(v)
            set_clauses.append(f"{k} = ?")
            values.append(v)

        set_clauses.append("updated_at = datetime('now')")
        values.append(task_id)

        sql = f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = ?"
        result = execute(sql, tuple(values))
        return result > 0

    def check_dedup(self, dedup_key: str, window_hours: int = 24) -> bool:
        """检查是否重复任务"""
        if not dedup_key:
            return False
        rows = query(
            "SELECT COUNT(*) as cnt FROM tasks WHERE dedup_key = ? AND extracted_at > datetime('now', ?)",
            (dedup_key, f"-{window_hours} hours")
        )
        return rows[0]["cnt"] > 0

    def get_task_stats(self) -> Dict:
        """获取任务统计"""
        rows = query(
            """SELECT status, COUNT(*) as cnt
               FROM tasks
               WHERE date(created_at) = date('now')
               GROUP BY status"""
        )
        stats = {"pending": 0, "in_progress": 0, "completed": 0, "cancelled": 0}
        for row in rows:
            stats[row["status"]] = row["cnt"]
        stats["overdue"] = len(self.get_overdue_tasks())
        return stats

    def cleanup_old_tasks(self, days: int = 30):
        """清理过期已完成/取消的任务"""
        execute(
            "DELETE FROM tasks WHERE status IN ('completed', 'cancelled') AND updated_at < datetime('now', ?)",
            (f"-{days} days",)
        )
