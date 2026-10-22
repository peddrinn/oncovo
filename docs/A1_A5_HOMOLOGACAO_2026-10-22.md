# Fechamento técnico A5 e homologação A1 — 22/10/2026

## A. Repositório e escopo

Branch `main`; HEAD inicial `e250a5fca911076d71c8834751681dd543981651` (Muitas implementações). Worktree inicial limpo; o commit inclui a homologação A5 anterior. Não houve pull/reset/checkout, commit, push ou merge. Nenhuma alteração preexistente foi descartada.

Arquivos novos: `etl/lotes_incrementais.py`, `etl/homologar_a1.py`, `tests/test_a1_incremental.py`, `docs/A1_COLETA_INCREMENTAL.md` e este relatório. Alterados: coletor opcional, duas triagens, documentos operacionais listados abaixo e decisões. Worker, frontend, schema, seed, prompt Maritaca, extrator, registry e overrides reais permanecem sem mudanças.

## B. A5: estado técnico e decisão editorial

A evidência anterior de 75 testes, TypeScript/runtime Worker/build Astro e integração HTTP/D1 foi examinada e preservada. O checkout inicial passou novamente nos 75 unittest. Não se repetiram indiscriminadamente build/frontend ou restauração da base principal: esses componentes não mudaram.

Nesta execução foram consultados schema, registros e `publication_meta` via Wrangler `--local --persist-to .wrangler/state`, e health dentro do container API. Compose mantém o mesmo bind mount `/app/.wrangler`; metadata e os 13 cards conferem com o Worker. Comparação com a evidência anterior: sete colunas de todos os cards idênticas. Principal: **13 linhas, 13 published, zero hidden, zero eventos**, antes/depois. Não houve escrita SQL na principal, portanto não foi necessário parar serviços para novo backup. Backup anterior verificado permanece em `etl/output/reconciliation/backup_20261022T191004Z/`.

Registry e overrides continuam vazios. Não foi encontrada aprovação humana nova. A fila anterior `etl/output/reconciliation/homologacao_final/a5_review_pending.csv` continua pendente e não foi sobrescrita.

Decisão concreta preparada para revisão:

| Caso | Proposta técnica | Aprovação necessária |
|---|---|---|
| Pescados da Esquina | Manter card `7f9c258e215d8a594ab37aca`, entidade `pl_023ed2a3f49ff39c5d8862c7`; vincular DXiKNIzEbfP e DYp5wrURWxO; fonte primária proposta DYp5wrURWxO; ocultar somente `6c4ca31679b544b260f84863` | Confirmar mesma unidade, fonte principal e promoção da registry; decisão A5 com revisor/data/motivo/HTTPS após snapshot pós-seed |
| SPACE FRIENDS / Space Friends Park | Manter `5659a5fe050b32416fa2eaad` e `469a589bc5e0702a2fff65f1` como duas entidades | Evidência humana sobre unidade/negócio antes de qualquer fusão |

Pescados tem nome/endereço coincidentes nos arquivos locais (Rua Bocaiuva, 3, Santa Tereza); isso sustenta a proposta determinística, sem necessidade técnica de override adicional, mas não substitui aprovação. SPACE FRIENDS tem nomes diferentes e endereço informado coincidente (Rua Catumbi, 390); pode ser mesma marca, mudança de nome ou negócios distintos. Não houve inspeção externa atual dos posts/unidades nem certificação de funcionamento.

**A5 tecnicamente validada; não editorialmente aplicada.** A aprovação real ausente não impediu A1 offline, explicitamente autorizada nesta tarefa.

## C. Implementação A1

Novo importador offline com batch_id determinístico/explicito, manifesto versionado, UTC com fuso, referência de fonte/método/autorização, perfis, janela pretendida, contagens, checksums e checkpoints. Identidade global `instagram:code`; perfis consultados são proveniência separada de autor/coautores. SHA-256 identifica conteúdo alterado; inputs/chunks preservam versões originais.

`pending/` não alimenta consumidores. Escritores são serializados por flock; chunks e manifestos usam arquivos temporários, fsync e replace. Somente lote íntegro é promovido por rename para `batches/`. Erros de JSON/encoding/campos/fuso/última linha sem newline bloqueiam a promoção integral. Retomada recusa alteração de entrada/configuração ou avanço inesperado do parent. Replay completo valida hashes e retorna o mesmo manifesto, sem nova escrita.

