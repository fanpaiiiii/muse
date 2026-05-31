"""SQLite 数据库层 - 所有表的创建和基础 CRUD"""
import sqlite3
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH: Optional[str] = None
_MEMORY_CONN: Optional[sqlite3.Connection] = None


def get_db_path() -> str:
    global DB_PATH
    if DB_PATH:
        return DB_PATH
    # 优先使用 HERMES_HOME 环境变量，否则使用默认路径
    hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
    db_dir = os.path.join(hermes_home, "data", "proactive")
    os.makedirs(db_dir, exist_ok=True)
    DB_PATH = os.path.join(db_dir, "proactive.db")
    return DB_PATH


def get_conn() -> sqlite3.Connection:
    """获取数据库连接 - :memory: 模式共享单连接"""
    global _MEMORY_CONN
    path = get_db_path()
    if path == ":memory:":
        if _MEMORY_CONN is None:
            _MEMORY_CONN = sqlite3.connect(":memory:")
            _MEMORY_CONN.row_factory = sqlite3.Row
            _MEMORY_CONN.execute("PRAGMA foreign_keys=ON")
        return _MEMORY_CONN
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化所有表"""
    conn = get_conn()
    conn.executescript("""
    -- 任务表
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        source TEXT DEFAULT 'extracted',  -- extracted|user_confirmed|system
        priority INTEGER DEFAULT 5,        -- 1-10, 10最高
        status TEXT DEFAULT 'pending',     -- pending|in_progress|completed|cancelled
        due_time TEXT,                      -- ISO datetime
        extracted_at TEXT NOT NULL,
        completed_at TEXT,
        dedup_key TEXT,
        metadata TEXT DEFAULT '{}',        -- JSON
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
    CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_time);
    CREATE INDEX IF NOT EXISTS idx_tasks_dedup ON tasks(dedup_key);

    -- 行为日志表
    CREATE TABLE IF NOT EXISTS behavior_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,  -- message_sent|message_received|task_created|task_completed|proactive_sent
        source TEXT,               -- telegram|feishu|system
        content TEXT,
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_behavior_type ON behavior_log(event_type);
    CREATE INDEX IF NOT EXISTS idx_behavior_time ON behavior_log(created_at);

    -- 用户画像表
    CREATE TABLE IF NOT EXISTS user_profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        value TEXT,
        confidence REAL DEFAULT 0.5,
        updated_at TEXT DEFAULT (datetime('now'))
    );

    -- 主动消息记录表
    CREATE TABLE IF NOT EXISTS proactive_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id TEXT NOT NULL,       -- N1-N9
        message TEXT NOT NULL,
        status TEXT DEFAULT 'pending',  -- pending|sent|failed|cancelled
        response TEXT,                   -- 用户回复
        platform TEXT,
        sent_at TEXT,
        response_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_proactive_node ON proactive_log(node_id);
    CREATE INDEX IF NOT EXISTS idx_proactive_status ON proactive_log(status);

    -- 消息队列表
    CREATE TABLE IF NOT EXISTS message_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target TEXT NOT NULL,        -- telegram:chat_id, feishu:chat_id
        message TEXT NOT NULL,
        priority INTEGER DEFAULT 5,
        status TEXT DEFAULT 'queued',  -- queued|sending|sent|failed
        retry_count INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 3,
        scheduled_at TEXT,             -- 定时发送
        created_at TEXT DEFAULT (datetime('now')),
        sent_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_queue_status ON message_queue(status);
    CREATE INDEX IF NOT EXISTS idx_queue_priority ON message_queue(priority DESC);

    -- 状态锁表
    CREATE TABLE IF NOT EXISTS state_lock (
        id INTEGER PRIMARY KEY,
        locked_by TEXT,
        locked_at TEXT,
        expires_at TEXT,
        reason TEXT
    );

    -- 去重记录表
    CREATE TABLE IF NOT EXISTS dedup_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL,
        action_type TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_dedup_key ON dedup_log(key);
    CREATE INDEX IF NOT EXISTS idx_dedup_time ON dedup_log(created_at);

    -- 对话历史表（供学习模块使用）
    CREATE TABLE IF NOT EXISTS conversation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,       -- user|assistant
        content TEXT NOT NULL,
        platform TEXT,
        session_id TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_history(session_id);
    """)
    conn.commit()
    _maybe_close(conn)


def now_iso() -> str:
    return datetime.now().isoformat()


def query(sql: str, params: tuple = ()) -> List[Dict]:
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    _maybe_close(conn)
    return [dict(r) for r in rows]


def execute(sql: str, params: tuple = ()) -> int:
    conn = get_conn()
    cursor = conn.execute(sql, params)
    conn.commit()
    lastrowid = cursor.lastrowid
    _maybe_close(conn)
    return lastrowid


def execute_many(sql: str, params_list: List[tuple]) -> int:
    conn = get_conn()
    cursor = conn.executemany(sql, params_list)
    conn.commit()
    count = cursor.rowcount
    _maybe_close(conn)
    return count


def _maybe_close(conn: sqlite3.Connection):
    """仅关闭文件数据库连接，内存数据库连接保持打开"""
    if conn is not _MEMORY_CONN:
        conn.close()
