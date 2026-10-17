-- Migration: 001_create_copilot_memory_tables.sql
-- Description: Tạo bảng lưu trữ lịch sử hội thoại, tin nhắn chi tiết, và bộ nhớ tóm tắt cho VinFast Sales Copilot
-- Compatible with: PostgreSQL 15+ / Supabase PostgreSQL 17

-- 1. Bảng quản lý phiên hội thoại (conversations)
CREATE TABLE IF NOT EXISTS conversations (
    session_id VARCHAR(64) PRIMARY KEY,
    owner_id VARCHAR(120) NOT NULL,
    title TEXT NOT NULL,
    last_seq INTEGER NOT NULL DEFAULT 0,
    customer_context TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_owner ON conversations (owner_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_expires ON conversations (expires_at);

-- 2. Bảng tin nhắn tuần tự (copilot_messages)
CREATE TABLE IF NOT EXISTS copilot_messages (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    request_id VARCHAR(64),
    seq INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_copilot_messages_session ON copilot_messages (session_id);
CREATE INDEX IF NOT EXISTS idx_copilot_messages_seq ON copilot_messages (session_id, seq ASC);

-- 3. Bảng bộ nhớ tóm tắt hội thoại (conversation_memories)
CREATE TABLE IF NOT EXISTS conversation_memories (
    session_id VARCHAR(64) PRIMARY KEY,
    summary_json TEXT NOT NULL DEFAULT '{}',
    summarized_through_seq INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL
);

-- 4. Bảng đồng bộ phiên đồng thời & legacy replay (copilot_sessions)
CREATE TABLE IF NOT EXISTS copilot_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    owner_id VARCHAR(120) NOT NULL,
    history_json TEXT NOT NULL,
    customer_context TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_copilot_sessions_owner ON copilot_sessions (owner_id);
CREATE INDEX IF NOT EXISTS idx_copilot_sessions_expires ON copilot_sessions (expires_at);

-- 5. Kích hoạt extension pgvector và bảng vector cho Copilot Knowledge Store
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_vectors (
    collection_name TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL,
    embedding VECTOR NOT NULL,
    PRIMARY KEY (collection_name, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_vectors_collection ON knowledge_vectors (collection_name);
