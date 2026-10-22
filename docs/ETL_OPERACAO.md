# ETL recuperado: operação, contratos e critérios

## Fluxo aprovado

```
coleta manual autorizada (--execute)
  → etl/raw/*.jsonl (não versionar)
  → triagem_avancada.py (auditoria, prioridades, dedupe post_code)
  → extrair_llm.py (dry-run / Maritaca, lotes pequenos)
  → validacao_extracao.py (evidência, conflitos e riscos)
  → criar_revisao.py (todo novo item começa review)
  → revisão humana (status, local/horário/preço e fonte)
  → preparar_publicacao.py (conflitos, tempo e regras de escopo)
  → output/search_items.jsonl e output/revisao.csv
  → gerar_seed.py (UPSERT em db/seed.sql)
  → D1 local → Worker → Astro
```

## Retenção dos melhores elementos do legado

`dia1_higienizacao_triagem.py` foi portado para `triagem_avancada.py` preservando: origem versus autor, colaboradores, menções, hash de legendas, localização genérica versus específica, recência, pesos por fonte, classificação heurística, grupos de prioridade, justificativa por linha, CSV de descartes e resumo JSON. **Correção:** `CURRENT_DATE` não fica em junho de 2026; é calculada no momento da execução.

O prompt `maritaca_legacy_v2.txt` replica o rigor do antigo `teste_maritaca_10_api.py` (verdadeiro/falso/nulo com evidências, horário comercial versus evento, evento recorrente, múltiplos eventos, preço, ingresso, dados de autor) com alteração explícita para **não solicitar `post_code`/`post_url` ao LLM**. Eles são injetados pelo Python após a resposta. O prompt não foi retestado economicamente nem quanto à qualidade da API nesta entrega.

## Dados e confidencialidade

- **Fatos:** `post_code`, `taken_at`, `source_profile`, `media_owner_username`, `caption_text_clean`, menções e localização dos posts brutos.
- **Inferências:** LLM produz `event`, `location`, `commercial_info`, `classification`, `quality`, sempre com evidência e confiança.
- **Decisões:** `publish_status` e revisão editorial não podem ser inferidos de uma única classificação sem supervisão.
- **Formato final:** `id`, `source_id`, `source_url`, `type`, `status`, `title`, `subtitle`, `description`, `city`, `neighborhood`, `address`, `starts_at`, `ends_at`, `price_*`, `categories`, `tags`, `search_text`, `rank_score_base` e `source_label`.
- **Segredos:** só variáveis de ambiente. Não versionar dados brutos, cookie/session, token ou credencial.

## Regras para impedir erros

- Post antigo pode provar um lugar existente no passado, não que ainda está aberto em 2026; confirmar antes do lançamento.
- Evento é `published` somente com data ISO inequívoca e término futuro em America/Sao_Paulo, confiança >= 0,75, tipo e local coerentes, e nenhuma flag crítica.
- Evento recorrente sem uma ocorrência concreta fica em `review`; não inventar próxima data.
- Horários de estabelecimento/happy hour/rodízio são **diferentes** de horário de evento.
- Preço desconhecido permanece `unknown`, não `free` ou `paid` por suposição.
- `is_free=true` com `ticket_required=true` requer revisão: ambos podem ser verdadeiros em situações específicas, mas **não publique sem checar**.
- Não produzir página com resultado fictício para preencher a base. Não publicar promoções como eventos.
- Busca `LIKE` com termos normalizados/sinônimos resolve variações comuns, não é busca semântica geral. QA de buscas e relevância é fase própria.

## Lote e custo

Use `--max-items 10` como piloto, compare as mesmas 10 legendas com extrações anteriores e verifique JSON válido, campos obrigatórios, evidências, falsos positivos e tempo/custo real. A alteração de prompt foi feita para preservar a qualidade do legado, não há garantia de tokenização/preço sem medição no provedor.

## Segurança/retirada

O seed utiliza UPSERT e não elimina linhas removidas de um catálogo parcial. Para despublicar um local encerrado, publique `status='hidden'` mediante uma operação editorial explícita. O Worker também protege contra eventos vencidos no momento de cada busca. Recomendação P0 antes de uma rotina recorrente: implantar reconciliação supervisionada de itens removidos do catálogo, não `DELETE` implícito.

**Auditoria histórica reexecutada em 21/10/2026:** 100 itens editoriais, 13 publicados, 38 em revisão (incluindo extrações parciais), 41 expirados, 8 ocultos. Os 13 são lugares e não constituem confirmação de operação atual.

