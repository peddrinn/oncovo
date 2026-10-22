# Contratos de dados — Frente A / A0

**Data:** 22/10/2026 · **Base examinada:** `main`/`67981bddcfc9b72de00c5f8e02f5495fc83e1e0c`.
**Estado:** inventário e contrato para homologação; não implica publicação ou atualização de dados reais.

## 1. Linhagem de dados

```text
Instagram / fonte autorizada
  → etl/raw/*.jsonl (raw imutável, privado, não versionar)
  → triagem_avancada.py (dedupe platform+post_code, filas e priorização)
  → extrair_llm.py + prompts/maritaca_legacy_v2.txt (dry-run por padrão)
  → validacao_extracao.py
  → criar_revisao.py (inicia sempre review)
  → aprovação humana (publicação explícita)
  → preparar_publicacao.py (etapas temporais e qualificação)
  → etl/output/search_items.jsonl (um card *por post*; intermediário)
  → resolver_entidades.py (identidades por unidade/ocorrência; staging)
  → etl/output/entities/search_items_canonical.jsonl + mapa de fontes
  → revisão dos candidatos, IDs e registry proposta
  → gerar_seed.py --input etl/output/entities/search_items_canonical.jsonl
  → db/seed.sql → D1 **local** → Worker /api/search → Astro
```

**Atenção:** o passo de resolução não executa `gerar_seed.py`; só a revisão humana permite prosseguir ao seed. Não migrar dados atuais do D1 durante A0/A2.

## 2. Inventário de campos e responsabilidade

| Camada | Identificadores e campos essenciais | Proveniência / proteção |
|---|---|---|
| Raw | `code`, `taken_at`, `_profile_username`, `_scraped_at`, `user.username`, `caption_text`, `location`, `coauthor_producers` | Conservar `source_profile` (perfil coletado) separado de `media_owner_username` (autor); pode conter material sensível; não commitar |
| Triagem | `post_code`, `source_profile`, `media_owner_username`, `caption_text_clean`, `triage_class`, `triage_score`, `taken_at`, `mentions`, `coauthors`, `location_name` | `platform + post_code` é identidade da postagem; coautoria ≠ nova postagem |
| LLM | `extraction_status`, `content_type`, `main_entity`, `event`, `location`, `commercial_info`, `classification`, `quality` | `post_code`, `post_url` e `prompt_version` são injetados pelo Python, não solicitados ao modelo |
| Revisão | `post_code`, `publish_status`, `display_title`, `display_subtitle`, `review_notes` | `criar_revisao.py` nunca aprova automaticamente; revisão humana obrigatória |
| Item intermediário | `id`, `source_id`, `source_url`, `type`, `status`, `title`, `subtitle`, `description`, `city`, `neighborhood`, `address`, `starts_at`, `ends_at`, `is_recurring`, `recurrence_text`, `price_label`, `price_type`, `categories`, `tags`, `search_text`, `rank_score_base`, `source_label` | Compatível com `db/schema.sql`, mas `id=hash(instagram,post_code)` **não equivale** à identidade física |
| Resolução A2 | `entity_id`, `card_id`, `original_card_id`, `post_code`, `source_url`, `is_primary` | Mapa offline de proveniência; `entity_id` = lugar/ocorrência, `card_id` = PK atual do D1; contrato HTTP não se altera |
| API `/api/search` | `query`, `items[]`, `total_returned`, `has_more`, `next_offset`; item contém `id`, `source_url`, `type`, `title`, `subtitle`, `description`, `neighborhood`, `address`, `starts_at`, `ends_at`, `price_label`, `price_type`, `categories`, `tags`, `source_label` | Worker retorna somente `published`; eventos vencidos são filtrados em runtime; não enviar mapeamento completo ao frontend |
| API `/api/health` | `status`, `version`, `dataset.dataset_version`, `dataset.generated_at`, `dataset.row_count`, `timezone` | Metadados do seed, sem dados brutos |

