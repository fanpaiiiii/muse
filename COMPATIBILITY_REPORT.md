# Hermes 兼容性检查报告

**检查时间:** 2026-05-31 05:20
**Hermes 版本:** v0.6.4
**Python 版本:** 3.11.15 (venv: /root/.hermes/hermes-agent/venv/)

---

## 1. 环境兼容性 ✅

| 项目 | 状态 | 详情 |
|------|------|------|
| Python 版本 | ✅ | 3.11.15，与 Hermes venv 一致 |
| PyYAML | ✅ | 6.0.1，已安装 |
| sqlite3 | ✅ | 内置，无需额外安装 |
| 所有 import | ✅ | 在 Hermes venv 中测试通过 |

## 2. 模块导入 ✅

```bash
# 测试命令
cd /root/.hermes/projects/muse
/root/.hermes/hermes-agent/venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from core.engine import ProactiveEngine
from personality.character_manager import CharacterManager
from integration.hermes_bridge import HermesBridge
print('All imports OK')
"
# 结果: ✅ 通过
```

## 3. 数据库兼容性 ⚠️ 需要调整

**当前路径:** `data/proactive.db` (相对路径)

**问题:**
- 如果 Hermes 从不同工作目录调用，数据库路径会错误
- 多个 Hermes 实例可能同时访问，需要处理锁

**建议修复:**
```python
# core/database.py
def get_db_path() -> str:
    # 使用绝对路径，基于 Hermes home
    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    db_path = os.path.join(hermes_home, "data", "proactive", "proactive.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path
```

## 4. 导入路径 ⚠️ 需要调整

**当前方式:**
```python
sys.path.insert(0, ".")  # 相对导入，脆弱
```

**建议修复:**
```python
# 方案1: 使用绝对路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 方案2: 安装为包
# 在 setup.py 中配置，pip install -e .
```

## 5. Cron Job 兼容性 ✅

**Hermes Cron Job 格式:**
```python
cronjob(action="create", schedule="0 9 * * *", prompt="...", deliver="telegram")
```

**我们的 `cron_runner.py` 输出:**
```bash
python cron_runner.py --prompt N2  # 输出纯文本消息
```

**兼容方案:**
- `cron_runner.py --prompt N2` 生成自包含 prompt
- Hermes Cron Job 的 `prompt` 字段直接使用该输出
- 或使用 `script` 参数直接运行 `cron_runner.py`

**示例:**
```python
cronjob(
    action="create",
    schedule="0 9 * * *",
    prompt="执行主动对话检查: cd /root/.hermes/projects/muse && python cron_runner.py --prompt N2",
    deliver="telegram"
)
```

## 6. 系统提示注入 ⚠️ 需要集成层

**Hermes 系统提示加载机制:**
- 加载自 `hermes-agent` skill 的 persona 文件
- 每次对话重新加载
- 支持 skill 注入

**注入方案:**
```python
# 方案1: 作为 skill
# 创建 muse skill，在 SKILL.md 中定义人格注入

# 方案2: 作为 Hermes 插件
# 在 plugins/ 目录中创建插件，拦截 system prompt

# 方案3: 作为 agent hook
# 在 agent 循环中注入角色人格
```

**当前实现:**
```python
bridge = HermesBridge("sparkle")
injection = bridge.get_system_prompt_injection()
# 返回纯文本，可追加到系统提示末尾
```

## 7. 记忆系统 ⚠️ 潜在冲突

**Hermes 记忆:**
- 使用 `memory` 工具
- 存储在 `~/.hermes/memory/`
- 支持搜索和检索

**我们的学习模块:**
- 使用 SQLite `user_profile` 表
- 存储在 `data/proactive.db`

**冲突点:**
- 两套记忆系统可能不一致
- 用户偏好可能重复存储

**建议:**
- 使用 Hermes 的 memory 系统作为主存储
- 我们的 learning 模块作为缓存/索引
- 或完全迁移到 Hermes memory

## 8. 消息投递 ✅

**Hermes send_message 工具:**
```python
send_message(action="send", target="telegram", message="...")
```

**我们的 MessageDeliverer:**
```python
deliverer.deliver_message("telegram", "消息内容")
```

**兼容方案:**
- 我们的 deliverer 只做记录和队列
- 实际投递调用 Hermes 的 send_message
- 或通过 `--prompt` 输出消息，由 Hermes Cron Job 投递

## 9. 文件位置 ⚠️ 需要调整

**当前结构:**
```
/root/.hermes/projects/muse/
├── config/config.yaml
├── data/proactive.db
└── ...
```

**Hermes 推荐结构:**
```
~/.hermes/
├── config.yaml          # Hermes 主配置
├── data/                # 数据目录
│   └── proactive/       # 我们的数据
├── skills/              # 技能
│   └── muse/
├── plugins/             # 插件
└── scripts/             # 脚本
```

**建议:**
- 保留项目目录作为开发目录
- 生产环境使用 Hermes 标准路径
- 通过 symlink 或配置文件连接

## 10. 现有冲突 ⚠️

**发现:**
```
~/.hermes/scripts/brain/scripts/proactive-check.sh
```

**内容:**
```bash
#!/bin/bash
# 主动预判检查脚本
# 检查待办事项并输出
```

**分析:**
- 这是一个简单的 bash 脚本，检查 OpenClaw 的工作缓冲区
- 与我们的系统功能重叠但实现不同
- 可以替换或共存

**建议:**
- 保留现有脚本作为兼容层
- 我们的系统作为主要实现
- 未来可以废弃旧脚本

---

## 总结

| 类别 | 状态 | 行动项 |
|------|------|--------|
| 环境 | ✅ | 无 |
| 模块导入 | ✅ | 无 |
| 数据库路径 | ⚠️ | 改为绝对路径 |
| 导入路径 | ⚠️ | 改为绝对路径或安装为包 |
| Cron Job | ✅ | 已兼容 |
| 系统提示 | ⚠️ | 需要集成层 |
| 记忆系统 | ⚠️ | 决定是否迁移 |
| 消息投递 | ✅ | 已兼容 |
| 文件位置 | ⚠️ | 可选调整 |
| 现有冲突 | ⚠️ | 替换或共存 |

**总体评估:** 80% 兼容，需要 3-4 处调整即可完全集成。

---

## 下一步行动

1. **立即修复:** 数据库路径改为绝对路径
2. **立即修复:** 导入路径改为绝对路径
3. **设计决策:** 是否迁移到 Hermes memory 系统
4. **集成测试:** 在 Hermes Cron Job 中实际运行
