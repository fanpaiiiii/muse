"""上下文桥接器 — 为 Cron Job 生成带人格状态的 prompt

核心职责：
1. 从 behavior_log 拉取最近对话
2. 从 persona_state 读取人格状态
3. 组装成完整的上下文注入 Cron prompt
4. 确保被动/主动对话的人格一致
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

from core.database import init_db, query
from analyzer.persona_state import (
    generate_persona_context,
    record_topic,
    record_recent_message,
    update_mood,
    get_current_mood,
    ensure_initialized,
)


def get_recent_conversation(limit: int = 10) -> List[Dict]:
    """从 behavior_log 拉取最近对话（排除 cron 提示）"""
    rows = query(
        """SELECT event_type, content, created_at 
           FROM behavior_log 
           WHERE event_type IN ('message_received', 'message_sent')
             AND content NOT LIKE '%cron job%'
             AND content NOT LIKE '%IMPORTANT%'
             AND content NOT LIKE '[SILENT]%'
           ORDER BY id DESC LIMIT ?""",
        (limit,)
    )
    
    messages = []
    for row in reversed(rows):
        role = "user" if row["event_type"] == "message_received" else "assistant"
        messages.append({
            "role": role,
            "text": row["content"][:300] if row["content"] else "",
            "time": row["created_at"],
        })
    
    return messages


def get_conversation_summary(messages: List[Dict]) -> str:
    """生成对话摘要"""
    if not messages:
        return "暂无最近对话记录。"
    
    lines = ["最近对话摘要:"]
    for msg in messages[-6:]:  # 最近6条
        role = "用户" if msg["role"] == "user" else "花火"
        text = msg["text"][:80].replace("\n", " ")
        lines.append(f"  {role}: {text}")
    
    return "\n".join(lines)


def get_hermes_session_topics() -> List[str]:
    """从 Hermes session 历史拉取最近话题关键词（对话记忆注入）"""
    import sqlite3
    state_db = os.path.expanduser("~/.hermes/state.db")
    if not os.path.exists(state_db):
        return []
    
    try:
        conn = sqlite3.connect(state_db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT content FROM messages 
            WHERE role = 'user' 
            ORDER BY id DESC LIMIT 20
        """).fetchall()
        conn.close()
        
        # 提取最近话题
        topics = []
        keyword_map = {
            "假发": "假发业务", "wigs": "假发业务",
            "宠物": "宠物用品", "pet": "宠物用品",
            "阿里": "阿里巴巴", "报价": "报价单",
            "部署": "服务器部署", "deploy": "服务器部署",
            "bug": "代码调试", "微信": "微信集成",
            "Telegram": "Telegram", "飞书": "飞书集成",
            "openclaw": "OpenClaw", "muse": "Muse系统",
            "图片": "图片生成", "image": "图片生成",
        }
        for row in rows:
            text = (row["content"] or "").lower()
            for kw, topic in keyword_map.items():
                if kw.lower() in text and topic not in topics:
                    topics.append(topic)
        return topics[:5]
    except Exception:
        return []


def get_recent_git_activity() -> str:
    """获取最近的 git 活动摘要"""
    import subprocess
    projects_dir = os.path.expanduser("~/projects")
    if not os.path.isdir(projects_dir):
        return ""
    
    activities = []
    try:
        for item in os.listdir(projects_dir)[:5]:
            git_dir = os.path.join(projects_dir, item, ".git")
            if os.path.isdir(git_dir):
                result = subprocess.run(
                    ["git", "log", "--oneline", "-3", "--since=2 days ago"],
                    cwd=os.path.join(projects_dir, item),
                    capture_output=True, text=True, timeout=5
                )
                if result.stdout.strip():
                    lines = result.stdout.strip().split(chr(10))
                    activities.append(f"{item}: {lines[0]}")
    except Exception:
        pass
    
    return chr(10).join(activities[:3]) if activities else ""


def extract_topics_from_messages(messages: List[Dict]) -> List[str]:
    """从对话中提取话题关键词"""
    topics = []
    
    # 简单的关键词提取
    keyword_patterns = {
        "假发": "假发业务",
        "wigs": "假发业务",
        "宠物": "宠物用品",
        "pet": "宠物用品",
        "阿里": "阿里巴巴",
        "alibaba": "阿里巴巴",
        "1688": "1688采购",
        "报价": "报价单",
        "quotation": "报价单",
        "部署": "服务器部署",
        "deploy": "服务器部署",
        "bug": "代码调试",
        "error": "代码调试",
        "微信": "微信集成",
        "wechat": "微信集成",
        "telegram": "Telegram",
        "飞书": "飞书集成",
    }
    
    for msg in messages:
        text = msg.get("text", "").lower()
        for keyword, topic in keyword_patterns.items():
            if keyword in text and topic not in topics:
                topics.append(topic)
    
    return topics[:5]


