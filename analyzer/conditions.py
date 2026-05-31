"""条件检查器 v2 — 带评分的结构化条件系统

硬条件: 任一命中 → 直接阻止
软条件: 每项扣分，总分 < 阈值 → 阻止
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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.database import init_db, query


# ============================================================
# 硬条件（任一命中 = 直接阻止，不进入评分）
# ============================================================

def check_hard_late_night(start_hour=23, end_hour=7):
    """深夜/凌晨"""
    hour = datetime.now().hour
    if hour >= start_hour or hour < end_hour:
        return True, f"深夜时段 {hour}:00，不打扰休息"
    return False, ""


def check_hard_system_busy():
    """系统维护中"""
    lock_file = os.path.join(PROJECT_ROOT, ".system_lock")
    if os.path.exists(lock_file):
        return True, "系统处于维护模式"
    return False, ""


def check_hard_daily_limit(max_daily=6):
    """今日已达上限"""
    today = datetime.now().strftime("%Y-%m-%d")
    rows = query(
        "SELECT COUNT(*) as cnt FROM proactive_messages WHERE target_date = ? AND status = 'sent'",
        (today,)
    )
    cnt = rows[0]["cnt"] if rows else 0
    if cnt >= max_daily:
        return True, f"今日已发 {cnt}/{max_daily} 条"
    return False, ""


HARD_CHECKS = [
    ("late_night", check_hard_late_night),
    ("system_busy", check_hard_system_busy),
    ("daily_limit", check_hard_daily_limit),
]


# ============================================================
# 软条件（每项扣分，返回扣分值）
# ============================================================

def score_user_just_active(minutes_since_active):
    """用户刚活跃 — 扣30分"""
    if minutes_since_active is None:
        return 0, "活跃状态未知"
    if minutes_since_active < 5:
        return 30, f"用户 {minutes_since_active:.0f} 分钟前活跃，不打断"
    if minutes_since_active < 15:
        return 10, f"用户 {minutes_since_active:.0f} 分钟前活跃，可能还在"
    return 0, ""


def score_message_interval(minutes_since_last_msg):
    """距上次主动消息间隔 — 扣25分"""
    if minutes_since_last_msg is None:
        return 0, "无历史消息"
    if minutes_since_last_msg < 180:
        return 40, f"距上次主动仅 {minutes_since_last_msg:.0f} 分钟（需≥360）"
    if minutes_since_last_msg < 360:
        return 25, f"距上次主动 {minutes_since_last_msg:.0f} 分钟，间隔偏短（需≥360）"
    if minutes_since_last_msg < 480:
        return 10, f"距上次主动 {minutes_since_last_msg:.0f} 分钟，可再等等"
    return 0, ""


def score_negative_mood(recent_messages):
    """负面情绪 — 扣20分"""
    if not recent_messages:
        return 0, ""

    negative_keywords = [
        "烦死了", "讨厌", "滚", "别烦我", "好累", "崩溃",
        "恶心", "垃圾", "操", "草", "tmd", "fuck",
        "不想干了", "算了", "无所谓", "不想做", "好烦",
    ]

    for msg in recent_messages:
        if msg.get("role") != "user":
            continue
        text = msg.get("text", "").lower()
        for kw in negative_keywords:
            if kw in text:
                return 20, f"检测到负面关键词「{kw}」"
    return 0, ""


def score_deep_work(recent_messages):
    """深度工作中 — 扣15分"""
    if not recent_messages or len(recent_messages) < 5:
        return 0, ""

    user_times = []
    for msg in recent_messages:
        if msg.get("role") == "user":
            try:
                t = datetime.fromisoformat(msg.get("time", ""))
                user_times.append(t)
            except (ValueError, TypeError):
                pass

    if len(user_times) < 5:
        return 0, ""

    user_times.sort()
    gaps = [(user_times[i+1] - user_times[i]).total_seconds() / 60
            for i in range(len(user_times)-1)]
    avg_gap = sum(gaps) / len(gaps) if gaps else 999

    if avg_gap < 2 and len(user_times) >= 8:
        return 15, f"消息密集（间隔 {avg_gap:.1f}min），深度工作中"
    if avg_gap < 3 and len(user_times) >= 5:
        return 8, f"消息较密（间隔 {avg_gap:.1f}min），可能在忙"
    return 0, ""


def score_duplicate(message_text, hours=24):
    """内容重复 — 扣10分"""
    if not message_text:
        return 0, ""

    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = query(
        "SELECT message FROM proactive_messages WHERE status = 'sent' AND created_at > ? ORDER BY id DESC LIMIT 10",
        (since,)
    )

    if not rows:
        return 0, ""

    msg_chars = set(message_text[:100])
    for row in rows:
        prev_chars = set(row.get("message", "")[:100])
        overlap = len(msg_chars & prev_chars) / max(len(msg_chars | prev_chars), 1)
        if overlap > 0.6:
            return 10, f"与历史消息相似度 {overlap:.0%}"
    return 0, ""


def score_traveling(recent_messages):
    """通勤中 — 扣10分"""
    if not recent_messages:
        return 0, ""

    travel_keywords = ["在路上", "出门了", "开车", "坐车", "地铁", "高铁", "飞机", "打车"]
    for msg in recent_messages:
        if msg.get("role") != "user":
            continue
        text = msg.get("text", "")
        for kw in travel_keywords:
            if kw in text:
                return 10, f"检测到出行关键词「{kw}」"
    return 0, ""


def score_meal_time():
    """非时间窗口 — 直接阻止"""
    hour = datetime.now().hour
    minute = datetime.now().minute
    t = hour * 60 + minute
    # 加载时间窗口
    config_path = os.path.join(PROJECT_ROOT, "config", "config.yaml")
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
        windows = config.get("time_windows", [])
    except Exception:
        windows = []

    if not windows:
        return 0, ""

    for w in windows:
        start_h, start_m = map(int, w["start"].split(":"))
        end_h, end_m = map(int, w["end"].split(":"))
        start_t = start_h * 60 + start_m
        end_t = end_h * 60 + end_m
        if start_t <= t <= end_t:
            return 0, ""

    return 30, f"当前 {hour}:{minute:02d} 不在任何时间窗口内"


SOFT_CHECKS = [
    ("user_just_active", score_user_just_active),
    ("message_interval", score_message_interval),
    ("negative_mood", score_negative_mood),
    ("deep_work", score_deep_work),
    ("duplicate", score_duplicate),
    ("traveling", score_traveling),
    ("meal_time", score_meal_time),
]


# ============================================================
# 汇总评分
# ============================================================

BASE_SCORE = 100
BLOCK_THRESHOLD = 40  # 总分低于此值 → 不主动对话


def evaluate(minutes_since_active=None, minutes_since_last_msg=None,
             recent_messages=None, proposed_message=None):
    """完整条件评估

    Returns:
        dict: {
            "hard_blocked": bool,
            "hard_reason": str,
            "score": int,             # 基础分 - 扣分
            "passed": bool,           # score >= 阈值
            "deductions": [...],      # 扣分明细
            "total_deduction": int,
        }
    """
    # 1. 硬条件检查
    for name, check_fn in HARD_CHECKS:
        blocked, reason = check_fn()
        if blocked:
            return {
                "hard_blocked": True,
                "hard_reason": f"[{name}] {reason}",
                "score": 0,
                "passed": False,
                "deductions": [{"condition": name, "deduction": 100, "reason": reason}],
                "total_deduction": 100,
            }

    # 2. 软条件评分
    deductions = []
    total_deduction = 0

    for name, score_fn in SOFT_CHECKS:
        try:
            if name in ("user_just_active",):
                deduction, reason = score_fn(minutes_since_active)
            elif name == "message_interval":
                deduction, reason = score_fn(minutes_since_last_msg)
            elif name in ("negative_mood", "deep_work", "traveling"):
                deduction, reason = score_fn(recent_messages)
            elif name == "duplicate":
                deduction, reason = score_fn(proposed_message)
            else:
                deduction, reason = score_fn()

            if deduction > 0:
                deductions.append({
                    "condition": name,
                    "deduction": deduction,
                    "reason": reason,
                })
                total_deduction += deduction
        except Exception as e:
            deductions.append({
                "condition": name,
                "deduction": 0,
                "reason": f"异常: {e}",
            })

    score = max(0, BASE_SCORE - total_deduction)

    return {
        "hard_blocked": False,
        "hard_reason": "",
        "score": score,
        "passed": score >= BLOCK_THRESHOLD,
        "deductions": deductions,
        "total_deduction": total_deduction,
        "base_score": BASE_SCORE,
        "threshold": BLOCK_THRESHOLD,
    }
