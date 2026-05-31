"""一键安装器 - 协调所有组件完成接入

流程:
1. 环境检测
2. 健康检查
3. 数据库初始化
4. 配置生成
5. Cron Job 注册
6. Skill 创建
7. 验证测试
"""
import os
import sys
import json
import time
from typing import Dict, Optional

# 确保项目根目录在 path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from setup.notifier import Notifier
from setup.health_checker import HealthChecker
from setup.adapter import AutoAdapter
from core.database import init_db, get_db_path


class Installer:
    """一键安装器"""

    def __init__(self, project_root: str = None, platform: str = None,
                 chat_id: str = None, skip_checks: bool = False,
                 verbose: bool = False):
        self.project_root = project_root or PROJECT_ROOT
        self.skip_checks = skip_checks
        self.verbose = verbose

        # 初始化通知器
        self.notifier = Notifier(platform=platform, chat_id=chat_id)

        # 初始化组件
        self.adapter = AutoAdapter(self.project_root)
        self.health_checker = HealthChecker(self.project_root)

        # 安装结果
        self.results = {
            "steps": [],
            "success": False,
            "error": None,
        }

    def install(self) -> bool:
        """执行完整安装流程"""
        total_steps = 6

        try:
            # 步骤 1: 环境检测
            self.notifier.start_step(1, total_steps, "环境检测")
            env_info = self._check_environment()
            self.notifier.complete_step(1, "环境检测", f"Python {env_info['python_version']}")

            # 步骤 2: 健康检查
            self.notifier.start_step(2, total_steps, "健康检查")
            can_proceed, reason = self._run_health_checks()
            if not can_proceed:
                self.notifier.fail_step(2, "健康检查", reason)
                self.results["error"] = reason
                return False
            self.notifier.complete_step(2, "健康检查", "所有检查通过")

            # 步骤 3: 数据库初始化
            self.notifier.start_step(3, total_steps, "数据库初始化")
            db_path = self._init_database()
            self.notifier.complete_step(3, "数据库初始化", db_path)

            # 步骤 4: 配置生成
            self.notifier.start_step(4, total_steps, "配置生成")
            config_path = self._generate_config()
            self.notifier.complete_step(4, "配置生成", config_path)

            # 步骤 5: Cron Job 定义
            self.notifier.start_step(5, total_steps, "Cron Job 定义")
            cron_jobs = self._generate_cron_jobs()
            self.notifier.complete_step(5, "Cron Job 定义", f"{len(cron_jobs)} 个任务")

            # 步骤 6: 验证测试
            self.notifier.start_step(6, total_steps, "验证测试")
            self._run_verification()
            self.notifier.complete_step(6, "验证测试", "全部通过")

            # 安装成功
            self.results["success"] = True
            summary = self._generate_summary()
            self.notifier.finish_success(summary)
            return True

        except Exception as e:
            self.results["error"] = str(e)
            self.notifier.finish_failure(str(e))
            return False

    def _check_environment(self) -> Dict:
        """检查环境"""
        return self.adapter.env

    def _run_health_checks(self) -> tuple:
        """运行健康检查"""
        results = self.health_checker.run_all(self.skip_checks)

        for r in results:
            if not r.passed:
                if r.critical:
                    return False, f"关键检查失败: {r.name} - {r.message}"
                else:
                    self.notifier.warn(f"非关键检查失败: {r.name} - {r.message}")

        return True, "所有检查通过"

    def _init_database(self) -> str:
        """初始化数据库"""
        init_db()
        return get_db_path()

    def _generate_config(self) -> str:
        """生成配置"""
        return self.adapter.write_integration_config()

    def _generate_cron_jobs(self) -> list:
        """生成 Cron Job 定义"""
        jobs = self.adapter.generate_cron_jobs()

        # 写入 cron_jobs.json 供后续使用
        jobs_path = os.path.join(self.project_root, "setup", "cron_jobs.json")
        with open(jobs_path, "w") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

        return jobs

    def _run_verification(self):
        """运行验证测试"""
        # 测试数据库
        from core.database import query
        tables = query("SELECT name FROM sqlite_master WHERE type='table'")
        if len(tables) < 8:
            raise Exception(f"数据库表不完整: {len(tables)}/8")

        # 测试角色系统
        from personality.character_manager import CharacterManager
        cm = CharacterManager("sparkle")
        if not cm.name:
            raise Exception("角色系统加载失败")

        # 测试引擎
        from core.engine import ProactiveEngine
        engine = ProactiveEngine()
        context = engine.get_context()
        if "activity" not in context:
            raise Exception("引擎初始化失败")

        # 测试消息生成
        greeting = engine.personality.get_greeting(3, 1)
        if not greeting:
            raise Exception("消息生成失败")

    def _generate_summary(self) -> str:
        """生成安装摘要"""
        cron_jobs = self.adapter.generate_cron_jobs()
        db_path = get_db_path()

        summary = f"""📦 安装详情:
• 数据库: {db_path}
• 配置: {self.project_root}/config/config.yaml
• Cron Jobs: {len(cron_jobs)} 个
• 角色: 花火 (假面愚者)

📋 Cron Job 列表:
"""
        for job in cron_jobs:
            summary += f"  • {job['name']} ({job['schedule']})\n"

        return summary

    def uninstall(self) -> bool:
        """卸载（清理）"""
        try:
            # 清理数据库
            db_path = get_db_path()
            if os.path.exists(db_path):
                os.remove(db_path)

            # 清理配置
            config_path = os.path.join(self.project_root, "setup", "integration.json")
            if os.path.exists(config_path):
                os.remove(config_path)

            # 清理 cron jobs 定义
            jobs_path = os.path.join(self.project_root, "setup", "cron_jobs.json")
            if os.path.exists(jobs_path):
                os.remove(jobs_path)

            self.notifier.send("🗑️ 卸载完成")
            return True
        except Exception as e:
            self.notifier.send(f"❌ 卸载失败: {e}")
            return False
