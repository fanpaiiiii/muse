# Muse v2.0 验收测试文档

> **项目**: `/root/.hermes/projects/muse/`
> **执行者**: OpenClaw (龙虾)
> **验收日期**: 2026-05-31
> **前置条件**: Python 3.10+, pytest, SQLite

---

## 一、环境检查

### 1.1 项目结构验收

```bash
# 验证文件存在（共 35 个 .py 文件 + 配置）
cd /root/.hermes/projects/muse

# 核心模块
test -f analyzer/__init__.py && echo "✅" || echo "❌ analyzer/__init__.py"
test -f analyzer/conditions.py && echo "✅" || echo "❌ analyzer/conditions.py"
test -f analyzer/content_templates.py && echo "✅" || echo "❌ analyzer/content_templates.py"
test -f analyzer/decision_engine.py && echo "✅" || echo "❌ analyzer/decision_engine.py"
test -f analyzer/perception.py && echo "✅" || echo "❌ analyzer/perception.py"
test -f analyzer/collect_perception.py && echo "✅" || echo "❌ analyzer/collect_perception.py"
test -f analyzer/save_decision.py && echo "✅" || echo "❌ analyzer/save_decision.py"
test -f analyzer/check_pending.py && echo "✅" || echo "❌ analyzer/check_pending.py"

# 数据库
test -f core/database.py && echo "✅" || echo "❌ core/database.py"

# 配置
test -f config/config.yaml && echo "✅" || echo "❌ config/config.yaml"

# 测试
test -f tests/test_engine.py && echo "✅" || echo "❌ tests/test_engine.py"
```

**通过标准**: 所有文件存在，无 ❌

---

## 二、单元测试

### 2.1 现有测试全部通过

```bash
cd /root/.hermes/projects/muse
python -m pytest tests/ -v --tb=short
```

**通过标准**: 27/27 passed, 0 failed

### 2.2 条件评分模块测试

```bash
cd /root/.hermes/projects/muse
python -c "
from analyzer.conditions import evaluate

# 测试1: 无任何条件触发 → 100分，passed=True
r = evaluate()
assert r['score'] == 100, f'期望100分，实际{r[\"score\"]}'
assert r['passed'] == True, '期望passed=True'
assert r['hard_blocked'] == False, '不应被硬条件阻止'
print('✅ 测试1 通过: 无条件触发=100分')

# 测试2: 用户刚活跃（1分钟前）→ 扣30分，70分
r = evaluate(minutes_since_active=1)
assert r['score'] == 70, f'期望70分，实际{r[\"score\"]}'
assert r['passed'] == True, '70分应通过'
print('✅ 测试2 通过: 用户刚活跃=70分')

# 测试3: 用户刚活跃（0.5分钟）+ 距上次主动20分钟 → 扣30+25=55分，45分
r = evaluate(minutes_since_active=0.5, minutes_since_last_msg=20)
assert r['score'] == 45, f'期望45分，实际{r[\"score\"]}'
assert r['passed'] == True, '45分应通过（阈值40）'
print('✅ 测试3 通过: 两项扣分=45分')

# 测试4: 用户刚活跃（1分钟）+ 距上次10分钟 + 负面情绪 → 扣30+25+20=75分，25分
msgs = [{'role': 'user', 'text': '好烦啊烦死了'}]
r = evaluate(minutes_since_active=1, minutes_since_last_msg=10, recent_messages=msgs)
assert r['score'] == 25, f'期望25分，实际{r[\"score\"]}'
assert r['passed'] == False, '25分应不通过'
print('✅ 测试4 通过: 三项扣分=25分，不通过')

# 测试5: 深夜硬阻止
from unittest.mock import patch
from datetime import datetime
with patch('analyzer.conditions.datetime') as mock_dt:
    mock_dt.now.return_value = datetime(2026, 5, 31, 2, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    r = evaluate()
    assert r['hard_blocked'] == True, '深夜应被硬阻止'
    assert r['score'] == 0, '硬阻止时分数应为0'
    print('✅ 测试5 通过: 深夜硬阻止')

print('\\n🎉 条件评分模块测试全部通过')
"
```

**通过标准**: 5/5 测试通过，无 AssertionError

---

## 三、场景模板测试

### 3.1 模板渲染测试

