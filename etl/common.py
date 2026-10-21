"""Funções puras do ETL; sem dependências externas (Python >=3.11)."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Sao_Paulo')
NOW = lambda: datetime.now(TZ)
STOP = {'a','as','o','os','um','uma','de','da','do','das','dos','em','na','no','nas','nos',
        'para','por','com','e','que','onde','quero','procurar','busca','buscar','bh','belo','horizonte'}
ALIASES = {
  'hamburguer': ['hamburgueria', 'burger', 'burguer', 'hamburger', 'podrao'],
  'hamburgueria': ['hamburguer', 'burger', 'burguer', 'hamburger'],
  'cafe': ['cafeteria', 'cafe colonial'],
  'crianca': ['criancas', 'kids', 'infantil', 'familia'],
  'familia': ['familiar', 'crianca', 'kids', 'infantil'],
  'pagode': ['samba'],
  'gratuito': ['gratis', 'entrada franca'],
  'musica': ['musical', 'show', 'ao vivo'],
  'rock': ['rock and roll'],
  'restaurante': ['gastronomia', 'comida'],
}

def plain(value: object) -> str:
    txt = unicodedata.normalize('NFKD', str(value or '').lower())
    txt = ''.join(ch for ch in txt if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', ' ', txt).strip()

def search_index(*values: object) -> str:
    parts: list[str] = []
    for val in values:
        if isinstance(val, list):
            parts.extend(str(x) for x in val if x is not None)
        elif val is not None:
            parts.append(str(val))
    text = plain(' '.join(parts))
    tokens = set(text.split())
    synonyms = [alias for token in tokens for alias in ALIASES.get(token, [])]
    return f'{text} {plain(" ".join(synonyms))}'.strip()[:2500]

def read_jsonl(path: Path):
    with path.open(encoding='utf-8') as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError('registro precisa ser objeto JSON')
                yield payload
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f'{path}:{number}: {exc}') from exc

def write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as out:
        for item in rows:
            out.write(json.dumps(item, ensure_ascii=False, separators=(',', ':'))+'\n')

def canonical_id(source: str, code: str, discriminator: str = '') -> str:
    return hashlib.sha256(f'{source}:{code}:{discriminator}'.encode()).hexdigest()[:24]

def get_dict(obj: object) -> dict:
    return obj if isinstance(obj, dict) else {}

def list_strings(obj: object) -> list[str]:
    if isinstance(obj, list):
        return [str(x).strip()[:80] for x in obj if isinstance(x, str) and x.strip()][:15]
    return []

def event_dates(event: dict) -> tuple[str | None, str | None]:
    """Conservador: aceita APENAS datas ISO explícitas, sem inferir ano ou recorrência."""
    start = event.get('date_start')
    if not isinstance(start, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', start):
        return None, None
    try:
        first = date.fromisoformat(start)
        last = date.fromisoformat(event.get('date_end') or start)
        if last < first or last - first > timedelta(days=14):
            return None, None
    except (ValueError, TypeError):
        return None, None
    def parse_clock(value: object, fallback: time):
        if isinstance(value, str) and re.fullmatch(r'\d{2}:\d{2}',value):
            try: return time.fromisoformat(value)
            except ValueError: pass
        return fallback
    start_dt = datetime.combine(first, parse_clock(event.get('time_start'), time(0,0)), tzinfo=TZ)
    end_dt = datetime.combine(last, parse_clock(event.get('time_end'), time(23,59)), tzinfo=TZ)
    if end_dt < start_dt:
        # Não presumir evento noturno que vira o dia seguinte.
        return None, None
    return start_dt.isoformat(timespec='seconds'), end_dt.isoformat(timespec='seconds')

def safe_source_url(code: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_-]{5,30}',code):
        return ''
    return f'https://www.instagram.com/p/{code}/'