Cada lote completo disponibiliza snapshot lógico global e delta de novos/alterados. Reencontro em outro perfil acumula proveniência sem segunda entrada LLM. Posts ausentes de lote parcial continuam no snapshot global. Não há matching de estabelecimentos na coleta.

Coletor legado permanece opcional. Foi removido splitlines; raw de aquisição não é sobrescrito. Sidecar registra perfis completos/falhos e impede promover aquisição parcial. Retomada pula perfis completos; perfil interrompido pode ser consultado com sobreposição, deduplicada na A1. Cliente real/login não foram executados: somente cliente falso nos testes. Fonte/método exigem autorização externa e `--authorization-reference` na execução futura.

As duas triagens preservam `_source_profiles`. O contrato `messages_for` foi exercitado sem chamada externa e sem alterar prompt/extrator. Limite reconhecido: o cache legado da A3 é por post_code, não por hash; extração de revisão alterada exige arquivo/contexto por lote e implementação/validação própria na A3, sem reutilizar silenciosamente a versão antiga.

## D. Testes e evidências

| Verificação | Resultado |
|---|---|
| Baseline Docker do checkout inicial | 75/75 unittest aprovados |
| Suíte Docker final | **98/98 aprovados**, zero falhas, zero skips |
| Subconjunto A1 final | **23/23 aprovados** |
| Subconjunto A5 final | **23/23 aprovados** |
| Auditoria de cópia editorial histórica | 100 objetos/100 códigos distintos, zero inválidos/duplicatas |
| Integração offline final A1→triagem→preparação sintética→A2 | Aprovada, contrato LLM renderizado sem executar API |
| Integração Wrangler/D1 local isolada | PASS SQL, verify, guards, repetição, rollback e restauração integral aprovados |
| git diff --check | Aprovado |

A1 cobre post novo, repetido no mesmo/outro perfil, legenda alterada, U+2028, JSON inválido, gravação interrompida, chunks temporários, pausa/retomada, checkpoint por perfil, corrupção de arquivo, colisão de batch_id, parent avançado e adaptador opcional falso. As regressões A2/A5 cobrem unidades/filiais, nomes sem endereço, mudança de nome, eventos em datas distintas/vencidos, promoção, recorrência ambígua, revisão editorial, fontes ausentes, fusão aprovada de fixture e bloqueio sem aprovação.

Evidências ignoradas:

- `etl/output/a1_validation/`: logs finais Docker/A1/A5, inspeção real, health, comparação com A5 e auditoria editorial.
- `etl/output/a1_final_offline/`: manifestos, versões, triagem, mapa/registry propostos e `scale.json` da versão final offline.
- `db/reconciliation/a1_20261022_v1/`: ensaio Wrangler, comandos completos, stdout/stderr separados, snapshots, plano, SQL, backup e manifestos.
- As evidências A5 anteriores foram preservadas.

Os unittest usam Python/SQLite em memória. O ensaio Wrangler usa processos Docker/Miniflare reais e arquivos D1 persistentes isolados. Não somar os subconjuntos aos 98 testes como se fossem testes únicos adicionais. Alterações finais em metadados/checkpoints/contagens e adaptador foram revalidadas na suíte e ensaio offline; a lógica SQL/A2 não mudou depois do ensaio D1, por isso não se repetiu essa operação cara sem necessidade.

## E. Métricas dos lotes e escala

Raw histórico `etl/raw/all_posts.jsonl` e extrações completas não estavam presentes. A amostra editorial com 100 itens foi auditada em cópia; não foi usada como raw nem como extração. O staging histórico existente continua com 13 fontes e 12 entidades propostas, não estabelecimentos comprovadamente ativos. Não se inventaram taxas reais de aquisição/qualidade.

Ensaio incremental sintético:

| Lote | Recebidos | Novos | Repetidos | Alterados | Inválidos/descartados de ingestão | Delta |
|---|---:|---:|---:|---:|---:|---:|
| Inicial | 2 | 2 | 0 | 0 | 0 | 2 |
| Incremento | 4 | 2 | 2 | 0 | 0 | 2 |

