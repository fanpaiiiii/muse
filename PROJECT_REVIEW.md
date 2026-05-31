# Muse - 全面检视报告

**检视时间:** 2026-05-31
**项目版本:** v1.0.0
**代码规模:** 40个文件 / 3892行代码 / 27个测试

---

## 一、项目总览

### 核心目标
将 Hermes 从被动工具升级为主动「数字同事」—— 能感知用户行为、自动提取任务、在合适时机主动发起对话。

### 架构层次
```
┌─────────────────────────────────────────────────┐
│                 Hermes Agent                     │
│            (工具 + 能力 + 逻辑)                   │
└─────────────────────┬───────────────────────────┘
                      │ 系统提示注入
┌─────────────────────▼───────────────────────────┐
│              角色人格层 (sparkle)                  │
│         (花火的声音 + 风格 + 行为约束)              │
└─────────────────────┬───────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│              主动对话引擎 (ProactiveEngine)        │
│  ┌──────────┬──────────┬──────────┬──────────┐  │
│  │ 感知模块  │ 任务模块  │ 调度模块  │ 投递模块  │  │
│  └──────────┴──────────┴──────────┴──────────┘  │
│  ┌──────────┬──────────┐                        │
│  │ 学习模块  │ 人格模块  │                        │
│  └──────────┴──────────┘                        │
└─────────────────────┬───────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│              数据层 (SQLite)                      │
│     tasks / behavior_log / user_profile /        │
│     proactive_log / message_queue /              │
│     state_lock / dedup_log / conversation_history│
└─────────────────────────────────────────────────┘
```

---

## 二、功能清单

### 2.1 感知模块 (Perception)

| 功能 | 函数 | 实际逻辑 |
|------|------|----------|
| 任务提取 | `TaskExtractor.extract_tasks()` | 正则匹配关键词 → 按句子拆分 → 提取时间 → 估算优先级 |
| 时间提取 | `TaskExtractor._extract_time()` | 4种模式: "X小时后" / "X分钟后" / "HH:MM" / "明天/下周" |
| 优先级估算 | `TaskExtractor._estimate_priority()` | 基础5分 + 紧急词+3 + deadline+2 + 任务词+1 |
| 去重key生成 | `TaskExtractor.generate_dedup_key()` | MD5(content)[:12] |
| 活跃检测 | `ActivityAnalyzer.is_user_active()` | 查 behavior_log 最近记录，<5分钟=活跃 |
| 活跃上下文 | `ActivityAnalyzer.get_activity_context()` | 返回: 分钟数/是否活跃/是否空闲/今日主动数/今日完成数 |
| 活跃时段分析 | `ActivityAnalyzer.get_active_hours()` | 按小时分组统计 behavior_log |
| 行为记录 | `ActivityAnalyzer.record_event()` | INSERT INTO behavior_log |

### 2.2 任务模块 (Task)

| 功能 | 函数 | 实际逻辑 |
|------|------|----------|
| 添加任务 | `TaskManager.add_task()` | INSERT INTO tasks，自动设 extracted_at |
| 获取任务 | `TaskManager.get_task()` | SELECT * WHERE id = ? |
| 待处理列表 | `TaskManager.get_pending_tasks()` | WHERE status='pending' ORDER BY priority DESC, due_time ASC |
| 逾期任务 | `TaskManager.get_overdue_tasks()` | WHERE due_time < datetime('now') |
| 即将到期 | `TaskManager.get_upcoming_tasks(hours)` | WHERE due_time <= now+hours AND > now |
| 高优先级 | `TaskManager.get_tasks_by_priority(min)` | WHERE priority >= min |
| 完成任务 | `TaskManager.complete_task()` | UPDATE status='completed', completed_at=now |
| 取消任务 | `TaskManager.cancel_task()` | UPDATE status='cancelled' |
| 去重检查 | `TaskManager.check_dedup()` | WHERE dedup_key=? AND extracted_at > 24h内 |
| 任务统计 | `TaskManager.get_task_stats()` | GROUP BY status |
| 清理旧任务 | `TaskManager.cleanup_old_tasks()` | DELETE WHERE updated_at < 30天前 |

