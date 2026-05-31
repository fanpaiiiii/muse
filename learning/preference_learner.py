"""偏好学习器 - 从交互中学习用户偏好"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from core.database import query, execute, now_iso


class PreferenceLearner:
    """从用户交互中学习偏好"""

    # 偏好类别
    CATEGORIES = {
        "communication": ["回复长度", "语言偏好", "语气偏好"],
        "schedule": ["活跃时段", "休息时段", "工作节奏"],
        "task": ["任务类型偏好", "优先级判断", "提醒方式"],
        "topic": ["常聊话题", "关注领域", "兴趣点"],
    }

    def record_interaction(self, event_type: str, content: str = None,
                           platform: str = None, metadata: dict = None):
        """记录交互事件"""
        execute(
            """INSERT INTO behavior_log (event_type, source, content, metadata, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (event_type, platform, content, json.dumps(metadata or {}))
        )

    def record_conversation(self, role: str, content: str, platform: str = None,
                            session_id: str = None):
        """记录对话"""
        execute(
            """INSERT INTO conversation_history (role, content, platform, session_id, created_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (role, content, platform, session_id)
        )

    def update_preference(self, key: str, value: str, confidence: float = 0.5):
        """更新偏好"""
        execute(
            """INSERT INTO user_profile (key, value, confidence, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET
               value = excluded.value,
               confidence = MAX(confidence, excluded.confidence),
               updated_at = datetime('now')""",
            (key, value, confidence)
        )

    def get_preference(self, key: str) -> Optional[str]:
        """获取偏好值"""
        rows = query("SELECT value FROM user_profile WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def analyze_active_hours(self, days: int = 14) -> Dict:
        """分析活跃时段"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = query(
            """SELECT strftime('%H', created_at) as hour, COUNT(*) as cnt
               FROM behavior_log
               WHERE created_at > ? AND event_type = 'message_received'
               GROUP BY hour ORDER BY cnt DESC""",
            (cutoff,)
        )
        if not rows:
            return {"peak_hours": [], "quiet_hours": []}

        hours = [(int(r["hour"]), r["cnt"]) for r in rows]
        avg = sum(c for _, c in hours) / len(hours)

        peak = [h for h, c in hours if c > avg * 1.5]
        quiet = [h for h, c in hours if c < avg * 0.3]

        return {"peak_hours": sorted(peak), "quiet_hours": sorted(quiet)}

    def analyze_response_patterns(self, days: int = 14) -> Dict:
        """分析回复模式"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = query(
            """SELECT content FROM conversation_history
               WHERE role = 'user' AND created_at > ?""",
            (cutoff,)
        )
        if not rows:
            return {"avg_length": 0, "common_words": []}

        lengths = [len(r["content"]) for r in rows]
        avg_len = sum(lengths) / len(lengths) if lengths else 0

        return {
            "avg_length": avg_len,
            "total_messages": len(rows),
        }

    def learn_from_task_completion(self, task_id: int):
        """从任务完成中学习"""
        task = query("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not task:
            return

        task = task[0]
        if task.get("due_time") and task.get("completed_at"):
            due = datetime.fromisoformat(task["due_time"])
            completed = datetime.fromisoformat(task["completed_at"])
            # 提前/按时/逾期完成
            if completed <= due:
                self.update_preference("task_completion_pattern", "on_time", 0.7)
            else:
                self.update_preference("task_completion_pattern", "late", 0.7)

    def get_daily_summary(self) -> Dict:
        """获取今日交互摘要"""
        today = datetime.now().strftime("%Y-%m-%d")

        messages = query(
            "SELECT COUNT(*) as cnt FROM behavior_log WHERE date(created_at) = ? AND event_type = 'message_received'",
            (today,)
        )
        tasks_created = query(
            "SELECT COUNT(*) as cnt FROM tasks WHERE date(created_at) = ?",
            (today,)
        )
        tasks_completed = query(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'completed' AND date(completed_at) = ?",
            (today,)
        )
        proactive_sent = query(
            "SELECT COUNT(*) as cnt FROM proactive_log WHERE date(sent_at) = ? AND status = 'sent'",
            (today,)
        )

        return {
            "date": today,
            "messages_received": messages[0]["cnt"] if messages else 0,
            "tasks_created": tasks_created[0]["cnt"] if tasks_created else 0,
            "tasks_completed": tasks_completed[0]["cnt"] if tasks_completed else 0,
            "proactive_sent": proactive_sent[0]["cnt"] if proactive_sent else 0,
        }

    def get_learning_stats(self) -> Dict:
        """获取学习统计"""
        prefs = query("SELECT COUNT(*) as cnt FROM user_profile")
        behaviors = query(
            "SELECT COUNT(*) as cnt FROM behavior_log WHERE created_at > datetime('now', '-7 days')"
        )
        conversations = query(
            "SELECT COUNT(*) as cnt FROM conversation_history WHERE created_at > datetime('now', '-7 days')"
        )
        return {
            "preferences_count": prefs[0]["cnt"] if prefs else 0,
            "recent_behaviors": behaviors[0]["cnt"] if behaviors else 0,
            "recent_conversations": conversations[0]["cnt"] if conversations else 0,
        }
