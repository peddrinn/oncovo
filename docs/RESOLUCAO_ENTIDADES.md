# Operação A2 — Resolução de estabelecimentos e eventos

**Não coleta dados, não chama LLM e não conecta ao D1.** Este procedimento é uma homologação offline, não uma ordem de publicação.

## Executar somente após revisão editorial

```bash
# 1. Fluxo Python já validado no projeto, sem alterar prompt/processamento:
docker compose run --rm etl etl/preparar_publicacao.py \
  --approved etl/items_publicaveis.jsonl \
  --extractions etl/processed/extracoes.jsonl \
  --output etl/output/search_items.jsonl \
  --report etl/output/revisao.csv

# 2. Resolver entidades antes do seed, usando aprovações + fontes:
docker compose run --rm etl etl/resolver_entidades.py \
  --input etl/output/search_items.jsonl \
  --extractions etl/processed/extracoes.jsonl \
  --registry etl/entity_registry.json \
  --overrides etl/entity_overrides.json \
  --outdir etl/output/entities

# 3. Testes sem rede (em máquina com Docker instalado):
docker compose run --rm etl -m unittest discover -s tests -v
```

Não execute `gerar_seed.py` apontando para o catálogo novo antes de revisar as saídas abaixo. Não execute `--remote` nesta etapa.

## Arquivos gerados por lote

| Arquivo | Finalidade |
|---|---|
| `search_items_canonical.jsonl` | Uma linha por entidade resolvida; mesmas colunas do seed anterior, **sem alterar Worker / D1** |
| `source_entity_map.csv` | Mapa auditável de `post_code` para `entity_id`/`card_id`; `is_primary` determina a fonte principal do card |
| `merge_candidates.csv` | Possíveis duplicações **não fundidas automaticamente**; `pending_review` exige decisão humana |
| `entity_registry.proposed.json` | Proposta de IDs persistentes. **Não sobrescreve** `etl/entity_registry.json` |
| `entity_report.json` | Contagens de fontes, entidades, fusões, candidatos, eventos excluídos, IDs de card modificados e pendências |

## Fusão e rejeição manual

Edite `etl/entity_overrides.json` (versionável). Exemplo com códigos **fictícios**:

```json
{
  "version": 1,
  "approved_groups": [
    {
      "type": "place",
      "sources": ["instagram:FAKEPOST001", "instagram:FAKEPOST002"],
      "reason": "Mesma unidade comprovada pelo endereço e verificação editorial",
      "reviewed_by": "revisor",
      "reviewed_at": "2026-10-22"
    }
  ],
  "rejected_pairs": [
    {
      "type": "place",
      "sources": ["instagram:FAKEPOST001", "instagram:FAKEPOST003"],
      "reason": "Filiais com entradas separadas"
    }
  ]
}
```

Exigir referência de evidência externa no registro editorial operacional para cada fusão, além do texto de justificativa. Não aprovar um merge só por nome, bairro ou Instagram handle. O script rejeita decisões contraditórias.

### Gate para promover um registry

1. Conferir `entity_report.json` e **todas** as linhas de `merge_candidates.csv`; manter pendências abertas fora da publicação consolidada.
2. Conferir `source_entity_map.csv`, sobretudo `original_card_id != card_id`, e consultar se o ID antigo já existe no D1 de homologação.
3. Validar fonte primária, título, endereço, preço e se o local realmente existe/está ativo; eventos exigem rechecagem temporal.
4. Somente com aprovação humana, copiar `entity_registry.proposed.json` para `etl/entity_registry.json` e versionar o commit junto ao override. Essa cópia **não** é feita pelo script.
5. Após gate, gerar seed explicitamente via `docker compose run --rm etl etl/gerar_seed.py --input etl/output/entities/search_items_canonical.jsonl --output db/seed.sql`.
6. Antes de aplicar seed no D1 local, auditar IDs que deixam de ser exibidos por fusão. **UPSERT não retira cards antigos.** Despublicação exige SQL de reconciliação separado em A5, com backup e revisão. Enquanto não houver tal reconciliação, não considerar a deduplicação implantada em produção.

### Regras de segurança e limites

- Nunca versionar `etl/output/`, `etl/raw/`, `etl/processed/` ou credenciais.
- O registro pode sobreviver a lotes parciais; a ausência de post não elimina mapeamento anterior.
- Se a mesma unidade foi cadastrada com identidades conflitantes em execuções anteriores, o script **falha com erro**: registrar reconciliação explícita em A5, não inventar substituição.
- O primeiro ID de card de uma fusão não aprovada previamente é escolhido de forma determinística entre IDs de origem; depois, **o registro aprovado fixa a PK**, mesmo quando a fonte primária mudar.
- Alterações de nome/endereço criam novas assinaturas, podendo exigir override e revisão editorial; não são atualizadas automaticamente.
- Sem logradouro e número, o script não funde por similaridade. Isso é intencional (priorizar falsos negativos sobre falsos positivos).
- Não usar fonte histórica como prova de operação atual. Não chamar dados antigos de atuais.

## Pré-condição A0: arquivo JSONL íntegro

Antes de processar arquivos históricos, executar:

```bash
python etl/auditar_jsonl.py --input etl/raw/all_posts.jsonl --kind raw \
  --report etl/processed/raw_audit.json
python etl/auditar_jsonl.py --input etl/processed/extracoes.jsonl --kind extraction \
  --report etl/processed/extraction_audit.json
```

Retorno 2 = linha inválida; 3 = chave ausente ou duplicata em etapa posterior ao raw. **Ambos bloqueiam** avanço do lote. No raw, duplicatas de `code` são relatadas mas não bloqueiam: a triagem existente faz dedupe por postagem. Não concatenar fragmentos de legenda para recuperar JSON automaticamente; repetir exportação limpa ou correção revisada separadamente.

<!-- Frente A A5 integração 22-10-2026 -->
## Continuação A5 — reconciliação do catálogo com D1 local

Após homologar as entidades, seguir `docs/A5_RECONCILIACAO_D1_LOCAL.md`. A A2 não promove `entity_registry.proposed.json` nem executa despublicação automaticamente. Reconciliar somente IDs já identificados e aprovados.

## Entrada incremental A1 — 22/10/2026

A1 deduplica **posts**, não estabelecimentos. Novas revisões no delta passam por triagem, extração validada e revisão antes de gerar cards. Reusar a registry revisada entre lotes mantém a PK quando surge fonte nova; uma registry proposta sintética não deve substituir a real. O ensaio A1→A2→A5 confirmou ordem inversa/lotes parciais, uma nova fonte na entidade existente, filiais preservadas e ocultação somente após aprovação de fixture. Relatório: [A1_A5_HOMOLOGACAO_2026-10-22.md](A1_A5_HOMOLOGACAO_2026-10-22.md).
