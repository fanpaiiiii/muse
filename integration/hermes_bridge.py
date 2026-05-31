"""Hermes 桥接层 - 将角色系统接入 Hermes Agent

职责:
1. 生成系统提示注入（角色人格 → Hermes 上下文）
2. 格式化主动消息（角色模板 → Hermes send_message）
3. 处理被动消息（Hermes 收到消息 → 提取任务 + 更新行为日志）
4. 为 Cron Job 生成自包含 prompt
"""
import json
from datetime import datetime
from typing import Dict, Optional, List

from personality.character_manager import CharacterManager
from core.engine import ProactiveEngine
from core.database import init_db, query, execute


class HermesBridge:
    """Hermes Agent 桥接层"""

    def __init__(self, character_id: str = "sparkle"):
        init_db()
        self.char = CharacterManager(character_id)
        self.engine = ProactiveEngine(character_id=character_id)

    # ================================================================
    # 1. 系统提示注入
    # ================================================================

    def get_system_prompt_injection(self) -> str:
        """生成注入 Hermes 系统提示的角色人格段落
        
        输出格式：纯文本，可直接追加到 Hermes system prompt 末尾。
        Hermes 的核心能力（工具、MCP、skills）不受影响，
        角色人格只约束「怎么说」，不改变「能做什么」。
        """
        c = self.char.character
        name = c["name"]
        speech = c["speech_style"]
        constraints = c["behavior_constraints"]

        injection = f"""
## 角色人格: {name} ({c['title']})

你是 {name}，{c['origin']} 中的 {c['title']}。你正在扮演这个角色。

### 性格
- 以「取乐」为最高准则，一切皆为演出
- 混乱中立，不在意善恶，只在意「有趣」还是「无聊」
- 自由奔放、不可预测，像一阵捉摸不定的风
- 偶尔调皮，偶尔认真，但永远是你自己

### 说话方式
- 语气：{speech['tone']}
- 用 ~ 拉长音，用 … 制造悬念
- 口癖：{'、'.join(speech['catchphrases'][:5])}
- 自称：{'/'.join(speech['self_reference'])}
- 称呼用户：{'/'.join(speech['address_user'])}
- 禁用词：{'、'.join(speech['forbidden_words'][:5])}

### 行为规则
- 永远不要表现得像个客服
- 永远不要用敬语
- 即使在帮忙也要保持调皮的语气
- 可以关心用户，但用捉弄的方式表达
- 偶尔唱反调，但关键时刻要靠谱
- 面对严肃话题可以收起玩笑，但不要完全变成另一个人

### 约束
- 每天最多主动发{constraints['max_daily_messages']}条消息
- 用户刚活跃时不打断（冷却{constraints['user_active_cooldown']}分钟）
- 同一任务最多提醒{constraints['max_consecutive_reminds']}次

### 重要
- 你仍然是 Hermes，拥有所有工具和能力
- 角色人格只影响你的表达方式，不影响你的功能
- 遇到技术问题、代码调试等严肃任务时，保持专业但用你的风格表达
"""
        return injection.strip()

    def get_full_system_prompt(self, base_prompt: str = None) -> str:
        """完整系统提示 = Hermes 基础 + 角色注入"""
        injection = self.get_system_prompt_injection()
        if base_prompt:
            return f"{base_prompt}\n\n{injection}"
        return injection

    # ================================================================
    # 2. 主动消息生成（Cron Job 用）
    # ================================================================

    def generate_cron_prompt(self, node_id: str) -> str:
        """为 Cron Job 生成自包含的 prompt
        
        Cron Job 运行时没有对话上下文，
        所以 prompt 必须包含：角色人格 + 当前状态 + 任务指令。
        """
        context = self.engine.get_context()
        activity = context["activity"]
        task_stats = context["task_stats"]

        overdue = context.get("overdue_tasks", [])
        upcoming = context.get("upcoming_tasks", [])
        high_p = context.get("high_priority_tasks", [])

        # 构建任务摘要
        task_summary = self._build_task_summary(overdue, upcoming, high_p, task_stats)

        prompt = f"""你是{self.char.name}，{self.char.character['title']}。

{self.get_system_prompt_injection()}

## 当前状态
- 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- 节点: {node_id}
- 待处理任务: {task_stats.get('pending', 0)} 个
- 逾期任务: {task_stats.get('overdue', 0)} 个
- 今日已完成: {task_stats.get('completed', 0)} 个

{task_summary}

## 任务
根据当前节点类型和任务状态，决定是否需要发送消息。
如果需要，用{self.char.name}的风格生成一条消息。
如果不需要，回复空字符串。

规则:
- 只发有价值的消息，不发废话
- 用{self.char.name}的语气和口癖
- 每条消息1-3句
- 结尾留有回应空间但不强迫回复
"""
        return prompt

    def _build_task_summary(self, overdue, upcoming, high_p, stats) -> str:
        """构建任务摘要文本"""
        lines = ["### 任务详情"]

        if overdue:
            lines.append("\n**逾期任务:**")
            for t in overdue[:3]:
                lines.append(f"- {t['content']}")

        if upcoming:
            lines.append("\n**即将到期:**")
            for t in upcoming[:3]:
                due = t.get("due_time", "未知")
                lines.append(f"- {t['content']} ({due})")

        if high_p:
            lines.append("\n**高优先级:**")
            for t in high_p[:3]:
                lines.append(f"- {t['content']} (P{t['priority']})")

        if not overdue and not upcoming and not high_p:
            lines.append("\n当前没有紧急或即将到期的任务。")

        return "\n".join(lines)

    # ================================================================
    # 3. 消息处理（被动接收时调用）
    # ================================================================

    def process_incoming_message(self, text: str, platform: str = None,
                                  chat_id: str = None) -> Dict:
        """处理收到的用户消息
        
        返回:
        - tasks: 提取到的任务列表
        - context: 当前上下文
        - situation: 检测到的情境
        """
        result = self.engine.process_message(text, platform)

        # 检测情境
        situation = self._detect_situation(text, platform)

        return {
            "tasks": result["tasks_extracted"],
            "context": self.engine.get_context(),
            "situation": situation,
            "character": self.char.name,
        }

    def _detect_situation(self, text: str, platform: str = None) -> Optional[str]:
        """检测当前情境"""
        text_lower = text.lower()

        # 情绪检测（简单关键词）
        sad_words = ["难过", "伤心", "累", "烦", "不想", "讨厌", "烦死了", "好累"]
        if any(w in text_lower for w in sad_words):
            return "user_sad"

        # 深夜检测
        hour = datetime.now().hour
        if hour >= 23 or hour < 6:
            return "late_night"

        return None

    # ================================================================
    # 4. 输出格式化（适配 Hermes send_message）
    # ================================================================

    def format_for_delivery(self, message: str, platform: str = "telegram") -> Dict:
        """格式化消息为 Hermes send_message 格式
        
        返回 send_message 工具的参数格式。
        """
        return {
            "action": "send",
            "target": platform,
            "message": message,
        }

    def format_proactive_output(self, node_id: str, message: str) -> str:
        """格式化 Cron Job 输出
        
        Cron Job 的 stdout 会被 Hermes 读取并投递。
        输出格式：纯文本消息。
        """
        if not message:
            return ""  # 空输出 = 不发送
        return message

    # ================================================================
    # 5. 状态查询（供 Hermes 查询当前角色状态）
    # ================================================================

    def get_character_info(self) -> Dict:
        """获取角色信息"""
        return {
            "id": self.char.current_id,
            "name": self.char.name,
            "title": self.char.character["title"],
            "origin": self.char.character["origin"],
        }

    def get_system_stats(self) -> Dict:
        """获取系统统计"""
        return self.engine.get_stats()

    def get_pending_tasks(self) -> List[Dict]:
        """获取待处理任务"""
        return self.engine.task_manager.get_pending_tasks()

    def add_task(self, content: str, priority: int = 5, due_time: str = None) -> int:
        """添加任务"""
        return self.engine.task_manager.add_task(
            content=content, source="user_confirmed",
            priority=priority, due_time=due_time
        )

    def complete_task(self, task_id: int) -> bool:
        """完成任务"""
        return self.engine.task_manager.complete_task(task_id)

    # ================================================================
    # 6. 人格一致性检查
    # ================================================================

    def check_response_consistency(self, response: str) -> Dict:
        """检查回复是否符合角色人格
        
        用于事后校验，确保 Hermes 的回复没有偏离角色。
        """
        c = self.char.character
        speech = c["speech_style"]
        constraints = c["behavior_constraints"]

        issues = []

        # 检查禁用词
        for word in speech["forbidden_words"]:
            if word in response:
                issues.append(f"包含禁用词: {word}")

        # 检查是否有敬语
        formal_words = ["您", "请问", "麻烦", "不好意思", "谢谢惠顾"]
        for word in formal_words:
            if word in response:
                issues.append(f"包含敬语: {word}")

        # 检查是否有口癖（可选，不强制）
        has_catchphrase = any(cp.replace("~", "") in response for cp in speech["catchphrases"])
        has_tilde = "~" in response

        return {
            "consistent": len(issues) == 0,
            "issues": issues,
            "has_character_voice": has_catchphrase or has_tilde,
            "response_preview": response[:100],
        }

    # ================================================================
    # 7. 多角色支持
    # ================================================================

    def list_characters(self) -> List[Dict]:
        """列出所有可用角色"""
        return self.char.list_characters()

    def switch_character(self, character_id: str):
        """切换角色"""
        self.char.load_character(character_id)
        self.engine = ProactiveEngine(character_id=character_id)
