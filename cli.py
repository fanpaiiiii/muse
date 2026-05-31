#!/usr/bin/env python3
"""CLI 工具 - 与Muse交互
用法:
    python cli.py add-task "内容" [--priority 5] [--due "2024-01-01T10:00"]
    python cli.py list-tasks [--status pending] [--overdue]
    python cli.py complete <task_id>
    python cli.py cancel <task_id>
    python cli.py stats
    python cli.py config
    python cli.py test-node <node_id>
    python cli.py process "消息文本"
"""
import sys
import os
import json
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from core.engine import ProactiveEngine
from core.database import init_db


def cmd_add_task(engine, args):
    task_id = engine.task_manager.add_task(
        content=args.content,
        priority=args.priority,
        due_time=args.due,
        source="user_confirmed"
    )
    print(f"任务已添加，ID: {task_id}")


def cmd_list_tasks(engine, args):
    if args.overdue:
        tasks = engine.task_manager.get_overdue_tasks()
        print(f"逾期任务 ({len(tasks)}):")
    else:
        tasks = engine.task_manager.get_pending_tasks()
        print(f"待处理任务 ({len(tasks)}):")

    for t in tasks:
        due = f" → {t['due_time']}" if t.get("due_time") else ""
        print(f"  [{t['id']}] P{t['priority']} {t['content']}{due}")


def cmd_complete(engine, args):
    if engine.task_manager.complete_task(args.task_id):
        print(f"任务 {args.task_id} 已完成")
    else:
        print(f"任务 {args.task_id} 不存在或已完成")


def cmd_cancel(engine, args):
    if engine.task_manager.cancel_task(args.task_id):
        print(f"任务 {args.task_id} 已取消")
    else:
        print(f"任务 {args.task_id} 不存在或已处理")


def cmd_stats(engine, args):
    stats = engine.get_stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def cmd_config(engine, args):
    from core.config_loader import load_config
    cfg = load_config()
    print(json.dumps(cfg, ensure_ascii=False, indent=2))


def cmd_test_node(engine, args):
    analysis = engine.analyze_node(args.node_id)
    print(f"节点分析: {json.dumps(analysis, ensure_ascii=False, indent=2)}")


def cmd_process(engine, args):
    result = engine.process_message(args.text)
    print(f"提取到 {len(result['tasks_extracted'])} 个任务")
    for task in result["tasks_extracted"]:
        print(f"  - [{task['id']}] {task['content']}")


def main():
    parser = argparse.ArgumentParser(description="Muse CLI")
    subparsers = parser.add_subparsers(dest="command")

    # add-task
    p = subparsers.add_parser("add-task")
    p.add_argument("content")
    p.add_argument("--priority", type=int, default=5)
    p.add_argument("--due", help="ISO datetime")

    # list-tasks
    p = subparsers.add_parser("list-tasks")
    p.add_argument("--status", default="pending")
    p.add_argument("--overdue", action="store_true")

    # complete
    p = subparsers.add_parser("complete")
    p.add_argument("task_id", type=int)

    # cancel
    p = subparsers.add_parser("cancel")
    p.add_argument("task_id", type=int)

    # stats
    subparsers.add_parser("stats")

    # config
    subparsers.add_parser("config")

    # test-node
    p = subparsers.add_parser("test-node")
    p.add_argument("node_id")

    # process
    p = subparsers.add_parser("process")
    p.add_argument("text")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    init_db()
    engine = ProactiveEngine()

    cmd_map = {
        "add-task": cmd_add_task,
        "list-tasks": cmd_list_tasks,
        "complete": cmd_complete,
        "cancel": cmd_cancel,
        "stats": cmd_stats,
        "config": cmd_config,
        "test-node": cmd_test_node,
        "process": cmd_process,
    }
    cmd_map[args.command](engine, args)


if __name__ == "__main__":
    main()