O schema **continua intacto** nesta entrega. `source_id` no card canônico representa a fonte primária; o vínculo de *todas* as fontes fica no `source_entity_map.csv`, não no D1. Um arquivo de mapeamento offline é deliberadamente escolhido antes de uma migração de schema.

## 3. Invariantes e bloqueios

- Mesma postagem: unicidade por `instagram:post_code` (sem fundir postagens só por legenda ou coautor).
- Mesmo lugar: auto-fusão somente por título normalizado + cidade + endereço **com logradouro e número exatos**. Unidade (`loja 1`, `loja 2`) faz parte do endereço; filiais permanecem separadas. Sem rua/número, emitir candidato; nome/handle semelhantes não bastam.
- Mesmo evento/ocorrência: título + cidade + local inequívoco + `starts_at` + `ends_at` exatos; eventos em dias diferentes não fundem.
- Estado publicável: `published` explícito no item de entrada; `review`, `hidden`, `expired`, `promotion` não podem sair para catálogo. Eventos devem ter início/fim ISO com fuso, término não passado.
- Conflito no registro fixado de IDs **interrompe o lote**; não renumerar silenciosamente.
- Fonte primária pode evoluir segundo score/completude; PK do card permanece fixada no registry revisado. Caso uma fusão elimine um card previamente publicado, **a resolução não o despublica automaticamente**.
- Lotes parciais não implicam remoção. UPSERT não despublica ausentes. Uma reconciliação editorial explicitamente aprovada será feita em A5.
- `confidence_overall >= .75` é necessário, mas insuficiente: `preparar_publicacao.py` também bloqueia dados parciais, riscos críticos, promoções e eventos sem data.
- Links de fontes ficam em `source_entity_map.csv`; URLs de posts derivam localmente do `post_code`.

## 4. Auditoria do material histórico disponibilizado

O arquivo editorial `items_publicaveis.jsonl` disponível no projeto possui 100 registros; estado editorial bruto no arquivo: 25 `published`, 63 `review`, 11 `expired` e 1 `hidden`. Esses 25 **não são 25 resultados publicáveis**: as regras de `preparar_publicacao.py` reduzem o catálogo histórico a 13 lugares elegíveis, conforme relatório de 21/10/2026 em `docs/ETL_OPERACAO.md`.

Os arquivos históricos fornecidos foram inspecionados com leitura binária por linhas `\n`: são JSONL válidos. `all_posts.jsonl` contém 1.170 objetos válidos e 4 códigos repetidos; `extracoes_validas_100.jsonl` contém 100 objetos válidos. Ambos incluem `U+2028` dentro de textos livres: 224 ocorrências no raw e 2 na extração. Uma tentativa inicial com `str.splitlines()` produziu falsos erros por tratar `U+2028` como separador de registro. **Não usar `str.splitlines()` para parsear JSONL de conteúdo social.**

**Nenhuma das 13 sugestões históricas comprova que o estabelecimento continua aberto em outubro de 2026.** Não tratar dados de demonstração como catálogo atualizado.

## 5. Evidência e limites da verificação

- Branch `main` sem commits posteriores ao SHA-base em 22/10/2026.
- Contratos de `common.py`, `preparar_publicacao.py`, `gerar_seed.py`, `validacao_extracao.py`, `extrair_llm.py`, prompt versionado, `schema.sql`, `worker/index.ts`, testes e docs examinados.
- A2 testado sem redes/serviços externos com `python -m unittest discover -s tests -v` (testes adicionados).
- A execução de Docker/Wrangler D1 local precisa ser repetida no repositório do desenvolvedor, já validado manualmente anteriormente; esta sessão não disponibiliza o executável Docker nem permissão GitHub de escrita.
- O `dataset_version` já existe na API health; não precisa nova rota ou alteração de contrato na Frente B.

## 6. Verificação de integridade JSONL (A0)

