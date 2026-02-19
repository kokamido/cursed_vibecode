import aiosqlite
from pathlib import Path

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "chat.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL DEFAULT 'New Chat',
    system_prompt   TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant')),
    text            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    sort_order      INTEGER NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cost            REAL
);

CREATE TABLE IF NOT EXISTS message_images (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    data_url   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_prompts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS endpoints (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    name                      TEXT NOT NULL,
    base_url                  TEXT NOT NULL,
    api_key                   TEXT NOT NULL DEFAULT '',
    cost_per_million_input    REAL NOT NULL DEFAULT 0,
    cost_per_million_output   REAL NOT NULL DEFAULT 0,
    created_at                TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _db():
    return aiosqlite.connect(DB_PATH)


async def init_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    async with _db() as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.executescript(SCHEMA)
        # Idempotent migration: add system_prompt column if missing
        try:
            await db.execute("ALTER TABLE conversations ADD COLUMN system_prompt TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        # Idempotent migrations: add token/cost columns to messages if missing
        for col, typ in [
            ("input_tokens", "INTEGER NOT NULL DEFAULT 0"),
            ("output_tokens", "INTEGER NOT NULL DEFAULT 0"),
            ("cost", "REAL"),
        ]:
            try:
                await db.execute(f"ALTER TABLE messages ADD COLUMN {col} {typ}")
            except Exception:
                pass
        # Idempotent migration: create endpoints table if missing
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS endpoints (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                name                      TEXT NOT NULL,
                base_url                  TEXT NOT NULL,
                api_key                   TEXT NOT NULL DEFAULT '',
                cost_per_million_input    REAL NOT NULL DEFAULT 0,
                cost_per_million_output   REAL NOT NULL DEFAULT 0,
                created_at                TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        # Idempotent migrations: add cost columns if missing
        for col, typ in [
            ("cost_per_million_input", "REAL NOT NULL DEFAULT 0"),
            ("cost_per_million_output", "REAL NOT NULL DEFAULT 0"),
        ]:
            try:
                await db.execute(f"ALTER TABLE endpoints ADD COLUMN {col} {typ}")
            except Exception:
                pass
        await db.commit()


# ── Conversations ──

async def list_conversations():
    async with _db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, title, system_prompt, updated_at FROM conversations ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def create_conversation(title="New Chat"):
    async with _db() as db:
        cursor = await db.execute(
            "INSERT INTO conversations (title) VALUES (?)", (title,)
        )
        await db.commit()
        conv_id = cursor.lastrowid
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, title, system_prompt, created_at, updated_at FROM conversations WHERE id = ?",
            (conv_id,),
        )
        row = await cursor.fetchone()
        return dict(row)


async def delete_conversation(conv_id):
    async with _db() as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        await db.commit()


async def rename_conversation(conv_id, title):
    async with _db() as db:
        await db.execute(
            "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title, conv_id),
        )
        await db.commit()


async def set_conversation_system_prompt(conv_id, text):
    async with _db() as db:
        await db.execute(
            "UPDATE conversations SET system_prompt = ?, updated_at = datetime('now') WHERE id = ?",
            (text, conv_id),
        )
        await db.commit()


# ── System Prompts Library ──

async def list_system_prompts():
    async with _db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, text, created_at FROM system_prompts ORDER BY name"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def create_system_prompt(name, text):
    async with _db() as db:
        cursor = await db.execute(
            "INSERT INTO system_prompts (name, text) VALUES (?, ?)", (name, text)
        )
        await db.commit()
        prompt_id = cursor.lastrowid
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, text, created_at FROM system_prompts WHERE id = ?",
            (prompt_id,),
        )
        row = await cursor.fetchone()
        return dict(row)


async def delete_system_prompt(prompt_id):
    async with _db() as db:
        await db.execute("DELETE FROM system_prompts WHERE id = ?", (prompt_id,))
        await db.commit()


# ── Messages ──

async def get_messages(conv_id):
    async with _db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, role, text, sort_order, input_tokens, output_tokens, cost FROM messages "
            "WHERE conversation_id = ? ORDER BY sort_order",
            (conv_id,),
        )
        msgs = [dict(r) for r in await cursor.fetchall()]

        for msg in msgs:
            cursor = await db.execute(
                "SELECT data_url FROM message_images WHERE message_id = ?",
                (msg["id"],),
            )
            msg["images"] = [row[0] for row in await cursor.fetchall()]

        return msgs


async def delete_message(msg_id):
    async with _db() as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
        await db.commit()


async def add_message(conv_id, role, text, images=None, input_tokens=0, output_tokens=0, cost=None):
    async with _db() as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # Determine next sort_order
        cursor = await db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM messages WHERE conversation_id = ?",
            (conv_id,),
        )
        (sort_order,) = await cursor.fetchone()

        cursor = await db.execute(
            "INSERT INTO messages (conversation_id, role, text, sort_order, input_tokens, output_tokens, cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (conv_id, role, text, sort_order, input_tokens, output_tokens, cost),
        )
        msg_id = cursor.lastrowid

        if images:
            for data_url in images:
                await db.execute(
                    "INSERT INTO message_images (message_id, data_url) VALUES (?, ?)",
                    (msg_id, data_url),
                )

        # Auto-title: if this is the first user message and title is still "New Chat"
        if role == "user" and sort_order == 0:
            cur = await db.execute(
                "SELECT title FROM conversations WHERE id = ?", (conv_id,)
            )
            row = await cur.fetchone()
            if row and row[0] == "New Chat" and text.strip():
                auto_title = text.strip()[:50]
                await db.execute(
                    "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
                    (auto_title, conv_id),
                )

        # Touch updated_at
        await db.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conv_id,),
        )

        await db.commit()

        return {"id": msg_id, "role": role, "text": text, "images": images or [], "sort_order": sort_order, "input_tokens": input_tokens, "output_tokens": output_tokens, "cost": cost}


# ── Endpoints ──

async def list_endpoints():
    async with _db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, base_url, api_key, cost_per_million_input, cost_per_million_output, created_at FROM endpoints ORDER BY name"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_endpoint(endpoint_id):
    async with _db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, base_url, api_key, cost_per_million_input, cost_per_million_output FROM endpoints WHERE id = ?",
            (endpoint_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_endpoint(name, base_url, api_key, cost_per_million_input=0, cost_per_million_output=0):
    async with _db() as db:
        cursor = await db.execute(
            "INSERT INTO endpoints (name, base_url, api_key, cost_per_million_input, cost_per_million_output) VALUES (?, ?, ?, ?, ?)",
            (name, base_url, api_key, cost_per_million_input, cost_per_million_output),
        )
        await db.commit()
        endpoint_id = cursor.lastrowid
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, base_url, api_key, cost_per_million_input, cost_per_million_output, created_at FROM endpoints WHERE id = ?",
            (endpoint_id,),
        )
        row = await cursor.fetchone()
        return dict(row)


async def delete_endpoint(endpoint_id):
    async with _db() as db:
        await db.execute("DELETE FROM endpoints WHERE id = ?", (endpoint_id,))
        await db.commit()
