# Frente A — A5: reconciliação explícita e reversível no D1 **local**

Data: 22/10/2026. Base para aplicar: `main` `720b91a406ef6cdbfaad57edc7240f2f38cb2f4a`.

**Objetivo:** fazer o catálogo canônico e o D1 **local** concordarem sem esconder estabelecimentos que não apareceram em lotes parciais. Esta entrega NÃO faz coleta, LLM, login, migração de schema, atualização do Worker ou operação remota.

## Gates obrigatórios

- A2: validar `merge_candidates.csv`, `source_entity_map.csv`, fonte principal e `entity_registry.proposed.json`. Os overrides e registry **no commit 720b91a estão vazios**. Não os tratar como aprovados. Confirmar manualmente se os dois posts de *Pescados da Esquina* são da mesma unidade; o candidato *SPACE FRIENDS / Space Friends Park* permanece distinto enquanto não houver confirmação.
- Verificar escopo e atualidade antes de **qualquer publicação pública**: os 13 cards históricos (12 entidades no staging) são demonstração, não prova de estabelecimentos em operação.
- Exportar snapshot **depois de aplicar o seed canônico local**, pois o `source_id` do card retido pode mudar ao selecionar fonte primária. Nunca usar apenas `db/seed.sql` como prova do estado do D1.
- Aprovação de despublicação exige edição humana do CSV: `editorial_decision=approved_hide_duplicate`, `reviewed_by`, `reviewed_at` (`YYYY-MM-DD`), `approval_reason` e `approval_evidence_url` (HTTPS). Campos de justificativa/evidência da proposta automática **não** substituem a aprovação humana.
- Planejador **não executa** SQL. É impossível produzir SQL válido a partir de uma fila inteiramente pendente. Reversão exige snapshot posterior e nova geração de SQL.

## 1. Preparar catálogo canônico

Se os arquivos ainda não estão gerados, execute os passos já aprovados de `docs/RESOLUCAO_ENTIDADES.md` usando extrações históricas disponíveis **apenas em homologação**:

```bash
# Arquivo `etl/processed/extracoes.jsonl` precisa conter extrações já existentes.
docker compose run --rm etl etl/preparar_publicacao.py \
  --approved etl/items_publicaveis.jsonl \
  --extractions etl/processed/extracoes.jsonl \
  --output etl/output/search_items.jsonl \
  --report etl/output/revisao.csv

docker compose run --rm etl etl/resolver_entidades.py \
  --input etl/output/search_items.jsonl \
  --extractions etl/processed/extracoes.jsonl \
  --registry etl/entity_registry.json \
  --overrides etl/entity_overrides.json \
  --outdir etl/output/entities
```

**Antes de gerar o seed:** revisar CSV de candidatos, entidades canônicas e registry proposta, aprovar explicitamente os grupos pertinentes. Promoção da registry é uma operação humana separada. Não substitua a registry fixada em produção a partir de dados históricos sem análise.

## 2. Backup integral da base local antes do seed

Pare a API para evitar cópia de arquivos SQLite enquanto há escritas. O backup da pasta persistente é o **rollback integral** do processo (inclui alterações feitas pelo seed sobre cards retidos, não apenas os ocultados na reconciliação).

```bash
docker compose stop api
mkdir -p etl/output/reconciliation db/reconciliation
# Linux/macOS, backup NÃO versionado
tar -czf etl/output/reconciliation/d1_local_antes_a5.tar.gz .wrangler/state
```

Em Windows/PowerShell, compacte a pasta `.wrangler/state` com o serviço API parado, em vez de usar `tar` se necessário. Confira que o backup foi criado; se a pasta não existir, interrompa o procedimento.

## 3. Aplicar apenas o seed canônico no D1 local

**O seed original `db/seed.sql` pode ser substituído após aprovação editorial do staging.** Faça cópia antes da geração (`etl/output/reconciliation/seed_anterior.sql`) e nunca use `--remote`.

```bash
cp db/seed.sql etl/output/reconciliation/seed_anterior.sql
# Somente após homologar catálogo, fontes e IDs:
docker compose run --rm etl etl/gerar_seed.py \
  --input etl/output/entities/search_items_canonical.jsonl \
  --output db/seed.sql

docker compose run --rm api npx wrangler d1 execute oncovo-db \
  --local --persist-to .wrangler/state --file db/seed.sql
```