Rode `python etl/auditar_jsonl.py --input etl/raw/all_posts.jsonl --kind raw --report etl/processed/raw_audit.json` antes da triagem, e use `--kind extraction`/`--kind editorial` para lotes correspondentes. O relatório é apenas agregado, com checksum e números de linhas, sem legendas nem IDs. Saída não-zero bloqueia ingestão até reexportação/correção rastreada. No tipo `raw`, duplicatas legítimas de `code` são reportadas e tratadas pela triagem, sem bloquear entrada; em etapas já deduplicadas, duplicatas bloqueiam.

Nas **cópias históricas anexadas a esta auditoria** (não assumir que são toda a base atual), o relatório com delimitador binário `\n` confirmou:

| Arquivo | Registros JSONL | Objetos válidos | Linhas inválidas | Códigos duplicados |
|---|---:|---:|---:|---:|
| `all_posts.jsonl` | 1.170 | 1.170 | 0 | 4 |
| `extracoes_validas_100.jsonl` | 100 | 100 | 0 | 0 |
| `items_publicaveis.jsonl` | 100 | 100 | 0 | 0 |

O `U+2028` presente em legendas é conteúdo válido de string JSON. O fluxo correto lê registros por *newline byte* (`\n`), não pelos separadores Unicode aceitos por `str.splitlines()`. A nova auditoria valida a estrutura sem expor legendas e **não tenta corrigir ou descartar registros**. Os 4 códigos duplicados no raw exigem a deduplicação já implementada na triagem; o arquivo raw não precisa ser modificado.

## Contrato A1 incremental — 22/10/2026

`etl/lotes_incrementais.py` recebe raw (`code`, `caption_text`, `taken_at` ISO com fuso quando informado, `user`, localização e coautores), sem inferir aprovação editorial. Acrescenta `platform`, `_content_hash` e `_source_profiles` cumulativo; `_profile_username` mantém um representante compatível. `user.username` continua autor. Cada batch completo tem input imutável, chunks, observações, catálogo lógico, delta e manifesto com hashes/métricas/checkpoints. `pending` e `failed` não alimentam consumidores.

Identidade global `instagram:code`; não confundir com `entity_id`/`card_id` da A2. Perfil novo com mesmo conteúdo não gera nova linha delta; alteração relevante preserva versões e demanda revisão. As duas triagens mantêm perfis múltiplos. A saída avançada permanece compatível com `messages_for`/prompt atual; A3 não foi executada, e cache por revisão/hash requer trabalho autorizado na sua própria fase. Detalhes de campos, métricas e retomada: [A1_COLETA_INCREMENTAL.md](A1_COLETA_INCREMENTAL.md).

## Contrato A3/A4 versionado — 22/10/2026

A entrada da triagem mantém proveniência/score/classe, mas a mensagem LLM usa somente legenda e metadados factuais (data, autor, localização, mentions/coautores); perfil de descoberta e ranking não são enviados para evitar invalidação irrelevante. O prompt original continua intacto. `request_id` inclui entrada efetiva/prompt/modelo/parâmetros/contrato/provedor. `extraction_id` congela raw_response/validated_payload e metadados, incluindo batch/usage/tentativa; o payload normalizado também permanece no nível superior para leitores existentes.

Cache só aceita resultados completos/íntegros/revalidados; legacy_unverified e partial não são equivalentes a sucesso versionado. O plano distingue estimativa aproximada, bounds declarados verificados, reservas e usage real; moeda/preços precisam de origem explícita. Sem gabarito humano, avaliações por campo não recebem acurácia inventada.

A4 adiciona extraction_id/evidence_digest ao contrato editorial; publicação versionada exige correspondência exata com a extração e campos humanos de revisão/atualidade. Formato legado continua legível, sem transformá-lo em aprovação atual. Não houve alteração de schema D1/Worker/API. Detalhes e campos operacionais nos documentos A3/A4.
