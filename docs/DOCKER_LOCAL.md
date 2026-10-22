# Oncovô? — execução local com Docker (antes da Cloudflare)

**Objetivo:** executar frontend Astro, API Worker, D1 emulado pelo Wrangler/Miniflare e ETL Python **sem criar conta Cloudflare**. Comandos executados no diretório-raiz do repositório atualizado. Docker Desktop/Engine + `docker compose` v2 obrigatórios. **Nenhum comando abaixo usa `--remote`.**

## 0. Antes de iniciar

- Faça commit/backup de sua branch e aplique o ZIP desta entrega sobre o repositório atualizado (`peddrinn/oncovo`); preserve `package-lock.json`, `web/package-lock.json`, imagens e favicons que já existem no repositório.
- Confirme que `package-lock.json` e `web/package-lock.json` existem, bem como `web/public/logo.png`.
- Arquivos no antigo `.env` do ZIP não devem ser copiados. Se suas credenciais antigas forem verdadeiras, rotacione-as.
- Não precisa de Node ou de Python instalados na máquina para iniciar os containers. Apenas Docker e terminal. O smoke test Python pode ser executado por Python do sistema, ou com `docker compose exec ...` (veja observação abaixo).
- Windows: use PowerShell e `docker compose` diretamente; os comandos `make` são opcionais.

## 1. Primeira compilação

```bash
docker compose config
docker compose build api web etl
```

A instalação de pacotes NPM requer acesso à internet **no build**. Docker baixará imagens do registry. Para coletar também do Instagram, use `docker compose --profile collector build collector` apenas quando for necessário.

## 2. Criar schema e inserir catálogo de demonstração

```bash
docker compose run --rm api npx wrangler d1 execute oncovo-db --local --persist-to .wrangler/state --file db/schema.sql
docker compose run --rm api npx wrangler d1 execute oncovo-db --local --persist-to .wrangler/state --file db/seed.sql
```

O diretório local `.wrangler/` é montado no container e persiste o banco. A **mesma opção `--persist-to .wrangler/state`** aparece no serviço `api` e nos dois comandos, evitando dois bancos diferentes. Não execute `--remote` durante esta etapa.

`db/seed.sql` usa uma amostra histórica de estabelecimentos; resultados exibidos não provam que os locais ainda estejam funcionando.

## 3. Ligar tudo

```bash
docker compose up -d api web
docker compose ps
docker compose logs -f --tail=80 api web
```

Abra **http://localhost:4321** (frontend). API: **http://localhost:8787/api/health**; busca: **http://localhost:8787/api/search?q=bar**. Para sair dos logs: `Ctrl+C` (não derruba os serviços). Para parar: `docker compose down` (mantém banco). Para remover o banco local, pare os containers e apague `.wrangler/state` após fazer backup — **nunca** faça isso sobre um DB remoto.

Verificação programática após os serviços subirem:

```bash
python scripts/smoke_local.py
```

Se não tiver Python no host: abra as URLs no navegador e confirme `status: ok`, retorno de lista em `/api/search?q=bar` e cards na home.

## 4. Testes internos de ETL e TypeScript

```bash
docker compose run --rm etl -m unittest discover -s tests -v
# alternativa fora de Docker, se tiver Node + npm já instalados:
npm ci
npx tsc --project worker/tsconfig.json --noEmit
```

A suíte completa de Worker (mocks) é executada no CI do GitHub. O teste acima do ETL usa o volume `tests/` montado somente para leitura.

## 5. Recriar catálogo após revisar novas extrações

Guarde dados históricos fora do controle de versão (`etl/raw`, `etl/processed`). `db/seed.sql` fornecido já permite testar busca sem credenciais. Para reproduzir pipeline:

