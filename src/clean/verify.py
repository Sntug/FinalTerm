"""Validate A3 contract/identity integrity and reproduce every row from raw A2 sources."""
import argparse
import json
from pathlib import Path

from src.collect.common import REPO_ROOT, within, record_bytes
from src.collect.contract import contract, load_records, validate_records
from src.collect.pilot import snapshot_payload
from .pipeline import load_config, load_input, check_scope, summarize, CODE_VERSION, DEFAULT_CONFIG
from .resolution import resolve
from .text import canonical_json, sha256, identifier, evidence_id, text_record


def validate_integrity(data):
    for name, rows in data.items():
        validate_records(name, rows)
    papers = {r['paper_id']: r for r in data['papers.jsonl']}
    sources = {r['source_record_id']: r for r in data['source_records.jsonl']}
    nodes = {r['id']: r for r in data['nodes.csv']}
    evidence = {r['evidence_id']: r for r in data['evidence.jsonl']}
    decisions = {r['decision_id']: r for r in data['merge_log.jsonl']}
    texts = {r['text_version_id']: r for r in data['text_versions.jsonl']}
    if data['edges.csv']:
        raise ValueError('A3 must not create graph edges')
    for t in texts.values():
        if t['source_record_id'] not in sources or t['paper_id'] not in papers or text_record(t['paper_id'], t['source_record_id'], t['field_path'], t['normalized_text'], t['parser_version'], t['captured_at']) != t:
            raise ValueError('Invalid text binding')
    registry = {r['paper_id']: r for r in data['paper_registry.csv']}
    if set(registry) != set(papers):
        raise ValueError('Registry/Paper membership differs')
    for pid, p in papers.items():
        for key in ('title', 'doi', 'cvf_url', 'owner', 'conference', 'conference_year', 'scope', 'track'):
            if registry[pid][key] != p[key]:
                raise ValueError('Registry/Paper mismatch')
        for field in ('title', 'abstract'):
            tid = p[field + '_text_version_id']
            if p[field] is not None and (tid not in texts or texts[tid]['normalized_text'] != p[field] or texts[tid]['paper_id'] != pid):
                raise ValueError('Paper/text mismatch')
    groups = {}
    for row in data['authorships.csv']:
        pid, aid = row['paper_id'], row['authorship_id']
        if pid not in papers or aid != identifier('authorship', pid, str(row['author_order'])):
            raise ValueError('Invalid authorship identity')
        author = papers[pid]['authors'][row['author_order'] - 1]
        if (row['author_name'], row['author_name_raw'], aid) != (author['name'], author['name_raw'], author['authorship_id']):
            raise ValueError('CVF authorship order/name changed')
        if row['source_record_id'] != papers[pid]['representative_source_record_id']:
            raise ValueError('CVF authorship source changed')
        for key in ('source_record_id', 'identity_source_record_id', 'affiliation_source_record_id'):
            sid = row[key]
            if sid and (sid not in sources or sources[sid]['paper_id'] != pid):
                raise ValueError('Authorship source belongs to another Paper')
        if (row['identity_status'] == 'resolved') != bool(row['author_id']):
            raise ValueError('Author ID/status mismatch')
        if row['author_id'] and (not row['identity_source_record_id'] or row['author_id'] not in nodes or nodes[row['author_id']]['label'] != 'Author'):
            raise ValueError('Resolved Author missing source/entity')
        if (row['affiliation_status'] == 'verified') != bool(row['institution_id']):
            raise ValueError('Institution ID/status mismatch')
        if row['institution_id'] and (not row['author_id'] or not row['affiliation_source_record_id'] or row['institution_id'] not in nodes or nodes[row['institution_id']]['label'] != 'Institution'):
            raise ValueError('Verified affiliation missing source/entity')
        if any(d not in decisions for d in row['decision_ids']):
            raise ValueError('Authorship decision missing')
        groups.setdefault(aid, []).append(row)
    if set(groups) != {a['authorship_id'] for p in papers.values() for a in p['authors']}:
        raise ValueError('Authorship membership changed')
    for rows in groups.values():
        if len({(r['author_id'], r['identity_status']) for r in rows}) != 1:
            raise ValueError('Conflicting identities within one authorship')
    for p in papers.values():
        ids = [groups[a['authorship_id']][0]['author_id'] for a in p['authors']]
        ids = [a for a in ids if a]
        if len(ids) != len(set(ids)):
            raise ValueError('Same Author ID assigned twice in one Paper')
    for e in evidence.values():
        if e['evidence_id'] != evidence_id(e) or e['source_record_id'] not in sources or e['paper_id'] not in papers:
            raise ValueError('Evidence identity/source missing')
        if sources[e['source_record_id']]['url'] != e['source_url'] or sources[e['source_record_id']]['paper_id'] not in (None, e['paper_id']):
            raise ValueError('Evidence bound to wrong source')
        if e['evidence_kind'] != 'metadata' or any(e[k] is not None for k in ('text_version_id', 'normalized_text_sha256', 'normalization_version', 'start_char', 'end_char')):
            raise ValueError('A3 requires metadata evidence without NLP offsets')
    for d in decisions.values():
        if not d['evidence_ids'] or any(e not in evidence for e in d['evidence_ids']):
            raise ValueError('Decision evidence missing')
        if d['action'] in ('merge', 'split') and (d['review_mode'] != 'manual' or d['reviewed_by'] not in ('A', 'B')):
            raise ValueError('Canonical merge/split requires manual approval')
        if any(p not in papers for p in d['affected_paper_ids']) or any(a not in groups for a in d['affected_authorship_ids']):
            raise ValueError('Decision foreign key missing')
    alias_keys = set()
    for a in data['alias_map.csv']:
        key = (a['entity_type'], a['source'], a['external_id'])
        if key in alias_keys or a['alias_id'] != identifier('alias', *key) or a['decision_id'] not in decisions:
            raise ValueError('Invalid or ambiguous alias')
        alias_keys.add(key)
        if a['canonical_id'] not in (papers if a['entity_type'] == 'Paper' else nodes):
            raise ValueError('Alias canonical entity missing')
    for r in data['needs_review.csv']:
        if r['paper_id'] not in papers or any(e not in evidence for e in r['evidence_ids']):
            raise ValueError('Review foreign key missing')
    for n in nodes.values():
        if n['label'] not in ('Author', 'Institution') or set(n['properties_json']) - set(contract()['node_properties'][n['label']]):
            raise ValueError('Unexpected entity properties')
        if not n['source_record_ids'] or any(s not in sources for s in n['source_record_ids']):
            raise ValueError('Entity source missing')


