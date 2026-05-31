#!/usr/bin/env python3
"""一键接入脚本 - Muse × Hermes

用法:
    python setup.py                      # 一键接入（自动检测环境）
    python setup.py --platform telegram   # 指定推送平台
    python setup.py --skip-checks         # 跳过健康检查
    python setup.py --verbose             # 详细输出
    python setup.py --uninstall           # 卸载
    python setup.py --dry-run             # 试运行（不实际安装）

全程通过 Telegram 推送进度。
"""
import os
import sys
import argparse

# 确保项目根目录在 path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(
        description="Muse × Hermes 一键接入",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python setup.py                      # 自动检测环境并接入
  python setup.py --platform telegram  # 通过 Telegram 推送进度
  python setup.py --skip-checks        # 跳过健康检查
  python setup.py --uninstall          # 卸载系统
        """
    )

    parser.add_argument("--platform", choices=["telegram", "feishu", "local"],
                        help="推送平台 (默认: auto)")
    parser.add_argument("--chat-id", help="目标聊天 ID")
    parser.add_argument("--skip-checks", action="store_true",
                        help="跳过健康检查")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="详细输出")
    parser.add_argument("--uninstall", action="store_true",
                        help="卸载系统")
    parser.add_argument("--dry-run", action="store_true",
                        help="试运行（不实际安装）")
    parser.add_argument("--project-root", default=PROJECT_ROOT,
                        help="项目根目录")

    args = parser.parse_args()

    # 导入安装器
    from setup.installer import Installer

    installer = Installer(
        project_root=args.project_root,
        platform=args.platform,
        chat_id=args.chat_id,
        skip_checks=args.skip_checks,
        verbose=args.verbose,
    )

    if args.uninstall:
        print("🗑️ 开始卸载...")
        success = installer.uninstall()
        sys.exit(0 if success else 1)

    if args.dry_run:
        print("🔍 试运行模式...")
        from setup.health_checker import HealthChecker
        checker = HealthChecker(args.project_root)
        results = checker.run_all(args.skip_checks)
        print(checker.get_summary())
        can_proceed, reason = checker.can_proceed()
        print(f"\\n{'✅ 可以继续' if can_proceed else '❌ 无法继续'}: {reason}")
        sys.exit(0 if can_proceed else 1)

    # 正式安装
    print("🚀 开始接入Muse...")
    print(f"📦 项目目录: {args.project_root}")
    print(f"📱 推送平台: {args.platform or 'auto'}")
    print()

    success = installer.install()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
