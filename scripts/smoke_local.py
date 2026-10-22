"""Smoke test HTTP após `docker compose up -d api web`. Apenas leitura."""
import json
import sys
import urllib.error
import urllib.request


def check(url, expected=200):
    try:
        with urllib.request.urlopen(url, timeout=12) as r:
            data = r.read().decode('utf-8')
            if r.status != expected:
                raise AssertionError(f'{url}: HTTP {r.status}, esperado {expected}')
            return data
    except urllib.error.HTTPError as exc:
        raise AssertionError(f'{url}: HTTP {exc.code}') from exc


def main():
    html = check('http://localhost:4321/')
    assert 'Oncovô' in html or 'oncovô' in html, 'Frontend sem identificação'
    assert '/logo.png' in html, 'Logo não encontrada no HTML'
    health = json.loads(check('http://localhost:8787/api/health'))
    assert health.get('status') == 'ok', f'D1 ainda não inicializado: {health}'
    data = json.loads(check('http://localhost:8787/api/search?q=bar'))
    assert isinstance(data.get('items'), list), 'Resultado da API inválido'
    print(f"OK: frontend, logo, D1, Worker, busca. {len(data['items'])} resultado(s) para 'bar'.")
    if not data['items']:
        print('ATENÇÃO: API funcional, mas o termo bar não encontrou itens; revise seed e catálogo.')


if __name__ == '__main__':
    try: main()
    except (AssertionError, urllib.error.URLError, ValueError) as e:
        print(f'FALHA: {e}', file=sys.stderr)
        sys.exit(1)