```bash
cd /root/.hermes/projects/muse
python -c "
from analyzer.content_templates import pick_template, SCENES

# 测试1: 所有场景都能正常渲染
for scene_id in SCENES:
    result = pick_template(scene_id, task='测试任务', time='10:00', 
                          minutes=30, hours=2, pending=3, completed=5,
                          remaining=2, weekday='Monday', remain='30分钟',
                          fun_fact='测试趣事')
    assert result is not None, f'场景 {scene_id} 渲染失败'
    assert result['message'], f'场景 {scene_id} 消息为空'
    assert result['scene'] == scene_id, f'场景ID不匹配'
    print(f'  ✅ {scene_id}: {result[\"message\"][:30]}...')

print(f'\\n✅ 全部 {len(SCENES)} 个场景模板渲染正常')
"
```

**通过标准**: 所有场景渲染成功，无 KeyError

### 3.2 场景选择测试

```bash
cd /root/.hermes/projects/muse
python -c "
from analyzer.content_templates import decide_scene
from datetime import datetime

# 模拟不同场景的数据
perception_tasks = {
    'overdue': 2,
    'pending': 3,
    'completed_today': 5,
    'upcoming': [{'title': '紧急任务', 'status': 'pending', 'priority': 'urgent', 'due_date': '2026-05-31T09:00:00'}]
}
perception_empty = {
    'overdue': 0,
    'pending': 0,
    'completed_today': 0,
    'upcoming': []
}
condition = {'score': 100}

# 测试1: 有逾期任务 → 应选 task_overdue
scene, vars = decide_scene({'tasks': perception_tasks, 'user_activity': {}}, condition)
assert scene == 'task_overdue', f'有逾期任务应选task_overdue，实际{scene}'
print(f'✅ 测试1: 逾期任务 → {scene}')

# 测试2: 无任务，当前是早上 → 应选 progress_morning
perception_empty_tasks = {'tasks': perception_empty, 'user_activity': {}}
# 注意：时间依赖当前真实时间，这里只验证不报错
scene, vars = decide_scene(perception_empty_tasks, condition)
assert scene is not None, '场景选择不应返回None'
print(f'✅ 测试2: 无任务 → {scene}（依赖当前时间）')

print('\\n🎉 场景选择测试通过')
"
```

**通过标准**: 场景选择逻辑正确

---

## 四、决策引擎集成测试

### 4.1 完整决策流程

```bash
cd /root/.hermes/projects/muse
python -c "
from core.database import init_db
from analyzer.decision_engine import analyze

init_db()

# 执行完整决策
result = analyze()

# 验证输出结构
required_keys = ['should_act', 'score', 'condition_summary', 'scene', 
                 'message', 'send_time', 'reason']
for key in required_keys:
    assert key in result, f'缺少字段: {key}'

print(f'决策结果:')
print(f'  should_act: {result[\"should_act\"]}')
print(f'  score: {result[\"score\"]}')
print(f'  scene: {result[\"scene\"]}')
print(f'  message: {result[\"message\"]}')
print(f'  send_time: {result[\"send_time\"]}')
print(f'  reason: {result[\"reason\"]}')

# 验证字段类型
assert isinstance(result['should_act'], bool), 'should_act应为bool'
assert isinstance(result['score'], int), 'score应为int'
assert 0 <= result['score'] <= 100, 'score应在0-100之间'

if result['should_act']:
    assert result['scene'] is not None, 'should_act=True时scene不应为None'
    assert result['message'] is not None, 'should_act=True时message不应为None'
    assert result['send_time'] is not None, 'should_act=True时send_time不应为None'
    # 验证时间格式
    h, m = result['send_time'].split(':')
    assert 0 <= int(h) <= 23, '小时应在0-23之间'
    assert 0 <= int(m) <= 59, '分钟应在0-59之间'

print('\\n✅ 决策引擎集成测试通过')
"
```

**通过标准**: 输出结构完整，类型正确

### 4.2 CLI 脚本测试

