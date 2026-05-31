"""人格状态追踪器 — 保证被动/主动对话的人格一致性

这是 Muse 的「记忆核心」。记录：
- 最近话题（避免重复、保持连贯）
- 情绪状态（影响语气选择）
- 共享梗/内部笑话（增强人格真实感）
- 最近的主动/被动消息（避免割裂）
"""
import os
os.environ["TZ"] = "Asia/Shanghai"
try:
    import time
    time.tzset()
except (ImportError, AttributeError):
    pass

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.database import init_db, query, execute


# ============================================================
# 人格状态表初始化
# ============================================================

def init_persona_state_table():
    """创建人格状态表"""
    from core.database import get_conn
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS persona_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        state_key TEXT NOT NULL UNIQUE,
        state_value TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_persona_key ON persona_state(state_key);
    """)
    conn.commit()


def get_state(key: str, default=None) -> Optional[str]:
    """获取状态值"""
    rows = query("SELECT state_value FROM persona_state WHERE state_key = ?", (key,))
    if rows:
        return rows[0]["state_value"]
    return default


def set_state(key: str, value: str):
    """设置状态值"""
    execute(
        """INSERT INTO persona_state (state_key, state_value, updated_at) 
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(state_key) DO UPDATE SET state_value = ?, updated_at = datetime('now')""",
        (key, value, value)
    )


def get_state_json(key: str, default=None):
    """获取 JSON 状态值"""
    val = get_state(key)
    if val:
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            pass
    return default if default is not None else []


def set_state_json(key: str, value):
    """设置 JSON 状态值"""
    set_state(key, json.dumps(value, ensure_ascii=False))


# ============================================================
# 话题追踪
# ============================================================

MAX_TOPICS = 10  # 保留最近10个话题


# ============================================================
# 反馈闭环追踪
# ============================================================

def record_proactive_response(message_id: int, responded: bool):
    """记录用户对主动消息的反馈"""
    history = get_state_json("feedback_history", [])
    history.append({
        "message_id": message_id,
        "responded": responded,
        "time": datetime.now().isoformat(),
    })
    history = history[-20:]
    set_state_json("feedback_history", history)


def get_engagement_score() -> int:
    """根据反馈历史计算参与度分数（正=加分，负=减分）"""
    history = get_state_json("feedback_history", [])
    if not history:
        return 0
    recent = history[-10:]
    responded = sum(1 for h in recent if h.get("responded"))
    total = len(recent)
    if total == 0:
        return 0
    rate = responded / total
    consecutive_ignores = 0
    for h in reversed(history):
        if h.get("responded"):
            break
        consecutive_ignores += 1
    if consecutive_ignores >= 5:
        return -30
    elif consecutive_ignores >= 3:
        return -20
    elif rate >= 0.7:
        return +15
    elif rate >= 0.4:
        return +5
    elif rate < 0.2:
        return -10
    return 0


def get_consecutive_ignores() -> int:
    """获取连续忽略次数"""
    history = get_state_json("feedback_history", [])
    count = 0
    for h in reversed(history):
        if h.get("responded"):
            break
        count += 1
    return count


def get_first_seen_date() -> str:
    """获取首次使用日期（渐进式激活）"""
    val = get_state("first_seen_date")
    if not val:
        val = datetime.now().strftime("%Y-%m-%d")
        set_state("first_seen_date", val)
    return val


def get_days_since_first_seen() -> int:
    """获取使用天数"""
    first = get_first_seen_date()
    try:
        first_dt = datetime.strptime(first, "%Y-%m-%d")
        return (datetime.now() - first_dt).days
    except ValueError:
        return 0


def record_topic(topic: str, source: str = "passive"):
    """记录一个话题

    Args:
        topic: 话题关键词/摘要
        source: 'passive' (被动对话) 或 'proactive' (主动对话)
    """
    topics = get_state_json("recent_topics", [])
    
    # 去重：如果已有相同话题，移到最新
    topics = [t for t in topics if t.get("topic") != topic]
    
    topics.append({
        "topic": topic,
        "source": source,
        "time": datetime.now().isoformat(),
    })
    
    # 只保留最近 N 个
    topics = topics[-MAX_TOPICS:]
    set_state_json("recent_topics", topics)


def get_recent_topics(limit: int = 5) -> List[Dict]:
    """获取最近话题"""
    topics = get_state_json("recent_topics", [])
    return topics[-limit:]


def get_topics_summary() -> str:
    """生成话题摘要（供 Cron prompt 注入）"""
    topics = get_recent_topics(5)
    if not topics:
        return "最近没有对话记录。"
    
    lines = []
    for t in topics:
        time_str = t.get("time", "")[:16]
        source = "被动" if t.get("source") == "passive" else "主动"
        lines.append(f"- [{source}] {t['topic']} ({time_str})")
    
    return "最近话题:\n" + "\n".join(lines)


# ============================================================
# 情绪状态追踪
# ============================================================

# 花火的情绪关键词映射
MOOD_KEYWORDS = {
    "playful": ["有趣", "好玩", "嘻嘻", "哈哈", "笑", "乐", "嘻嘻~", "好~戏"],
    "bored": ["无聊", "没意思", "好闲", "闲得", "发慌"],
    "curious": ["什么", "为什么", "怎么", "吗", "？"],
    "focused": ["搞定", "完成", "继续", "下一步", "开始"],
    "tired": ["累了", "困了", "休息", "晚安", "好累"],
    "excited": ["太棒", "厉害", "牛", "绝了", "惊艳"],
}


def detect_user_mood(recent_messages: List[Dict]) -> str:
    """从最近消息检测用户情绪
    
    策略：
    1. 优先从用户消息中提取关键词
    2. 回退：从助手消息推断对话氛围
    3. 回退：基于时间段的默认情绪
    4. 惯性：保持上一次的情绪（避免频繁跳变）
    """
    mood_scores = {mood: 0 for mood in MOOD_KEYWORDS}
    user_msg_count = 0
    
    for msg in recent_messages:
        text = msg.get("text", "")
        if not text:
            continue
        
        if msg.get("role") == "user":
            user_msg_count += 1
        
        # 用户消息权重 x2，助手消息权重 x1
        weight = 2 if msg.get("role") == "user" else 1
        for mood, keywords in MOOD_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    mood_scores[mood] += weight
    
    # 有匹配结果
    if any(mood_scores.values()):
        return max(mood_scores, key=lambda k: mood_scores[k])
    
    # 回退1：基于时间段
    hour = datetime.now().hour
    if 6 <= hour < 9:
        return "neutral"      # 早晨：平静
    elif 9 <= hour < 12:
        return "focused"      # 上午：专注
    elif 12 <= hour < 14:
        return "neutral"      # 午间：平静
    elif 14 <= hour < 18:
        return "focused"      # 下午：专注
    elif 18 <= hour < 22:
        return "playful"      # 傍晚：轻松
    else:
        return "tired"        # 深夜：疲惫
    
    # 回退2：情绪惯性（保持上次）
    last_mood = get_state("user_mood")
    if last_mood and last_mood != "unknown":
        return last_mood
    
    return "neutral"


def update_mood(recent_messages: List[Dict]):
    """更新情绪状态"""
    mood = detect_user_mood(recent_messages)
    set_state("user_mood", mood)
    
    # 记录情绪变化
    history = get_state_json("mood_history", [])
    history.append({
        "mood": mood,
        "time": datetime.now().isoformat(),
    })
    # 只保留最近20条
    history = history[-20:]
    set_state_json("mood_history", history)


def get_current_mood() -> str:
    """获取当前情绪"""
    return get_state("user_mood", "neutral")


# ============================================================
# 共享记忆（内部梗、上下文引用）
# ============================================================

MAX_SHARED_MEMORIES = 8


def add_shared_memory(memory: str, context: str = ""):
    """添加共享记忆（内部梗、趣事等）"""
    memories = get_state_json("shared_memories", [])
    memories.append({
        "memory": memory,
        "context": context,
        "time": datetime.now().isoformat(),
    })
    memories = memories[-MAX_SHARED_MEMORIES:]
    set_state_json("shared_memories", memories)


def get_shared_memories(limit: int = 3) -> List[Dict]:
    """获取最近的共享记忆"""
    memories = get_state_json("shared_memories", [])
    return memories[-limit:]


def get_memories_summary() -> str:
    """生成共享记忆摘要"""
    memories = get_shared_memories(3)
    if not memories:
        return ""
    
    lines = ["共享记忆（内部梗/上下文）:"]
    for m in memories:
        lines.append(f"- {m['memory']}")
    return "\n".join(lines)


# ============================================================
# 最近消息记录（避免重复）
# ============================================================

def record_recent_message(message: str, msg_type: str = "proactive"):
    """记录最近发送的消息（避免重复内容）"""
    recent = get_state_json("recent_messages", [])
    recent.append({
        "message": message[:200],
        "type": msg_type,
        "time": datetime.now().isoformat(),
    })
    recent = recent[-15:]  # 保留最近15条
    set_state_json("recent_messages", recent)


def get_recent_messages_summary() -> str:
    """获取最近消息摘要"""
    messages = get_state_json("recent_messages", [])
    if not messages:
        return ""
    
    lines = ["最近发送的消息:"]
    for m in messages[-5:]:
        time_str = m.get("time", "")[:16]
        lines.append(f"- [{m.get('type', '?')}] {m['message'][:50]}... ({time_str})")
    return "\n".join(lines)


# ============================================================
# 对话风格追踪
# ============================================================

def record_style_choice(style: str):
    """记录使用的对话风格"""
    set_state("last_style", style)
    
    history = get_state_json("style_history", [])
    history.append({
        "style": style,
        "time": datetime.now().isoformat(),
    })
    history = history[-10:]
    set_state_json("style_history", history)


def get_style_suggestion() -> str:
    """根据历史推荐当前风格"""
    history = get_state_json("style_history", [])
    mood = get_current_mood()
    
    # 如果最近连续用同一种风格，建议换一种
    if len(history) >= 3:
        recent_styles = [h["style"] for h in history[-3:]]
        if len(set(recent_styles)) == 1:
            current = recent_styles[0]
            alternatives = {
                "teasing": "caring",
                "caring": "mysterious",
                "mysterious": "dramatic",
                "dramatic": "teasing",
            }
            return alternatives.get(current, "teasing")
    
    # 根据情绪推荐
    mood_styles = {
        "playful": "teasing",
        "bored": "dramatic",
        "tired": "caring",
        "focused": "mysterious",
        "excited": "dramatic",
    }
    return mood_styles.get(mood, "teasing")


# ============================================================
# 完整上下文生成（供 Cron prompt 注入）
# ============================================================

def generate_persona_context() -> str:
    """生成完整的人格上下文（供 Tier 1/Tier 2 Cron prompt 注入）

    这是保证人格一致性的核心。每次 Cron Job 运行时，
    Agent 会读取这个上下文，确保：
    1. 知道最近聊了什么（话题连贯）
    2. 知道用户的情绪（语气适配）
    3. 知道自己之前说了什么（避免重复）
    4. 知道该用什么风格（一致性）
    5. 知道用户反馈如何（动态调整频率）
    """
    init_persona_state_table()
    
    topics = get_topics_summary()
    mood = get_current_mood()
    memories = get_memories_summary()
    recent_msgs = get_recent_messages_summary()
    style = get_style_suggestion()
    
    # 反馈闭环数据
    engagement = get_engagement_score()
    ignores = get_consecutive_ignores()
    days = get_days_since_first_seen()
    
    mood_names = {
        "playful": "开心/调皮",
        "bored": "无聊",
        "curious": "好奇",
        "focused": "专注",
        "tired": "疲惫",
        "excited": "兴奋",
        "neutral": "平静",
    }
    
    feedback_line = ""
    if engagement > 0:
        feedback_line = f"\n用户参与度: +{engagement}分（回复积极，可多互动）"
    elif engagement < 0:
        feedback_line = f"\n用户参与度: {engagement}分（连续忽略{ignores}次，应降频）"
    else:
        feedback_line = "\n用户参与度: 中性（无足够数据）"
    
    activation_line = f"\n使用天数: {days}天"
    if days < 7:
        activation_line += "（渐进式激活：仅推任务场景）"
    else:
        activation_line += "（已激活：可推社交场景）"
    
    context = f"""## 人格状态（实时）

当前用户情绪: {mood_names.get(mood, mood)}
推荐对话风格: {style}{feedback_line}{activation_line}

{topics}

{memories}

{recent_msgs}

### 风格指南
- teasing: 戏谑调侃，用~拉长音，故意唱反调
- caring: 关心但用捉弄的方式，比如"本小姐才不是担心你呢"
- mysterious: 制造悬念，用...停顿，说一半留一半
- dramatic: 夸张表演，像在舞台上，好~戏~开~演~
"""
    return context.strip()


# ============================================================
# 初始化
# ============================================================

def ensure_initialized():
    """确保表已创建"""
    init_persona_state_table()


if __name__ == "__main__":
    init_db()
    ensure_initialized()
    print(generate_persona_context())
