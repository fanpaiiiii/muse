"""健康检查器 - 验证所有组件是否就绪

检查项:
1. Python 环境
2. 依赖包
3. Hermes 连接
4. 数据库
5. 配置文件
6. Cron Job 系统
7. 消息平台
"""
import os
import sys
import subprocess
import importlib
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    critical: bool = True  # 是否关键检查


class HealthChecker:
    """系统健康检查器"""

    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.results: List[CheckResult] = []

    def run_all(self, skip_checks: bool = False) -> List[CheckResult]:
        """运行所有检查"""
        self.results = []

        checks = [
            ("python_version", self.check_python_version),
            ("dependencies", self.check_dependencies),
            ("hermes_home", self.check_hermes_home),
            ("database_path", self.check_database_path),
            ("config_file", self.check_config_file),
            ("character_system", self.check_character_system),
            ("cron_system", self.check_cron_system),
            ("telegram", self.check_telegram),
        ]

        if skip_checks:
            return [CheckResult("skipped", True, "检查已跳过", critical=False)]

        for name, check_fn in checks:
            try:
                result = check_fn()
                self.results.append(result)
            except Exception as e:
                self.results.append(CheckResult(name, False, f"异常: {e}", critical=True))

        return self.results

    def check_python_version(self) -> CheckResult:
        """检查 Python 版本"""
        version = sys.version_info
        if version.major == 3 and version.minor >= 10:
            return CheckResult("python_version", True, f"Python {version.major}.{version.minor}.{version.micro}")
        return CheckResult("python_version", False, f"Python {version.major}.{version.minor} 需要 3.10+")

    def check_dependencies(self) -> CheckResult:
        """检查依赖包"""
        required = ["yaml", "sqlite3", "json", "hashlib", "importlib"]
        missing = []
        for pkg in required:
            try:
                importlib.import_module(pkg)
            except ImportError:
                missing.append(pkg)

        if missing:
            return CheckResult("dependencies", False, f"缺少: {', '.join(missing)}")
        return CheckResult("dependencies", True, "所有依赖可用")

    def check_hermes_home(self) -> CheckResult:
        """检查 Hermes 目录"""
        hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
        if os.path.isdir(hermes_home):
            config = os.path.join(hermes_home, "config.yaml")
            if os.path.exists(config):
                return CheckResult("hermes_home", True, hermes_home)
            return CheckResult("hermes_home", False, f"配置文件不存在: {config}")
        return CheckResult("hermes_home", False, f"Hermes 目录不存在: {hermes_home}")

    def check_database_path(self) -> CheckResult:
        """检查数据库路径"""
        hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
        db_dir = os.path.join(hermes_home, "data", "proactive")
        try:
            os.makedirs(db_dir, exist_ok=True)
            # 测试写入权限
            test_file = os.path.join(db_dir, ".test")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            return CheckResult("database_path", True, db_dir)
        except Exception as e:
            return CheckResult("database_path", False, f"无法写入: {e}")

    def check_config_file(self) -> CheckResult:
        """检查配置文件"""
        config_path = os.path.join(self.project_root, "config", "config.yaml")
        if os.path.exists(config_path):
            import yaml
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            if "character" in config and "nodes" in config:
                return CheckResult("config_file", True, f"角色: {config['character'].get('id', 'unknown')}")
            return CheckResult("config_file", False, "配置文件格式错误")
        return CheckResult("config_file", False, f"配置文件不存在: {config_path}")

    def check_character_system(self) -> CheckResult:
        """检查角色系统"""
        try:
            sys.path.insert(0, self.project_root)
            from personality.character_manager import CharacterManager
            cm = CharacterManager("sparkle")
            return CheckResult("character_system", True, f"角色: {cm.name}")
        except Exception as e:
            return CheckResult("character_system", False, f"角色系统异常: {e}")

    def check_cron_system(self) -> CheckResult:
        """检查 Cron 系统"""
        hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
        cron_config = os.path.join(hermes_home, "config.yaml")
        if os.path.exists(cron_config):
            import yaml
            with open(cron_config, "r") as f:
                config = yaml.safe_load(f)
            cron = config.get("cron", {})
            if cron.get("max_parallel_jobs") is not None or cron.get("wrap_response"):
                return CheckResult("cron_system", True, "Cron 系统可用")
            return CheckResult("cron_system", True, "Cron 系统默认配置")
        return CheckResult("cron_system", False, "Hermes 配置不存在")

    def check_telegram(self) -> CheckResult:
        """检查 Telegram 连接"""
        env_file = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                content = f.read()
            if "TELEGRAM_BOT_TOKEN=" in content:
                # 提取 token 并验证格式
                for line in content.split("\n"):
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        token = line.split("=", 1)[1]
                        if ":" in token and len(token) > 20:
                            return CheckResult("telegram", True, "Bot Token 已配置")
                        return CheckResult("telegram", False, "Bot Token 格式错误")
        return CheckResult("telegram", False, "未找到 Telegram Bot Token")

    def get_summary(self) -> str:
        """获取检查摘要"""
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        critical_failed = [r for r in self.results if not r.passed and r.critical]

        lines = [f"健康检查: {passed}/{total} 通过"]
        for r in self.results:
            status = "✅" if r.passed else "❌"
            lines.append(f"  {status} {r.name}: {r.message}")

        if critical_failed:
            lines.append(f"\n⚠️ {len(critical_failed)} 个关键检查失败")

        return "\n".join(lines)

    def can_proceed(self) -> Tuple[bool, str]:
        """判断是否可以继续安装"""
        critical_failed = [r for r in self.results if not r.passed and r.critical]
        if critical_failed:
            reasons = [f"{r.name}: {r.message}" for r in critical_failed]
            return False, "关键检查失败:\n" + "\n".join(reasons)
        return True, "所有关键检查通过"