### 2.3 调度模块 (Scheduler)

| 功能 | 函数 | 实际逻辑 |
|------|------|----------|
| 节点分析 | `NodeScheduler.analyze_node()` | 6层检查: 锁→活跃→上限→冷却→去重→触发 |
| 节点触发 | `NodeScheduler.execute_node_analysis()` | 获取锁+记录去重+返回触发状态 |
| 到期节点 | `NodeScheduler.get_due_nodes()` | 当前小时 ±1 小时内的节点 |
| 状态锁获取 | `StateLock.acquire()` | 检查无锁→INSERT锁→设过期时间 |
| 状态锁释放 | `StateLock.release()` | DELETE WHERE id=1 |
| 状态锁检测 | `StateLock.is_locked()` | WHERE expires_at > now |
| 去重检查 | `DedupEngine.is_duplicate()` | WHERE key=? AND created_at > 24h内 |
| 去重记录 | `DedupEngine.record()` | INSERT INTO dedup_log |
| 去重清理 | `DedupEngine.cleanup()` | DELETE WHERE created_at < 7天前 |

### 2.4 投递模块 (Delivery)

| 功能 | 函数 | 实际逻辑 |
|------|------|----------|
| 消息入队 | `MessageDeliverer.queue_message()` | INSERT INTO message_queue |
| 获取待发 | `MessageDeliverer.get_pending_messages()` | WHERE status='queued' AND scheduled_at <= now |
| 标记发送 | `MessageDeliverer.mark_sent()` | UPDATE status='sent', sent_at=now |
| 标记失败 | `MessageDeliverer.mark_failed()` | retry_count+1, 超max则failed否则重试 |
| 直接投递 | `MessageDeliverer.deliver_message()` | 记录proactive_log + print到stdout |
| 重试投递 | `MessageDeliverer.deliver_with_retry()` | 最多3次，间隔30秒 |
| 投递统计 | `MessageDeliverer.get_today_stats()` | GROUP BY status WHERE today |

### 2.5 人格模块 (Personality)

| 功能 | 函数 | 实际逻辑 |
|------|------|----------|
| 角色加载 | `CharacterManager.load_character()` | importlib动态加载characters/xxx.py |
| 系统提示 | `CharacterManager.get_system_prompt()` | 拼接: 性格+说话方式+行为规则+约束 |
| 问候生成 | `CharacterPersonality.get_greeting()` | random.choice模板 + format |
| 任务提醒 | `CharacterPersonality.get_task_reminder()` | random.choice模板 + format |
| 工作汇总 | `CharacterPersonality.get_summary()` | 计算score + random.choice模板 |
| 休息提醒 | `CharacterPersonality.get_wellness_check()` | random.choice模板 |
| 晚间回顾 | `CharacterPersonality.get_evening_reflection()` | random.choice模板 |
| 社交消息 | `CharacterPersonality.get_social_message()` | random.choice模板 |
| 随机消息 | `CharacterPersonality.get_random_message()` | random.choice模板 |
| 情境回复 | `CharacterPersonality.get_situation_response()` | 根据situation规则选择消息 |
| 发送判断 | `CharacterPersonality.should_deliver()` | 检查: 冷却+每日上限 |
| 幽默度 | `CharacterPersonality.get_humor_level()` | 根据情境动态调整0-1 |
| 用户适配 | `CharacterPersonality.adapt_to_user()` | 根据偏好调整行为约束 |

### 2.6 学习模块 (Learning)

| 功能 | 函数 | 实际逻辑 |
|------|------|----------|
| 记录交互 | `PreferenceLearner.record_event()` | INSERT INTO behavior_log |
| 记录对话 | `PreferenceLearner.record_conversation()` | INSERT INTO conversation_history |
| 更新偏好 | `PreferenceLearner.update_preference()` | INSERT OR UPDATE user_profile |
| 获取偏好 | `PreferenceLearner.get_preference()` | SELECT WHERE key=? |
| 活跃分析 | `PreferenceLearner.analyze_active_hours()` | 按小时分组+计算avg+分peak/quiet |
| 回复分析 | `PreferenceLearner.analyze_response_patterns()` | 统计消息长度和数量 |
| 任务学习 | `PreferenceLearner.learn_from_task_completion()` | 对比due_time和completed_at |
| 每日摘要 | `PreferenceLearner.get_daily_summary()` | 4个COUNT查询 |
| 学习统计 | `PreferenceLearner.get_learning_stats()` | 偏好数/近期行为/近期对话 |

