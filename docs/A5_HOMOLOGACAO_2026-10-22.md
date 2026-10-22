# Homologação A5 — 22/10/2026

Base: `main` em `720b91a406ef6cdbfaad57edc7240f2f38cb2f4a`. Alterações A5 preexistentes preservadas. Nenhum commit/push.

## A. Diagnóstico inicial

- A5 instalada: script, testes, documentação e D-030/D-031/D-032 presentes, ainda sem commit.
- O sandbox não acessava `/var/run/docker.sock`; comandos Docker funcionaram com execução autorizada fora do sandbox. Não foi necessário mudar permissões do socket.
- Nenhum container estava ativo inicialmente. A persistência existia em `.wrangler/state/v3`; `rg --files` sozinho não a mostrou por respeitar arquivos ignorados. A inspeção recursiva confirmou os bancos.
- Compose monta a mesma pasta do host em `/app/.wrangler`; API e consultas usam `--local --persist-to .wrangler/state`, banco `oncovo-db`, UUID placeholder. Wrangler instalado na imagem: 4.151.3; Node 22.23.4.
- Editorial com 100 registros e catálogo intermediário com 13 presentes. Extrações completas, `etl/processed/` e staging canônico anterior ausentes. Não se reproduziu a transformação dos 100 posts sem as extrações; reproduziu-se a resolução a partir dos 13 cards existentes.
- Registry e overrides aprovados vazios. Não existe autorização editorial real para ocultar Pescados ou fundir SPACE FRIENDS.
- Frontend antigo falhou ao reiniciar: Astro acusava PID 19 de outro servidor. Recriação apenas do container web removeu o estado de processo obsoleto.

## B. Correções

`etl/reconciliar_d1_local.py`: a verificação SQL anterior podia retornar PASS só pelo status dos IDs antigos, sem conferir o destino. Agora confere status, fonte, tipo, título e endereço de origem e destino, além do timestamp congelado do destino. `verify_snapshot` também passou a conferir tipo e timestamp canônicos. O timestamp da origem não deve ser igual ao anterior: o próprio UPDATE o altera.

`tests/test_a5_reconciliation.py`: duas regressões novas, incluindo subcasos de tipo/timestamp/status canônico alterado e fonte antiga alterada. Não se modificaram Worker, frontend, contratos, schema, seed versionado, prompt, registry ou overrides.

Documentação operacional e decisões recebem adendos; decisões anteriores permanecem preservadas.

## C. Testes e evidências

| Camada | Resultado |
|---|---|
| Python em Docker, antes da correção | 73/73 aprovados |
| A5 isolada, antes da correção | 21/21 aprovados |
| Python em Docker, após correção | 75/75 aprovados, 0 falhas, 0 skips |
| A5 isolada, após correção | 23/23 aprovados (subconjunto dos 75) |
| Worker TypeScript | `tsc --noEmit` e compilação aprovados |
| Worker runtime com mocks | 10 verificações aprovadas |
| Astro | build aprovado, quatro páginas |
| Wrangler/D1 real em persistência sintética separada | seed, aplicação, SQL PASS, snapshot verificado, idempotência, rollback e restauração integral aprovados |

Os testes unittest usam SQLite em memória. O ensaio D1 usa o Wrangler/Miniflare da imagem API, via Docker, com arquivos persistentes reais; não é contabilizado como teste SQLite em memória.

Evidências locais ignoradas pelo Git:

- `etl/output/reconciliation/homologacao/python_final.log` e `a5_final.log`.
- `etl/output/reconciliation/homologacao_final/commands.json`: argumentos, stdout, stderr e códigos de saída do ensaio D1.
- `result.json`, `synthetic_verify.json`, snapshots antes/depois/segunda aplicação/rollback/restauração, plano e manifests no mesmo diretório.
- `backup_integrity.json`: SHA-256 da cópia principal e `PRAGMA integrity_check` sobre cópias temporárias dos SQLite; igualdade de todas as colunas de `search_items` e `publication_meta` na restauração sintética.
- SQL efetivamente aplicado somente à persistência sintética: `db/reconciliation/homologacao/`.

O stdout Wrangler foi capturado em UTF-8 por `subprocess.run(capture_output=True, text=True, encoding='utf-8')`; stderr Compose ficou separado. `json.loads` validou o documento antes da gravação. Não se filtraram logs arbitrariamente nem se fabricaram snapshots.

## D. Banco e catálogo

| Métrica | Antes | Depois |
|---|---:|---:|
| D1 principal: total | 13 | 13 |
| D1 principal: publicados | 13 | 13 |
| D1 principal: ocultos | 0 | 0 |
| D1 principal: eventos | 0 | 0 |
| Entidades no staging histórico | — | 12 |
| Fontes mapeadas | — | 13 |
| Grupos determinísticos propostos | — | 1 |
| Pares adicionais pendentes | — | 1 |

Snapshots principais antes/depois idênticos em todas as sete colunas selecionadas. O health retorna `dataset_version=bd8ec9df1886ee93`, `row_count=13`, geração `2026-10-21T15:06:44-03:00`, consistente com `publication_meta` consultado pelo Wrangler. Montagem e conteúdo API/CLI confirmam a persistência usada pelo Worker.

