"""决策引擎 — 结构化分析 + LLM 微调

流程:
1. 收集感知数据
2. 硬条件过滤
3. 软条件评分
4. 场景选择 + 模板渲染
5. 时间决策
6. 输出结构化决策（LLM 只做微调，不做从零决策）
"""
import json
import os
import sys
import random
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.database import init_db, query
from analyzer.perception import collect_all
from analyzer.conditions import evaluate
from analyzer.content_templates import decide_scene, pick_template


# ============================================================
# 时间决策器
# ============================================================

def decide_send_time(perception, scene_priority):
    """决定消息发送时间

    规则:
    - 高优先级（逾期/即将到期）→ 10分钟内
    - 中优先级 → 15-30分钟随机
    - 低优先级 → 30-50分钟随机
    - 不超过当前小时

    Returns:
        str: "HH:MM" 格式
    """
    now = datetime.now()
    current_minute = now.hour * 60 + now.minute
    hour_end = (now.hour + 1) * 60  # 当前小时结束的分钟数

    if scene_priority == "high":
        delay = random.randint(3, 10)
    elif scene_priority == "medium":
        delay = random.randint(15, 30)
    else:
        delay = random.randint(30, 50)

    target_minute = current_minute + delay

    # 不超过当前小时
    if target_minute >= hour_end:
        target_minute = hour_end - 2

    # 不超过23:59
    if target_minute >= 24 * 60:
        target_minute = 23 * 60 + 55

    target_h = target_minute // 60
    target_m = target_minute % 60
    return f"{target_h:02d}:{target_m:02d}"


# ============================================================
# 主决策函数
# ============================================================

def analyze():
    """执行完整分析流程

    Returns:
        dict: {
            "should_act": bool,
            "score": int,
            "condition_summary": str,
            "scene": str,
            "message": str,
            "send_time": str,
            "reason": str,
            "raw_data": dict,
        }
    """
    # 1. 收集感知
    perception = collect_all()
    activity = perception.get("user_activity", {})
    messages = perception.get("recent_messages", [])

    # 2. 条件评估
    minutes_since_active = activity.get("minutes_since_active")
    minutes_since_last_msg = None
    # 从 proactive_history 计算
    history = perception.get("proactive_history", {})
    today_msgs = history.get("today", [])
    if today_msgs:
        last_time = today_msgs[-1].get("time")
        if last_time:
            try:
                last_dt = datetime.strptime(f"{datetime.now().strftime('%Y-%m-%d')} {last_time}", "%Y-%m-%d %H:%M")
                minutes_since_last_msg = (datetime.now() - last_dt).total_seconds() / 60
            except ValueError:
                pass

    condition = evaluate(
        minutes_since_active=minutes_since_active,
        minutes_since_last_msg=minutes_since_last_msg,
        recent_messages=messages,
    )

    # 3. 硬条件阻止
    if condition["hard_blocked"]:
        return {
            "should_act": False,
            "score": 0,
            "condition_summary": condition["hard_reason"],
            "scene": None,
            "message": None,
            "send_time": None,
            "reason": condition["hard_reason"],
            "raw_data": {"perception": perception, "condition": condition},
        }

    # 4. 软条件评分不足
    if not condition["passed"]:
        reasons = " + ".join([d["reason"] for d in condition["deductions"]])
        return {
            "should_act": False,
            "score": condition["score"],
            "condition_summary": f"评分 {condition['score']}/{condition.get('base_score', 100)}，低于阈值 {condition.get('threshold', 40)}",
            "scene": None,
            "message": None,
            "send_time": None,
            "reason": reasons,
            "raw_data": {"perception": perception, "condition": condition},
        }

    # 5. 选择场景 + 渲染模板
    scene_id, template_vars = decide_scene(perception, condition)
    template_result = pick_template(scene_id, **template_vars)

    if not template_result:
        return {
            "should_act": False,
            "score": condition["score"],
            "condition_summary": "模板选择失败",
            "scene": None,
            "message": None,
            "send_time": None,
            "reason": "场景模板不存在",
            "raw_data": {"perception": perception, "condition": condition},
        }

    # 6. 决定发送时间
    send_time = decide_send_time(perception, template_result["priority"])

    # 7. 组装结果
    deduction_summary = "、".join([d["reason"] for d in condition["deductions"]]) if condition["deductions"] else "无"

    return {
        "should_act": True,
        "score": condition["score"],
        "condition_summary": f"评分 {condition['score']}/{condition.get('base_score', 100)}，扣分: {deduction_summary}",
        "scene": scene_id,
        "message": template_result["message"],
        "send_time": send_time,
        "reason": f"场景: {template_result['description']}，优先级: {template_result['priority']}",
        "raw_data": {"perception": perception, "condition": condition},
    }


if __name__ == "__main__":
    init_db()
    result = analyze()

    # 输出精简版（给 LLM 做微调）
    output = {
        "should_act": result["should_act"],
        "score": result["score"],
        "condition": result["condition_summary"],
        "scene": result["scene"],
        "proposed_message": result["message"],
        "send_time": result["send_time"],
        "reason": result["reason"],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
