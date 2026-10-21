import assert from 'node:assert/strict';
import worker from './.compiled/index.js';
const calls=[];
const db={prepare(sql){const call={sql,params:[]};calls.push(call);return {
  bind(...params){call.params=params;return this},
  async all(){return {results:[{id:'1',type:'place',title:'Hamburgueria',source_url:'https://www.instagram.com/p/ABC123/'}]}},
  async first(){return {one:1}}
}}};
const env={DB:db,ALLOWED_ORIGINS:'http://localhost:4321'};
function req(path,origin='http://localhost:4321',method='GET'){
  return new Request('https://api.example.test'+path,{method,headers:{Origin:origin}});
}
const response=await worker.fetch(req('/api/search?q=hamburger'),env);
assert.equal(response.status,200);
assert.equal(response.headers.get('access-control-allow-origin'),'http://localhost:4321');
const payload=await response.json();assert.equal(payload.items[0].title,'Hamburgueria');
assert.ok(calls.at(-1).params.includes('%hamburgueria%'),'sinônimo ausente');
assert.equal((await worker.fetch(req('/api/search?q='+encodeURIComponent('x'.repeat(161))),env)).status,400);
assert.equal((await worker.fetch(req('/api/search'),env)).status,400);
assert.equal((await worker.fetch(req('/api/search?q=bar','https://evil.test'),env)).headers.get('access-control-allow-origin'),null);
assert.equal((await worker.fetch(req('/api/search?q=bar','https://evil.test','OPTIONS'),env)).status,403);
assert.equal((await worker.fetch(req('/api/health'),env)).status,200);
assert.equal((await worker.fetch(req('/api/unknown'),env)).status,404);
await worker.fetch(req('/api/search?q=eventos%20hoje'),env);
assert.ok(calls.at(-1).sql.includes("type = 'event'"),'filtro temporal ausente');
await worker.fetch(req('/api/search?q=bar&neighborhood=%25'),env);
assert.ok(calls.at(-1).params.some(x=>String(x).includes('\\%')),'wildcard não escapado');
console.log('Worker: 10 verificações de runtime passaram');