def verify(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    config = load_config(root, config_path)
    source, original, bodies, input_verified = load_input(root, config['input_manifest'])
    check_scope(config, original)
    path = config['processed_dir'] + '/snapshot_manifest.json'
    manifest = json.loads(within(root, path).read_text(encoding='utf-8'))
    if manifest['source_snapshot_id'] != source['snapshot_id'] or manifest['code_version'] != CODE_VERSION:
        raise ValueError('A3 source/code version mismatch')
    if manifest['snapshot_id'] != 'snapshot:v2:' + sha256(canonical_json(snapshot_payload(manifest)).encode()):
        raise ValueError('A3 snapshot hash mismatch')
    if manifest['graph_ready'] is not False or manifest['node_count'] is not None or manifest['edge_count'] is not None:
        raise ValueError('A3 is not a complete graph snapshot')
    spec = contract()
    if len(manifest['files']) != len(spec['files']) or {Path(f['path']).name for f in manifest['files']} != set(spec['files']):
        raise ValueError('Missing/duplicate contract table')
    records = {}
    for f in manifest['files']:
        table = within(root, f['path'])
        if not table.is_relative_to(within(root, 'data/processed')) or sha256(table.read_bytes()) != f['sha256']:
            raise ValueError('A3 table hash/path mismatch')
        records[table.name] = load_records(table)
        if len(records[table.name]) != f['record_count'] or f['role'] != spec['files'][table.name]['stage']:
            raise ValueError('A3 table count/role mismatch')
    validate_integrity(records)
    rebuilt = resolve(original, bodies, source['snapshot_id'], manifest['created_at'])
    for name, rows in rebuilt.items():
        if record_bytes(name, spec['files'][name]['fields'], rows) != record_bytes(name, spec['files'][name]['fields'], records[name]):
            raise ValueError('A3 output does not reproduce from source: ' + name)
    if manifest['applied_decision_ids'] != [r['decision_id'] for r in records['merge_log.jsonl']]:
        raise ValueError('Applied decision list mismatch')
    summary = json.loads(within(root, config['processed_dir'] + '/cleaning_summary.json').read_text(encoding='utf-8'))
    expected = {**summarize(original, records, config['target_count']), 'snapshot_id': manifest['snapshot_id'],
                'source_snapshot_id': source['snapshot_id'], 'manifest': path, 'input_verification': input_verified}
    if summary != expected:
        raise ValueError('Cleaning summary differs from actual records')
    return dict(passed=True, snapshot_id=manifest['snapshot_id'], tables_checked=len(records),
                records_checked=sum(map(len, records.values())), raw_sources_checked=len(bodies),
                deterministic_replay=True, graph_ready=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPO_ROOT)
    parser.add_argument('--config', default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        result = verify(args.root, args.config)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f'ERROR: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
