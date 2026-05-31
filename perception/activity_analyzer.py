"""活动分析器 - 分析用户活跃度和对话模式"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from core.database import query, now_iso


class ActivityAnalyzer:
    """分析用户活动模式"""

    def __init__(self, active_threshold: int = 5, idle_threshold: int = 120):
        """
        Args:
            active_threshold: 最近N分钟内有消息视为活跃
            idle_threshold: N分钟无消息视为空闲
        """
        self.active_threshold = active_threshold
        self.idle_threshold = idle_threshold

    def is_user_active(self) -> bool:
        """用户当前是否活跃"""
        last_event = query(
            "SELECT created_at FROM behavior_log ORDER BY created_at DESC LIMIT 1"
        )
        if not last_event:
            return False

        last_time = datetime.fromisoformat(last_event[0]["created_at"])
        minutes_ago = (datetime.now() - last_time).total_seconds() / 60
        return minutes_ago < self.active_threshold

    def get_minutes_since_active(self) -> float:
        """距离上次活跃的分钟数"""
        last_event = query(
            "SELECT created_at FROM behavior_log ORDER BY created_at DESC LIMIT 1"
        )
        if not last_event:
            return 999.0
        last_time = datetime.fromisoformat(last_event[0]["created_at"])
        return (datetime.now() - last_time).total_seconds() / 60

    def get_activity_context(self) -> Dict:
        """获取当前活动上下文"""
        minutes_since = self.get_minutes_since_active()
        today_proactive = query(
            "SELECT COUNT(*) as cnt FROM proactive_log WHERE date(created_at) = date('now') AND status = 'sent'"
        )
        today_completed = query(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'completed' AND date(completed_at) = date('now')"
        )

        return {
            "minutes_since_active": minutes_since,
            "is_active": minutes_since < self.active_threshold,
            "is_idle": minutes_since > self.idle_threshold,
            "today_proactive_count": today_proactive[0]["cnt"] if today_proactive else 0,
            "today_completed_count": today_completed[0]["cnt"] if today_completed else 0,
        }

    def get_active_hours(self, days: int = 7) -> Dict:
        """分析过去N天的活跃时段"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = query(
            """SELECT strftime('%H', created_at) as hour, COUNT(*) as cnt
               FROM behavior_log
               WHERE created_at > ? AND event_type = 'message_received'
               GROUP BY hour ORDER BY cnt DESC""",
            (cutoff,)
        )
        return {row["hour"]: row["cnt"] for row in rows}

    def get_conversation_frequency(self, days: int = 7) -> Dict:
        """分析对话频率"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = query(
            """SELECT date(created_at) as day, COUNT(*) as cnt
               FROM behavior_log
               WHERE created_at > ? AND event_type = 'message_received'
               GROUP BY day ORDER BY day""",
            (cutoff,)
        )
        return {row["day"]: row["cnt"] for row in rows}

    def record_event(self, event_type: str, source: str = None, content: str = None, metadata: dict = None):
        """记录行为事件"""
        from core.database import execute
        execute(
            """INSERT INTO behavior_log (event_type, source, content, metadata)
               VALUES (?, ?, ?, ?)""",
            (event_type, source, content, json.dumps(metadata or {}))
        )

    def get_user_preferences(self) -> Dict:
        """从 user_profile 表读取用户偏好"""
        rows = query("SELECT key, value, confidence FROM user_profile ORDER BY confidence DESC")
        return {row["key"]: {"value": row["value"], "confidence": row["confidence"]} for row in rows}

    def update_user_preference(self, key: str, value: str, confidence: float = 0.5):
        """更新用户偏好"""
        from core.database import execute
        execute(
            """INSERT INTO user_profile (key, value, confidence, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET
               value = excluded.value,
               confidence = MAX(confidence, excluded.confidence),
               updated_at = datetime('now')""",
            (key, value, confidence)
        )
