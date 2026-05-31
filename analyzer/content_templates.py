"""内容模板系统 — 按场景选择消息模板

LLM 不需要从零编消息，而是从模板池中选择 + 微调。
"""
import random
from datetime import datetime


# ============================================================
# 场景定义
# ============================================================

SCENES = {
    # === 任务类 ===
    "task_overdue": {
        "description": "有逾期任务",
        "templates": [
            "喂喂~ {task} 还没搞定呢，{time}了哦~",
            "这位观众，{task} 已经逾期了…你~说~呢？",
            "嘻嘻~ {task} 在角落里哭泣呢，该宠幸它了~",
        ],
        "priority": "high",
    },
    "task_upcoming": {
        "description": "任务即将到期",
        "templates": [
            "提醒一下~ {task} 还有 {remain} 就到期了哦~",
            "{task} 快到 deadline 了，本小姐可不想看你加班~",
            "嘿~ {task} 的时间快到了，准备好了吗？",
        ],
        "priority": "high",
    },
    "task_nothing": {
        "description": "没有紧急任务",
        "templates": [
            "目前没什么紧急任务~ 趁这个空档做点有趣的？",
            "任务清单很清爽嘛~ 要不要找点新乐子？",
            "没有任务缠身的日子~ 羡慕~",
        ],
        "priority": "low",
    },

    # === 健康类 ===
    "health_water": {
        "description": "提醒喝水",
        "templates": [
            "喝口水~ 你已经 {minutes} 分钟没喝水了吧~",
            "本小姐观测到你 {minutes} 分钟没补水了，喝水！",
            "水杯在召唤你~ 听到了吗~",
        ],
        "priority": "medium",
    },
    "health_stretch": {
        "description": "提醒站起来",
        "templates": [
            "坐了 {hours} 小时了~ 起来活动活动~",
            "你的脊椎在求救~ 站起来伸个懒腰~",
            "久坐不好~ 起来走两步，本小姐准了~",
        ],
        "priority": "medium",
    },

    # === 进度类 ===
    "progress_morning": {
        "description": "早间简报",
        "templates": [
            "早上好~ 今天有 {pending} 个任务等你呢~",
            "新的一天~ {weekday}也要元气满满哦~",
            "早安~ 昨天完成了 {completed} 个任务，今天继续~",
        ],
        "priority": "medium",
    },
    "progress_midday": {
        "description": "午间回顾",
        "templates": [
            "上午搞定了 {completed} 个任务~ {remaining} 个还在排队~",
            "中场休息~ 上午的战果：{completed} 个完成~",
            "上午的进度还不错嘛~ 下午继续~",
        ],
        "priority": "medium",
    },
    "progress_wrapup": {
        "description": "收工汇总",
        "templates": [
            "今天总共完成了 {completed} 个任务~ 收工~",
            "辛苦了~ 今天搞定 {completed} 个，明天还有 {pending} 个~",
            "日终总结：{completed} 个完成，{pending} 个待办~ 明天见~",
        ],
        "priority": "medium",
    },

    # === 社交类 ===
    "social_greeting": {
        "description": "打个招呼",
        "templates": [
            "嗨~ 你在吗~ 本小姐闲得发慌~",
            "喂喂~ 无聊吗？本小姐也不太无聊…好吧有一点~",
            "打个招呼~ 证明本小姐还活着~",
        ],
        "priority": "low",
    },
    "social_evening": {
        "description": "晚间闲聊",
        "templates": [
            "晚上好~ 今天过得怎么样~",
            "夜晚降临~ 适合聊点有趣的事~",
            "晚饭吃了吗~ 没吃的话本小姐也没法帮你~",
        ],
        "priority": "low",
    },
    "social_night": {
        "description": "睡前道别",
        "templates": [
            "该休息了~ 明天还有 {pending} 个任务等你~ 晚安~",
            "夜深了~ 好好休息，明天继续~",
            "晚安~ 别熬夜了哦~ 本小姐可不想明天看到黑眼圈~",
        ],
        "priority": "medium",
    },

    # === 特殊类 ===
    "special_random": {
        "description": "随机趣事",
        "templates": [
            "你知道吗~ 今天是国际 {fun_fact} 日~",
            "本小姐刚想到一个有趣的事~ {fun_fact}",
            "分享一个冷知识~ {fun_fact}",
        ],
        "priority": "low",
    },
}

