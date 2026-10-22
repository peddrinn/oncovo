# Publicação segura — passo a passo

**Pré-condição:** passar pelo checklist em [`DOCKER_LOCAL.md`](DOCKER_LOCAL.md) antes de criar/usar uma conta Cloudflare. A versão deste pacote usa `database_id` fictício `00000000-0000-0000-0000-000000000000` para testes locais: **não** faça qualquer `--remote` antes de criar o D1 real e substituir este UUID. **Não rode o schema antigo com `DROP TABLE`**, nem o gerador de seed antigo com `DELETE FROM search_items`.

## 1. Preparação e commit

Aplique o conteúdo deste pacote por cima da raiz do clone original, preservando `web/public/favicon.svg`, `LICENSE` e os dois `package-lock.json` (a logo horizontal passa a vir deste pacote). Faça revisão de `git diff` antes do commit. A pasta `.wrangler/` está versionada no repositório original e deve ser retirada do índice:

```bash
git rm -r --cached .wrangler
# Isso não elimina seus dados locais: apenas deixa de versionar estados internos.
git status
```

Como esses arquivos já estiveram públicos, confira o histórico para eventuais dados sensíveis. Se alguma credencial aparecer, revogue-a; `.gitignore` não remove o histórico antigo.

## 2. Validação local (antes de publicar)

**Preferir o ambiente Docker reproduzível de [`DOCKER_LOCAL.md`](DOCKER_LOCAL.md)**. Os comandos abaixo são uma alternativa sem Docker, quando Node/Python já estiverem instalados.

```bash
npm ci
npm ci --prefix web
python -m unittest discover -s tests -v
python etl/preparar_publicacao.py --approved etl/items_publicaveis.jsonl \
  --extractions /caminho/extracoes_validas_100.jsonl --raw /caminho/all_posts.jsonl
python etl/gerar_seed.py
npx wrangler d1 execute oncovo-db --local --file db/schema.sql
npx wrangler d1 execute oncovo-db --local --file db/seed.sql
npx wrangler dev
```

Em outro terminal, na pasta `web`: `cp .env.example .env && npm run dev`. Faça pelo menos 20 buscas reais e testes no celular. Não execute `npm ci` se você modificar `package.json` sem atualizar primeiro os respectivos lockfiles via `npm install`.

## 3. Criar conta Cloudflare e D1 remoto (somente DEPOIS de validar Docker)

1. Crie sua conta Cloudflare, vincule GitHub e instale/autentique Wrangler localmente quando estiver pronto para publicar.
2. Crie o D1 definitivo com `npx wrangler d1 create oncovo-db` e copie o UUID retornado para `database_id` em `wrangler.toml` (substituindo **o placeholder**).
3. Confirme a conta e o banco com `npx wrangler d1 info oncovo-db` antes de qualquer importação.
4. Se o D1 estiver NOVO/vazio, você pode pular o backup inicial. Se tiver dados importantes, exporte e guarde backup **fora do Git**.

Somente após revisar a base e confirmar que está operando no projeto correto:

```bash
npx wrangler login
npx wrangler d1 info oncovo-db
# Se já houver dados remotos: npx wrangler d1 export oncovo-db --remote --output=./oncovo-backup.sql
# Faça backup antes de modificar um banco existente; não envie o arquivo ao Git.
npx wrangler d1 execute oncovo-db --remote --file db/schema.sql
npx wrangler d1 execute oncovo-db --remote --file db/seed.sql
npx wrangler d1 execute oncovo-db --remote --command "SELECT status, type, count(*) FROM search_items GROUP BY status,type;"
```

**Cuidado com legado:** D1 pode conter linhas antigas não afetadas pelo UPSERT (IDs antigos aleatórios). O Worker filtra eventos vencidos e itens não aprovados, mas lugares antigos `published` podem permanecer visíveis. Identifique-os e revise-os explicitamente; não execute limpeza global automatizada sem um plano de migração e backup. Este pacote não fornece garantia de limpeza de conteúdo legado não inspecionado.

## 4. Worker

Em `wrangler.toml`, atualize `ALLOWED_ORIGINS` para incluir o domínio EXATO do Cloudflare Pages em produção e as origens locais para desenvolvimento (se necessárias). Depois:

```bash
npx wrangler deploy
# Use a URL BASE mostrada pelo Wrangler, NÃO acrescente /api/search na variável da web.
curl 'https://SEU-WORKER.workers.dev/api/health'
curl 'https://SEU-WORKER.workers.dev/api/search?q=hamburger'
```

A URL acima é ilustrativa, não um endereço existente. Para testar CORS, verifique a requisição feita pelo navegador hospedado em Pages, não só o `curl`.

## 5. Cloudflare Pages (Git conectado)

No painel da Cloudflare, Workers & Pages → Create → Pages → conectar GitHub, selecionar este repositório. Configuração do projeto estático Astro:

| Parâmetro | Valor |
|---|---|
| Diretório raiz | `web` |
| Framework | Astro |
| Comando de build | `npm run build` |
| Diretório de saída | `dist` |
| Versão do Node | 22.12+ (recomendado Node 22 atualizado) |
| Variável de ambiente | `PUBLIC_API_URL=https://URL-REAL-DO-WORKER` |

O frontend faz chamadas **diretas** ao Worker; Cloudflare Pages não recebe binding D1. Configure a mesma variável para Preview, usando backend de teste ou uma origem de preview autorizada. Para previews em subdomínios dinâmicos, avalie CORS e não use `*` automaticamente.

## 6. Aceite de implantação

Confirme: páginas `/`, `/sobre/`, `/privacidade/`, `/termos/` acessíveis; fonte e mapa funcionando; busca com acentos, sinônimos e URL maliciosa; eventos vencidos ausentes; CORS correto; nenhuma falha no console; versão da base no health; 20 pesquisas reais avaliadas manualmente. Ative Web Analytics nas métricas do projeto Pages se desejar medição de acessos. Cloudflare Web Analytics não fornece eventos personalizados de pesquisa/clique: essa instrumentação demanda decisão separada de produto e privacidade.

**Publicação pública só após resolver as pendências listadas em `docs/LANCAMENTO.md`.**
