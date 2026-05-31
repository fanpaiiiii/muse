"""节点调度器 - 管理 N1-N9 分析节点"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from core.config_loader import get_config
from core.database import query, execute, now_iso
from scheduler.state_lock import StateLock
from scheduler.dedup_engine import DedupEngine
from perception.activity_analyzer import ActivityAnalyzer


class NodeScheduler:
    """管理 9 个分析节点的调度决策"""

    def __init__(self):
        self.nodes = get_config("nodes", {})
        self.state_lock = StateLock()
        self.dedup = DedupEngine()
        self.activity = ActivityAnalyzer()

    def analyze_node(self, node_id: str) -> Dict:
        """分析节点是否应该触发"""
        node = self.nodes.get(node_id)
        if not node:
            return {"should_trigger": False, "reason": f"Node {node_id} not found"}

        result = {
            "node_id": node_id,
            "node_name": node["name"],
            "node_type": node["type"],
            "should_trigger": False,
            "reason": "",
            "context": {},
        }

        # 1. 检查状态锁
        if self.state_lock.is_locked():
            lock_info = self.state_lock.get_lock_info()
            result["reason"] = f"状态锁被 {lock_info.get('locked_by', 'unknown')} 占用"
            return result

        # 2. 检查用户活跃状态
        activity_ctx = self.activity.get_activity_context()
        result["context"] = activity_ctx

        # 用户刚活跃 → 不打断
        if activity_ctx["minutes_since_active"] < 5:
            result["reason"] = "用户刚活跃，不打断"
            return result

        # 3. 检查每日消息上限
        if activity_ctx["today_proactive_count"] >= 8:
            result["reason"] = f"今日已发送 {activity_ctx['today_proactive_count']} 条主动消息"
            return result

        # 4. 检查冷却时间
        cooldown = node.get("cooldown", 60)
        last_sent = query(
            """SELECT sent_at FROM proactive_log
               WHERE node_id = ? AND status = 'sent'
               ORDER BY sent_at DESC LIMIT 1""",
            (node_id,)
        )
        if last_sent:
            last_time = datetime.fromisoformat(last_sent[0]["sent_at"])
            if (datetime.now() - last_time).total_seconds() < cooldown * 60:
                result["reason"] = f"冷却中，还需 {cooldown} 分钟"
                return result

        # 5. 去重检查
        dedup_key = f"node_{node_id}_{datetime.now().strftime('%Y%m%d')}"
        if self.dedup.is_duplicate(dedup_key, "node_trigger"):
            result["reason"] = "今日已触发过去重"
            return result

        # 6. 通过所有检查
        result["should_trigger"] = True
        result["reason"] = "通过所有检查，建议触发"
        return result

    def get_due_nodes(self) -> List[str]:
        """获取当前应该检查的节点"""
        current_hour = datetime.now().hour
        due_nodes = []
        for node_id, node in self.nodes.items():
            node_hour = node.get("hour", 0)
            # 在节点时间 ±1 小时内
            if abs(current_hour - node_hour) <= 1:
                due_nodes.append(node_id)
        return due_nodes

    def execute_node_analysis(self, node_id: str) -> Tuple[bool, str, dict]:
        """执行节点分析并返回结果"""
        analysis = self.analyze_node(node_id)
        if not analysis["should_trigger"]:
            return False, analysis["reason"], analysis["context"]

        # 获取锁
        if not self.state_lock.acquire(node_id, f"Node {node_id} triggered"):
            return False, "获取状态锁失败", analysis["context"]

        # 记录去重
        dedup_key = f"node_{node_id}_{datetime.now().strftime('%Y%m%d')}"
        self.dedup.record(dedup_key, "node_trigger")

        return True, "节点触发成功", analysis["context"]

    def release_lock(self, node_id: str = None):
        """释放锁"""
        self.state_lock.release(node_id)
