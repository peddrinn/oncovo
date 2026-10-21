# Controles de segurança, privacidade e integridade

- A chave `MARITACA_API_KEY` é somente local/servidor e nunca aparece no Worker ou frontend.
- Não inclua `all_posts.jsonl` nem `extracoes_validas_100.jsonl` no Git sem revisão de licenças, direitos e informações pessoais. `.gitignore` protege apenas novos arquivos não rastreados.
- O repositório GitHub atual versiona `.wrangler/state/` (estado SQLite local). Remova do índice e audite o histórico antes de compartilhar.
- A API é pública e de leitura: não expõe conexão D1 nem rotas de escrita. O SQL usa placeholders D1, escape para LIKE e limites de quantidade.
- CORS restrito protege o uso em navegadores de outras origens, **não impede chamadas por bots nem autentica clientes**.
- HTML dinâmico é construído com `textContent`, não com `innerHTML` de fontes externas. Links exigem HTTPS e `rel=noopener noreferrer`.
- Segurança de conteúdo: revisar cabeçalhos, WAF, limites de taxa e CSP compatível com o domínio real antes de grande divulgação.
- Data freshness: Worker bloqueia eventos vencidos, inclusive caso o seed não tenha sido regenerado; lugares exigem revisão de operação.
- A interface publica somente descrições derivadas curtas e link à fonte; não exibe legendas completas do Instagram.
- LGPD: as páginas informativas disponíveis são apenas textos preliminares. Defina controladoria, canal de contato e política definitiva se houver coleta, analytics personalizado ou formulário.
- Sem upload de dados brutos, vídeos ou fotografias de terceiros ao site.