### 2.7 核心引擎 (Engine)

| 功能 | 函数 | 实际逻辑 |
|------|------|----------|
| 消息处理 | `ProactiveEngine.process_message()` | 记录行为+记录对话+提取任务+去重+存储 |
| 节点分析 | `ProactiveEngine.analyze_node()` | 委托给NodeScheduler |
| 上下文获取 | `ProactiveEngine.get_context()` | 汇总: activity+task_stats+overdue+upcoming+high_priority |
| 早间简报 | `ProactiveEngine._generate_morning_brief()` | 调用personality.get_greeting() |
| 任务提醒 | `ProactiveEngine._generate_task_reminder()` | 优先级: 逾期>即将到期>高优先级 |
| 工作汇总 | `ProactiveEngine._generate_summary()` | 调用personality.get_summary() |
| 休息检查 | `ProactiveEngine._generate_wellness_check()` | 分析最近10条消息时间跨度，>2小时则提醒 |
| 社交互动 | `ProactiveEngine._generate_social()` | 60%概率随机发消息 |
| 晚间回顾 | `ProactiveEngine._generate_reflection()` | 调用personality.get_evening_reflection() |
| 完整节点处理 | `ProactiveEngine.process_node()` | 分析→生成→投递→释放锁 |
| 发送主动消息 | `ProactiveEngine.send_proactive()` | 记录+去重+投递+释放锁 |
| 系统统计 | `ProactiveEngine.get_stats()` | 汇总所有模块统计 |

### 2.8 Hermes 桥接 (Integration)

| 功能 | 函数 | 实际逻辑 |
|------|------|----------|
| 系统提示注入 | `HermesBridge.get_system_prompt_injection()` | 生成角色人格文本段落 |
| 完整提示 | `HermesBridge.get_full_system_prompt()` | base_prompt + injection |
| Cron Prompt | `HermesBridge.generate_cron_prompt()` | 角色人格+当前状态+任务详情+指令 |
| 消息处理 | `HermesBridge.process_incoming_message()` | 委托engine.process_message() |
| 情境检测 | `HermesBridge._detect_situation()` | 关键词+时间检测 |
| 格式化投递 | `HermesBridge.format_for_delivery()` | 转为send_message参数格式 |
| 一致性检查 | `HermesBridge.check_response_consistency()` | 检查禁用词+敬语+口癖 |
| 角色切换 | `HermesBridge.switch_character()` | 重新加载character+重建engine |

### 2.9 安装系统 (Setup)

| 功能 | 函数 | 实际逻辑 |
|------|------|----------|
| 进度推送 | `Notifier.send()` | 自动检测平台→curl调用Telegram API |
| 步骤通知 | `Notifier.start_step/complete_step/fail_step()` | 格式化emoji+进度+详情 |
| 完成通知 | `Notifier.finish_success()` | 汇总: 耗时+结果+下一步 |
| 健康检查 | `HealthChecker.run_all()` | 8项检查: python/deps/hermes/db/config/char/cron/telegram |
| 环境检测 | `AutoAdapter._detect_environment()` | Python版本/Hermes路径/平台/Token |
| 配置生成 | `AutoAdapter.write_integration_config()` | 写入integration.json |
| Cron定义 | `AutoAdapter.generate_cron_jobs()` | 生成9个job定义 |
| 安装编排 | `Installer.install()` | 6步流程: 检测→检查→数据库→配置→Cron→验证 |

### 2.10 入口工具

