"""自适应配置器 - 根据环境自动生成配置

功能:
- 检测当前环境
- 自动配置路径
- 生成 Hermes 集成配置
- 创建 Cron Job 定义
"""
import os
import yaml
from datetime import datetime
from typing import Dict, List, Optional


class AutoAdapter:
    """自适应配置器"""

    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
        self.env = self._detect_environment()

    def _detect_environment(self) -> Dict:
        """检测当前环境"""
        env = {
            "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
            "hermes_home": self.hermes_home,
            "project_root": self.project_root,
            "platform": "linux",
            "user": os.environ.get("USER", "root"),
        }

        # 检测平台
        if os.path.exists("/root/.hermes"):
            env["platform"] = "hermes_server"

        # 检测 Telegram
        env_file = os.path.join(self.hermes_home, ".env")
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        env["telegram_token"] = line.strip().split("=", 1)[1]
                    elif line.startswith("TELEGRAM_CHAT_ID="):
                        env["telegram_chat_id"] = line.strip().split("=", 1)[1]

        # 检测飞书
        if os.environ.get("FEISHU_APP_ID"):
            env["feishu_enabled"] = True

        return env

    def generate_cron_jobs(self) -> List[Dict]:
        """生成 Cron Job 定义"""
        script_path = os.path.join(self.project_root, "cron_runner.py")

        jobs = []
        nodes = {
            "N1": {"schedule": "0 7 * * *", "name": "早间简报"},
            "N2": {"schedule": "0 9 * * *", "name": "任务推送"},
            "N3": {"schedule": "0 10 * * 1-5", "name": "休息检查"},
            "N4": {"schedule": "0 11 * * 1-5", "name": "午间回顾"},
            "N5": {"schedule": "0 12 * * *", "name": "午间互动"},
            "N6": {"schedule": "0 14 * * 1-5", "name": "下午推送"},
            "N7": {"schedule": "0 17 * * 1-5", "name": "收工汇总"},
            "N8": {"schedule": "0 20 * * *", "name": "晚间回顾"},
            "N9": {"schedule": "0 23 * * *", "name": "睡前简报"},
        }

        for node_id, config in nodes.items():
            jobs.append({
                "name": f"proactive-{node_id.lower()}",
                "schedule": config["schedule"],
                "prompt": f"""你是一个主动对话系统。请执行以下操作：

1. 运行检查脚本获取当前状态:
   cd {self.project_root} && python cron_runner.py --prompt {node_id}

2. 根据输出决定是否发送消息

3. 如果有消息，使用 send_message 发送到 telegram

注意：如果脚本输出为空，则不发送任何消息。""",
                "deliver": "telegram",
                "skills": [],
                "enabled_toolsets": ["terminal", "file"],
            })

        return jobs

    def generate_skill_definition(self) -> Dict:
        """生成 Hermes Skill 定义"""
        return {
            "name": "muse",
            "description": "Muse - 角色化智能助手",
            "category": "hermes",
            "version": "1.0.0",
            "skill_md": f"""---
name: muse
description: Muse，支持角色化人格和智能任务管理
category: hermes
---

# Muse

## 功能
- 自动从对话中提取任务
- 在合适时机主动发送提醒
- 角色化人格（花火/假面愚者）
- 智能调度和去重

## 使用

### 查看状态
```bash
cd {self.project_root}
python cron_runner.py --stats
```

### 手动触发
```bash
python cron_runner.py --node N2
```

### 处理文本
```bash
python cli.py process "提醒我明天开会"
```

### 添加任务
```bash
python cli.py add-task "准备PPT" --priority 8
```

## 角色
当前角色: 花火 (假面愚者)
切换角色: 修改 config/config.yaml 中的 character.id
""",
        }

    def write_integration_config(self) -> str:
        """写入集成配置文件"""
        config = {
            "version": "1.0.0",
            "installed_at": datetime.now().isoformat(),
            "project_root": self.project_root,
            "hermes_home": self.hermes_home,
            "character": "sparkle",
            "database": os.path.join(self.hermes_home, "data", "proactive", "proactive.db"),
            "cron_jobs": [j["name"] for j in self.generate_cron_jobs()],
            "platforms": {
                "telegram": self.env.get("telegram_token") is not None,
                "feishu": self.env.get("feishu_enabled", False),
            },
        }

        config_path = os.path.join(self.project_root, "setup", "integration.json")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        return config_path
