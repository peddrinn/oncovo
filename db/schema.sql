-- Schema não destrutivo. Banco D1 já existente: mantém linhas anteriores.
-- Antes de rodar no remoto, efetue backup e confira schema atual.
CREATE TABLE IF NOT EXISTS search_items (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  source_url TEXT,
  type TEXT NOT NULL CHECK(type IN ('place','event','promotion')),
  status TEXT NOT NULL CHECK(status IN ('published','review','expired','hidden')),
  title TEXT NOT NULL,
  subtitle TEXT,
  description TEXT,
  city TEXT DEFAULT 'Belo Horizonte',
  neighborhood TEXT,
  address TEXT,
  starts_at TEXT,
  ends_at TEXT,
  is_recurring INTEGER DEFAULT 0,
  recurrence_text TEXT,
  price_label TEXT,
  price_type TEXT,
  categories TEXT,
  tags TEXT,
  search_text TEXT NOT NULL,
  rank_score_base REAL DEFAULT 0.0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  published_at TEXT,
  source_label TEXT DEFAULT 'Instagram'
);
CREATE INDEX IF NOT EXISTS idx_search_items_status ON search_items(status);
CREATE INDEX IF NOT EXISTS idx_search_items_type ON search_items(type);
CREATE INDEX IF NOT EXISTS idx_search_items_city ON search_items(city);
CREATE INDEX IF NOT EXISTS idx_search_items_starts_at ON search_items(starts_at);
CREATE INDEX IF NOT EXISTS idx_search_items_published_type ON search_items(status,type,rank_score_base);
CREATE INDEX IF NOT EXISTS idx_search_items_source_id ON search_items(source_id);

CREATE TABLE IF NOT EXISTS publication_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