| 工具 | 入口 | 功能 |
|------|------|------|
| `setup.py` | 一键接入 | 环境检测→健康检查→数据库→配置→Cron→验证 |
| `cron_runner.py` | Cron调度 | 检查节点→触发→生成消息→投递 |
| `cli.py` | 命令行 | add-task/list-tasks/complete/cancel/stats/process |

---

## 三、数据流

### 3.1 被动消息处理流
```
用户发消息
    ↓
Hermes 收到
    ↓
HermesBridge.process_incoming_message()
    ↓
├── activity.record_event() → behavior_log
├── learner.record_conversation() → conversation_history
├── task_extractor.extract_tasks() → 正则匹配
│   ├── 有任务 → task_manager.add_task() → tasks表
│   └── 无任务 → 跳过
└── _detect_situation() → 情境判断
    ↓
返回: tasks + context + situation
```

### 3.2 主动消息触发流
```
Cron Job 定时触发 (每小时检查)
    ↓
cron_runner.py --prompt N2
    ↓
engine.process_node("N2")
    ↓
scheduler.execute_node_analysis("N2")
    ├── state_lock.is_locked() → 被锁? 拒绝
    ├── activity.get_activity_context()
    │   ├── minutes_since_active < 5 → 拒绝(不打断)
    │   └── today_proactive_count >= 8 → 拒绝(上限)
    ├── last_sent + cooldown > now → 拒绝(冷却)
    ├── dedup.is_duplicate() → 拒绝(重复)
    └── 通过 → 获取锁 + 记录去重
    ↓
engine.generate_proactive_message("N2")
    ├── 根据节点类型选择生成方法
    │   ├── task_reminder → 查逾期/即将到期/高优先级
    │   ├── summary → 查今日完成/剩余
    │   ├── memory_recall → 早间简报
    │   ├── wellness → 分析连续活跃时间
    │   ├── social → 60%概率随机
    │   └── reflection → 晚间回顾
    └── 调用personality对应模板
    ↓
engine.send_proactive("N2", message)
    ├── deliverer.record_proactive() → proactive_log
    ├── dedup.record() → dedup_log
    ├── deliverer.deliver_with_retry() → print到stdout
    └── scheduler.release_lock() → 释放锁
    ↓
Hermes Cron Job 读取stdout → send_message投递
```

### 3.3 角色人格加载流
```
ProactiveEngine(character_id="sparkle")
    ↓
CharacterPersonality("sparkle")
    ↓
CharacterManager("sparkle")
    ↓
importlib.import_module("personality.characters.sparkle")
    ↓
sparkle.get_sparkle_config()
    ↓
返回完整配置: personality_core + speech_style + templates + rules
    ↓
get_system_prompt() → 拼接角色提示文本
pick_message("morning") → random.choice + format
should_deliver(context) → 检查约束条件
```

### 3.4 安装接入流
```
python setup.py
    ↓
Installer.install()
    ↓
[1/6] 环境检测 → AutoAdapter._detect_environment()
    ├── Python版本
    ├── Hermes路径
    └── Telegram Token
    ↓
[2/6] 健康检查 → HealthChecker.run_all()
    ├── python_version ✅
    ├── dependencies ✅
    ├── hermes_home ✅
    ├── database_path ✅
    ├── config_file ✅
    ├── character_system ✅
    ├── cron_system ✅
    └── telegram ✅
    ↓
[3/6] 数据库初始化 → init_db() → 8张表
    ↓
[4/6] 配置生成 → AutoAdapter.write_integration_config()
    ↓
[5/6] Cron Job 定义 → 生成9个job → cron_jobs.json
    ↓
[6/6] 验证测试
    ├── 数据库表完整性
    ├── 角色系统加载
    ├── 引擎初始化
    └── 消息生成
    ↓
Notifer.finish_success() → Telegram推送完成通知
```

---

## 四、数据库表结构

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| tasks | 待办任务 | content, priority, status, due_time, dedup_key |
| behavior_log | 行为日志 | event_type, source, content, metadata |
| user_profile | 用户画像 | key, value, confidence |
| proactive_log | 主动消息记录 | node_id, message, status, platform |
| message_queue | 消息队列 | target, message, priority, retry_count |
| state_lock | 状态锁 | locked_by, expires_at, reason |
| dedup_log | 去重记录 | key, action_type |
| conversation_history | 对话历史 | role, content, platform, session_id |

