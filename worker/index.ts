/** Oncovo API: endpoint público SOMENTE leitura. D1 não é exposto no frontend. */
export interface Env { DB: D1Database; ALLOWED_ORIGINS?: string }

type SearchItem = {
  id: string; source_url: string | null; type: 'place'|'event';
  title: string; subtitle: string | null; description: string | null;
  neighborhood: string | null; address: string | null; starts_at: string | null;
  ends_at: string | null; price_label: string | null; price_type: string | null;
  categories: string | null; tags: string | null; source_label: string | null;
};

const STOP = new Set(['a','as','o','os','um','uma','de','da','do','das','dos','em','na','no','nas','nos',
  'para','por','com','e','que','quero','onde','bh','belo','horizonte','procurar','buscar','busca']);
const SYNONYMS: Record<string,string[]> = {
  hamburguer: ['hamburguer','hamburgueria','hamburger','burger','burguer','podrao'],
  hamburgueria: ['hamburgueria','hamburguer','burger','burguer','hamburger'],
  hamburger: ['hamburger','hamburguer','hamburgueria','burger','burguer'],
  burger: ['burger','burguer','hamburgueria','hamburguer'],
  burguer: ['burguer','burger','hamburgueria','hamburguer'],
  cafe: ['cafe','cafeteria'],
  crianca: ['crianca','criancas','infantil','kids','familia'],
  criancas: ['criancas','crianca','infantil','kids','familia'],
  familia: ['familia','crianca','infantil','kids'],
  gratuito: ['gratuito','gratis'],
  gratis: ['gratis','gratuito'],
  pagode: ['pagode','samba'],
  musica: ['musica','musical','show'],
  restaurante: ['restaurante','gastronomia'],
};
const normalize = (v:string) => v.normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
const escapeLike = (v:string) => v.replace(/[\\%_]/g, '\\$&');
const json = (v:unknown,status=200,origin?:string,ttl=0) => new Response(JSON.stringify(v),{
  status,headers:{'Content-Type':'application/json; charset=utf-8','X-Content-Type-Options':'nosniff',
    'Cache-Control':ttl?`public, max-age=${ttl}`:'no-store',
    'Vary':'Origin',...(origin?{'Access-Control-Allow-Origin':origin}:{})},
});
const localParts = (now:Date) => {
  const pieces = new Intl.DateTimeFormat('en-US',{timeZone:'America/Sao_Paulo',year:'numeric',
    month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'})
    .formatToParts(now);
  const part = (k:string) => pieces.find(p=>p.type===k)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}:${part('second')}`;
};
const dayString=(d:Date)=>d.toISOString().slice(0,10);
function dateWindow(scope:string,today:string):[string,string]|null {
  if (!scope) return null;
  const date = new Date(`${today.slice(0,10)}T12:00:00Z`);
  if(scope==='tomorrow') date.setUTCDate(date.getUTCDate()+1);
  if(scope==='weekend') {
    const weekday=date.getUTCDay(); // Sunday=0; próxima ocorrência de sábado
    const delta=weekday===0?-1:(6-weekday+7)%7;
    date.setUTCDate(date.getUTCDate()+delta);
    const sat=dayString(date);date.setUTCDate(date.getUTCDate()+1);
    return [sat,dayString(date)];
  }
  const day=dayString(date);return [day,day];
}
function searchParameters(url:URL) {
  const raw=(url.searchParams.get('q')||'').trim();
  if(raw.length>160) throw new Error('Consulta longa demais (limite: 160 caracteres)');
  const original = normalize(raw);
  if (original.length < 2) throw new Error('Informe ao menos dois caracteres para buscar');
  const tokens=original.split(' ').filter(Boolean);
  const all=new Set(tokens);
  let scope=url.searchParams.get('date')||'';
  if(!scope) {
    if (all.has('hoje')) scope='today';
    else if (all.has('amanha')) scope='tomorrow';
    else if (all.has('fim') && all.has('semana')) scope='weekend';
  }
  if (!['','today','tomorrow','weekend'].includes(scope)) throw new Error('Filtro date inválido');
  const explicitType=url.searchParams.get('type')||'';
  if (!['','place','event'].includes(explicitType)) throw new Error('Filtro type inválido');
  const onlyFree=url.searchParams.get('price_type')==='free' || all.has('gratis') || all.has('gratuito');
  const inferredEvent=all.has('evento')||all.has('eventos');
  const inferredPlace=all.has('lugares')||all.has('lugar');
  const type=explicitType||(inferredEvent?'event':inferredPlace?'place':'');
  const intent=new Set(['hoje','amanha','fim','semana','final','finalzinho','evento','eventos','lugar','lugares','gratis','gratuito']);
  const relevant=tokens.filter(t=>t.length>1&&!STOP.has(t)&&!intent.has(t));
  if(relevant.length>8) throw new Error('Use até 8 termos relevantes');
  const limitRaw=Number(url.searchParams.get('limit')??20);
  const offsetRaw=Number(url.searchParams.get('offset')??0);
  if(!Number.isInteger(limitRaw)||limitRaw<1||limitRaw>30||!Number.isInteger(offsetRaw)||offsetRaw<0||offsetRaw>300)
    throw new Error('Paginação inválida');
  const neighborhood=(url.searchParams.get('neighborhood')||'').trim();
  const category=(url.searchParams.get('category')||'').trim();
  if(neighborhood.length>80||category.length>80) throw new Error('Filtro longo demais');
  return {raw,relevant,scope,type,onlyFree,limit:limitRaw,offset:offsetRaw,neighborhood,category};
}

export default {
  async fetch(request:Request,env:Env):Promise<Response> {
    const url=new URL(request.url);
    const origin=request.headers.get('Origin')||'';
    const allowed = new Set((env.ALLOWED_ORIGINS||'').split(',').map(x=>x.trim()).filter(Boolean));
    const cors=allowed.has(origin)?origin:undefined;
    if(request.method==='OPTIONS') {
      return new Response(null,{status:cors?204:403,headers:{
        ...(cors?{'Access-Control-Allow-Origin':cors,'Access-Control-Allow-Methods':'GET, OPTIONS',
          'Access-Control-Allow-Headers':'Content-Type'}:{}),'Vary':'Origin'}});
    }
    if(request.method!=='GET') return json({error:'Método não permitido'},405,cors);
    if(url.pathname==='/api/health') {
      try {
        await env.DB.prepare('SELECT 1').first();
        const metadata=await env.DB.prepare("SELECT key,value FROM publication_meta WHERE key IN ('dataset_version','generated_at','row_count')").all<{key:string,value:string}>();
        const data=Object.fromEntries((metadata.results||[]).map(entry=>[entry.key,entry.value]));
        return json({status:'ok',version:'mvp-1',dataset:data,timezone:'America/Sao_Paulo'},200,cors);
      }
      catch {return json({status:'unavailable'},503,cors);}
    }
    if(url.pathname==='/api/suggestions') return json({suggestions:[
      {label:'Eventos hoje',q:'eventos hoje'}, {label:'Fim de semana',q:'eventos fim de semana'},
      {label:'Gratuito',q:'gratuito'}, {label:'Música ao vivo',q:'música ao vivo'},
      {label:'Bar',q:'bar'}, {label:'Restaurante',q:'restaurante'},
      {label:'Família',q:'criança'}]},200,cors,300);
    if(url.pathname!=='/api/search')return json({error:'Rota não encontrada'},404,cors);
    let params:ReturnType<typeof searchParameters>;
    try {params=searchParameters(url);}
    catch(e) {return json({error:e instanceof Error?e.message:'Parâmetros inválidos'},400,cors);}
    try {
      const localNow=localParts(new Date());
      const where:string[]=["status = 'published'","type IN ('place','event')",
        // Compatibilidade: esconde datas antigas textuais como "às 18h".
        "(type = 'place' OR (starts_at IS NOT NULL AND substr(starts_at,5,1) = '-' AND substr(COALESCE(ends_at,starts_at),1,19) >= ?))"];
      const bindings:(string|number)[]=[localNow];
      if(params.type){where.push('type = ?');bindings.push(params.type);}
      if(params.onlyFree){where.push("price_type = 'free'");}
      const window=dateWindow(params.scope,localNow);
      if(window){
        // Busca temporal do MVP: eventos, não horários de abertura de lugares.
        where.push("type = 'event' AND substr(starts_at,1,10) <= ? AND substr(COALESCE(ends_at,starts_at),1,10) >= ?");
        bindings.push(window[1],window[0]);
      }
      if(params.neighborhood){where.push("lower(neighborhood) LIKE ? ESCAPE '\\'");bindings.push('%'+escapeLike(params.neighborhood.toLowerCase())+'%');}
      if(params.category){where.push("lower(categories) LIKE ? ESCAPE '\\'");bindings.push('%'+escapeLike(params.category.toLowerCase())+'%');}
      for(const word of params.relevant){
        const choices=Array.from(new Set(SYNONYMS[word]??[word]));
        where.push('('+choices.map(()=>"search_text LIKE ? ESCAPE '\\'").join(' OR ')+')');
        bindings.push(...choices.map(choice=>'%'+escapeLike(choice)+'%'));
      }
      // Ranking: termos no título > tags > bairro > score de qualidade do ETL.
      let ranking='COALESCE(rank_score_base,0)';
      const rankBindings:(string|number)[]=[];
      for(const term of params.relevant.slice(0,3)){
        ranking+=" + CASE WHEN lower(title) LIKE ? ESCAPE '\\' THEN 40 ELSE 0 END";
        ranking+=" + CASE WHEN lower(tags) LIKE ? ESCAPE '\\' THEN 15 ELSE 0 END";
        ranking+=" + CASE WHEN lower(neighborhood) LIKE ? ESCAPE '\\' THEN 10 ELSE 0 END";
        rankBindings.push(...Array(3).fill('%'+escapeLike(term)+'%'));
      }
      const sql=`SELECT id,source_url,type,title,subtitle,description,neighborhood,address,starts_at,
        ends_at,price_label,price_type,categories,tags,source_label FROM search_items
        WHERE ${where.join(' AND ')} ORDER BY (${ranking}) DESC, created_at DESC, id ASC LIMIT ? OFFSET ?`;
      // Bindings na ordem SQL: SELECT sem parâmetros, WHERE primeiro, ORDER BY depois.
      const result=await env.DB.prepare(sql).bind(...bindings,...rankBindings,params.limit+1,params.offset).all<SearchItem>();
      const items=result.results||[];
      const has_more=items.length>params.limit;
      return json({query:params.raw,items:items.slice(0,params.limit),total_returned:Math.min(items.length,params.limit),
        has_more,next_offset:has_more?params.offset+params.limit:null},200,cors,60);
    } catch {
      return json({error:'Não foi possível consultar a busca agora'},503,cors);
    }
  }
};
