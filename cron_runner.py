#!/usr/bin/env python3
"""Cron 运行器 - Muse的入口点
用于 Hermes Cron Job 调用，或独立运行。

用法:
    python cron_runner.py                    # 检查当前应触发的节点
    python cron_runner.py --node N2          # 强制触发指定节点
    python cron_runner.py --process-text "..."  # 处理文本并提取任务
    python cron_runner.py --stats            # 显示系统统计
    python cron_runner.py --daemon           # 守护进程模式（持续运行）
"""
import sys
import os
import json
import time
import signal
import argparse
from datetime import datetime

# 确保项目根目录在 path 中（使用绝对路径）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from core.engine import ProactiveEngine
from core.database import init_db


def cmd_prompt(engine, node_id, character_id):
    """生成 Cron Job prompt（供 Hermes Cron 使用）"""
    from integration.hermes_bridge import HermesBridge
    init_db()
    bridge = HermesBridge(character_id)
    prompt = bridge.generate_cron_prompt(node_id)
    print(prompt)


def cmd_check(engine: ProactiveEngine):
    """检查当前应触发的节点并执行"""
    init_db()
    due_nodes = engine.scheduler.get_due_nodes()

    if not due_nodes:
        print("当前没有需要检查的节点。")
        return

    results = []
    for node_id in due_nodes:
        result = engine.process_node(node_id)
        results.append(result)

    # 输出结果
    triggered = [r for r in results if r.get("triggered")]
    if triggered:
        for r in triggered:
            if r.get("generated"):
                print(f"[SENT] {r.get('message', '')}")
            else:
                print(f"[SKIP] {r.get('reason', 'unknown')}")
    else:
        print("所有节点均已处理或无需触发。")


def cmd_node(engine: ProactiveEngine, node_id: str):
    """强制触发指定节点"""
    init_db()
    print(f"强制触发节点 {node_id}...")

    # 直接绕过调度检查
    message = engine.generate_proactive_message(node_id)
    if message:
        result = engine.send_proactive(node_id, message)
        print(f"[SENT] {message}")
        print(f"[RESULT] {json.dumps(result, ensure_ascii=False)}")
    else:
        print(f"[SKIP] 节点 {node_id} 无需发送消息")


def cmd_process_text(engine: ProactiveEngine, text: str):
    """处理文本并提取任务"""
    init_db()
    result = engine.process_message(text)
    print(f"[EXTRACTED] 提取到 {len(result['tasks_extracted'])} 个任务")
    for task in result["tasks_extracted"]:
        print(f"  - {task['content']} (优先级: {task['priority']})")


def cmd_stats(engine: ProactiveEngine):
    """显示系统统计"""
    init_db()
    stats = engine.get_stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def cmd_daemon(engine: ProactiveEngine):
    """守护进程模式"""
    init_db()
    print(f"[{datetime.now().isoformat()}] 主动对话守护进程启动")
    print("按 Ctrl+C 停止")

    running = True

    def handle_signal(sig, frame):
        nonlocal running
        print(f"\n[{datetime.now().isoformat()}] 收到停止信号，正在退出...")
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    check_interval = 300  # 5分钟检查一次

    while running:
        try:
            due_nodes = engine.scheduler.get_due_nodes()
            for node_id in due_nodes:
                result = engine.process_node(node_id)
                if result.get("triggered") and result.get("generated"):
                    print(f"[{datetime.now().isoformat()}] [SENT:{node_id}] {result.get('message', '')}")

            # 等待下一次检查
            for _ in range(check_interval):
                if not running:
                    break
                time.sleep(1)

        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(60)

    print(f"[{datetime.now().isoformat()}] 守护进程已停止")


def cmd_cleanup(engine: ProactiveEngine):
    """清理旧数据"""
    init_db()
    engine.task_manager.cleanup_old_tasks(30)
    engine.deliverer.cleanup_old_messages(7)
    engine.scheduler.dedup.cleanup(7)
    print("清理完成")


def main():
    parser = argparse.ArgumentParser(description="Muse Cron 运行器")
    parser.add_argument("--node", help="强制触发指定节点 (N1-N9)")
    parser.add_argument("--process-text", help="处理文本并提取任务")
    parser.add_argument("--stats", action="store_true", help="显示系统统计")
    parser.add_argument("--daemon", action="store_true", help="守护进程模式")
    parser.add_argument("--cleanup", action="store_true", help="清理旧数据")
    parser.add_argument("--personality", default=None, help="人格风格")
    parser.add_argument("--character", default="sparkle", help="角色ID (sparkle/...)")
    parser.add_argument("--prompt", help="生成指定节点的 Cron prompt (如 N2)")

    args = parser.parse_args()
    engine = ProactiveEngine(args.personality, character_id=args.character)

    if args.prompt:
        cmd_prompt(engine, args.prompt, args.character)
    elif args.node:
        cmd_node(engine, args.node)
    elif args.process_text:
        cmd_process_text(engine, args.process_text)
    elif args.stats:
        cmd_stats(engine)
    elif args.daemon:
        cmd_daemon(engine)
    elif args.cleanup:
        cmd_cleanup(engine)
    else:
        cmd_check(engine)


if __name__ == "__main__":
    main()
