-- Case Lens: Initial schema for Quebec case law storage with pgvector
-- Run this migration in the Supabase SQL Editor.

-- Enable pgvector extension for embedding similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Main cases table storing structured case data + embeddings
CREATE TABLE cases (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    canlii_id TEXT UNIQUE NOT NULL,
    database_id TEXT NOT NULL,
    title TEXT NOT NULL,
    citation TEXT,
    decision_date DATE,
    court TEXT,
    jurisdiction TEXT DEFAULT 'qc',
    language TEXT,
    keywords TEXT,
    case_type TEXT,
    summary TEXT,
    full_text TEXT,
    parties JSONB,
    key_facts JSONB,
    timeline JSONB,
    url TEXT,
    embedding vector(1024),
    cited_cases JSONB DEFAULT '[]',
    citing_cases JSONB DEFAULT '[]',
    cited_legislation JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX idx_cases_embedding ON cases
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_cases_database_id ON cases(database_id);
CREATE INDEX idx_cases_decision_date ON cases(decision_date);
CREATE INDEX idx_cases_case_type ON cases(case_type);
CREATE INDEX idx_cases_canlii_id ON cases(canlii_id);

-- RPC function for vector similarity search
CREATE OR REPLACE FUNCTION match_cases(query_embedding vector(1024), match_count int)
RETURNS TABLE(id uuid, title text, citation text, similarity float)
AS $$
    SELECT id, title, citation, 1 - (embedding <=> query_embedding) AS similarity
    FROM cases
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$ LANGUAGE sql;

-- Auto-update updated_at on row changes
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