<!-- Frente A A0/A2 22-10-2026 -->
## Atualização A0/A2 — 22/10/2026

O Docker da aplicação (Astro em `4321`, health Worker em `8787` e buscas no catálogo de teste) foi **validado manualmente pelo desenvolvedor em 22/10/2026**. Registros anteriores de pendência referem-se ao estado anterior dessa validação; isto **não** equivale a suíte Docker/CI integral nem publicação remota.

Antes da triagem, `etl/auditar_jsonl.py` valida a integridade dos lotes JSONL e bloqueia dados corrompidos. Novo gate **offline**: após `preparar_publicacao.py`, rodar `etl/resolver_entidades.py` conforme `docs/RESOLUCAO_ENTIDADES.md`. Ele cria staging com uma entidade por unidade/ocorrência, `source_entity_map.csv`, `merge_candidates.csv`, `entity_registry.proposed.json`, relatório e nenhum efeito no D1. Nenhum seed deve ser gerado a partir do staging sem revisão dos IDs e fusões. `gerar_seed.py` permanece o mesmo; para catálogo já aprovado, usar `--input etl/output/entities/search_items_canonical.jsonl`. Nunca inferir remoções de lote parcial; fluxo de despublicação/reconciliação será A5.

Documentação de contrato: `docs/CONTRATOS_DADOS.md`. O prompt Maritaca e a coleta continuam intactos; não usar `--execute` nem `--remote` sem autorização própria.

<!-- Frente A A5 local 22-10-2026 -->
## Reconciliação A5 — D1 local (22/10/2026)

A documentação atualizada para a reconciliação auditável está em `docs/A5_RECONCILIACAO_D1_LOCAL.md`. Gerar seed canônico somente com aprovação editorial; obter snapshot REAL do D1 local DEPOIS do seed; gerar CSV de revisão, aprovar despublicação de IDs substituídos, gerar `UPDATE` condicional e verificar. O SQL não é executado pelo Python. Não usar `--remote` e não tratar ausência em lote parcial como motivo para ocultar um lugar.

## A1 incremental — homologação de 22/10/2026

Antes da triagem, importar raw autorizado com `etl/lotes_incrementais.py`, conforme [A1_COLETA_INCREMENTAL.md](A1_COLETA_INCREMENTAL.md). O ledger preserva inputs/versões/proveniência e disponibiliza delta novo/alterado somente quando o lote está completo. Triar `batches/<batch_id>/delta.jsonl`; nunca consumir pending. Perfis de descoberta não são autor/coautores. Replay do mesmo lote não é ordem para repetir estágios pagos.

A1 foi validada offline e integrada à A2/A5 sintética no D1 isolado; nenhuma aquisição real nem extração paga ocorreu. Aprovações reais de registry e reconciliação A5 seguem pendentes. Posts alterados precisam de extração/revisão por versão: o cache legado A3 por post_code não resolve essa decisão. Resultados e limitações: [A1_A5_HOMOLOGACAO_2026-10-22.md](A1_A5_HOMOLOGACAO_2026-10-22.md).

## A3/A4 versionadas — 22/10/2026

O bloqueio anterior de cache por post_code foi tratado em `etl/extracao_versionada.py`; `extrair_llm.py` encaminha ao planejador. Fluxo: A1 completa → triagem com SHA-256 → plano offline → autorização paga separada → resultado durável/versionado → fila A4 review → decisão humana da versão exata → preparação → A2 → A5. Nenhuma inferência paga ocorreu nesta entrega.

Score/classe de triagem e perfil de descoberta ficam na auditoria, fora da mensagem ao modelo; legenda/dados factuais, prompt, modelo e parâmetros definem a identidade. Exports históricos não equivalem automaticamente ao cache novo. Filas/exports anteriores não são sobrescritos e publicação não escolhe arbitrariamente uma revisão dentre múltiplas.

Operação: [A3_EXTRACAO_VERSIONADA.md](A3_EXTRACAO_VERSIONADA.md). Qualidade: [A3_AVALIACAO_QUALIDADE.md](A3_AVALIACAO_QUALIDADE.md). Revisão CSV/JSONL: [A4_REVISAO_EDITORIAL.md](A4_REVISAO_EDITORIAL.md). Piloto e autorizações separadas: [PILOTO_DADOS_RECENTES.md](PILOTO_DADOS_RECENTES.md).
