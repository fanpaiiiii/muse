"""兼容性导入 — context_bridge 实际位于 analyzer/ 包

旧代码可能从 core.context_bridge 导入，这里做转发。
"""
from analyzer.context_bridge import *  # noqa: F401,F403
from analyzer.context_bridge import build_full_context, get_recent_conversation  # noqa: F401