O seed **não** despublica automaticamente IDs antigos; é isso que o passo seguinte resolve. O arquivo `db/seed.sql` pertence ao repositório e deve ser revisado antes de ser commitado para não publicar inadvertidamente o catálogo histórico.

## 4. Exportar o estado *real* do D1 local após o seed

O CLI Wrangler suporta `--json` e `--local`. O redirecionamento abaixo grava os resultados **na máquina host** (`etl/output` está ignorado pelo Git):

```bash
docker compose run --rm api npx wrangler d1 execute oncovo-db \
  --local --persist-to .wrangler/state --json \
  --command "SELECT id,source_id,status,type,title,address,updated_at FROM search_items ORDER BY id" \
  > etl/output/reconciliation/d1_depois_seed.json
```

Valide que o arquivo contém `results` e todas as colunas. O planejador recusa `updated_at` ausente, IDs repetidos e arquivo vazio.

## 5. Gerar fila editorial e aprovar *somente* os casos comprovados

```bash
docker compose run --rm etl etl/reconciliar_d1_local.py prepare-review \
  --snapshot etl/output/reconciliation/d1_depois_seed.json \
  --canonical etl/output/entities/search_items_canonical.jsonl \
  --source-map etl/output/entities/source_entity_map.csv \
  --output etl/output/reconciliation/a5_review.csv
```

Abra `a5_review.csv`. Todas as linhas vêm com `pending_review`. Para uma ação aprovada, preencha as cinco colunas editoriais exigidas (decisão, revisor, data, justificativa e URL da evidência). Uma linha rejeitada recebe `rejected` e não vira SQL. **Não marque o candidato SPACE FRIENDS como fusão sem evidência.**

## 6. Gerar plano SQL (somente gera arquivos)

```bash
docker compose run --rm etl etl/reconciliar_d1_local.py plan \
  --snapshot etl/output/reconciliation/d1_depois_seed.json \
  --canonical etl/output/entities/search_items_canonical.jsonl \
  --source-map etl/output/entities/source_entity_map.csv \
  --decisions etl/output/reconciliation/a5_review.csv \
  --outdir db/reconciliation
```

Arquivos produzidos (ignorados pelo Git): `db/reconciliation/a5_plan.json`, `a5_apply.sql`, `a5_verify.sql`. O script recomputa o relatório A2 e verifica que ninguém editou IDs, destinos ou tipos no CSV. Só considera ações aprovadas sobre IDs comprovados no snapshot.

**Revisar o plano e o SQL antes de executar.** O `UPDATE` é uma única instrução com guardas para **todas** as ações: exige que todos os IDs antigos estejam publicados, com fonte/tipo/título/endereço/`updated_at` observados, e que os respectivos cards canônicos existam publicados, com os mesmos valores congelados. Se uma guarda falhar, nenhuma ação é efetuada. Não há `DELETE` nem `BEGIN/COMMIT` (não suportados pelo D1).

## 7. Aplicar no D1 local e verificar

```bash
# EXECUÇÃO SOMENTE LOCAL, após aprovação explícita do CSV/SQL
docker compose run --rm api npx wrangler d1 execute oncovo-db \
  --local --persist-to .wrangler/state --json \
  --file db/reconciliation/a5_apply.sql

# Verificação SQL (reconciliation_check deve ser PASS)
docker compose run --rm api npx wrangler d1 execute oncovo-db \
  --local --persist-to .wrangler/state --json \
  --file db/reconciliation/a5_verify.sql

# Snapshot posterior para verificação determinística e possibilidade de rollback
docker compose run --rm api npx wrangler d1 execute oncovo-db \
  --local --persist-to .wrangler/state --json \
  --command "SELECT id,source_id,status,type,title,address,updated_at FROM search_items ORDER BY id" \
  > etl/output/reconciliation/d1_depois_a5.json

docker compose run --rm etl etl/reconciliar_d1_local.py verify \
  --plan db/reconciliation/a5_plan.json \
  --snapshot etl/output/reconciliation/d1_depois_a5.json
```

O comando `verify` sai com status **0** apenas se os cards substituídos estiverem ocultos e os canônicos publicados. Os demais cards, inclusive ausentes em lotes parciais, não são alvos do SQL. Uma segunda execução do mesmo `UPDATE` não altera nada (idempotente), mas **sempre** rode a verificação.

