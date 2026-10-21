# Oncovô? — busca local de experiências em Belo Horizonte

**MVP:** campo de busca, filtros rápidos, lista de cards, links para a fonte e mapa. Sem login, chatbot, banco vetorial, painel de administração ou páginas individuais. O LLM é utilizado somente no ETL offline.

## Arquitetura

```text
Instagram (dados capturados localmente)
  → Python: triagem → extração LLM (opcional, Maritaca) → revisão editorial
  → Python: normalização + verificação temporal → db/seed.sql
  → D1 (SQLite) → Cloudflare Worker /api/search
  → Cloudflare Pages (Astro 7 + Tailwind 4)
```

## Começo rápido

Requisitos: Python 3.11+, Node.js >=22.12, conta Cloudflare com D1 existente e Wrangler autenticado. O repositório original já contém `web/public/logo.png`, `web/public/favicon.svg`, `package-lock.json` e `web/package-lock.json`; conserve esses arquivos ao aplicar o pacote.

```bash
npm ci
npm ci --prefix web
python -m unittest discover -s tests -v

# Extrações históricas: use o seu arquivo local, nunca publique dados brutos.
python etl/preparar_publicacao.py \
  --approved etl/items_publicaveis.jsonl \
  --extractions /CAMINHO/extracoes_validas_100.jsonl \
  --raw /CAMINHO/all_posts.jsonl
python etl/gerar_seed.py

# Primeiro no D1 LOCAL (usa arquivos db/schema.sql e db/seed.sql)
npx wrangler d1 execute oncovo-db --local --file db/schema.sql
npx wrangler d1 execute oncovo-db --local --file db/seed.sql
npm run dev
```

Em outro terminal:

```bash
cd web
cp .env.example .env
npm run dev
```

Acesse `http://localhost:4321`. Se a API responder em outro endereço, ajuste `PUBLIC_API_URL` em `web/.env` com a **URL base**, por exemplo `http://localhost:8787` (sem `/api/search`).

**Produção:** leia [`docs/PUBLICACAO.md`](docs/PUBLICACAO.md) antes de executar QUALQUER comando `--remote`. O seed inclui só as aprovações e eventos válidos no momento em que foi gerado; reexecute o ETL antes de subir a base.

## Estrutura

- `etl/triagem.py`: deduplica por código do post e cria fila de legendas suficientes.
- `etl/extrair_llm.py`: processa até 10 posts por execução (uma requisição por post); por padrão é *dry run* (sem custo), a flag `--execute` efetua chamadas reais ao modelo.
- `etl/preparar_publicacao.py`: junta extração e aprovação, aplica regras de produto, gera auditoria CSV e registros D1.
- `etl/gerar_seed.py`: IDs reproduzíveis e UPSERT não destrutivo.
- `db/schema.sql`, `db/seed.sql`: tabelas e dados locais de publicação, mais metadados da versão.
- `worker/index.ts`: API pública (`/api/search`, `/api/suggestions`, `/api/health`).
- `web/`: Astro estático, Tailwind 4, cards de texto e links seguros.
- `tests/`: validação de pipeline, SQL e comportamento do Worker.
- `docs/`: implantação, decisões e itens pendentes.

## Regras de produto e segurança

- Só itens aprovados (`published`) e com confiança mínima podem entrar no seed.
- Eventos somente com datas ISO defensáveis e não expiradas; **promoções fora da busca**.
- `starts_at` para lugares é sempre `NULL`: horário de funcionamento não é evento.
- D1 fica atrás do Worker e não é embarcado no HTML.
- SQL parametrizado, limite de paginação, sem endpoints públicos de inserção, CORS restrito a origens configuradas, saída textual segura no DOM.
- A busca usa normalização, sinônimos e ranking básico, sem custos de LLM por requisição.
- O endpoint de health divulga versão da aplicação e hash do catálogo publicado.
- A única base de teste fornecida foi gerada em junho de 2026 e precisa de checagem de estabelecimentos antes de lançamento oficial.

## Auditoria inicial com o material disponível em 20/10/2026

Dos 100 itens editoriais: **13 itens publicáveis (lugares), 32 em revisão, 41 expirados, 14 ocultados**. O pacote inclui `etl/output/revisao.csv` e um seed para os 13 lugares elegíveis; não atesta que todos continuam abertos. Nenhum evento histórico foi mantido como futuro.

## Limites declarados

Não há scraping automático em produção, deduplicação semântica entre posts diferentes do mesmo lugar, inventário atualizado de estabelecimentos nem telemetria personalizada. Cloudflare Web Analytics pode ser habilitado na interface de Pages para page views; no momento, **não** mede cliques nem pesquisas. Revisar `docs/LANCAMENTO.md` antes de publicar. O acesso à conta de Cloudflare e às configurações do domínio deve ser feito pelo operador do projeto; nenhuma operação remota foi executada nesta entrega.
