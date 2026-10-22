# Oncovô? — descoberta de lugares e eventos em BH

**MVP:** busque experiências em Belo Horizonte e veja cards com lugar, endereço, data do evento (quando houver), preço, tags e link para a fonte original. **Sem login e sem chatbot na interface.** O processamento de dados/LLM acontece offline, em Python.

## Esta versão

Atualização de 21/10/2026, feita após revisar o primeiro projeto. Preserva o estilo da home original (logo vermelho, fundo âmbar, linguagem informal), recupera a triagem avançada e as regras rigorosas de extração LLM, e adiciona **ambiente local Docker Compose com D1 emulado**, antes da criação da conta Cloudflare.

**Este pacote é um overlay para o repositório atualizado, não uma cópia Git completa.** Conserve os arquivos não incluídos (principalmente `package-lock.json`, `web/package-lock.json` e `web/public/favicon.svg`). Não copie o ZIP legado com `.env`, `.venv` ou credenciais para dentro do novo projeto.

## Primeira execução local — sem conta Cloudflare

Tenha Docker Engine/Desktop e Compose v2. Rode na raiz do repositório:

```bash
docker compose config
docker compose build api web etl

docker compose run --rm api npx wrangler d1 execute oncovo-db --local --persist-to .wrangler/state --file db/schema.sql
docker compose run --rm api npx wrangler d1 execute oncovo-db --local --persist-to .wrangler/state --file db/seed.sql

docker compose up -d api web
```

Abra **http://localhost:4321** (site) e **http://localhost:8787/api/health** (status). Opcional: `python scripts/smoke_local.py` para verificar os dois endpoints. Para parar: `docker compose down`. Para ver logs: `docker compose logs -f api web`.

**Tutorial com solução de problemas:** [docs/DOCKER_LOCAL.md](docs/DOCKER_LOCAL.md).

O banco é local/persistente em `.wrangler/state`; `db/seed.sql` contém uma amostra antiga **apenas para testar**, não um catálogo de produção conferido. Cloudflare não precisa ser configurado agora.

## Testes e fluxo do ETL

```bash
# Sem gastar créditos de IA:
docker compose run --rm etl -m unittest discover -s tests -v

# Se você colocar seu arquivo histórico em etl/raw/all_posts.jsonl:
docker compose run --rm etl etl/triagem_avancada.py --input etl/raw/all_posts.jsonl --outdir etl/processed/dia1

# Apenas prévia, sem chamada LLM:
docker compose run --rm etl etl/extrair_llm.py
```

**Pipeline completo e coleta opcional:** [docs/ETL_OPERACAO.md](docs/ETL_OPERACAO.md). O coletor usa `instagrapi` de forma **manual e opt-in**; confirme autorização e os termos da plataforma antes de acionar `--execute`.

## Arquitetura

```text
Fontes autorizadas / arquivos históricos
    ↓  (offline, opcional)
Coleta Python → JSONL bruto (gitignored)
    ↓
Triagem avançada + dedupe + relatórios
    ↓
Maritaca (opcional) → extração estruturada com evidências
    ↓
Validação e APROVAÇÃO HUMANA
    ↓
JSONL de publicação → SQL UPSERT não destrutivo
    ↓
D1 [local: Wrangler/Miniflare | futuro: Cloudflare]
    ↓
Worker read-only /api/search
    ↓
Astro/Tailwind → cards de resultados
```

## Documentação essencial

- [decisions.md](decisions.md) — histórico e status das decisões; bloqueios para o lançamento.
- [docs/ANALISE_PRIMEIRA_VERSAO.md](docs/ANALISE_PRIMEIRA_VERSAO.md) — avaliação do legado por arquivo/componente e veredito de migração.
- [docs/DOCKER_LOCAL.md](docs/DOCKER_LOCAL.md) — passo a passo e diagnóstico do ambiente local.
- [docs/ETL_OPERACAO.md](docs/ETL_OPERACAO.md) — contratos, revisão, scripts, cuidados com as datas e custo.
- [docs/PUBLICACAO.md](docs/PUBLICACAO.md) — guia anterior de implantação Cloudflare; só utilize **depois** de aprovar o ambiente local.
- [docs/SEGURANCA.md](docs/SEGURANCA.md), [docs/LANCAMENTO.md](docs/LANCAMENTO.md) — controles anteriores.

## Segurança e estado do lançamento

1. O arquivo histórico enviado contém segredos em `.env` e scripts de teste. **Rotacione tudo que ainda é válido.** Nenhum segredo foi incluído na entrega.
2. Nunca use `--remote` durante o desenvolvimento local; o `wrangler.toml` deste pacote traz ID placeholder. Ao criar a conta D1 definitiva, substitua esse UUID com um ID obtido no painel/CLI.
3. A API usa SELECT parametrizado; o frontend não contém a base completa. O `Origin` de CORS não é controle de autenticação.
4. A publicação de lugares e eventos exige confirmação editorial recente. Eventos de junho de 2026 não são tratados como atuais.
5. **Validação realizada aqui:** testes Python e TypeScript (mocks), triagem avançada sobre o arquivo histórico. **Validação não realizada aqui:** build/execução reais do Docker, navegação visual/tempo de resposta no navegador e integração com conta Cloudflare. Elas estão no checklist de `docs/DOCKER_LOCAL.md`.