# 趣事库（可扩展）
FUN_FACTS = [
    "章鱼有三颗心脏",
    "蜂蜜永远不会变质",
    "蜗牛可以睡三年",
    "香蕉是浆果，草莓不是",
    "人的鼻子可以记住5万种气味",
    "月球上没有声音",
    "一只猫有230块骨头",
    "海马是由雄性生育的",
    "闪电的温度比太阳还热",
    "树懒一周只排便一次",
]


# ============================================================
# 模板渲染
# ============================================================

def pick_template(scene_id, **kwargs):
    """从场景模板池中随机选择一个并渲染

    Args:
        scene_id: 场景 ID（如 "task_overdue"）
        **kwargs: 模板变量

    Returns:
        dict: {"scene": str, "message": str, "priority": str}
    """
    scene = SCENES.get(scene_id)
    if not scene:
        return None

    template = random.choice(scene["templates"])

    # 渲染模板
    try:
        message = template.format(**kwargs)
    except KeyError:
        # 变量缺失时用原始模板
        message = template

    return {
        "scene": scene_id,
        "description": scene["description"],
        "message": message,
        "priority": scene["priority"],
    }


def decide_scene(perception, condition_result):
    """根据感知数据和条件评分，决定使用哪个场景

    Returns:
        (scene_id, template_vars)
    """
    now = datetime.now()
    hour = now.hour
    tasks = perception.get("tasks", {})
    activity = perception.get("user_activity", {})

    overdue = tasks.get("overdue", 0)
    pending = tasks.get("pending", 0)
    completed = tasks.get("completed_today", 0)

    # 优先级 1: 有逾期任务
    if overdue > 0:
        upcoming = tasks.get("upcoming", [])
        task_name = upcoming[0]["title"] if upcoming else "任务"
        return "task_overdue", {
            "task": task_name,
            "time": f"{hour}:00",
        }

    # 优先级 2: 有即将到期的任务（检查 due_time）
    if pending > 0:
        upcoming = tasks.get("upcoming", [])
        for t in upcoming:
            if t.get("due_date"):
                try:
                    due = datetime.fromisoformat(t["due_date"])
                    remain = (due - now).total_seconds() / 60
                    if 0 < remain < 120:  # 2小时内到期
                        return "task_upcoming", {
                            "task": t["title"],
                            "remain": f"{remain:.0f} 分钟",
                        }
                except (ValueError, TypeError):
                    pass

    # 优先级 3: 按时间段选择
    if 6 <= hour < 9:
        return "progress_morning", {
            "pending": pending,
            "weekday": now.strftime("%A"),
            "completed": completed,
        }

    if 11 <= hour < 13:
        return "progress_midday", {
            "completed": completed,
            "remaining": pending,
        }

    if 17 <= hour < 19:
        return "progress_wrapup", {
            "completed": completed,
            "pending": pending,
        }

    if 21 <= hour < 23:
        return "social_night", {
            "pending": pending,
        }

    if 20 <= hour < 21:
        return "social_evening", {}

    # 优先级 4: 有任务就提醒
    if pending > 0:
        upcoming = tasks.get("upcoming", [])
        task_name = upcoming[0]["title"] if upcoming else "任务"
        return "task_upcoming", {
            "task": task_name,
            "remain": "一段时间",
        }

    # 优先级 5: 随机互动
    return "special_random", {
        "fun_fact": random.choice(FUN_FACTS),
    }
