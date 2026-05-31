"""任务提取器 - 从对话中提取待办任务"""
import re
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict

# 时间表达式正则
TIME_PATTERNS = {
    "today": (r"今天|今晚|今日", lambda: datetime.now().replace(hour=18, minute=0)),
    "tomorrow": (r"明天|明日", lambda: (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0)),
    "next_week": (r"下周|下星期", lambda: (datetime.now() + timedelta(days=7)).replace(hour=9, minute=0)),
    "next_month": (r"下个月|下月", lambda: (datetime.now() + timedelta(days=30)).replace(hour=9, minute=0)),
    "hour_later": (r"(\d+)小时后", None),  # 动态处理
    "minute_later": (r"(\d+)分钟后", None),  # 动态处理
    "specific_time": (r"(\d{1,2})[点时:：](\d{0,2})", None),  # 动态处理
}

# 任务关键词
TASK_KEYWORDS = [
    "提醒我", "记得", "别忘", "要做", "待办", "需要",
    "明天", "下周", "deadline", "ddl", "赶紧", "尽快",
    "完成", "check", "处理", "跟进", "确认", "提交",
    "回复", "发送", "准备", "整理", "检查", "更新",
]


class TaskExtractor:
    """从文本中提取任务"""

    def __init__(self, custom_keywords: List[str] = None):
        self.keywords = TASK_KEYWORDS + (custom_keywords or [])

    def extract_tasks(self, text: str) -> List[Dict]:
        """从文本中提取任务列表"""
        tasks = []
        # 检查是否包含任务关键词
        if not any(kw in text for kw in self.keywords):
            return tasks

        # 按句子拆分
        sentences = re.split(r'[。！？\n；;]', text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 检查是否包含任务关键词
            matched_keywords = [kw for kw in self.keywords if kw in sentence]
            if not matched_keywords:
                continue

            # 提取时间信息
            due_time = self._extract_time(sentence)
            priority = self._estimate_priority(sentence, matched_keywords)

            tasks.append({
                "content": sentence,
                "due_time": due_time.isoformat() if due_time else None,
                "priority": priority,
                "source": "extracted",
                "matched_keywords": matched_keywords,
            })

        return tasks

    def _extract_time(self, text: str) -> Optional[datetime]:
        """提取时间信息"""
        now = datetime.now()

        # 小时后
        match = re.search(r'(\d+)小时后', text)
        if match:
            return now + timedelta(hours=int(match.group(1)))

        # 分钟后
        match = re.search(r'(\d+)分钟后', text)
        if match:
            return now + timedelta(minutes=int(match.group(1)))

        # 具体时间
        match = re.search(r'(\d{1,2})[点时:：](\d{0,2})', text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2)) if match.group(2) else 0
            target = now.replace(hour=hour, minute=minute, second=0)
            if target <= now:
                target += timedelta(days=1)
            return target

        # 关键词时间
        for key, val in TIME_PATTERNS.items():
            if key in ("hour_later", "minute_later", "specific_time"):
                continue
            if isinstance(val, tuple):
                pattern, func = val
            else:
                pattern, func = val, val
            if isinstance(pattern, str) and re.search(pattern, text):
                return func() if callable(func) else None

        return None

    def _estimate_priority(self, text: str, keywords: List[str]) -> int:
        """估算任务优先级 (1-10)"""
        priority = 5

        # 紧急关键词提升优先级
        urgent_words = ["赶紧", "尽快", "马上", "立刻", "urgent", "紧急"]
        if any(w in text for w in urgent_words):
            priority += 3

        # deadline 提升
        if any(w in text for w in ["deadline", "ddl", "截止"]):
            priority += 2

        # 一般任务关键词
        task_words = ["提醒", "记得", "别忘"]
        if any(w in text for w in task_words):
            priority += 1

        return min(priority, 10)

    def generate_dedup_key(self, task: Dict) -> str:
        """生成去重 key"""
        import hashlib
        content = task.get("content", "")
        return hashlib.md5(content.encode()).hexdigest()[:12]