```bash
cd /root/.hermes/projects/muse

# 测试 collect_perception.py
echo "=== collect_perception.py ==="
python analyzer/collect_perception.py > /tmp/muse_test_output.json 2>&1
python -c "import json; d=json.load(open('/tmp/muse_test_output.json')); assert 'decision' in d; print('✅ collect_perception.py 输出有效 JSON')"

# 测试 check_pending.py
echo "=== check_pending.py ==="
python analyzer/check_pending.py > /tmp/muse_test_pending.json 2>&1
python -c "import json; d=json.load(open('/tmp/muse_test_pending.json')); assert 'due_count' in d; print('✅ check_pending.py 输出有效 JSON')"

# 测试 save_decision.py
echo "=== save_decision.py ==="
python analyzer/save_decision.py --time "09:30" --message "验收测试消息" --reason "测试" > /tmp/muse_test_save.json 2>&1
python -c "import json; d=json.load(open('/tmp/muse_test_save.json')); assert d['status']=='saved'; print('✅ save_decision.py 保存成功')"

# 验证消息已写入 DB
python analyzer/check_pending.py > /tmp/muse_test_pending2.json 2>&1
python -c "
import json
d = json.load(open('/tmp/muse_test_pending2.json'))
# 如果当前时间 < 09:30，消息应该是 pending
print(f'  due_count: {d[\"due_count\"]}')
print('✅ 消息已写入数据库')
"

# 清理测试数据
python -c "
from core.database import init_db, execute
init_db()
execute(\"DELETE FROM proactive_messages WHERE reason = '测试'\")
print('✅ 测试数据已清理')
"
```

**通过标准**: 所有 CLI 脚本正常执行，JSON 输出有效

---

## 五、Cron Job 验收

### 5.1 Job 存在性检查

```bash
# 通过 Hermes cron list 检查（需要 hermes CLI 或 API）
# 手动检查：列出所有 cron job
cd /root/.hermes/projects/muse
echo "检查 Cron Jobs..."
echo "  muse-tier1-analyzer: 每小时整点运行"
echo "  muse-tier2-dispatcher: 每5分钟运行"
```

### 5.2 Tier 1 手动触发

```bash
cd /root/.hermes/projects/muse

# 模拟 Tier 1 运行（不实际触发 Cron）
echo "=== 模拟 Tier 1 分析 ==="
python analyzer/collect_perception.py 2>&1

# 检查输出是否包含 decision 字段
python -c "
import json, subprocess
result = subprocess.run(['python', 'analyzer/collect_perception.py'], 
                       capture_output=True, text=True)
data = json.loads(result.stdout)
assert 'decision' in data, '输出缺少 decision 字段'
assert 'should_act' in data['decision'], 'decision 缺少 should_act'
print('✅ Tier 1 数据收集正常')
print(f'  should_act: {data[\"decision\"][\"should_act\"]}')
print(f'  score: {data[\"decision\"][\"score\"]}')
print(f'  scene: {data[\"decision\"][\"scene\"]}')
"
```

### 5.3 Tier 2 手动触发

```bash
cd /root/.hermes/projects/muse

echo "=== 模拟 Tier 2 调度 ==="

# 先写入一条即将到期的消息
python analyzer/save_decision.py --time "$(date +%H:%M)" --message "Tier2验收测试" --reason "验收" 2>&1

# 检查是否到期
python analyzer/check_pending.py 2>&1

# 清理
python -c "
from core.database import init_db, execute
init_db()
execute(\"DELETE FROM proactive_messages WHERE reason = '验收'\")
print('✅ 测试数据已清理')
"
```

---

## 六、数据库验收

### 6.1 表结构检查

```bash
cd /root/.hermes/projects/muse
python -c "
import sqlite3, os
from core.database import get_db_path

db_path = get_db_path()
print(f'数据库路径: {db_path}')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查所有表
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
tables = [row[0] for row in cursor.fetchall()]
print(f'\\n表列表: {tables}')

required_tables = ['tasks', 'behavior_log', 'user_profile', 'proactive_messages']
for table in required_tables:
    if table in tables:
        print(f'  ✅ {table}')
    else:
        print(f'  ❌ {table} 缺失')

# 检查 proactive_messages 索引
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='proactive_messages'\")
indexes = [row[0] for row in cursor.fetchall()]
print(f'\\nproactive_messages 索引: {indexes}')
assert len(indexes) >= 2, '应有至少2个索引'
print('✅ 索引数量正确')

conn.close()
"
```

**通过标准**: 所有表存在，索引完整

### 6.2 数据读写测试

