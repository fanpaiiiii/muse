"""核心引擎 - 协调所有模块的中央控制器"""
import json
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from core.config_loader import get_config
from core.database import init_db, query, execute, now_iso
from perception.task_extractor import TaskExtractor
from perception.activity_analyzer import ActivityAnalyzer
from task.task_manager import TaskManager
from personality.system_prompt import PersonalityManager
from personality.personality_manager import CharacterPersonality
from scheduler.node_scheduler import NodeScheduler
from delivery.message_deliverer import MessageDeliverer
from learning.preference_learner import PreferenceLearner


class ProactiveEngine:
    """主动对话核心引擎"""

    def __init__(self, personality_style: str = None, character_id: str = "sparkle"):
        # 初始化数据库
        init_db()

        # 加载配置
        style = personality_style or get_config("personality.style", "calm_witty")

        # 初始化所有模块
        self.personality = CharacterPersonality(character_id)
        self.task_extractor = TaskExtractor(
            get_config("perception.task_keywords", [])
        )
        self.activity = ActivityAnalyzer(
            active_threshold=get_config("perception.activity.active_threshold_minutes", 5),
            idle_threshold=get_config("perception.activity.idle_threshold_minutes", 120),
        )
        self.task_manager = TaskManager()
        self.scheduler = NodeScheduler()
        self.deliverer = MessageDeliverer()
        self.learner = PreferenceLearner()

    # === 感知接口 ===

    def process_message(self, text: str, platform: str = None,
                        session_id: str = None) -> Dict:
        """处理收到的消息 - 提取任务 + 记录行为"""
        result = {
            "tasks_extracted": [],
            "event_recorded": True,
        }

        # 记录行为
        self.activity.record_event("message_received", platform, text)

        # 记录对话
        self.learner.record_conversation("user", text, platform, session_id)

        # 提取任务
        tasks = self.task_extractor.extract_tasks(text)
        for task in tasks:
            dedup_key = self.task_extractor.generate_dedup_key(task)
            if not self.task_manager.check_dedup(dedup_key):
                task_id = self.task_manager.add_task(
                    content=task["content"],
                    source=task["source"],
                    priority=task["priority"],
                    due_time=task.get("due_time"),
                    dedup_key=dedup_key,
                )
                result["tasks_extracted"].append({"id": task_id, **task})

        return result

    # === 判断接口 ===

    def analyze_node(self, node_id: str) -> Dict:
        """分析节点是否应该触发"""
        return self.scheduler.analyze_node(node_id)

    def get_context(self) -> Dict:
        """获取当前完整上下文"""
        activity_ctx = self.activity.get_activity_context()
        task_stats = self.task_manager.get_task_stats()
        overdue = self.task_manager.get_overdue_tasks()
        upcoming = self.task_manager.get_upcoming_tasks(hours=2)
        high_priority = self.task_manager.get_tasks_by_priority(min_priority=7)

        return {
            "activity": activity_ctx,
            "task_stats": task_stats,
            "overdue_tasks": overdue,
            "upcoming_tasks": upcoming,
            "high_priority_tasks": high_priority,
            "now": now_iso(),
        }

    # === 行动接口 ===

    def generate_proactive_message(self, node_id: str) -> Optional[str]:
        """为指定节点生成主动消息"""
        context = self.get_context()
        activity_ctx = context["activity"]

        # 检查是否应该发送
        if not self.personality.should_deliver(activity_ctx):
            return None

        node_info = self.scheduler.nodes.get(node_id, {})
        node_type = node_info.get("type", "unknown")

        message = None

        if node_type == "task_reminder":
            message = self._generate_task_reminder(context)
        elif node_type == "summary":
            message = self._generate_summary(context)
        elif node_type == "memory_recall":
            message = self._generate_morning_brief(context)
        elif node_type == "wellness":
            message = self._generate_wellness_check(context)
        elif node_type == "social":
            message = self._generate_social(context)
        elif node_type == "reflection":
            message = self._generate_reflection(context)

        return message

    def _generate_task_reminder(self, context: dict) -> Optional[str]:
        """生成任务提醒"""
        overdue = context.get("overdue_tasks", [])
        upcoming = context.get("upcoming_tasks", [])
        high_p = context.get("high_priority_tasks", [])

        if overdue:
            task = overdue[0]
            time_info = "已逾期"
            return self.personality.get_task_reminder(task["content"], time_info)

        if upcoming:
            task = upcoming[0]
            due = datetime.fromisoformat(task["due_time"])
            delta = due - datetime.now()
            hours = delta.total_seconds() / 3600
            if hours < 1:
                time_info = f"还有{int(delta.total_seconds()/60)}分钟"
            else:
                time_info = f"还有{int(hours)}小时"
            return self.personality.get_task_reminder(task["content"], time_info)

        if high_p:
            task = high_p[0]
            return self.personality.get_task_reminder(task["content"], "优先处理")

        return None

    def _generate_summary(self, context: dict) -> str:
        """生成工作汇总"""
        stats = context.get("task_stats", {})
        return self.personality.get_summary(
            stats.get("completed", 0),
            stats.get("pending", 0)
        )

    def _generate_morning_brief(self, context: dict) -> str:
        """生成早间简报"""
        stats = context.get("task_stats", {})
        pending = stats.get("pending", 0)
        overdue = stats.get("overdue", 0)
        return self.personality.get_greeting(pending, overdue)

    def _generate_wellness_check(self, context: dict) -> Optional[str]:
        """生成休息提醒"""
        # 分析连续活跃时间
        recent_events = query(
            """SELECT created_at FROM behavior_log
               WHERE event_type = 'message_received'
               ORDER BY created_at DESC LIMIT 10"""
        )
        if len(recent_events) < 5:
            return None

        # 检查最近消息时间跨度
        first = datetime.fromisoformat(recent_events[-1]["created_at"])
        last = datetime.fromisoformat(recent_events[0]["created_at"])
        span_minutes = (last - first).total_seconds() / 60

        if span_minutes > 120:  # 连续活跃超过2小时
            return self.personality.get_wellness_check()

        return None

    def _generate_social(self, context: dict) -> Optional[str]:
        """生成社交互动"""
        # 花火风格：随机想聊天
        if random.random() < 0.6:  # 60% 概率发消息
            return self.personality.get_social_message()
        return None

    def _generate_reflection(self, context: dict) -> str:
        """生成晚间回顾"""
        summary = self.learner.get_daily_summary()
        return self.personality.get_evening_reflection(summary.get("tasks_completed", 0))

    # === 投递接口 ===

    def send_proactive(self, node_id: str, message: str, platform: str = "telegram") -> Dict:
        """发送主动消息"""
        # 记录
        log_id = self.deliverer.record_proactive(node_id, message, "sent")

        # 去重记录
        dedup_key = f"msg_{node_id}_{datetime.now().strftime('%Y%m%d%H%M')}"
        self.scheduler.dedup.record(dedup_key, "proactive")

        # 投递
        result = self.deliverer.deliver_with_retry("", message, platform)

        # 释放锁
        self.scheduler.release_lock(node_id)

        return {"log_id": log_id, "delivery": result}

    def process_node(self, node_id: str) -> Dict:
        """完整节点处理流程"""
        # 1. 分析是否触发
        triggered, reason, context = self.scheduler.execute_node_analysis(node_id)
        if not triggered:
            return {"triggered": False, "reason": reason}

        try:
            # 2. 生成消息
            message = self.generate_proactive_message(node_id)
            if not message:
                return {"triggered": True, "generated": False, "reason": "无需发送"}

            # 3. 发送
            result = self.send_proactive(node_id, message)

            return {
                "triggered": True,
                "generated": True,
                "message": message,
                "result": result,
            }
        finally:
            # 4. 释放锁
            self.scheduler.release_lock(node_id)

    # === 管理接口 ===

    def get_stats(self) -> Dict:
        """获取系统完整统计"""
        return {
            "tasks": self.task_manager.get_task_stats(),
            "delivery": self.deliverer.get_today_stats(),
            "learning": self.learner.get_learning_stats(),
            "activity": self.activity.get_activity_context(),
            "daily_summary": self.learner.get_daily_summary(),
        }