Após os dois lotes: 4 posts lógicos, 3 entidades, 1 grupo de fusão por evidência exata, 5 pares candidatos sem aprovação automática. Os nomes iguais de filiais geram candidatos identificáveis, mas endereços diferentes impedem fusão. A fila avançada executada no incremento tinha 2 candidatos LLM, sem chamadas pagas. Legenda alterada foi testada separadamente: uma revisão detectada com versão anterior preservada. Inválidos e arquivo interrompido foram bloqueados em fixtures separadas, sem promoção.

Simulação final no host, sem rede: N posts únicos + 20% de observações repetidas, isto é, 16,67% do total recebido. Tempos incluem IO local/fsync e instrumentação tracemalloc da A1. Memória Python é pico da A1; `process_maxrss_kib` no JSON é high-water acumulado do processo, incluindo A2/ordem inversa. Não é benchmark de produção.

| Únicos | Recebidos | A1 (s) | A2 (s) | Pico Python A1 (MiB) | Entidades | Candidatos | Arquivos | Erros |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 120 | 0.296 | 0.056 | 1.25 | 100 | 600 | 11 | 0 |
| 500 | 600 | 1.016 | 0.281 | 2.04 | 500 | 3064 | 15 | 0 |
| 1000 | 1200 | 1.659 | 0.459 | 3.02 | 1000 | 6144 | 21 | 0 |
| 5000 | 6000 | 8.033 | 2.786 | 10.00 | 5000 | 30784 | 69 | 0 |

IDs foram estáveis na ordem inversa em todos os volumes. Nomes artificiais muito semelhantes produziram 30.784 candidatos em 5.000 entidades distintas: é carga de revisão, não fusão automática nem taxa real de duplicação de BH. Buckets grandes de bairro/nome podem ter custo quadrático no resolvedor atual. Não se alterou o limiar/arquitetura para fazer benchmark parecer melhor; priorizar observação da fila e amostra real antes de otimizar. Snapshots integrais por lote também têm custo de armazenamento proporcional ao histórico; não foi implementado expurgo automático.

## F. Integração A2/A5 e reversão

Script reproduzível: `etl/homologar_a1.py`. Persistência usada: `.wrangler/a1_a1_20261022_v1/state`, nova e isolada, com a mesma configuração D1 da aplicação. Inicial canônico com 2 linhas; incremento simula ID legado de fonte nova e adiciona outra filial. Seed canônico repetido preserva IDs; a nova fonte usa o ID já fixado, mesmo mudando a fonte primária. Ordem invertida e lote parcial com apenas a nova fonte preservam entidade/registry de fontes ausentes.

Antes da A5: 4 linhas publicadas; após aprovação **somente de fixture**: 4 linhas, 3 publicadas e 1 hidden. O item ausente do incremento e os demais não alvos ficaram idênticos no snapshot. Sem aprovação, plano bloqueado. Timestamp de origem propositalmente atrasado impediu aplicação; verify falhou. Após reposição da fixture/snapshot esperado, SQL retornou PASS e verify passou. Segunda aplicação manteve snapshot inteiro idêntico, incluindo timestamps.

Rollback SQL retornou as 4 linhas a published. Backup integral foi copiado após schema/seed inicial com one-offs encerrados, antes dos seeds de incremento, e conferido por SHA-256. Restauração em `.wrangler/a1_a1_20261022_v1_restored/state` recuperou exatamente `search_items` (todas as colunas) e `publication_meta`, também conferida via Wrangler. A principal não foi restaurada nem recebeu fixtures. Reprocessar A1 retorna o mesmo batch completo; não agenda publicação repetida. A repetição do seed canônico não ressuscita o ID legado ocultado porque ele não pertence ao canônico.

## G. Segurança

Nenhuma coleta real, login externo, download de novas fontes, chamada Maritaca, deploy, operação D1 remota, limpeza de catálogo ou promoção editorial foi executada. Todos os comandos D1 registram `--local` e persistência explícita. Aprovações `SYNTHETIC_TEST_ONLY`/example.test estão apenas em fixtures isoladas. Não houve alteração do prompt ou inclusão de raw/legendas privadas no Git. Dados da amostra editorial já versionada foram apenas copiados para pasta ignorada.