O ensaio sintético inicial tinha 3 linhas: 3 publicadas antes da A5, 2 publicadas e 1 oculta depois, ainda 3 linhas; segunda aplicação sem qualquer alteração no snapshot, inclusive timestamps. Rollback retorna 3 publicadas. A restauração integral recupera também a fonte anterior ao UPSERT, comprovada pela comparação completa das duas tabelas. Uma fixture adicional de evento expirado é inserida apenas para integração HTTP isolada.

## E. Reconciliação e gate editorial

**Nenhum ID real foi alterado.** `6c4ca31679b544b260f84863` permanece publicado; destino proposto `7f9c258e215d8a594ab37aca` também. A fila `homologacao_final/a5_review_pending.csv` tem uma proposta `pending_review`, sem revisor/data/justificativa/evidência de aprovação preenchidos.

SPACE FRIENDS (`DRxdMZgESuA`) e Space Friends Park (`DXgJ9oLDUJu`) permanecem duas entidades. Fonte, entity_id, card_id e original_card_id foram regenerados pelo resolvedor; o grupo Pescados reproduziu `pl_023ed2a3f49ff39c5d8862c7` e o remapeamento histórico esperado.

Aprovações com revisor `SYNTHETIC_TEST_ONLY` e domínio `example.test` pertencem exclusivamente às fixtures FAKEA5 em `.wrangler/a5-synthetic-final/state`; não autorizam qualquer registro real. A registry proposta não foi promovida. Nenhum seed canônico foi aplicado ao banco principal; por isso seu snapshot se chama `d1_real_antes.json`, e não “pós-seed”.

## F. Segurança e reversão

Backup principal: `etl/output/reconciliation/backup_20261022T191004Z/state`, criado às 16:10:04 de São Paulo (19:10:04 UTC), com todos os serviços inicialmente parados e antes de executar consultas D1. Manifest contém 22 arquivos; todos os hashes conferem. Cada SQLite passou `integrity_check` em cópia temporária, sem alterar o backup original.

Para restauração integral da principal, se necessária: parar API e quaisquer escritores, arquivar o estado corrente em novo diretório, copiar `backup_20261022T191004Z/state` para `.wrangler/state`, conferir hashes antes de iniciar serviços e conferir consultas/metadados. Nunca sobrepor uma pasta ativa nem mesclar arquivos WAL de estados distintos. A restauração da principal não foi necessária e não foi executada.

Rollback SQL recupera apenas status das origens e atualiza seu timestamp; não restaura fonte/título modificados pelo seed. Restauração integral recupera tabelas e metadados anteriores ao seed. O procedimento foi provado em `.wrangler/a5-restored-final/state`, sem substituir a principal.

Todos os comandos D1 de execução tiveram `--local`; os argumentos estão no log. Nenhum deploy, scraping, login, chamada paga, operação D1 remota, limpeza de catálogo ou promoção de registry foi executado. A consulta pública à documentação oficial Cloudflare e a instalação de TypeScript no container temporário foram apenas apoio técnico.

## G. Estado final

**A5 tecnicamente validada, pendente de aprovação editorial.** O ensaio Wrangler/D1 foi sintético e isolado; a aplicação editorial real continua pendente. Isto não certifica operação atual dos estabelecimentos.

## H. Próximo passo antes da A1

1. Revisar as duas fontes de Pescados, confirmar unidade/fonte principal, aprovar catálogo e registry propostos. Manter SPACE FRIENDS separado enquanto pendente.
2. Registrar decisão de despublicação com revisor, data ISO, motivo e URL HTTPS no CSV. Não tratar a proposta automática como aprovação.
3. Com decisão disponível: novo backup com escritores parados; preservar seed anterior; gerar/aplicar seed canônico local; exportar snapshot realmente pós-seed; regenerar/revisar plano a partir desse estado; aplicar/verificar e testar buscas. Não reutilizar plano sintético ou snapshot anterior ao seed.
4. Só então iniciar A1 com escopo e autorização de coleta próprios. Para publicação pública, revalidar atualidade dos lugares e eventos separadamente.

## Complemento de integração HTTP

`homologacao_final/api_synthetic.json` comprova que a API em porta 8788 retornou exatamente `a5_test_FAKEA5001` (canônico) e `a5_test_FAKEA5003` (não relacionado), omitindo `a5_test_FAKEA5002` (hidden) e `a5_expired` (evento vencido ainda published no D1). A fixture adicional elevou a base sintética de integração a quatro linhas, sem alterar a principal. O container de integração foi parado e removido ao término.

`api_real_health.json`, `api_real_pescados.json`, `api_real_bar.json` e `api_real_eventos_hoje.json` registram o serviço principal em 8787: health ok, ambos os Pescados ainda visíveis, busca bar funcional, eventos hoje sem resultados. Frontend em 4321 retornou HTTP 200 após recriação do container. Os serviços principais ficaram ativos para revisão local.
