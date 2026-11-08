"""Offline A3 pipeline over an immutable, verified A2 v2 snapshot."""
from collections import Counter
import gzip
import json
from pathlib import Path

from src.collect.common import REPO_ROOT, within, now_utc, json_bytes, record_bytes, publish
from src.collect.contract import contract, load_records
from src.collect.pilot import snapshot_payload
from src.collect.verify import verify as verify_a2
from .resolution import resolve, RULE, VERSION
from .text import canonical_json, sha256

CODE_VERSION = 'a3-clean-1.0.0'
DEFAULT_CONFIG = 'config/a_cvpr2024_a3.json'


def load_input(root, path):
    verified = verify_a2(root, path)
    manifest = json.loads(within(root, path).read_text(encoding='utf-8'))
    records = {Path(f['path']).name: load_records(within(root, f['path'])) for f in manifest['files']}
    bodies = {s['source_record_id']: gzip.decompress(within(root, s['raw_path']).read_bytes())
              for s in records['source_records.jsonl']}
    return manifest, records, bodies, verified


def load_config(root, path):
    config = json.loads(within(root, path).read_text(encoding='utf-8'))
    required = {'input_manifest', 'processed_dir', 'owner', 'conference', 'conference_year', 'target_count'}
    if set(config) != required:
        raise ValueError('A3 config keys must be exactly: ' + ', '.join(sorted(required)))
    if (config['conference'], config['conference_year']) not in {('CVPR', 2024), ('ICCV', 2023)}:
        raise ValueError('Unsupported conference edition')
    if type(config['target_count']) is not int or config['target_count'] < 1 or not config['owner']:
        raise ValueError('Expected positive target_count and owner')
    source = within(root, config['input_manifest'])
    output = within(root, config['processed_dir'])
    corpus = config['conference'].lower() + str(config['conference_year'])
    if not output.is_relative_to(within(root, 'data/processed/' + corpus)) or output == source.parent or source.is_relative_to(output):
        raise ValueError('A3 output must be a separate directory in the configured processed corpus')
    return config


def check_scope(config, records):
    for paper in records['papers.jsonl']:
        if any(paper[k] != config[k] for k in ('owner', 'conference', 'conference_year')):
            raise ValueError('Input owner/edition differs from A3 config: ' + paper['paper_id'])
        if paper['scope'] != 'core' or paper['track'] != 'main':
            raise ValueError('Input contains non-core/non-main Paper: ' + paper['paper_id'])


def summarize(original, records, target):
    groups = {}
    for row in records['authorships.csv']:
        groups.setdefault(row['authorship_id'], []).append(row)
    verified = [r for r in records['paper_registry.csv'] if r['status'] == 'cvf_verified']
    institutions = {r['institution_id'] for r in records['authorships.csv'] if r['institution_id']}
    authors = {r['author_id'] for r in records['authorships.csv'] if r['author_id']}
    resolved = sum(rows[0]['identity_status'] == 'resolved' for rows in groups.values())
    affiliations = sum(any(r['affiliation_status'] == 'verified' for r in rows) for rows in groups.values())
    collisions = {r['paper_id'] for r in records['needs_review.csv'] if (r['field_name'] or '').startswith('identifier_collision')}
    return dict(target_papers=target, input_papers=len(original['papers.jsonl']), output_papers=len(records['papers.jsonl']),
        valid_core_papers=len(verified), dropped_papers=0, duplicate_papers_removed=0,
        papers_with_identifier_conflicts=len(collisions),
        input_output_delta=len(records['papers.jsonl']) - len(original['papers.jsonl']),
        output_target_delta=len(records['papers.jsonl']) - target,
        resolved_authors=len(authors), resolved_institutions=len(institutions),
        distinct_authorships=len(groups), authorship_rows=len(records['authorships.csv']),
        resolved_authorships=resolved, authorships_without_author_id=len(groups) - resolved,
        authorships_with_verified_affiliation=affiliations, authorships_without_verified_affiliation=len(groups) - affiliations,
        authorship_rows_without_institution_id=sum(r['institution_id'] is None for r in records['authorships.csv']),
        authorships_with_multiple_institutions=sum(len({r['institution_id'] for r in rows if r['institution_id']}) > 1 for rows in groups.values()),
        papers_with_verified_affiliation=len({r['paper_id'] for r in records['authorships.csv'] if r['institution_id']}),
        alias_count=len(records['alias_map.csv']), decision_counts=dict(Counter(r['action'] for r in records['merge_log.jsonl'])),
        review_count=len(records['needs_review.csv']), review_by_entity=dict(Counter(r['entity_type'] for r in records['needs_review.csv'])),
        review_by_issue=dict(Counter(r['field_name'] for r in records['needs_review.csv'])),
        network_requests=0, graph_ready=False,
        delivery_complete=len(verified) == target and len(records['papers.jsonl']) == target,
        manual_identity_review_complete=not any(r['review_status'] == 'open' for r in records['needs_review.csv']))


