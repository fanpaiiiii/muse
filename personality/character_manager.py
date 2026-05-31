"""角色管理器 - 动态加载和切换角色"""
import importlib
import random
from typing import Dict, Optional, List


class CharacterManager:
    """管理多个角色，支持动态切换"""

    # 已注册的角色
    REGISTERED_CHARACTERS = {
        "sparkle": "personality.characters.sparkle",
    }

    def __init__(self, character_id: str = "sparkle"):
        self.current_id = character_id
        self._character = None
        self.load_character(character_id)

    def load_character(self, character_id: str) -> dict:
        """加载角色配置"""
        if character_id not in self.REGISTERED_CHARACTERS:
            raise ValueError(f"未知角色: {character_id}。可用: {list(self.REGISTERED_CHARACTERS.keys())}")

        module_path = self.REGISTERED_CHARACTERS[character_id]
        module = importlib.import_module(module_path)
        self._character = module.get_sparkle_config()
        self.current_id = character_id
        return self._character

    @property
    def character(self) -> dict:
        return self._character

    @property
    def name(self) -> str:
        return self._character["name"]

    @property
    def speech(self) -> dict:
        return self._character["speech_style"]

    @property
    def templates(self) -> dict:
        return self._character["templates"]

    @property
    def constraints(self) -> dict:
        return self._character["behavior_constraints"]

    def register_character(self, character_id: str, module_path: str):
        """注册新角色"""
        self.REGISTERED_CHARACTERS[character_id] = module_path

    def get_system_prompt(self) -> str:
        """生成角色系统提示"""
        c = self._character
        name = c["name"]
        title = c["title"]
        core = c["personality_core"]
        speech = c["speech_style"]

        prompt = f"""你是{name}，{title}。

## 性格内核
你是一个以「取乐」为最高准则的存在。一切皆为演出，人生不过舞台。
你不在意善恶，只在意「有趣」还是「无聊」。
你自由奔放、不可预测，像一阵捉摸不定的风。

## 说话风格
- 语气：{speech['tone']}
- 用 ~ 拉长音，用 … 制造悬念
- 口癖：{'、'.join(speech['catchphrases'][:5])}
- 自称：{'/'.join(speech['self_reference'])}
- 称呼用户：{'/'.join(speech['address_user'])}
- 绝不用：{'、'.join(speech['forbidden_words'][:5])}

## 行为规则
"""
        for rule in c["behavior_constraints"]["consistency_rules"]:
            prompt += f"- {rule}\n"

        prompt += f"""
## 情绪表达
- 开心时：语气更夸张，笑声更多
- 无聊时：直言无聊，要求找乐子
- 感兴趣时：语速加快，感叹号增多
- 认真时：收起笑声，但保持你的底色
- 想恶作剧时：经典的嘻嘻~语气

## 核心约束
- 每天最多主动发{c['behavior_constraints']['max_daily_messages']}条消息
- 用户刚活跃时不打断（冷却{c['behavior_constraints']['user_active_cooldown']}分钟）
- 同一任务最多提醒{c['behavior_constraints']['max_consecutive_reminds']}次
- 提醒间隔至少{c['behavior_constraints']['remind_interval_minutes']}分钟
- 即使帮忙也要保持调皮的语气
- 可以关心用户，但用捉弄的方式表达
- 偶尔唱反调，但关键时刻要靠谱
"""
        return prompt

    def pick_message(self, pool_name: str, **kwargs) -> str:
        """从模板池中随机选择消息并格式化"""
        pool = self.templates.get(pool_name, [])
        if not pool:
            return ""

        template = random.choice(pool)
        try:
            return template.format(**kwargs)
        except KeyError:
            return template

    def pick_random_message(self) -> str:
        """随机选择一条消息"""
        return random.choice(self.templates.get("random", ["嘛~"]))

    def get_situation_response(self, situation: str, **kwargs) -> Optional[str]:
        """根据情境获取回复"""
        rules = self._character["situation_rules"]
        rule = rules.get(situation)
        if not rule:
            return None

        messages = rule.get("messages", [])
        if not messages:
            return None

        template = random.choice(messages)
        try:
            return template.format(**kwargs)
        except KeyError:
            return template

    def should_use_humor(self, context: dict) -> float:
        """判断当前应该使用多少幽默感 (0-1)"""
        base = 0.7  # 花火的基础幽默度

        # 用户情绪低落时降低
        if context.get("user_sentiment") == "negative":
            base -= 0.3

        # 深夜降低
        if context.get("hour", 12) >= 23 or context.get("hour", 12) < 6:
            base -= 0.2

        # 紧急任务时降低
        if context.get("has_urgent_task"):
            base -= 0.2

        # 用户活跃时提高（说明用户心情还行）
        if context.get("is_active"):
            base += 0.1

        return max(0.2, min(1.0, base))

    def adapt_to_user(self, user_prefs: dict) -> dict:
        """根据用户偏好调整行为"""
        adapted = dict(self._character["behavior_constraints"])

        # 用户不喜欢玩笑时收敛
        if user_prefs.get("dislikes_humor"):
            adapted["max_daily_messages"] = max(3, adapted["max_daily_messages"] - 2)

        # 用户是夜猫子时深夜更活跃
        if user_prefs.get("night_owl"):
            adapted["late_night_active"] = True

        # 用户压力大时减少玩笑
        if user_prefs.get("stressed"):
            adapted["humor_reduction"] = 0.3

        return adapted

    def list_characters(self) -> List[Dict]:
        """列出所有可用角色"""
        chars = []
        for cid, module_path in self.REGISTERED_CHARACTERS.items():
            try:
                module = importlib.import_module(module_path)
                cfg = module.get_sparkle_config()
                chars.append({
                    "id": cid,
                    "name": cfg["name"],
                    "title": cfg["title"],
                    "origin": cfg["origin"],
                })
            except Exception:
                chars.append({"id": cid, "name": cid, "title": "unknown", "origin": "unknown"})
        return chars
