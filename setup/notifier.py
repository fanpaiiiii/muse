"""进度推送器 - 通过 Telegram/Feishu 推送安装进度

支持:
- 实时进度推送
- 分步骤通知
- 成功/失败通知
- 自动检测可用平台
"""
import json
import os
import subprocess
import time
from datetime import datetime
from typing import Optional, Dict, List


class Notifier:
    """跨平台进度推送器"""

    def __init__(self, platform: str = None, chat_id: str = None):
        """
        Args:
            platform: 推送平台 (telegram/feishu/auto)
            chat_id: 目标聊天 ID
        """
        self.platform = platform or self._detect_platform()
        self.chat_id = chat_id or self._detect_chat_id()
        self.bot_token = self._load_bot_token()
        self.steps: List[Dict] = []
        self.start_time = time.time()

    def _detect_platform(self) -> str:
        """自动检测可用平台"""
        # 优先 Telegram
        if os.environ.get("TELEGRAM_BOT_TOKEN") or self._find_telegram_token():
            return "telegram"
        # 其次 Feishu
        if os.environ.get("FEISHU_APP_ID"):
            return "feishu"
        return "local"  # 本地输出

    def _detect_chat_id(self) -> str:
        """自动检测聊天 ID"""
        if self.platform == "telegram":
            return os.environ.get("TELEGRAM_CHAT_ID", "8081746929")
        elif self.platform == "feishu":
            return os.environ.get("FEISHU_CHAT_ID", "oc_1912d157b6a06e3c302de81d5fc6e206")
        return ""

    def _find_telegram_token(self) -> Optional[str]:
        """从 Hermes 配置中查找 Telegram token"""
        env_file = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        return line.strip().split("=", 1)[1]
        return None

    def _load_bot_token(self) -> Optional[str]:
        """加载 bot token"""
        if self.platform == "telegram":
            return self._find_telegram_token()
        elif self.platform == "feishu":
            return os.environ.get("FEISHU_APP_SECRET")
        return None

    def send(self, message: str, level: str = "info"):
        """发送消息"""
        if self.platform == "telegram":
            self._send_telegram(message)
        elif self.platform == "feishu":
            self._send_feishu(message)
        else:
            self._send_local(message)

    def _send_telegram(self, message: str):
        """通过 Telegram Bot API 发送"""
        token = self.bot_token
        if not token:
            self._send_local(message)
            return

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        try:
            result = subprocess.run(
                ["curl", "-s", "-X", "POST", url, "-H", "Content-Type: application/json",
                 "-d", json.dumps(payload)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                self._send_local(message)
        except Exception:
            self._send_local(message)

    def _send_feishu(self, message: str):
        """通过飞书发送"""
        # 飞书需要先获取 token，这里简化处理
        self._send_local(f"[Feishu] {message}")

    def _send_local(self, message: str):
        """本地输出"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    # === 进度追踪 ===

    def start_step(self, step_num: int, total: int, name: str):
        """开始一个步骤"""
        self.current_step = step_num
        self.total_steps = total
        emoji = self._step_emoji(step_num, total)
        msg = f"{emoji} [{step_num}/{total}] {name}..."
        self.send(msg)
        self.steps.append({"name": name, "status": "running", "start": time.time()})

    def complete_step(self, step_num: int, name: str, detail: str = ""):
        """完成一个步骤"""
        emoji = "✅"
        msg = f"{emoji} [{step_num}/{self.total_steps}] {name} 完成"
        if detail:
            msg += f" — {detail}"
        self.send(msg)
        if self.steps and self.steps[-1]["name"] == name:
            self.steps[-1]["status"] = "done"
            self.steps[-1]["end"] = time.time()

    def fail_step(self, step_num: int, name: str, error: str):
        """步骤失败"""
        emoji = "❌"
        msg = f"{emoji} [{step_num}/{self.total_steps}] {name} 失败\n原因: {error}"
        self.send(msg)
        if self.steps and self.steps[-1]["name"] == name:
            self.steps[-1]["status"] = "failed"
            self.steps[-1]["error"] = error

    def skip_step(self, step_num: int, name: str, reason: str):
        """跳过步骤"""
        emoji = "⏭️"
        msg = f"{emoji} [{step_num}/{self.total_steps}] {name} 跳过 — {reason}"
        self.send(msg)

    def warn(self, message: str):
        """发送警告"""
        self.send(f"⚠️ {message}")

    def info(self, message: str):
        """发送信息"""
        self.send(f"ℹ️ {message}")

    # === 完成通知 ===

    def finish_success(self, summary: str = ""):
        """安装成功"""
        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        done = sum(1 for s in self.steps if s["status"] == "done")
        total = len(self.steps)

        msg = f"""🎉 接入完成！

📊 结果: {done}/{total} 步骤成功
⏱️ 耗时: {minutes}分{seconds}秒
🎭 角色: 花火 (假面愚者)

{summary}

💡 下一步:
• 手动测试: python cron_runner.py --prompt N2
• 查看统计: python cron_runner.py --stats
• 守护进程: python cron_runner.py --daemon"""
        self.send(msg)

    def finish_failure(self, error: str):
        """安装失败"""
        msg = f"""❌ 接入失败

原因: {error}

🔧 修复建议:
1. 检查日志: cat /root/.hermes/projects/muse/setup.log
2. 手动运行: python setup.py --verbose
3. 跳过问题: python setup.py --skip-checks"""
        self.send(msg)

    def _step_emoji(self, current: int, total: int) -> str:
        """步骤进度 emoji"""
        progress = current / total
        if progress < 0.25:
            return "🔹"
        elif progress < 0.5:
            return "🔶"
        elif progress < 0.75:
            return "🔷"
        else:
            return "🔸"
