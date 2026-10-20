# etl/gerar_seed.py
import json
import uuid
import os

INPUT_FILE = "etl/items_publicaveis.jsonl" # Ajuste o caminho se necessário
OUTPUT_FILE = "db/seed.sql"

def escape_sql(value):
    """Escapa aspas simples para evitar quebra no SQL e trata nulos."""
    if value is None or value == "":
        return "NULL"
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    
    clean_str = str(value).replace("'", "''")
    return f"'{clean_str}'"

def generate_sql():
    if not os.path.exists(INPUT_FILE):
        print(f"Erro: Arquivo {INPUT_FILE} não encontrado. Gere-o primeiro.")
        return

    inserts = []
    
    # Limpa a tabela antes de inserir (opcional, bom para o MVP durante testes)
    inserts.append("DELETE FROM search_items;\n")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
                
            item = json.loads(line)
            
            # Regra de Negócio: Só sobe o que está publicado
            if item.get("publish_status") != "published":
                continue

            # Mapeamento seguro para o Schema do Banco
            # Fallbacks adicionados para evitar erros caso a chave não exista no JSON bruto
            id_val = escape_sql(str(uuid.uuid4()))
            source_id = escape_sql(item.get("post_code", "unknown"))
            source_url = escape_sql(item.get("post_url", ""))
            type_val = escape_sql(item.get("content_type", "place"))
            status = escape_sql(item.get("publish_status", "published"))
            title = escape_sql(item.get("display_title", "Sem Título"))
            subtitle = escape_sql(item.get("display_subtitle", ""))
            description = escape_sql(item.get("caption_text_clean", ""))
            
            location = item.get("location", {})
            city = escape_sql(location.get("city", "Belo Horizonte"))
            neighborhood = escape_sql(location.get("neighborhood", ""))
            address = escape_sql(location.get("address", ""))
            
            starts_at = escape_sql(item.get("starts_at", ""))
            ends_at = escape_sql(item.get("ends_at", ""))
            
            price_type = escape_sql(item.get("price_type", "unknown"))
            
            classification = item.get("classification", {})
            categories = escape_sql(classification.get("category", ""))
            tags = escape_sql(classification.get("tags", []))
            
            search_text = escape_sql(item.get("search_text", ""))
            source_label = escape_sql(item.get("source_profile", "Instagram"))

            sql = f"""INSERT INTO search_items (
                id, source_id, source_url, type, status, title, subtitle, description, 
                city, neighborhood, address, starts_at, ends_at, price_type, 
                categories, tags, search_text, source_label
            ) VALUES (
                {id_val}, {source_id}, {source_url}, {type_val}, {status}, {title}, {subtitle}, {description},
                {city}, {neighborhood}, {address}, {starts_at}, {ends_at}, {price_type},
                {categories}, {tags}, {search_text}, {source_label}
            );"""
            
            inserts.append(sql)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("\n".join(inserts))
        
    print(f"Sucesso! {len(inserts) - 1} itens 'published' convertidos para {OUTPUT_FILE}.")

if __name__ == "__main__":
    generate_sql()