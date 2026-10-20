// worker/index.ts

export interface Env {
  // Faz o link (binding) com o banco D1 configurado no wrangler.toml
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Headers de CORS para permitir que o seu futuro site Astro acesse a API
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Content-Type': 'application/json'
    };

    // Responde ao preflight do navegador para CORS
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // Rota 1: Status da Aplicação (Health Check)
    if (url.pathname === '/api/health') {
      return new Response(JSON.stringify({ status: 'ativo', version: '1.0' }), {
        headers: corsHeaders
      });
    }

    // Rota 2: Busca Principal (MVP)
    if (url.pathname === '/api/search') {
      const query = url.searchParams.get('q') || '';
      
      // Quebra a busca por espaços e remove vazios. Ex: "bar savassi" -> ["bar", "savassi"]
      const terms = query.toLowerCase().split(' ').filter(t => t.trim().length > 0);
      
      try {
        let sqlQuery = `
          SELECT 
            id, source_url, type, title, subtitle, description, 
            neighborhood, address, starts_at, price_label, tags, source_label
          FROM search_items
          WHERE status = 'published'
        `;
        
        const bindParams: string[] = [];

        // Adiciona um AND dinâmico para cada termo da busca
        if (terms.length > 0) {
          const likeClauses = terms.map(term => {
            bindParams.push(`%${term}%`);
            return `search_text LIKE ?`;
          });
          sqlQuery += ` AND (${likeClauses.join(' AND ')})`;
        }

        sqlQuery += ` ORDER BY rank_score_base DESC, created_at DESC LIMIT 20`;

        // Executa a query com os parâmetros dinâmicos
        const stmt = env.DB.prepare(sqlQuery).bind(...bindParams);
        const { results } = await stmt.all();

        return new Response(JSON.stringify({
          query: query,
          total_returned: results.length,
          items: results
        }), { headers: corsHeaders });

      } catch (error) {
        return new Response(JSON.stringify({ error: 'Erro interno na busca' }), { 
          status: 500, 
          headers: corsHeaders 
        });
      }
    }

    // Rota não encontrada
    return new Response(JSON.stringify({ error: 'Not found' }), { 
      status: 404, 
      headers: corsHeaders 
    });
  },
};