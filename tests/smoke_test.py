#!/usr/bin/env python3
"""Muse 主动测试 — 端到端冒烟测试

验证 Muse 管线的端到端行为，不等 Cron 触发。
使用 freezegun 控制时间，临时数据库隔离测试数据。

freeze_time 直接冻结 datetime.now() 到指定时间，不受系统时区影响。
所有时间使用北京时间（与 Muse 代码的 TZ=Asia/Shanghai 一致）。

用法:
    python tests/smoke_test.py           # 运行所有场景
    python tests/smoke_test.py -v        # 详细输出
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
import importlib
from datetime import datetime, timedelta
from freezegun import freeze_time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def setup_isolated_db():
    """创建临时数据库，替换 core.database 的路径"""
    import core.database as db_mod

    tmp_dir = tempfile.mkdtemp(prefix="muse_smoke_")
    db_path = os.path.join(tmp_dir, "test_proactive.db")

    db_mod.DB_PATH = db_path
    db_mod._MEMORY_CONN = None
    try:
        db_mod.get_conn().close()
    except Exception:
        pass

    db_mod.init_db()
    from analyzer.persona_state import init_persona_state_table
    init_persona_state_table()
    return db_path, tmp_dir


def cleanup_db(tmp_dir):
    """清理临时目录"""
    import core.database as db_mod
    db_mod.DB_PATH = None
    db_mod._MEMORY_CONN = None
    shutil.rmtree(tmp_dir, ignore_errors=True)


def insert_sent(time_str, message="测试消息", reason="测试"):
    """插入已发送消息"""
    import core.database as db_mod
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    db_mod.execute(
        """INSERT INTO proactive_messages 
           (target_time, target_date, message, reason, status, created_at, sent_at) 
           VALUES (?, ?, ?, ?, 'sent', ?, ?)""",
        (time_str, today, message, reason, now.isoformat(), now.isoformat())
    )


def insert_behavior(event_type="message_received", minutes_ago=30):
    """插入行为记录"""
    import core.database as db_mod
    ts = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat()
    db_mod.execute(
        """INSERT INTO behavior_log (event_type, source, content, metadata, created_at)
           VALUES (?, 'test', 'test message', '{}', ?)""",
        (event_type, ts)
    )


def run_pipeline():
    """运行感知+决策管线，返回JSON"""
    import analyzer.collect_perception as cp
    importlib.reload(cp)

    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        cp.main()
    output = buf.getvalue().strip()
    return json.loads(output) if output else {}


class TestScenario1_MorningFirstMessage(unittest.TestCase):
    """场景1: 空数据库 + 早上9点 → 应该生成早安消息"""

    def setUp(self):
        self.db_path, self.tmp_dir = setup_isolated_db()

    def tearDown(self):
        cleanup_db(self.tmp_dir)

    @freeze_time("2026-06-01 09:00:00")
    def test_morning_generates_message(self):
        """空DB + 早9点 → should_act=True"""
        insert_behavior("message_received", minutes_ago=60)
        result = run_pipeline()

        self.assertTrue(result["decision"]["should_act"],
                        f"早9点空DB应该发送消息，实际: {result['decision']}")
        self.assertEqual(result["today_sent"], [],
                         "空DB时today_sent应为空数组")

    @freeze_time("2026-06-01 08:00:00")
    def test_morning_scene_is_progress(self):
        """早8点(在6-9窗口内) → 场景应为 progress_morning"""
        insert_behavior("message_received", minutes_ago=60)
        result = run_pipeline()

        if result["decision"]["should_act"]:
            self.assertEqual(result["decision"]["scene"], "progress_morning",
                             f"早8点场景应为progress_morning，实际: {result['decision']['scene']}")


class TestScenario2_ReasonableInterval(unittest.TestCase):
    """场景2: 今天已发1条(2小时 ago) + 上午11点 → 引擎应允许"""

    def setUp(self):
        self.db_path, self.tmp_dir = setup_isolated_db()

    def tearDown(self):
        cleanup_db(self.tmp_dir)

    @freeze_time("2026-06-01 11:00:00")
    def test_allows_after_long_interval(self):
        """已发1条(2h前) + 11点 → should_act=True"""
        insert_behavior("message_received", minutes_ago=60)
        insert_sent("09:00", "早安消息", "morning")

        result = run_pipeline()

        self.assertTrue(result["decision"]["should_act"],
                        f"距上次2小时应允许发送，实际: {result['decision']}")
        self.assertEqual(len(result["today_sent"]), 1)
        self.assertIn("早安", result["today_sent"][0]["msg"])


class TestScenario3_TooClose(unittest.TestCase):
    """场景3: 今天已发1条(5分钟 ago) → 引擎应阻止或评分很低"""

    def setUp(self):
        self.db_path, self.tmp_dir = setup_isolated_db()

    def tearDown(self):
        cleanup_db(self.tmp_dir)

    @freeze_time("2026-06-01 11:05:00")
    def test_blocks_when_too_close(self):
        """已发1条(5分钟前) → should_act=False 或 score大幅下降"""
        insert_behavior("message_received", minutes_ago=1)
        insert_sent("11:00", "刚才的消息", "test")

        result = run_pipeline()
        d = result["decision"]

        if d["should_act"]:
            self.assertLessEqual(d["score"], 70,
                                 f"距上次5分钟score应<=70，实际={d['score']}")
        else:
            reason = d.get("condition", "") + d.get("reason", "")
            self.assertTrue(any(kw in reason for kw in ["分钟", "间隔", "距上次", "score"]),
                            f"阻止原因应与距离相关: {reason}")


class TestScenario4_LateNight(unittest.TestCase):
    """场景4: 深夜 → 硬条件阻止"""

    def setUp(self):
        self.db_path, self.tmp_dir = setup_isolated_db()

    def tearDown(self):
        cleanup_db(self.tmp_dir)

    @freeze_time("2026-06-01 23:30:00")
    def test_blocks_at_23_30(self):
        """深夜23:30 → should_act=False"""
        insert_behavior("message_received", minutes_ago=10)
        result = run_pipeline()
        self.assertFalse(result["decision"]["should_act"],
                         f"深夜应阻止: {result['decision']}")

    @freeze_time("2026-06-01 03:00:00")
    def test_blocks_at_3am(self):
        """凌晨3点 → should_act=False"""
        result = run_pipeline()
        self.assertFalse(result["decision"]["should_act"],
                         f"凌晨3点应阻止: {result['decision']}")


class TestScenario5_AntiHallucination(unittest.TestCase):
    """场景5: today_sent 数据真实性验证"""

    def setUp(self):
        self.db_path, self.tmp_dir = setup_isolated_db()

    def tearDown(self):
        cleanup_db(self.tmp_dir)

    @freeze_time("2026-06-01 10:00:00")
    def test_empty_today_sent(self):
        """空DB → today_sent必须为空数组"""
        insert_behavior("message_received", minutes_ago=30)
        result = run_pipeline()

        self.assertIn("today_sent", result)
        self.assertEqual(len(result["today_sent"]), 0)

    @freeze_time("2026-06-01 10:00:00")
    def test_today_sent_matches_reality(self):
        """发1条 → today_sent恰好有1条"""
        insert_behavior("message_received", minutes_ago=30)
        insert_sent("09:00", "真实的早安", "morning")

        result = run_pipeline()

        self.assertEqual(len(result["today_sent"]), 1)
        self.assertIn("真实的早安", result["today_sent"][0]["msg"])

    @freeze_time("2026-06-01 10:00:00")
    def test_hallucination_blocked(self):
        """如果跳过原因提到'已发送'，today_sent必须非空"""
        insert_behavior("message_received", minutes_ago=30)
        result = run_pipeline()

        d = result["decision"]
        if not d["should_act"]:
            reason = d.get("condition", "") + d.get("reason", "")
            if any(kw in reason for kw in ["已发送", "发过", "距上次"]):
                self.assertGreater(len(result["today_sent"]), 0,
                                   f"幻觉检测：原因提到'已发送'但today_sent为空: {reason}")


class TestScenario6_DailyLimit(unittest.TestCase):
    """场景6: 今日达上限 → 阻止"""

    def setUp(self):
        self.db_path, self.tmp_dir = setup_isolated_db()

    def tearDown(self):
        cleanup_db(self.tmp_dir)

    @freeze_time("2026-06-01 15:00:00")
    def test_blocks_after_6_messages(self):
        """发满6条 → should_act=False"""
        insert_behavior("message_received", minutes_ago=30)
        for i in range(6):
            insert_sent(f"0{8+i}:00", f"消息{i}", f"r{i}")

        result = run_pipeline()
        self.assertFalse(result["decision"]["should_act"],
                         f"满6条应阻止: {result['decision']}")


class TestScenario7_PersonaVoice(unittest.TestCase):
    """场景7: 花火人设一致性"""

    def setUp(self):
        self.db_path, self.tmp_dir = setup_isolated_db()

    def tearDown(self):
        cleanup_db(self.tmp_dir)

    @freeze_time("2026-06-01 14:00:00")
    def test_message_has_tilde(self):
        """消息应包含~或…（花火特征）"""
        insert_behavior("message_received", minutes_ago=60)
        result = run_pipeline()

        if result["decision"]["should_act"] and result["decision"]["proposed_message"]:
            msg = result["decision"]["proposed_message"]
            self.assertTrue(any(c in msg for c in ["~", "…"]),
                            f"消息应有花火特征: {msg[:80]}")
            self.assertFalse(any(kw in msg for kw in ["请问", "不好意思", "麻烦您"]),
                             f"消息不应含禁用词: {msg[:80]}")


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