---

## 五、配置项

```yaml
nodes:          # 9个调度节点 (N1-N9)
character:      # 角色ID (sparkle)
personality:    # 人格风格/口癖/禁忌
delivery:       # 投递配置 (重试/平台)
perception:     # 感知配置 (关键词/阈值)
dedup:          # 去重配置 (窗口/清理)
database:       # 数据库路径
```

---

## 六、Cron Job 定义

| Job | Schedule | 节点 | 类型 | 用途 |
|-----|----------|------|------|------|
| proactive-n1 | 0 7 * * * | N1 | memory_recall | 早间简报 |
| proactive-n2 | 0 9 * * * | N2 | task_reminder | 任务推送 |
| proactive-n3 | 0 10 * * 1-5 | N3 | wellness | 休息检查 |
| proactive-n4 | 0 11 * * 1-5 | N4 | task_reminder | 午间回顾 |
| proactive-n5 | 0 12 * * * | N5 | social | 午间互动 |
| proactive-n6 | 0 14 * * 1-5 | N6 | task_reminder | 下午推送 |
| proactive-n7 | 0 17 * * 1-5 | N7 | summary | 收工汇总 |
| proactive-n8 | 0 20 * * * | N8 | reflection | 晚间回顾 |
| proactive-n9 | 0 23 * * * | N9 | summary | 睡前简报 |

---

## 七、花火角色设定

| 维度 | 内容 |
|------|------|
| 九型人格 | 7w8 (享乐主义者偏挑战者) |
| 开放性 | 0.95 |
| 尽责性 | 0.2 |
| 外向性 | 0.85 |
| 宜人性 | 0.25 |
| 神经质 | 0.15 |
| 口癖 | 嘻嘻~ / 好~戏~开~演~ / 有趣~ / 无聊~ |
| 自称 | 本小姐 / 我 / 花火 |
| 禁用词 | 请问 / 不好意思 / 麻烦您 / 谢谢惠顾 |
| 模板数 | 早安4 + 提醒5 + 汇总4 + 休息3 + 晚间4 + 社交3 + 随机4 = 27条 |
| 情境规则 | 用户上线/任务完成/用户缺席/任务逾期/深夜/用户低落 |

---

## 八、测试覆盖

| 测试类 | 测试数 | 覆盖功能 |
|--------|--------|----------|
| TestDatabase | 1 | 数据库初始化 |
| TestTaskExtractor | 5 | 任务提取/时间/优先级/去重key |
| TestTaskManager | 6 | 增删改查/去重/统计 |
| TestStateLock | 2 | 获取释放/重复获取 |
| TestDedupEngine | 1 | 检查并记录 |
| TestMessageDeliverer | 3 | 入队/发送/记录 |
| TestPreferenceLearner | 3 | 记录/偏好/摘要 |
| TestPersonality | 3 | 系统提示/问候/发送判断 |
| TestProactiveEngine | 3 | 消息处理/上下文/统计 |
| **合计** | **27** | **全部通过** |

---

## 九、实际逻辑总结

### 系统本质
**感知 → 判断 → 行动** 闭环:

1. **感知**: 从用户消息中提取任务 + 记录行为模式
2. **判断**: 9个分析节点根据当前状态决定是否触发
3. **行动**: 用角色人格生成消息 → 去重+限流 → 投递

### 关键设计
- **状态锁**: 防止多个Cron Job同时发送消息
- **去重引擎**: 同一消息24小时内不重复
- **冷却机制**: 用户活跃时不打断，两次消息间隔≥45分钟
- **角色人格**: 模板化消息 + 情境规则 + 行为约束
- **模块化**: 7个独立模块，可单独测试和替换

### 局限性
1. 任务提取依赖正则，复杂语义无法处理
2. 用户情绪检测仅靠关键词，准确度有限
3. 角色模板固定，无法动态生成新内容
4. 学习模块需要足够数据才能发挥作用
5. 与Hermes的记忆系统未完全整合
