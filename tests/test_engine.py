#!/usr/bin/env python3
"""测试套件 - 验证所有模块"""
import sys
import os
import json
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_db, query, execute, get_db_path
from core.config_loader import load_config, get_config
from perception.task_extractor import TaskExtractor
from perception.activity_analyzer import ActivityAnalyzer
from task.task_manager import TaskManager
from personality.system_prompt import PersonalityManager
from scheduler.state_lock import StateLock
from scheduler.dedup_engine import DedupEngine
from scheduler.node_scheduler import NodeScheduler
from delivery.message_deliverer import MessageDeliverer
from learning.preference_learner import PreferenceLearner
from core.engine import ProactiveEngine


class TestDatabase(unittest.TestCase):
    """数据库层测试"""

    def setUp(self):
        # 重置内存数据库
        import core.database as db
        db._MEMORY_CONN = None
        db.DB_PATH = ":memory:"
        init_db()

    def test_init_db(self):
        """测试数据库初始化"""
        tables = query("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [t["name"] for t in tables]
        self.assertIn("tasks", table_names)
        self.assertIn("behavior_log", table_names)
        self.assertIn("user_profile", table_names)
        self.assertIn("proactive_log", table_names)
        self.assertIn("message_queue", table_names)
        self.assertIn("state_lock", table_names)
        self.assertIn("dedup_log", table_names)
        self.assertIn("conversation_history", table_names)


class TestTaskExtractor(unittest.TestCase):
    """任务提取器测试"""

    def setUp(self):
        self.extractor = TaskExtractor()

    def test_extract_with_keyword(self):
        """测试关键词匹配"""
        tasks = self.extractor.extract_tasks("提醒我明天开会")
        self.assertGreater(len(tasks), 0)
        self.assertIn("提醒我", tasks[0]["matched_keywords"])

    def test_extract_without_keyword(self):
        """测试无关键词时返回空"""
        tasks = self.extractor.extract_tasks("今天天气不错")
        self.assertEqual(len(tasks), 0)

    def test_extract_urgent(self):
        """测试紧急任务"""
        tasks = self.extractor.extract_tasks("赶紧处理这个紧急任务")
        self.assertGreater(len(tasks), 0)
        self.assertGreater(tasks[0]["priority"], 5)

    def test_extract_time(self):
        """测试时间提取"""
        tasks = self.extractor.extract_tasks("明天提醒我开会")
        self.assertGreater(len(tasks), 0)
        self.assertIsNotNone(tasks[0]["due_time"])

    def test_dedup_key(self):
        """测试去重 key 生成"""
        task = {"content": "提醒我明天开会"}
        key1 = self.extractor.generate_dedup_key(task)
        key2 = self.extractor.generate_dedup_key(task)
        self.assertEqual(key1, key2)


class TestTaskManager(unittest.TestCase):
    """任务管理器测试"""

    def setUp(self):
        import core.database as db
        db._MEMORY_CONN = None
        db.DB_PATH = ":memory:"
        init_db()
        self.manager = TaskManager()

    def test_add_task(self):
        """测试添加任务"""
        task_id = self.manager.add_task("测试任务", priority=7)
        self.assertIsNotNone(task_id)
        task = self.manager.get_task(task_id)
        self.assertEqual(task["content"], "测试任务")
        self.assertEqual(task["priority"], 7)

    def test_complete_task(self):
        """测试完成任务"""
        task_id = self.manager.add_task("测试任务")
        result = self.manager.complete_task(task_id)
        self.assertTrue(result)
        task = self.manager.get_task(task_id)
        self.assertEqual(task["status"], "completed")
        self.assertIsNotNone(task["completed_at"])

    def test_cancel_task(self):
        """测试取消任务"""
        task_id = self.manager.add_task("测试任务")
        result = self.manager.cancel_task(task_id)
        self.assertTrue(result)
        task = self.manager.get_task(task_id)
        self.assertEqual(task["status"], "cancelled")

    def test_get_pending_tasks(self):
        """测试获取待处理任务"""
        self.manager.add_task("任务1")
        self.manager.add_task("任务2")
        pending = self.manager.get_pending_tasks()
        self.assertEqual(len(pending), 2)

    def test_dedup(self):
        """测试去重"""
        self.manager.add_task("测试任务", dedup_key="abc123")
        self.assertTrue(self.manager.check_dedup("abc123"))
        self.assertFalse(self.manager.check_dedup("xyz789"))

    def test_task_stats(self):
        """测试任务统计"""
        self.manager.add_task("任务1")
        self.manager.add_task("任务2")
        task_id = self.manager.add_task("任务3")
        self.manager.complete_task(task_id)
        stats = self.manager.get_task_stats()
        self.assertEqual(stats["pending"], 2)
        self.assertEqual(stats["completed"], 1)


class TestStateLock(unittest.TestCase):
    """状态锁测试"""

    def setUp(self):
        import core.database as db
        db._MEMORY_CONN = None
        db.DB_PATH = ":memory:"
        init_db()
        self.lock = StateLock()

    def test_acquire_release(self):
        """测试获取和释放锁"""
        self.assertTrue(self.lock.acquire("N1", "test"))
        self.assertTrue(self.lock.is_locked())
        self.lock.release("N1")
        self.assertFalse(self.lock.is_locked())

    def test_double_acquire(self):
        """测试重复获取锁"""
        self.assertTrue(self.lock.acquire("N1", "test"))
        self.assertFalse(self.lock.acquire("N2", "test2"))  # 第二次应该失败


class TestDedupEngine(unittest.TestCase):
    """去重引擎测试"""

    def setUp(self):
        import core.database as db
        db._MEMORY_CONN = None
        db.DB_PATH = ":memory:"
        init_db()
        self.dedup = DedupEngine()

    def test_check_and_record(self):
        """测试检查并记录"""
        key = "test_key_123"
        self.assertFalse(self.dedup.check_and_record(key))  # 首次不是重复
        self.assertTrue(self.dedup.check_and_record(key))   # 第二次是重复


class TestMessageDeliverer(unittest.TestCase):
    """消息投递器测试"""

    def setUp(self):
        import core.database as db
        db._MEMORY_CONN = None
        db.DB_PATH = ":memory:"
        init_db()
        self.deliverer = MessageDeliverer()

    def test_queue_message(self):
        """测试消息入队"""
        msg_id = self.deliverer.queue_message("test_target", "test message")
        self.assertIsNotNone(msg_id)
        pending = self.deliverer.get_pending_messages()
        self.assertEqual(len(pending), 1)

    def test_deliver(self):
        """测试消息发送"""
        result = self.deliverer.deliver_message("test", "test message")
        self.assertTrue(result)

    def test_proactive_log(self):
        """测试主动消息记录"""
        log_id = self.deliverer.record_proactive("N1", "test message")
        self.assertIsNotNone(log_id)


class TestPreferenceLearner(unittest.TestCase):
    """偏好学习器测试"""

    def setUp(self):
        import core.database as db
        db._MEMORY_CONN = None
        db.DB_PATH = ":memory:"
        init_db()
        self.learner = PreferenceLearner()

    def test_record_interaction(self):
        """测试记录交互"""
        self.learner.record_interaction("message_received", "hello", "telegram")

    def test_update_preference(self):
        """测试更新偏好"""
        self.learner.update_preference("language", "zh", 0.8)
        value = self.learner.get_preference("language")
        self.assertEqual(value, "zh")

    def test_daily_summary(self):
        """测试每日摘要"""
        summary = self.learner.get_daily_summary()
        self.assertIn("date", summary)
        self.assertIn("messages_received", summary)


class TestPersonality(unittest.TestCase):
    """人格管理器测试"""

    def setUp(self):
        self.pm = PersonalityManager("calm_witty")

    def test_system_prompt(self):
        """测试系统提示"""
        prompt = self.pm.get_system_prompt()
        self.assertIn("Hermes", prompt)

    def test_greeting(self):
        """测试问候语"""
        greeting = self.pm.get_greeting(3, 1)
        self.assertTrue("3" in greeting or "1" in greeting)

    def test_should_deliver(self):
        """测试是否应该发送"""
        # 用户活跃时不发送
        self.assertFalse(self.pm.should_deliver({"minutes_since_active": 2}))
        # 达到上限时不发送
        self.assertFalse(self.pm.should_deliver({"today_proactive_count": 8, "minutes_since_active": 10}))
        # 正常情况发送
        self.assertTrue(self.pm.should_deliver({"minutes_since_active": 10, "today_proactive_count": 3}))


class TestProactiveEngine(unittest.TestCase):
    """核心引擎集成测试"""

    def setUp(self):
        import core.database as db
        db._MEMORY_CONN = None
        db.DB_PATH = ":memory:"
        init_db()
        self.engine = ProactiveEngine()

    def test_process_message(self):
        """测试消息处理"""
        result = self.engine.process_message("提醒我明天开会")
        self.assertGreater(len(result["tasks_extracted"]), 0)

    def test_get_context(self):
        """测试获取上下文"""
        context = self.engine.get_context()
        self.assertIn("activity", context)
        self.assertIn("task_stats", context)

    def test_stats(self):
        """测试系统统计"""
        stats = self.engine.get_stats()
        self.assertIn("tasks", stats)
        self.assertIn("delivery", stats)


if __name__ == "__main__":
    unittest.main(verbosity=2)