```bash
# Etapa 1: se tiver etl/raw/all_posts.jsonl
docker compose run --rm etl etl/triagem_avancada.py --input etl/raw/all_posts.jsonl --outdir etl/processed/dia1 --llm-limit 100
# Etapa 2: simulação: não chama API nem gasta tokens
docker compose run --rm etl etl/extrair_llm.py --input etl/processed/dia1/dia1_fila_llm_100.jsonl
# Etapa 3: para rodar LLM de verdade, defina MARITACA_API_KEY em .env local e confirme o custo ANTES.
# docker compose run --rm etl etl/extrair_llm.py --execute --max-items 10
# Etapa 4: gerar fila editorial (NÃO aprova itens)
docker compose run --rm etl etl/criar_revisao.py --input etl/processed/extracoes.jsonl
# Edite com revisão humana o publish_status em etl/processed/para_revisao.jsonl.
docker compose run --rm etl etl/preparar_publicacao.py --approved etl/processed/para_revisao.jsonl --extractions etl/processed/extracoes.jsonl
docker compose run --rm etl etl/gerar_seed.py
# Atenção: se não houver nenhum item aprovado, a geração falhará — propositalmente.
# Depois de conferir etl/output/revisao.csv e o SQL gerado, rode o comando local de seed acima.
```

## 6. Coleta manual opcional (não faz parte de `up`)

Somente execute após confirmar que tem autorização e pode usar o método nos termos da plataforma. Credenciais (se necessárias) vão no `.env` local, **não em scripts nem no Git**:

```bash
cp .env.example .env
# editar .env local sem commitar
# apenas exibe intenção, sem login/chamada:
docker compose run --rm collector etl/instagram_collect.py --profiles ondeirbh comabembh --max-per-profile 10
# execução real exige --execute; não há retries para contornar bloqueios:
# docker compose run --rm collector etl/instagram_collect.py --profiles ondeirbh --max-per-profile 10 --execute
```

O resultado fica em `etl/raw/coleta_instagram.jsonl`, ignorado pelo Git. O build do coletor é separado justamente porque `instagrapi` possui dependências/risco operacional próprios. Se preferir API oficial/autorizada, troque apenas o conector de coleta, mantendo o JSONL de saída.

## 7. Solução de problemas

| Sintoma | Verificação/ação |
|---|---|
| `npm ci` falha | Preserve **ambos** os lockfiles atuais do GitHub. Não use `npm install` aleatório para corrigir dependências em produção. |
| Porta 4321/8787 ocupada | Pare serviço conflitante, ou adapte porta host e `PUBLIC_API_URL`/`ALLOWED_ORIGINS` de forma consistente. |
| Frontend carrega sem estilos | Confira `web/src/layouts/Base.astro` importando `../styles/global.css` e `@import "tailwindcss"`. |
| `health` retorna 503 | Execute `schema.sql` no mesmo `.wrangler/state`; confira logs da API. |
| Busca retorna lista vazia | Confira seed local, `status`, consulta e atualidade; 13 itens históricos não cobrem todas as intenções. |
| `ERR_CONNECTION_REFUSED` em browser | A URL `PUBLIC_API_URL` tem de ser acessível **pelo navegador da máquina**, por isso usa `localhost:8787`, não `api:8787`. |
| Dados somem entre containers | Verifique que você executou os comandos sempre na mesma pasta raiz, com `--persist-to .wrangler/state`. |
| LLM não executa | Sem `--execute` é dry-run; depois configure `MARITACA_API_KEY` fora do código. |
| Login Instagram falha | Não contorne desafios; revise credenciais, permissão, termos e método oficial. |

## Critérios de aprovação local para prosseguir ao deploy

- [ ] `docker compose config` sem erros.
- [ ] Builds `api`/`web`/`etl` concluídos.
- [ ] `GET /api/health` retorna `status: ok` e metadados do catálogo.
- [ ] `GET /api/search?q=bar` retorna JSON válido (com ou sem hits conforme catálogo).
- [ ] Home em 4321 abre, logo vermelha e fundo âmbar renderizam; layout mobile não quebra.
- [ ] Acessibilidade básica: teclado navega, estados de carga/vazio/erro aparecem.
- [ ] Testes Python + TypeScript passam.
- [ ] Arquivos `.env`, `.wrangler`, raw JSONL e sessões NÃO são rastreados pelo Git.
- [ ] Dados de locais e eventos foram verificados editorialmente antes de compartilhar.

**Referências oficiais:** Cloudflare D1 [desenvolvimento local](https://developers.cloudflare.com/d1/best-practices/local-development/), [comandos Wrangler](https://developers.cloudflare.com/d1/wrangler-commands/) e [persistência](https://developers.cloudflare.com/workers/local-development/local-data/).