**Atenção operacional:** `prepare-review`, `plan` e `verify` são Python e podem rodar no container ETL; `a5_apply.sql` é aplicado exclusivamente pelo container API. Não há endpoint administrativo no Worker.

## 8. Reversão

Reversão **das ocultações**: a partir do snapshot pós-aplicação ainda atual, gere um novo SQL condicional e revise-o:

```bash
docker compose run --rm etl etl/reconciliar_d1_local.py rollback \
  --plan db/reconciliation/a5_plan.json \
  --snapshot etl/output/reconciliation/d1_depois_a5.json \
  --outdir db/reconciliation

docker compose run --rm api npx wrangler d1 execute oncovo-db \
  --local --persist-to .wrangler/state --file db/reconciliation/a5_rollback.sql
```

Depois, exporte outro snapshot e execute `verify --rolled-back`. A reversão falhará se o registro oculto ou o card canônico tiver mudado desde os snapshots revisados.

**Reversão integral do seed + reconciliação:** pare os containers, faça backup do estado atual e restaure a pasta `.wrangler/state` do backup anterior ao seed (somente no ambiente de homologação). O SQL de rollback **não reverte** edições de título/fonte ocorridas no UPSERT canônico.

## 9. Critérios de aceite e limites

- Aprovados = ocultos após verificação; canônicos = publicados; não mapeados = preservados.
- Repetir `a5_apply.sql` não modifica estado nem duplica linhas.
- Se snapshot/registro evoluir desde a aprovação, update atômico efetua zero alterações; `verify` deve falhar, impedindo que o caso seja considerado concluído.
- Nenhuma remissão implícita de lotes parciais.
- Guardas com `updated_at` têm granularidade do próprio campo; isto **não** substitui backup e verificação.
- `--remote` não está autorizado por este procedimento. Sem certificado de operação atual, **não** promover catálogo histórico para produção.
- Testes Python/SQLite incluem atomicidade lógica, idempotência, bloqueios e reversão; **Wrangler/D1 Docker não está instalado no ambiente do pacote**, portanto execução de comandos acima precisa ocorrer na máquina do projeto.

## Homologação executada em 22/10/2026

O registro anterior de Wrangler não testado foi superado pelo ensaio documentado em [A5_HOMOLOGACAO_2026-10-22.md](A5_HOMOLOGACAO_2026-10-22.md): 75 testes Python, 23 A5, TypeScript, 10 verificações Worker e build Astro aprovados; aplicação, idempotência e duas formas de reversão comprovadas em persistência D1 sintética isolada. **Aplicação editorial real pendente**; principal permanece com 13 lugares publicados e nenhuma ocultação.

A pós-verificação SQL agora confere também fonte/tipo/título/endereço dos dois lados e timestamp canônico. `verify` confere tipo e timestamp do destino. Não basta contar origens ocultas para declarar sucesso.

Cuidados confirmados na máquina:

- `rg --files` ignora `.wrangler`; use inspeção explícita/recursiva para localizar a persistência. Não inicialize outra base por concluir que ela está ausente.
- Prefira `docker compose run --rm --no-deps -T api ...` para operações CLI; evita iniciar dependências e TTY. Capture stdout/stderr separados em UTF-8 e valide JSON inteiro; não remova linhas indiscriminadamente. `--local`, `--persist-to` e `--json` foram conferidos no help da imagem e na [documentação oficial](https://developers.cloudflare.com/d1/wrangler-commands/).
- Aplique SQL gerado por `--file`, como nos exemplos. Ao passar SQL com comentário inicial `--` por argumento separado `--command`, o parser Wrangler pode interpretá-lo como opção. Use arquivo, ou um único argumento `--command=SQL` em captura programática sem shell.
- Use diretórios de backup com timestamp e manifest SHA-256, sem sobrescrever backups anteriores. Pare todos os escritores e confira o backup antes de qualquer escrita. Para verificar SQLite, trabalhe sobre uma cópia do backup.
- As extrações históricas não estão neste checkout. É possível reproduzir somente o staging a partir de `etl/output/search_items.jsonl` sem `--extractions`, pois esse argumento é opcional; registre essa limitação. Não substitua arquivos editoriais nem invente extrações.
- Havendo PID Astro obsoleto após reinício, recriar somente o container web resolveu a execução local nesta sessão, sem alteração no frontend.
