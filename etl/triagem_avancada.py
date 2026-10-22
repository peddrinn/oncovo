#!/usr/bin/env python3
"""
Dia 1 — Higienização e triagem de posts Instagram para o Oncovo.

Entrada esperada:
  JSONL com 1 post por linha, no formato retornado pelo instagrapi/export atual.

Saídas:
  - dia1_posts_limpos.jsonl: registros limpos e enriquecidos para auditoria/ETL
  - dia1_posts_limpos.csv: mesma base em CSV compacto
  - dia1_fila_llm_100.csv: 100 posts mais prioritários para extração com LLM
  - dia1_fila_llm_100.jsonl: mesma fila em JSONL
  - dia1_descartados.csv: posts descartados ou não mantidos, com motivo
  - dia1_resumo.json: métricas do processamento

Uso:
  python etl/triagem_avancada.py --input etl/raw/all_posts.jsonl --outdir etl/processed/dia1
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

CURRENT_DATE = datetime.now(timezone.utc)  # nunca fixar a data de triagem historicamente

GENERIC_LOCATION_NAMES = {
    "belo horizonte",
    "belo horizonte-mg",
    "belo horizonte mg",
    "belo horizonte, brazil",
    "belo horizonte, brasil",
    "minas gerais",
    "bh",
    "belohorizonte",
}

SOURCE_WEIGHT = {
    "vamobh": 15,
    "ondeirbh": 14,
    "oguiadebh": 14,
    "culturaliza.bh": 14,
    "comabembh": 11,
    "curtebh": 11,
    "bhebom": 9,
    "ondesairbh": 8,
    "pertindecasabh": 8,
    "bhemdobro": 5,
    "dicasdebh": 4,
    "umbarporsemanabh": 3,
}

EVENT_TERMS = [
    "evento", "programação", "agenda", "show", "festival", "festa", "arraiá", "arraial",
    "feira", "exposição", "espetáculo", "teatro", "cinema", "apresentação", "concerto",
    "samba", "pagode", "jazz", "forró", "roda de samba", "música ao vivo", "stand up",
    "corrida", "campeonato", "torneio", "estreia", "lançamento", "oficina", "workshop",
    "neste sábado", "neste domingo", "fim de semana", "fds", "hoje", "amanhã",
]

PLACE_TERMS = [
    "restaurante", "bar", "boteco", "café", "cafeteria", "padaria", "hamburgueria",
    "pizzaria", "sorveteria", "doceria", "churrascaria", "parque", "praça", "museu",
    "mercado", "shopping", "casa", "espaço", "unidade", "cardápio", "happy hour",
    "chopp", "drink", "drinks", "cerveja", "petisco", "porção", "rodízio", "self-service",
    "funcionamento", "endereço", "rua", "avenida", "av.", "bairro", "reservas",
]

TOURISM_TERMS = [
    "bate e volta", "viagem", "viajando", "pousada", "cachoeira", "trilha", "turistar",
    "inhotim", "lavras novas", "congonhas", "ouro preto", "brumadinho", "serra do cipó",
]

PROMO_TERMS = [
    "promoção", "desconto", "cupom", "grátis", "gratuito", "entrada franca", "free", "off",
    "preço", "valor", "valores", "r$", "combo", "rodada dupla", "compre", "ganha",
]

NOISE_TERMS = [
    "visto americano", "visto", "imóvel", "imoveis", "imóveis", "lote", "garagem", "alugada",
    "alugadas", "alugar", "vendo excelente", "fornecedor", "perfumes árabes", "atacado",
    "lojistas", "seguidores", "minha história", "minha pagina", "minha página", "carreira de",
    "aplicativo", "baixados na apple store", "grupo do whatsapp", "link da bio", "comente aqui embaixo",
]

SPONSORED_TERMS = ["publi", "publicidade", "patrocinado", "parceria paga", "oferecimento"]

RETAIL_NOISE_TERMS = [
    "nike", "adidas", "youcom", "outlet", "guarda-roupa", "tênis", "tenis", "roupa",
    "moda", "calçado", "calcado", "fone de ouvido", "compras acima", "cliente",
    "loja", "lojas", "shopee", "fornecedor", "perfume", "perfumes", "atacado",
]

STRONG_CULTURE_EVENT_TERMS = [
    "show", "festival", "teatro", "espetáculo", "espetaculo", "música", "musica",
    "samba", "pagode", "jazz", "forró", "forro", "arraiá", "arraia", "feira",
    "exposição", "exposicao", "cinema", "apresentação", "apresentacao",
]

DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?|"
    r"\d{1,2}\s*(?:e|-|a|até)\s*\d{1,2}[/.]\d{1,2}|"
    r"(?:segunda|terça|ter[cç]a|quarta|quinta|sexta|sábado|sabado|domingo)s?\b|"
    r"(?:janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro))",
    re.IGNORECASE,
)
TIME_RE = re.compile(r"\b(?:[01]?\d|2[0-3])\s*h(?:\s*(?:às|as|a|-)\s*(?:[01]?\d|2[0-3])\s*h)?\b", re.IGNORECASE)
PRICE_RE = re.compile(r"(?:R\$\s?\d+(?:[.,]\d{2})?|\b\d+[,\.]\d{2}\b)", re.IGNORECASE)
ADDRESS_RE = re.compile(r"\b(?:rua|r\.|avenida|av\.?|praça|alameda|rodovia)\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][^\n,;]{2,80}", re.IGNORECASE)
MENTION_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9._]+)")
HASHTAG_RE = re.compile(r"#([\wÀ-ÿ]+)")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
CONTROL_RE = re.compile(r"[\u0000-\u001f\u007f-\u009f]")


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON inválido na linha {line_no}: {exc}") from exc
            obj["_input_line"] = line_no
            rows.append(obj)
    return rows


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    # Remove controles mantendo quebras de linha úteis.
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(WHITESPACE_RE.sub(" ", line).strip() for line in text.split("\n"))
    text = MULTI_NEWLINE_RE.sub("\n\n", text).strip()
    return text


def text_for_hash(text: str) -> str:
    text = URL_RE.sub("", text.lower())
    text = re.sub(r"[@#][\wÀ-ÿ._]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sha1_short(text: str, n: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def nested_get(obj: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def usernames_from_people_list(values: Any) -> List[str]:
    out = []
    if not isinstance(values, list):
        return out
    for item in values:
        if not isinstance(item, dict):
            continue
        user = item.get("user") if isinstance(item.get("user"), dict) else item
        username = user.get("username") if isinstance(user, dict) else None
        if username:
            out.append(username)
    return sorted(set(out))


def count_terms(text_l: str, terms: Iterable[str]) -> int:
    return sum(1 for term in terms if term in text_l)


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def location_quality(location_name: str, location_address: str, lat: Any, lng: Any) -> Tuple[bool, bool]:
    loc_norm = unicodedata.normalize("NFKC", (location_name or "").lower()).strip()
    is_generic = loc_norm in GENERIC_LOCATION_NAMES or loc_norm.replace(",", "") in GENERIC_LOCATION_NAMES
    has_specific = bool(location_name and not is_generic) or bool(location_address) or (lat is not None and lng is not None and not is_generic)
    return has_specific, is_generic


def classify_and_score(row: Dict[str, Any]) -> Tuple[str, int, str, List[str]]:
    caption = row["caption_text_clean"]
    text_l = caption.lower()
    reasons: List[str] = []

    event_hits = count_terms(text_l, EVENT_TERMS)
    place_hits = count_terms(text_l, PLACE_TERMS)
    tourism_hits = count_terms(text_l, TOURISM_TERMS)
    promo_hits = count_terms(text_l, PROMO_TERMS)
    noise_hits = count_terms(text_l, NOISE_TERMS)
    sponsored_hits = count_terms(text_l, SPONSORED_TERMS)
    retail_noise_hits = count_terms(text_l, RETAIL_NOISE_TERMS)
    strong_culture_event_hits = count_terms(text_l, STRONG_CULTURE_EVENT_TERMS)

    has_date = bool(DATE_RE.search(caption))
    has_time = bool(TIME_RE.search(caption))
    has_price = bool(PRICE_RE.search(caption))
    has_address = bool(ADDRESS_RE.search(caption)) or bool(row.get("location_address"))
    has_specific_location = bool(row.get("has_specific_location"))

    if has_date:
        event_hits += 1
        reasons.append("tem_data")
    if has_time:
        event_hits += 1
        reasons.append("tem_horario")
    if has_address:
        place_hits += 1
        reasons.append("tem_endereco")
    if has_price:
        reasons.append("tem_preco")
    if has_specific_location:
        reasons.append("tem_localizacao_especifica")
    if row.get("mentions"):
        reasons.append("tem_mencoes")
    if row.get("coauthors"):
        reasons.append("tem_coautores")

    # Classe principal: útil, ambíguo ou ruído.
    if not caption.strip():
        klass = "descartar_sem_legenda"
    elif noise_hits >= 2 and (event_hits + place_hits + tourism_hits) < 3:
        klass = "descartar_ruido_claro"
    elif retail_noise_hits >= 2 and strong_culture_event_hits == 0 and tourism_hits == 0:
        klass = "descartar_varejo_comercial"
    elif tourism_hits >= 2 and event_hits < 3:
        klass = "turismo_bate_volta"
    elif event_hits >= max(2, place_hits):
        klass = "candidato_evento"
    elif place_hits >= 2:
        klass = "candidato_lugar"
    elif promo_hits >= 2 and (event_hits or place_hits):
        klass = "promocao_util"
    elif (event_hits + place_hits + tourism_hits + promo_hits) >= 2:
        klass = "revisao_manual_ambiguo"
    else:
        klass = "descartar_generico"

    score = 0
    score += SOURCE_WEIGHT.get(row.get("source_profile", ""), 0)
    score += min(28, event_hits * 5 + place_hits * 4 + tourism_hits * 4)
    score += min(10, promo_hits * 2)

    if has_specific_location:
        score += 12
    if has_address:
        score += 10
    if has_date:
        score += 12
    if has_time:
        score += 8
    if has_price:
        score += 6

    cap_len = len(caption)
    if 120 <= cap_len <= 2000:
        score += 8
    elif cap_len < 80:
        score -= 20
    elif cap_len > 2500:
        score -= 5

    taken_dt = parse_dt(row.get("taken_at"))
    if taken_dt:
        age_days = (CURRENT_DATE - taken_dt).days
        if age_days <= 7:
            score += 10
            reasons.append("muito_recente")
        elif age_days <= 30:
            score += 8
            reasons.append("recente_30d")
        elif age_days <= 90:
            score += 3
            reasons.append("recente_90d")
        elif age_days > 365 and klass == "candidato_evento":
            score -= 12
            reasons.append("evento_antigo")

    if row.get("caption_duplicate"):
        score -= 8
        reasons.append("legenda_duplicada")
    if row.get("location_is_generic"):
        score -= 4
        reasons.append("localizacao_generica")
    if noise_hits:
        score -= min(35, noise_hits * 10)
        reasons.append(f"ruido:{noise_hits}")
    if retail_noise_hits:
        score -= min(25, retail_noise_hits * 6)
        reasons.append(f"varejo:{retail_noise_hits}")
    if sponsored_hits:
        score -= min(8, sponsored_hits * 3)
        reasons.append("possivel_publi")

    if klass.startswith("descartar"):
        score = min(score, 20)

    score = max(0, min(100, score))

    if klass.startswith("descartar") or score < 25:
        queue = "descartar"
    elif score >= 70 and klass in {"candidato_evento", "candidato_lugar", "turismo_bate_volta", "promocao_util"}:
        queue = "alta_prioridade"
    elif score >= 45:
        queue = "media_prioridade"
    else:
        queue = "revisao_manual"

    return klass, score, queue, sorted(set(reasons))


def flatten_post(post: Dict[str, Any], code_count: Counter, caption_hash_count: Counter, source_profiles_by_code: Dict[str, List[str]]) -> Dict[str, Any]:
    caption_clean = normalize_text(post.get("caption_text"))
    caption_flat = re.sub(r"\s+", " ", caption_clean).strip()
    caption_hash = sha1_short(text_for_hash(caption_clean)) if caption_clean else ""

    loc = post.get("location") if isinstance(post.get("location"), dict) else {}
    user = post.get("user") if isinstance(post.get("user"), dict) else {}
    code = str(post.get("code") or "")
    source_profile = str(post.get("_profile_username") or "")
    media_owner = str(user.get("username") or "")
    coauthors = usernames_from_people_list(post.get("coauthor_producers"))
    tagged = usernames_from_people_list(post.get("usertags"))
    mentions = sorted(set(MENTION_RE.findall(caption_clean)))
    hashtags = sorted(set(h.lower() for h in HASHTAG_RE.findall(caption_clean)))

    location_name = normalize_text(loc.get("name")) if loc else ""
    location_address = normalize_text(loc.get("address")) if loc else ""
    lat = loc.get("lat") if loc else None
    lng = loc.get("lng") if loc else None
    has_specific_location, location_is_generic = location_quality(location_name, location_address, lat, lng)

    media_type = post.get("media_type")
    product_type = post.get("product_type") or ""
    if media_type == 1:
        media_format = "feed_image"
    elif media_type == 2:
        media_format = "reel_or_video"
    elif media_type == 8:
        media_format = "carousel"
    else:
        media_format = str(product_type or media_type or "unknown")

    row = {
        "platform": "instagram",
        "post_code": code,
        "post_url": f"https://www.instagram.com/p/{code}/" if code else "",
        "source_profile": source_profile,
        "source_profiles_all": ",".join(source_profiles_by_code.get(code, [source_profile])),
        "media_owner_username": media_owner,
        "media_owner_full_name": normalize_text(user.get("full_name")),
        "owner_differs_from_source": bool(source_profile and media_owner and source_profile != media_owner),
        "coauthors": ",".join(coauthors),
        "tagged_users": ",".join(tagged),
        "mentions": ",".join(mentions),
        "hashtags": ",".join(hashtags),
        "taken_at": post.get("taken_at") or "",
        "scraped_at": post.get("_scraped_at") or "",
        "media_type": media_type,
        "product_type": product_type,
        "media_format": media_format,
        "caption_text_clean": caption_clean,
        "caption_flat": caption_flat,
        "caption_len": len(caption_clean),
        "caption_hash": caption_hash,
        "caption_duplicate": bool(caption_hash and caption_hash_count[caption_hash] > 1),
        "code_duplicate": code_count[code] > 1 if code else False,
        "location_name": location_name,
        "location_address": location_address,
        "location_city": normalize_text(loc.get("city")) if loc else "",
        "location_lat": lat,
        "location_lng": lng,
        "has_specific_location": has_specific_location,
        "location_is_generic": location_is_generic,
        "like_count": post.get("like_count") or 0,
        "comment_count": post.get("comment_count") or 0,
        "view_count": post.get("view_count") or 0,
        "play_count": post.get("play_count") or 0,
        "is_paid_partnership": bool(post.get("is_paid_partnership")),
        "is_affiliate": bool(post.get("is_affiliate")),
        "input_line": post.get("_input_line"),
    }

    klass, score, queue, reasons = classify_and_score(row)
    row.update({
        "triage_class": klass,
        "triage_score": score,
        "triage_queue": queue,
        "triage_reasons": ",".join(reasons),
    })
    return row


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def choose_best_per_code(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mantém 1 registro por post_code, preferindo legenda maior, localização e score maior."""
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row.get("post_code") or f"__line_{row.get('input_line')}"].append(row)

    kept = []
    for _, items in groups.items():
        best = sorted(
            items,
            key=lambda r: (
                r.get("triage_score", 0),
                bool(r.get("has_specific_location")),
                r.get("caption_len", 0),
                SOURCE_WEIGHT.get(r.get("source_profile", ""), 0),
            ),
            reverse=True,
        )[0]
        best["kept_after_code_dedupe"] = True
        if len(items) > 1:
            best["triage_reasons"] = (best.get("triage_reasons", "") + ",dedupe_code_keep").strip(",")
        kept.append(best)
        for row in items:
            if row is not best:
                row["kept_after_code_dedupe"] = False
                row["triage_queue"] = "descartar"
                row["triage_class"] = "descartar_duplicado_code"
                row["triage_score"] = 0
                row["triage_reasons"] = (row.get("triage_reasons", "") + ",duplicado_code_nao_mantido").strip(",")
    return kept


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Caminho para all_posts.jsonl")
    parser.add_argument("--outdir", default="etl/processed/dia1", help="Diretório de saída")
    parser.add_argument("--llm-limit", type=int, default=100, help="Tamanho da fila prioritária para LLM")
    args = parser.parse_args()
    if not 1 <= args.llm_limit <= 10000:
        parser.error("--llm-limit deve ficar entre 1 e 10000")

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    raw_posts = load_jsonl(input_path)
    code_count = Counter(str(p.get("code") or "") for p in raw_posts)

    tmp_hashes = []
    for p in raw_posts:
        cap = normalize_text(p.get("caption_text"))
        tmp_hashes.append(sha1_short(text_for_hash(cap)) if cap else "")
    caption_hash_count = Counter(h for h in tmp_hashes if h)

    source_profiles_by_code: Dict[str, List[str]] = defaultdict(list)
    for p in raw_posts:
        code = str(p.get("code") or "")
        sources = p.get("_source_profiles", []) + [p.get("_profile_username")]
        if code:
            source_profiles_by_code[code] = sorted(set(source_profiles_by_code[code] + [src for src in sources if src]))

    rows = [flatten_post(p, code_count, caption_hash_count, source_profiles_by_code) for p in raw_posts]
    kept_rows = choose_best_per_code(rows)

    # Linhas finais mantidas no universo limpo: dedupe por code e não descartadas.
    clean_rows = sorted(
        [r for r in kept_rows if r.get("triage_queue") != "descartar"],
        key=lambda r: (r.get("triage_score", 0), r.get("taken_at", "")),
        reverse=True,
    )
    discard_rows = sorted(
        [r for r in rows if r.get("triage_queue") == "descartar" or not r.get("kept_after_code_dedupe", True)],
        key=lambda r: (r.get("triage_class", ""), r.get("triage_score", 0)),
        reverse=True,
    )

    priority_rows = sorted(
        clean_rows,
        key=lambda r: (
            1 if r.get("triage_queue") == "alta_prioridade" else 0,
            r.get("triage_score", 0),
            r.get("taken_at", ""),
        ),
        reverse=True,
    )[: args.llm_limit]

    base_fields = [
        "platform", "post_code", "post_url", "source_profile", "source_profiles_all",
        "media_owner_username", "media_owner_full_name", "owner_differs_from_source",
        "coauthors", "tagged_users", "mentions", "hashtags",
        "taken_at", "scraped_at", "media_format", "product_type",
        "caption_flat", "caption_len", "caption_hash", "caption_duplicate", "code_duplicate",
        "location_name", "location_address", "location_city", "location_lat", "location_lng",
        "has_specific_location", "location_is_generic",
        "like_count", "comment_count", "view_count", "play_count",
        "is_paid_partnership", "is_affiliate",
        "triage_class", "triage_score", "triage_queue", "triage_reasons", "input_line",
    ]
    json_fields_extra = base_fields + ["caption_text_clean", "kept_after_code_dedupe"]

    write_jsonl(outdir / "dia1_posts_limpos.jsonl", clean_rows)
    write_csv(outdir / "dia1_posts_limpos.csv", clean_rows, base_fields)
    write_jsonl(outdir / "dia1_fila_llm_100.jsonl", priority_rows)
    write_csv(outdir / "dia1_fila_llm_100.csv", priority_rows, base_fields)
    write_csv(outdir / "dia1_descartados.csv", discard_rows, base_fields)

    summary = {
        "input_file": str(input_path),
        "raw_posts": len(raw_posts),
        "unique_codes": len(set(r.get("post_code") for r in rows if r.get("post_code"))),
        "removed_by_code_dedupe": sum(1 for r in rows if r.get("kept_after_code_dedupe") is False),
        "clean_kept_posts": len(clean_rows),
        "discarded_posts": len(discard_rows),
        "llm_queue_size": len(priority_rows),
        "by_source_profile_raw": Counter(r.get("source_profile") for r in rows),
        "by_source_profile_clean": Counter(r.get("source_profile") for r in clean_rows),
        "by_triage_class": Counter(r.get("triage_class") for r in rows if r.get("kept_after_code_dedupe", True)),
        "by_triage_queue": Counter(r.get("triage_queue") for r in rows if r.get("kept_after_code_dedupe", True)),
        "by_media_format_clean": Counter(r.get("media_format") for r in clean_rows),
        "top_20_llm_queue": [
            {
                "post_code": r.get("post_code"),
                "source_profile": r.get("source_profile"),
                "media_owner_username": r.get("media_owner_username"),
                "triage_class": r.get("triage_class"),
                "triage_score": r.get("triage_score"),
                "taken_at": r.get("taken_at"),
                "caption_preview": r.get("caption_flat", "")[:180],
            }
            for r in priority_rows[:20]
        ],
    }
    with (outdir / "dia1_resumo.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=lambda x: dict(x) if isinstance(x, Counter) else str(x))

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=lambda x: dict(x) if isinstance(x, Counter) else str(x)))


if __name__ == "__main__":
    main()
