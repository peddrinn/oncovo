# Frente A — A2.1 Homologação histórica e auditoria de reconciliação

Data da análise: 22/10/2026. Entradas locais: `items_publicaveis.jsonl` (100) + `extracoes_validas_100.jsonl` (100), anexadas ao projeto. O fluxo usou a lógica existente de `preparar_publicacao.py`, sem chamadas externas. Essas entradas **não comprovam funcionamento atual dos lugares** nem constituem exportação real do D1 em produção.

## Resultado reproduzido

| Métrica | Valor |
|---|---:|
| Registros editoriais auditados | 100 |
| `published` após filtros do pipeline | 13 |
| `review` após filtros | 38 |
| `expired` após filtros | 41 |
| `hidden` após filtros | 8 |
| Entidades canônicas | 12 |
| Estabelecimentos únicos nesta amostra | 12 |
| Eventos elegíveis na amostra | 0 |
| Grupos de fusão por evidência determinística | 1 |
| Pares adicionais pendentes de revisão | 1 |
| IDs de origem substituídos em mapeamento | 1 |
| Despublicações propostas / aprovadas / executadas | 1 / 0 / 0 |

**Fusão detectada:** `instagram:DXiKNIzEbfP` + `instagram:DYp5wrURWxO` descrevem **Pescados da Esquina**, Rua Bocaiuva, 3, Santa Tereza; `entity_id=pl_023ed2a3f49ff39c5d8862c7`, `card_id=7f9c258e215d8a594ab37aca`. Revisar ambos os posts e confirmar mesma unidade antes de promover a registry proposta.

**Candidato não fundido:** `instagram:DRxdMZgESuA` (**SPACE FRIENDS**) + `instagram:DXgJ9oLDUJu` (**Space Friends Park**), ambos associados à Rua Catumbi, 390, Caiçara. Nomes diferentes, mesmo endereço informado. Pode ser uma denominação alternativa, rebranding ou atividades/unidades distintas no mesmo prédio. **Pendente de comprovação humana.**

**Reconciliação proposta, não executada:** `source_id=DYp5wrURWxO` tinha `original_card_id=6c4ca31679b544b260f84863`, mas na saída canônica participa do card `7f9c258e215d8a594ab37aca`. Em um cenário de catálogo anterior com 13 linhas, um UPSERT com 12 linhas deixa ambos publicados até despublicação explícita. O relatório solicita avaliação desse único ID substituído. Nenhuma linha foi oculta ou removida.

## Auditoria sem ações destrutivas

```bash
# Após gerar etl/output/search_items.jsonl e etl/output/entities conforme docs/RESOLUCAO_ENTIDADES.md:
docker compose run --rm etl etl/auditar_reconciliacao.py \
  --previous etl/output/search_items.jsonl \
  --canonical etl/output/entities/search_items_canonical.jsonl \
  --source-map etl/output/entities/source_entity_map.csv \
  --outdir etl/output/reconciliation
```

`--previous` aqui é **apenas um baseline histórico de demonstração**; não substitui backup/consulta do D1 local já populado. Em produção ou homologação real, usar snapshot confiável da tabela **antes** do seed canônico, comparar `id`, `source_id`, `status` e `type`, e verificar que nenhuma publicação mudou entre snapshot e revisão. O script não emite SQL e nunca executa operações remotas.

Saídas: `reconciliation_review.csv` (uma proposta com campos em branco para revisor/data/decisão) e `reconciliation_report.json` (contagens, entradas e hashes). Ausência de registro num lote parcial **não** implica `hidden`.

## Gate humano A2.1 → A5

1. Inspecionar as duas fontes de Pescados da Esquina; confirmar mesma unidade e escolher se aprova a consolidação. Não confundir **fusão de fontes** com recertificação de funcionamento atual.
2. Investigar SPACE FRIENDS vs Space Friends Park; preencher `etl/entity_overrides.json` com fusão aprovada **ou** rejeição explícita e evidência/revisor; não publicar pendência como fusão.
3. Revisar o `source_entity_map.csv`, em especial `original_card_id != card_id`; conferir títulos, URLs e unidade.
4. Comparar `reconciliation_review.csv` com snapshot/backup do D1 **local**; conferir impacto no Worker (`status='published'`) e preservar reversão.
5. Somente após aprovação editorial, promover `entity_registry.proposed.json` para `etl/entity_registry.json` e implementar A5 (despublicação explícita com transação/guardas e teste D1 local). Não mudar diretamente o `db/seed.sql` ou executar `--remote` nesta etapa.

## Evidência de testes

- Suíte incremental de **40 testes locais** aprovada (31 anteriores + 9 adicionais), sem Docker nesta sessão; a execução Docker no computador foi validada pelo usuário.
- O teste SQLite comprova que `UPSERT` sem reconciliação não esconde o duplicado herdado; o script de reconciliação só propõe.
- Nenhuma chamada paga, coleta, `--remote`, alteração do prompt ou do frontend/Worker/schema.