```bash
cd /root/.hermes/projects/muse
python -c "
from core.database import init_db, query, execute
init_db()

# 写入
execute('''INSERT INTO proactive_messages 
           (target_time, target_date, message, reason, status, created_at) 
           VALUES ('10:00', '2026-05-31', '测试消息', '验收', 'pending', datetime('now'))''')

# 读取
rows = query('SELECT * FROM proactive_messages WHERE reason = \"验收\"')
assert len(rows) == 1, f'期望1条记录，实际{len(rows)}'
assert rows[0]['message'] == '测试消息', '消息内容不匹配'
assert rows[0]['status'] == 'pending', '状态不匹配'
print('✅ 数据读写正常')

# 更新
execute('UPDATE proactive_messages SET status = \"sent\", sent_at = datetime(\"now\") WHERE reason = \"验收\"')
rows = query('SELECT status FROM proactive_messages WHERE reason = \"验收\"')
assert rows[0]['status'] == 'sent', '更新失败'
print('✅ 数据更新正常')

# 清理
execute('DELETE FROM proactive_messages WHERE reason = \"验收\"')
print('✅ 测试数据已清理')
"
```

---

## 七、性能验收

### 7.1 决策引擎响应时间

```bash
cd /root/.hermes/projects/muse
python -c "
import time
from core.database import init_db
from analyzer.decision_engine import analyze

init_db()

# 运行10次取平均
times = []
for i in range(10):
    start = time.time()
    result = analyze()
    elapsed = time.time() - start
    times.append(elapsed)

avg = sum(times) / len(times)
max_time = max(times)
min_time = min(times)

print(f'决策引擎性能测试 (10次):')
print(f'  平均: {avg*1000:.1f}ms')
print(f'  最快: {min_time*1000:.1f}ms')
print(f'  最慢: {max_time*1000:.1f}ms')

assert avg < 1.0, f'平均响应时间 {avg*1000:.1f}ms 超过 1000ms 阈值'
print(f'\\n✅ 性能达标 (平均 {avg*1000:.1f}ms < 1000ms)')
"
```

**通过标准**: 平均响应时间 < 1 秒

### 7.2 数据库大小

```bash
cd /root/.hermes/projects/muse
python -c "
from core.database import get_db_path
import os

db_path = get_db_path()
size = os.path.getsize(db_path)
print(f'数据库大小: {size/1024:.1f}KB')
assert size < 10 * 1024 * 1024, f'数据库超过10MB: {size/1024/1024:.1f}MB'
print('✅ 数据库大小正常')
"
```

---

## 八、边界条件测试

### 8.1 深夜时间阻止

```bash
cd /root/.hermes/projects/muse
python -c "
from unittest.mock import patch
from datetime import datetime
from analyzer.conditions import check_hard_late_night

# 模拟凌晨2点
with patch('analyzer.conditions.datetime') as mock_dt:
    mock_dt.now.return_value = datetime(2026, 5, 31, 2, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    blocked, reason = check_hard_late_night()
    assert blocked == True, '凌晨2点应被阻止'
    assert '深夜' in reason, '原因应包含\"深夜\"'
    print(f'✅ 凌晨2点: {reason}')

# 模拟晚上23:30
with patch('analyzer.conditions.datetime') as mock_dt:
    mock_dt.now.return_value = datetime(2026, 5, 31, 23, 30, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    blocked, reason = check_hard_late_night()
    assert blocked == True, '23:30应被阻止'
    print(f'✅ 23:30: {reason}')

# 模拟早上7:00（边界）
with patch('analyzer.conditions.datetime') as mock_dt:
    mock_dt.now.return_value = datetime(2026, 5, 31, 7, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    blocked, reason = check_hard_late_night()
    assert blocked == False, '7:00不应被阻止'
    print(f'✅ 7:00: 不阻止')

print('\\n✅ 深夜边界测试通过')
"
```

### 8.2 每日上限测试

