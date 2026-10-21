/** Tipagem mínima da API D1 utilizada; dispensa adicionar SDK ao runtime. */
interface D1PreparedStatement {
  bind(...values:(string|number|null)[]):D1PreparedStatement;
  all<T=Record<string,unknown>>():Promise<{results:T[]}>;
  first<T=Record<string,unknown>>():Promise<T|null>;
}
interface D1Database { prepare(sql:string):D1PreparedStatement }