def run(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    config = load_config(root, config_path)
    source, original, bodies, verified = load_input(root, config['input_manifest'])
    check_scope(config, original)
    directory = config['processed_dir']
    manifest_path = within(root, directory + '/snapshot_manifest.json')
    decisions_path = within(root, directory + '/merge_log.jsonl')
    if manifest_path.exists():
        created = json.loads(manifest_path.read_text(encoding='utf-8'))['created_at']
    elif decisions_path.exists():
        # Recover the run timestamp after interruption before manifest publication.
        decisions = load_records(decisions_path)
        if not decisions or any(d['snapshot_before'] != source['snapshot_id'] for d in decisions):
            raise ValueError('Partial A3 decisions do not belong to this input snapshot')
        times = {d['decided_at'] for d in decisions}
        if len(times) != 1:
            raise ValueError('Partial A3 decisions have inconsistent run timestamps')
        created = times.pop()
    else:
        created = now_utc()
    records = resolve(original, bodies, source['snapshot_id'], created)
    from .verify import validate_integrity
    validate_integrity(records)
    spec = contract()
    output, entries = {}, []
    source_entries = {Path(f['path']).name: f for f in source['files']}
    for name, rows in records.items():
        content = record_bytes(name, spec['files'][name]['fields'], rows)
        if sha256(content) == source_entries[name]['sha256']:
            # Reuse immutable A2 tables, especially source/raw/text, rather than making copies.
            entries.append(source_entries[name])
        else:
            path = directory + '/' + name
            output[within(root, path)] = content
            entries.append(dict(path=path, sha256=sha256(content), record_count=len(rows), role=spec['files'][name]['stage']))
    manifest = dict(project_id=spec['project_id'], schema_version=spec['schema_version'], code_version=CODE_VERSION,
        normalization_version=source['normalization_version'],
        parser_versions=sorted(set(source['parser_versions'] + ['a3-metadata-1.0.0'])),
        rule_versions={**source['rule_versions'], RULE: VERSION}, dictionary_versions={},
        applied_decision_ids=[r['decision_id'] for r in records['merge_log.jsonl']],
        graph_ready=False, node_count=None, edge_count=None, files=entries,
        created_at=created, source_snapshot_id=source['snapshot_id'])
    manifest['snapshot_id'] = 'snapshot:v2:' + sha256(canonical_json(snapshot_payload(manifest)).encode())
    summary = {**summarize(original, records, config['target_count']), 'snapshot_id': manifest['snapshot_id'],
               'source_snapshot_id': source['snapshot_id'], 'manifest': directory + '/snapshot_manifest.json',
               'input_verification': verified}
    output[within(root, directory + '/cleaning_summary.json')] = json_bytes(summary)
    output[manifest_path] = json_bytes(manifest)
    publish(output)
    return summary