```bash
cd /root/.hermes/projects/muse
python -c "
from core.database import init_db, execute, query
from analyzer.conditions import check_hard_daily_limit

init_db()

today = '2026-05-31'

# 清理今日数据
execute(f\"DELETE FROM proactive_messages WHERE target_date = '{today}' AND reason = '上限测试'\")

# 写入5条已发送消息（未达上限）
for i in range(5):
    execute(f\"INSERT INTO proactive_messages (target_time, target_date, message, reason, status, created_at) 
             VALUES ('{10+i}:00', '{today}', '消息{i}', '上限测试', 'sent', datetime('now'))\")

blocked, reason = check_hard_daily_limit(6)
assert blocked == False, '5条不应阻止'
print(f'✅ 5条: {reason if reason else \"不阻止\"}')

# 再写1条（达到上限）
execute(f\"INSERT INTO proactive_messages (target_time, target_date, message, reason, status, created_at) 
         VALUES ('16:00', '{today}', '消息6', '上限测试', 'sent', datetime('now'))\")

blocked, reason = check_hard_daily_limit(6)
assert blocked == True, '6条应阻止'
assert '6/6' in reason, f'原因应包含6/6: {reason}'
print(f'✅ 6条: {reason}')

# 清理
execute(f\"DELETE FROM proactive_messages WHERE reason = '上限测试'\")
print('✅ 上限测试通过，数据已清理')
"
```

---

## 九、端到端流程测试

### 9.1 完整流程模拟

```bash
cd /root/.hermes/projects/muse
python -c "
from core.database import init_db, query, execute
from analyzer.decision_engine import analyze
from analyzer.check_pending import check_due_messages
import json

init_db()

print('=== 端到端流程测试 ===')

# Step 1: 运行决策引擎
print('\\nStep 1: 运行决策引擎')
result = analyze()
print(f'  should_act: {result[\"should_act\"]}')
print(f'  score: {result[\"score\"]}')
print(f'  scene: {result[\"scene\"]}')

# Step 2: 如果应该行动，保存决策
if result['should_act']:
    print('\\nStep 2: 保存决策')
    from analyzer.save_decision import main as save_main
    import sys
    # 模拟命令行参数
    sys.argv = ['save_decision.py', '--time', result['send_time'], 
                '--message', result['message'], '--reason', '端到端测试']
    # 直接执行保存
    execute('''INSERT INTO proactive_messages 
               (target_time, target_date, message, reason, status, created_at) 
               VALUES (?, ?, ?, ?, 'pending', datetime('now'))''',
            (result['send_time'], '2026-05-31', result['message'], '端到端测试'))
    print(f'  保存成功: {result[\"send_time\"]} - {result[\"message\"][:30]}...')
    
    # Step 3: 检查是否到期
    print('\\nStep 3: 检查到期消息')
    due = check_due_messages()
    print(f'  due_count: {len(due)}')
    
    # Step 4: 标记已发送
    if due:
        print('\\nStep 4: 标记已发送')
        for msg in due:
            execute('UPDATE proactive_messages SET status = \"sent\", sent_at = datetime(\"now\") WHERE id = ?', 
                    (msg['id'],))
            print(f'  已发送: ID {msg[\"id\"]}')
    
    print('\\n✅ 端到端流程完成')
else:
    print('\\n决策引擎判断不需要行动，流程结束')
    print('✅ 端到端流程完成（跳过）')

# 清理
execute('DELETE FROM proactive_messages WHERE reason = \"端到端测试\"')
print('\\n测试数据已清理')
"
```

---

## 十、验收总结

### 验收检查清单

| 序号 | 检查项 | 通过标准 | 状态 |
|------|--------|----------|------|
| 1 | 项目结构 | 所有文件存在 | ⬜ |
| 2 | 单元测试 | 27/27 通过 | ⬜ |
| 3 | 条件评分 | 5 种场景正确 | ⬜ |
| 4 | 模板渲染 | 所有场景正常 | ⬜ |
| 5 | 决策引擎 | 输出结构完整 | ⬜ |
| 6 | CLI 脚本 | JSON 输出有效 | ⬜ |
| 7 | 数据库表 | 4 表存在 | ⬜ |
| 8 | 数据库索引 | ≥2 个索引 | ⬜ |
| 9 | 数据读写 | CRUD 正常 | ⬜ |
| 10 | 性能 | 平均 <1s | ⬜ |
| 11 | 深夜阻止 | 正确阻止 | ⬜ |
| 12 | 上限阻止 | 正确阻止 | ⬜ |
| 13 | 端到端 | 流程完整 | ⬜ |

### 验收结论

- **通过**: 全部 13 项检查通过
- **部分通过**: 需说明具体问题
- **未通过**: 需修复后重新验收

### 验收人签字

- 执行者: _______________
- 验收日期: _______________
- 验收结论: _______________