## H. Estado por frente

| Frente | Estado técnico | Pendência externa/editorial |
|---|---|---|
| A1 | **Concluída tecnicamente no escopo offline**, retomada e integração testadas | Aquisição real e compatibilidade live do adaptador exigem autorização e piloto; não foram executadas |
| A2 | **Concluída tecnicamente para o escopo exercitado**, IDs/fontes/filiais/tempos validados | Registry real, fusões e atualidade dependem de revisão humana; desempenho/candidatos exigem observação no piloto |
| A5 | **Concluída tecnicamente no D1 local sintético**, regressões preservadas | Aplicação editorial real de Pescados pendente; SPACE FRIENDS sem fusão aprovada |

Nenhuma dessas classificações equivale a prontidão para publicação pública.

## I. Próxima ação, commit e reprodução

Proposta de piloto: **160 observações em dois lotes de 80**, com autorização nominal de fontes/método: 60 gastronomia, 40 lazer/experiências, 40 agendas/eventos e 20 espaços culturais/públicos; janela pretendida de 60 dias para lugares e 21 para agendas, mantendo só ocorrências futuras comprovadas para publicação. Detalhes/custos/métricas/gates em `docs/A1_COLETA_INCREMENTAL.md`. O número é uma hipótese operacional, ajustável pela capacidade editorial e teto de gasto futuro; nenhum custo pago foi medido. Não executar o piloto ainda.

Decisões humanas pendentes: confirmar unidade e fonte principal de Pescados, promover registry revisada e aprovar/recusar a ocultação; investigar SPACE FRIENDS mantendo separado enquanto incerto; autorizar fonte/método do piloto e, separadamente na A3, orçamento e cache/reprocessamento por versão. Nenhuma aprovação deve ser inferida deste relatório.

Frente B: oferecer no fluxo de revisão a distinção post/entidade e fonte principal/secundárias; apresentar evidências de fusão sem aprovação automática; preparar capacidade editorial para candidatos e métricas de rendimento por fonte. Não houve mudança de frontend/contrato para antecipar essas decisões.

Arquivos para revisão e eventual commit:

- Novos `etl/lotes_incrementais.py`, `etl/homologar_a1.py`, `tests/test_a1_incremental.py`.
- Modificados `etl/instagram_collect.py`, `etl/triagem.py`, `etl/triagem_avancada.py`.
- `decisions.md`, `docs/A1_COLETA_INCREMENTAL.md`, `docs/A1_A5_HOMOLOGACAO_2026-10-22.md`, `docs/ETL_OPERACAO.md`, `docs/CONTRATOS_DADOS.md`, `docs/RESOLUCAO_ENTIDADES.md`, `docs/A5_HOMOLOGACAO_2026-10-22.md`, `docs/LANCAMENTO.md`.

Manter ignorados: `etl/raw/`, `etl/processed/`, `etl/output/`, `db/reconciliation/`, `.wrangler/`, caches, credenciais/cookies/sessões. Não promover propostas ou fixtures para registry/seed reais. As regras existentes de ignore já cobrem as novas evidências.

Comandos mínimos (na raiz):

```bash
docker compose run --rm etl -m unittest discover -s tests -v
docker compose run --rm etl -m unittest discover -s tests -p test_a1_incremental.py -v
# Saída nova em cada ensaio; sem redes:
docker compose run --rm etl etl/homologar_a1.py --outdir etl/output/a1_repro_novo --scale
# Host Linux/WSL: Docker necessário, D1 sempre isolado/local:
python3 etl/homologar_a1.py --outdir db/reconciliation/a1_repro_novo --wrangler
```

Nada foi commitado ou enviado. Os serviços locais existentes foram preservados.

Complemento explícito de reprocessamento: `reseed_commands.json`/`after_reseed.json` no ensaio D1 registram novo plano após rollback, nova aplicação e seed canônico **depois** da A5. Permaneceram 4 linhas, 3 published e 1 hidden, exatamente o mesmo mapa ID→status. O card legado não foi ressuscitado. A lógica foi incorporada ao script reproduzível; a extensão executada foi preservada nas evidências ignoradas.
