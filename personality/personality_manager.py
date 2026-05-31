"""人格管理器 - 整合角色系统，为引擎提供统一接口"""
import random
from datetime import datetime
from typing import Optional, Dict

from personality.character_manager import CharacterManager
from personality.system_prompt import PersonalityManager as BasePersonalityManager


class CharacterPersonality:
    """基于角色的人格管理器 - 替代原有的模板化人格"""

    def __init__(self, character_id: str = "sparkle"):
        self.char_manager = CharacterManager(character_id)
        self.base = BasePersonalityManager("calm_witty")  # 保留作为 fallback

    @property
    def name(self) -> str:
        return self.char_manager.name

    def get_system_prompt(self) -> str:
        """获取角色系统提示"""
        return self.char_manager.get_system_prompt()

    def get_greeting(self, task_count: int = 0, urgent_count: int = 0) -> str:
        """生成问候语"""
        return self.char_manager.pick_message("morning",
            task_count=task_count, urgent_count=urgent_count)

    def get_task_reminder(self, task_content: str, time_info: str) -> str:
        """生成任务提醒"""
        return self.char_manager.pick_message("task_reminder",
            task_content=task_content, time_info=time_info)

    def get_summary(self, completed_count: int, remaining_count: int) -> str:
        """生成工作汇总"""
        total = completed_count + remaining_count
        score = min(10, max(1, int(completed_count / max(total, 1) * 10))) if total > 0 else 5
        return self.char_manager.pick_message("summary",
            completed_count=completed_count,
            remaining_count=remaining_count,
            total=total,
            score=score)

    def get_wellness_check(self) -> str:
        """生成休息提醒"""
        return random.choice(self.char_manager.templates.get("wellness", ["休息一下~"]))

    def get_evening_reflection(self, completed_count: int = 0) -> str:
        """生成晚间回顾"""
        return self.char_manager.pick_message("evening",
            completed_count=completed_count)

    def get_social_message(self) -> str:
        """生成社交消息"""
        return random.choice(self.char_manager.templates.get("social", ["嘛~"]))

    def get_random_message(self) -> str:
        """随机消息"""
        return self.char_manager.pick_random_message()

    def get_situation_response(self, situation: str, **kwargs) -> Optional[str]:
        """情境回复"""
        return self.char_manager.get_situation_response(situation, **kwargs)

    def should_deliver(self, context: dict) -> bool:
        """判断是否应该发送消息"""
        constraints = self.char_manager.constraints

        # 用户活跃冷却
        minutes_since_active = context.get("minutes_since_active", 999)
        if minutes_since_active < constraints.get("user_active_cooldown", 3):
            return False

        # 每日上限
        today_count = context.get("today_proactive_count", 0)
        max_daily = constraints.get("max_daily_messages", 6)
        if today_count >= max_daily:
            return False

        return True

    def get_humor_level(self, context: dict) -> float:
        """获取当前幽默度"""
        return self.char_manager.should_use_humor(context)

    def adapt_to_user(self, user_prefs: dict) -> dict:
        """根据用户偏好调整"""
        return self.char_manager.adapt_to_user(user_prefs)

    def check_remind_cooldown(self, task_id: int, remind_count: int) -> bool:
        """检查任务提醒冷却"""
        constraints = self.char_manager.constraints
        max_reminds = constraints.get("max_consecutive_reminds", 2)
        return remind_count < max_reminds
