"""A1: ingestão JSONL offline, com lotes imutáveis e retomada por chunks.

Não acessa fontes, LLM ou D1. Só batches/ contém estados publicados da base raw;
pending/ nunca alimenta triagem. Um lock impede duas escritas concorrentes.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

VERSION = 'a1-v1'
RELEVANT = ('code', 'caption_text', 'taken_at', 'user', 'coauthor_producers',
            'location', 'media_type', 'product_type', 'resources', 'usertags')


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)
        handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


@contextmanager
def locked(store):
    store.mkdir(parents=True, exist_ok=True)
    with (store / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validate(row):
    if not isinstance(row, dict): raise ValueError('objeto esperado')
    if row.get('platform', 'instagram') != 'instagram':
        raise ValueError('plataforma não suportada nesta integração')
    if not isinstance(row.get('code'), str) or not re.fullmatch(r'[\w-]{5,30}', row['code'], re.ASCII):
        raise ValueError('code inválido')
    if not isinstance(row.get('caption_text', ''), str): raise ValueError('legenda inválida')
    value = row.get('taken_at')
    if value is not None:
        try: parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError as exc: raise ValueError('taken_at inválido') from exc
        if parsed.tzinfo is None: raise ValueError('taken_at exige fuso explícito')
    return row


def content_hash(row):
    return hashlib.sha256(json.dumps({k: row.get(k) for k in RELEVANT},
        sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def profiles(row):
    result = row.get('_source_profiles', [])
    if not isinstance(result, list) or not all(isinstance(x, str) for x in result):
        raise ValueError('_source_profiles deve ser lista de strings')
    return sorted(set(result + ([str(row['_profile_username'])] if row.get('_profile_username') else [])))


def latest(store):
    manifests = []
    for folder in (store / 'batches').glob('*'):
        manifest = load(folder / 'manifest.json')
        manifests.append((manifest['sequence'], folder, manifest))
    return max(manifests, key=lambda x: x[0]) if manifests else (0, None, None)


def check_files(folder, manifest):
    for name, digest in manifest['checksums'].items():
        if sha(folder / name) != digest: raise ValueError('Checksum divergente: ' + name)


def write_jsonl(path, rows):
    with path.open('w', encoding='utf-8') as handle:
        for row in rows: handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
        handle.flush(); os.fsync(handle.fileno())


def profile_checkpoints(stage, consulted, status):
    """Offsets desta cópia de arquivo; não são cursores de API nem prova de cobertura."""
    result = {p: dict(observations=0, last_input_line=None, latest_taken_at=None, status=status)
              for p in consulted}
    for file in sorted(stage.glob('chunk_*.json')):
        chunk = load(file)
        for offset, entry in enumerate(chunk['observations']):
            if 'row' not in entry: continue
            row = entry['row']
            for profile in profiles(row):
                item = result.setdefault(profile, dict(observations=0, last_input_line=None,
                                                       latest_taken_at=None, status=status))
                item['observations'] += 1
                item['last_input_line'] = chunk['start_line'] + offset
                taken = row.get('taken_at')
                if taken:
                    taken = datetime.fromisoformat(str(taken).replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
                    item['latest_taken_at'] = max(item['latest_taken_at'] or taken, taken)
    return result


def ingest(source: Path, store: Path, *, batch_id=None, source_name='local',
           method='jsonl-offline', authorization='local-file', consulted_profiles=(),
           window_start=None, window_end=None, max_records=None, chunk_size=100):
    acquisition = source.with_suffix(source.suffix + '.acquisition.json')
    if acquisition.exists() and load(acquisition).get('status') != 'complete':
        raise ValueError('Aquisição parcial/falha: não promover como lote completo')
    if chunk_size < 1 or (max_records is not None and max_records < 1):
        raise ValueError('Limites devem ser positivos')
    for value in (window_start, window_end):
        if value and datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('Janela temporal exige fuso')
    if window_start and window_end and datetime.fromisoformat(window_start.replace('Z','+00:00')) > datetime.fromisoformat(window_end.replace('Z','+00:00')):
        raise ValueError('Janela invertida')
    identity = dict(pipeline_version=VERSION, input_sha256=sha(source), source=source_name,
                    method=method, authorization=authorization, profiles=sorted(set(consulted_profiles)),
                    window_start=window_start, window_end=window_end)
    batch_id = batch_id or 'batch_' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', batch_id): raise ValueError('batch_id inválido')
    with locked(store):
        committed = store / 'batches' / batch_id
        if committed.exists():
            manifest = load(committed / 'manifest.json')
            if manifest['identity'] != identity: raise ValueError('batch_id reutilizado com outra entrada/configuração')
            check_files(committed, manifest)
            return manifest
        sequence, parent, previous = latest(store)
        stage = store / 'pending' / batch_id
        stage.mkdir(parents=True, exist_ok=True)
        meta_path = stage / 'meta.json'
        if not meta_path.exists():
            # Input é preservado antes do processamento; o arquivo externo nunca é alterado.
            shutil.copyfile(source, stage / 'input.jsonl')
            if sha(stage / 'input.jsonl') != identity['input_sha256']:
                raise ValueError('Entrada mudou durante cópia')
            atomic_json(meta_path, dict(identity=identity, parent=previous['batch_id'] if previous else None,
                                       started_at=now()))
            atomic_json(stage / 'manifest.json', dict(batch_id=batch_id, identity=identity,
                        started_at=load(meta_path)['started_at'], finished_at=None, status='partial',
                        checkpoint={'processed_lines':0, 'source_watermarks_advanced':False}))
        meta = load(meta_path)
        if meta['identity'] != identity or sha(stage / 'input.jsonl') != identity['input_sha256']:
            raise ValueError('Entrada/configuração mudou; retome com a cópia original ou crie outro lote')
        if meta['parent'] != (previous['batch_id'] if previous else None):
            raise ValueError('Base avançou durante pausa; crie novo batch_id para rebase auditável')
        chunks = sorted(stage.glob('chunk_*.json'))
        processed = 0
        for i, file in enumerate(chunks):
            item = load(file)
            if file.name != f'chunk_{i:08d}.json' or item['start_line'] != processed + 1:
                raise ValueError('Checkpoint não contíguo')
            processed = item['end_line']
        added = 0; buffer = []; eof = True
        def save_chunk():
            nonlocal processed, buffer
            if not buffer: return
            atomic_json(stage / f'chunk_{len(list(stage.glob("chunk_*.json"))):08d}.json',
                        dict(start_line=processed+1, end_line=processed+len(buffer), observations=buffer))
            processed += len(buffer); buffer = []
        with (stage / 'input.jsonl').open('rb') as handle:
            for line_no, raw in enumerate(handle, 1):
                if line_no <= processed: continue
                if max_records is not None and added >= max_records:
                    eof = False; break
                try:
                    if not raw.strip(): entry = {'blank': True}
                    else:
                        if not raw.endswith(b'\n'): raise ValueError('registro sem newline final; possível gravação interrompida')
                        row = validate(json.loads(raw.decode('utf-8'))); profiles(row)
                        entry = {'row': row}
                except (ValueError, UnicodeError, TypeError) as exc:
                    entry = {'invalid': type(exc).__name__, 'line': line_no}
                buffer.append(entry); added += 1
                if len(buffer) >= chunk_size: save_chunk()
        save_chunk()
        checkpoint = dict(processed_lines=processed, source_sha256=identity['input_sha256'],
                          source_watermarks_advanced=False)
        if not eof:
            checkpoint['profiles'] = profile_checkpoints(stage, identity['profiles'], 'partial')
            manifest = dict(batch_id=batch_id, identity=identity, status='partial',
                            started_at=meta['started_at'], finished_at=None, checkpoint=checkpoint)
            atomic_json(stage / 'manifest.json', manifest)
            return manifest
        logical = {}
        if parent:
            check_files(parent, previous)
            with (parent / 'catalog.jsonl').open(encoding='utf-8') as handle:
                logical = {f"instagram:{row['code']}": row for row in map(json.loads, handle)}
        metrics = dict(received=0, new=0, duplicates=0, changed=0, invalid=0, blank=0)
        delta = set(); events = []; seen_profiles = set(identity['profiles'])
        for file in sorted(stage.glob('chunk_*.json')):
            for entry in load(file)['observations']:
                if 'blank' in entry: metrics['blank'] += 1; continue
                metrics['received'] += 1
                if 'invalid' in entry: metrics['invalid'] += 1; continue
                row = entry['row']; key = 'instagram:' + row['code']; old = logical.get(key)
                digest = content_hash(row); profs = profiles(row); seen_profiles.update(profs)
                kind = 'new' if old is None else 'duplicate' if old['_content_hash'] == digest else 'changed'
                metrics[{'duplicate':'duplicates'}.get(kind, kind)] += 1
                if kind != 'duplicate': delta.add(key)
                profs = sorted(set(profs + (profiles(old) if old else [])))
                value = dict(row, platform='instagram', _source_profiles=profs, _content_hash=digest)
                if profs: value['_profile_username'] = profs[0]
                logical[key] = value
                events.append(dict(identity=key, content_hash=digest, kind=kind, profiles=profiles(row)))
        metrics['eligible_delta'] = len(delta)
        metrics['to_triage'] = 0 if metrics['invalid'] else len(delta)
        metrics['discarded'] = metrics['invalid']
        write_jsonl(stage / 'catalog.jsonl', [logical[k] for k in sorted(logical)])
        write_jsonl(stage / 'delta.jsonl', [logical[k] for k in sorted(delta)])
        write_jsonl(stage / 'observations.jsonl', events)
        manifest = dict(batch_id=batch_id, sequence=sequence+1, identity=identity,
                        started_at=meta['started_at'], finished_at=now(),
                        status='failed' if metrics['invalid'] else 'complete', metrics=metrics,
                        checkpoint={**checkpoint, 'profiles': profile_checkpoints(stage, seen_profiles, 'failed' if metrics['invalid'] else 'complete')},
                        checksums={p.name: sha(p) for p in stage.iterdir() if p.is_file() and p.suffix != '.tmp' and p.name != 'manifest.json'})
        atomic_json(stage / 'manifest.json', manifest)
        if not metrics['invalid']:
            committed.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage, committed)
            fd = os.open(committed.parent, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
        return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--store', type=Path, default=Path('etl/raw/incremental'))
    p.add_argument('--batch-id'); p.add_argument('--source', default='local')
    p.add_argument('--method', default='jsonl-offline'); p.add_argument('--authorization', default='local-file')
    p.add_argument('--profiles', nargs='*', default=[])
    p.add_argument('--window-start'); p.add_argument('--window-end')
    p.add_argument('--max-records', type=int)
    args = p.parse_args(argv)
    result = ingest(args.input, args.store, batch_id=args.batch_id, source_name=args.source,
                    method=args.method, authorization=args.authorization, consulted_profiles=args.profiles,
                    window_start=args.window_start, window_end=args.window_end, max_records=args.max_records)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['status'] == 'failed' else 0


if __name__ == '__main__': raise SystemExit(main())
