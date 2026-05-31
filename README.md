# Muse

## 概述
一个模块化的主动对话系统，能够：
- 从对话中自动提取待办任务
- 分析用户活跃模式
- 在合适时机主动发送提醒和汇总
- 通过学习优化交互体验

## 架构
```
muse/
├── config/config.yaml      # 系统配置
├── core/                    # 核心模块
│   ├── database.py         # SQLite 数据库层
│   ├── config_loader.py    # 配置加载器
│   └── engine.py           # 核心引擎
├── perception/              # 感知模块
│   ├── task_extractor.py   # 任务提取器
│   └── activity_analyzer.py # 活动分析器
├── task/                    # 任务模块
│   └── task_manager.py     # 任务管理器
├── personality/             # 人格模块
│   └── system_prompt.py    # 系统提示和人格定义
├── scheduler/               # 调度模块
│   ├── node_scheduler.py   # 节点调度器
│   ├── state_lock.py       # 状态锁
│   └── dedup_engine.py     # 去重引擎
├── delivery/                # 投递模块
│   └── message_deliverer.py # 消息投递器
├── learning/                # 学习模块
│   └── preference_learner.py # 偏好学习器
├── tests/                   # 测试套件
│   └── test_engine.py
├── data/                    # 数据目录
│   └── proactive.db        # SQLite 数据库
├── cron_runner.py          # Cron 运行器（入口）
└── cli.py                  # CLI 工具
```

## 快速开始

### 1. 运行测试
```bash
cd /root/.hermes/projects/muse
python -m pytest tests/ -v
# 或
python tests/test_engine.py
```

### 2. CLI 使用
```bash
# 添加任务
python cli.py add-task "明天开会" --priority 7

# 查看任务
python cli.py list-tasks
python cli.py list-tasks --overdue

# 完成/取消任务
python cli.py complete 1
python cli.py cancel 2

# 处理文本（自动提取任务）
python cli.py process "提醒我明天下午3点开会，赶紧准备PPT"

# 查看统计
python cli.py stats
```

### 3. Cron Runner
```bash
# 检查当前应触发的节点
python cron_runner.py

# 强制触发指定节点
python cron_runner.py --node N2

# 守护进程模式
python cron_runner.py --daemon

# 查看统计
python cron_runner.py --stats
```

## 节点说明
| 节点 | 时间 | 类型 | 用途 |
|------|------|------|------|
| N1 | 07:00 | memory_recall | 早间简报 |
| N2 | 09:00 | task_reminder | 任务推送 |
| N3 | 10:00 | wellness | 休息检查 |
| N4 | 11:00 | task_reminder | 午间回顾 |
| N5 | 12:00 | social | 午间互动 |
| N6 | 14:00 | task_reminder | 下午推送 |
| N7 | 17:00 | summary | 收工汇总 |
| N8 | 20:00 | reflection | 晚间回顾 |
| N9 | 23:00 | summary | 睡前简报 |

## 配置
编辑 `config/config.yaml` 可自定义：
- 调度节点时间
- 人格风格
- 投递平台
- 感知关键词
- 去重窗口
