# Critérios de go/no-go do soft launch

| Verificação | Estado deste pacote | Responsável operacional |
|---|---|---|
| Python: triagem, extração opcional, revisão, seed | Implementado; 12 testes Python + 10 verificações Worker passaram no ambiente de montagem | Projeto |
| Eventos vencidos bloqueados | Implementado no ETL e API | Projeto |
| Busca/cors/limites/ranking básicos | Implementado e parcialmente testado via mock + SQLite | Projeto |
| Astro e CSS integrados | Implementado, **build Astro não executado neste ambiente** | Dev/CI |
| Docker Compose local (API + Astro + D1) iniciado e testado | **Pendente: execução no computador do projeto** | Dev |
| D1 remoto migrado e conferido | **Não realizado** | Operador Cloudflare |
| Worker implantado e com origem Pages autorizada | **Não realizado** | Operador Cloudflare |
| Pages implantado com PUBLIC_API_URL | **Não realizado** | Operador Cloudflare |
| Marca original (`logo.png`) | Arte horizontal transparente original recuperada; confirmar no navegador | Dev |
| Páginas legais e contatos revisados | **Pendente: textos são modelos iniciais** | Responsável pelo projeto |
| 13 lugares da base revistos quanto à operação atual | **Pendente** | Revisão editorial |
| Eventos recentes para tornar a busca temporal útil | **Pendente** | Coleta/ETL |
| Analytics de page views (opcional) | Habilitar pelo painel Cloudflare Pages | Operador Cloudflare |
| Analytics de busca/clicks customizados | Não implementado nesta fase | Roadmap pós-soft-launch |
| Remoção de arquivos `.wrangler` do Git | **Pendente** | Dev |
| 20 consultas reais e teste mobile | **Pendente** | QA manual |

## Pesquisa de aceitação (amostragem)

- `hamburger`, `hamburgueria`, `burger`
- `restaurante`, `bar`, `café`
- `Santa Tereza`, `Savassi`, `Centro`, `Cidade Nova`
- `música ao vivo`, `pagode`, `rock`, `jazz`
- `evento gratuito hoje`, `eventos amanhã`, `eventos fim de semana`
- `lugar para ir com criança`, `família`
- Termo inexistente, termo com `%` ou `_`, 160+ caracteres, e URL inesperada

Registrar para cada consulta se trouxe um resultado **correto, atualizado e útil**, não apenas se a API retornou HTTP 200. Com apenas 13 lugares elegíveis, ausência de resultados para muitas buscas é esperada e não significa defeito da API.

## Pendências técnicas reconhecidas

1. Entity resolution: mesmo lugar divulgado por posts diferentes ainda pode gerar cards duplicados.
2. Equivalência linguística e relevância: sinônimos manuais cobrem termos comuns; não substituem avaliação por queries reais.
3. Proteção contra extração da base: dados não são baixados na build, mas uma API pública pode ser explorada; configurar proteção de bots/rate limits no painel Cloudflare se necessário.
4. Verificação de estabelecimentos: título/endereço/preço derivados da fonte social precisam de recertificação periódica.
5. Datas de recorrência e eventos noturnos que terminam no dia seguinte vão para revisão manual, não são inferidos silenciosamente.
6. A autenticação administrativa, pagamentos, painel, agente e motor vetorial continuam explicitamente fora do MVP.

<!-- Frente A A0/A2 22-10-2026 -->
## Atualização de estado — 22/10/2026

- **Docker local:** validado **manualmente pelo desenvolvedor**: frontend `localhost:4321`, health do Worker `localhost:8787/api/health`, consultas de demonstração. Substitui a anotação anterior de “pendente” apenas quanto à verificação manual; não implica CI completo.
- **A0 (contratos):** inventário em `docs/CONTRATOS_DADOS.md`.
- **A2 (identidade):** implementação conservadora e testes sintéticos/SQLite locais disponíveis em `etl/resolver_entidades.py`, `tests/test_entity_resolution.py`, `tests/test_entity_sqlite.py`. O script só gera staging e não modifica banco de dados.
- **Bloqueio de produção:** antes do seed canônico revisar candidatos, confirmar estabelecimentos ativos, aprovar registry, auditar remapeamento de IDs e executar reconciliação explícita no D1 local. O UPSERT atual **não** remove cards previamente publicados; A5 permanece pendente.
- **Sem coleta real, sem chamadas à Maritaca e sem D1 remoto** nesta rodada. A base do repositório é apenas demonstração histórica.

<!-- Frente A A5 gate 22-10-2026 -->
## Gate de dados A5 — 22/10/2026

Reconciliação local com plano SQL revisável e reversão condicionada foi implementada. **Não foi executada neste ambiente no Wrangler/D1 local real**: requer snapshot da máquina, aprovação editorial e comandos `--local` listados em `docs/A5_RECONCILIACAO_D1_LOCAL.md`. Não usar o catálogo histórico como prova de atualização. Registro anterior de Docker pendente foi superado pela validação manual informada pelo desenvolvedor.

## Resultado de homologação local A5 — 22/10/2026

Atualiza os registros anteriores de execução pendente: Python 75/75 (A5 23/23), TypeScript, runtime Worker e build Astro aprovados. Ensaio real Wrangler/D1 **sintético isolado** comprovou aplicação, idempotência e reversão. Principal preservada com 13 lugares publicados; catálogo/registry e despublicação real aguardam aprovação humana. Não constitui autorização de lançamento nem certificação de estabelecimentos ativos. Relatório: [A5_HOMOLOGACAO_2026-10-22.md](A5_HOMOLOGACAO_2026-10-22.md).

## A1 offline e integração A2/A5 — 22/10/2026

Infraestrutura de lotes incrementais, proveniência, versões e retomada implementada; integração sintética com Wrangler/D1 isolado aprovada. Isso não autoriza lançamento, aquisição externa ou gasto com LLM. Principal segue com 13 publicados, registry real não promovida e reconciliação editorial pendente. O piloto proposto aguarda autorização de fonte/método e, em fase própria, orçamento A3. Ver [A1_COLETA_INCREMENTAL.md](A1_COLETA_INCREMENTAL.md) e [relatório A1/A5](A1_A5_HOMOLOGACAO_2026-10-22.md).

## A3/A4 técnicas — 22/10/2026

Cache versionado, plano offline, reservas/usage, validação e revisão vinculada à evidência implementados e testados: 140 unittest aprovados e cenário completo no Wrangler/D1 isolado. Não houve aquisição nem inferência paga. Prompt, frontend, Worker, schema e registry reais preservados. Qualidade de modelo/dados recentes não medida: sem gabarito humano real, métricas de acurácia são null. Lançamento continua bloqueado por dados atuais, aprovações editoriais e validação real. Plano posterior: [PILOTO_DADOS_RECENTES.md](PILOTO_DADOS_RECENTES.md).