def update_persona_from_conversation():
    """从最近对话更新人格状态"""
    messages = get_recent_conversation(20)
    
    if not messages:
        return
    
    # 1. 更新情绪
    update_mood(messages)
    
    # 2. 提取并记录话题
    topics = extract_topics_from_messages(messages)
    for topic in topics:
        record_topic(topic, source="passive")
    
    # 3. 检测特殊事件（用于共享记忆）
    for msg in messages:
        if msg["role"] != "user":
            continue
        text = msg["text"]
        
        # 检测用户提到的趣事/梗
        if any(kw in text for kw in ["哈哈哈", "笑死", "太好笑", "有意思"]):
            record_recent_message(text[:100], "user_highlight")
        
        # 检测用户表达的情绪
        if any(kw in text for kw in ["感谢", "谢谢", "太棒了", "牛"]):
            record_recent_message(text[:100], "user_positive")


def build_full_context() -> str:
    """构建完整的上下文（供 Cron prompt 注入）

    这是「人格一致性」的核心输出。每次 Cron Job 运行时，
    Agent 读取这个上下文，就能「记住」之前聊了什么。
    """
    ensure_initialized()
    
    # 1. 更新人格状态
    update_persona_from_conversation()
    
    # 2. 获取人格状态上下文（含反馈信号）
    persona_ctx = generate_persona_context()
    
    # 3. 获取对话摘要
    messages = get_recent_conversation(8)
    conv_summary = get_conversation_summary(messages)
    
    # 4. 话题提取（从 behavior_log）
    topics = extract_topics_from_messages(messages)
    
    # 5. Hermes session 历史话题（对话记忆注入）
    session_topics = get_hermes_session_topics()
    all_topics = list(dict.fromkeys(topics + session_topics))  # 去重保序
    topic_str = "，".join(all_topics) if all_topics else "无明显话题"
    
    # 6. 最近 git 活动（感知层加厚）
    git_activity = get_recent_git_activity()
    git_str = ("\n## 最近开发活动\n" + git_activity) if git_activity else ""
    
    # 7. 今日已发送消息（防幻觉）
    from datetime import datetime as _dt
    today = _dt.now().strftime("%Y-%m-%d")
    sent_rows = query(
        "SELECT target_time, message FROM proactive_messages WHERE target_date = ? AND status = 'sent' ORDER BY sent_at",
        (today,)
    )
    if sent_rows:
        sent_lines = [f"- {r['target_time']}: {r['message'][:60]}" for r in sent_rows[-5:]]
        sent_str = "\n## 今日已发送消息（不可重复）\n" + "\n".join(sent_lines)
    else:
        sent_str = ""
    
    # 8. 反馈闭环数据
    from analyzer.persona_state import get_engagement_score, get_consecutive_ignores
    engagement = get_engagement_score()
    ignores = get_consecutive_ignores()
    if engagement != 0:
        feedback_str = f"\n## 用户反馈信号\n参与度分数: {engagement:+d}，连续忽略: {ignores}次"
    else:
        feedback_str = ""
    
    # 9. 组装
    full_context = f"""{persona_ctx}

## 最近对话（被动）
{conv_summary}

## 话题追踪
最近话题：{topic_str}
{git_str}
{sent_str}
{feedback_str}

### 一致性规则
- 你刚才和用户聊了什么，要接着聊，不要突然换话题
- 如果用户刚才在讨论工作，不要突然发冷知识
- 如果用户刚才很开心，保持轻松的语气
- 如果用户刚才在忙正事，不要发闲聊
- 避免重复：不要说最近已经说过的话
- 主动消息时优先提及最近的话题，让对话有连贯性
"""
    return full_context


# ============================================================
# 供 Tier 1/Tier 2 Prompt 注入的接口
# ============================================================

def get_injection_block() -> str:
    """生成可直接注入 Cron prompt 的上下文块

    用法: 在 Cron prompt 中插入此内容
    """
    ctx = build_full_context()
    return f"""
## 人格记忆（每次运行自动更新）

{ctx}
"""


if __name__ == "__main__":
    init_db()
    ctx = build_full_context()
    print(ctx)
