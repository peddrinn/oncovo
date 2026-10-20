-- db/schema.sql

DROP TABLE IF EXISTS search_items;

CREATE TABLE search_items (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_url TEXT,
    type TEXT NOT NULL, -- 'place', 'event', ou 'promotion'
    status TEXT NOT NULL, -- 'published', 'review', 'expired', 'hidden'
    title TEXT NOT NULL,
    subtitle TEXT,
    description TEXT,
    city TEXT DEFAULT 'Belo Horizonte',
    neighborhood TEXT,
    address TEXT,
    starts_at TEXT, -- Armazenado como ISO 8601 string
    ends_at TEXT,   -- Armazenado como ISO 8601 string
    is_recurring INTEGER DEFAULT 0, -- 0 para false, 1 para true (SQLite/D1 não tem boolean nativo)
    recurrence_text TEXT,
    price_label TEXT,
    price_type TEXT, -- 'free', 'paid', 'unknown'
    categories TEXT, -- JSON array em texto ou string separada por vírgulas
    tags TEXT,       -- JSON array em texto ou string separada por vírgulas
    search_text TEXT NOT NULL, -- Campo otimizado para a busca textual LIKE
    rank_score_base REAL DEFAULT 0.0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    published_at TEXT,
    source_label TEXT DEFAULT 'Instagram'
);

-- Índices essenciais para garantir que a busca e os filtros sejam rápidos
CREATE INDEX idx_search_items_status ON search_items(status);
CREATE INDEX idx_search_items_type ON search_items(type);
CREATE INDEX idx_search_items_city ON search_items(city);
CREATE INDEX idx_search_items_starts_at ON search_items(starts_at);