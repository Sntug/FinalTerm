"""Shared configured collection with cached resume and immutable exports."""
from __future__ import annotations
import json
from pathlib import Path
from src.clean.text import NORMALIZATION_VERSION, canonical_json, sha256
from .cache import HTTPCache, OpenAlexCache, SourceFailure, source_record
from .common import (CODE_VERSION, DEFAULT_CONFIG, PARSER_VERSION, atomic_json, json_bytes,
                     load_config, load_selection, now_utc, publish, record_bytes, within)
from .contract import contract, validate_records
from .cvf import CVFHTML, parse_detail, parse_listing
from .export import export_records
from .openalex import RULE_VERSION, collect_work, enrich


def build_records(root, config, offline=True, progress=None):
    selection = load_selection(root, config)
    cache = HTTPCache(root, config['raw_dir'], offline=offline, delay=config['delay_seconds'],
                      retries=config['retries'], timeout=config['timeout_seconds'], max_retry_wait=config['max_retry_wait_seconds'])
    def fetch(url, validated):
        try:
            return cache.get(url)
        except (RuntimeError, OSError) as exc:
            exc.validated_papers = validated
            raise
    body, meta = fetch(config['listing_url'], 0)
    listing = source_record(meta, None, 'listing')
    if selection.get('listing_source_record_id', listing['source_record_id']) != listing['source_record_id']:
        raise ValueError('Locked listing source changed')
    candidates = parse_listing(body, config['conference'], config['conference_year'])
    sources, observations = [listing], []
    for item in selection['papers']:
        if item['cvf_url'] not in candidates:
            raise ValueError('Paper absent from main conference listing')
        body, meta = fetch(item['cvf_url'], len(observations))
        source = source_record(meta, item['paper_id'], 'paper_detail')
        if item.get('source_record_id') and source['source_record_id'] != item['source_record_id']:
            raise ValueError('Locked detail source changed')
        parsed = parse_detail(body, item['cvf_url'], config['conference'], config['conference_year'])
        if item.get('doi') and item['doi'] != parsed['doi']:
            raise ValueError('Registry DOI not confirmed by CVF source')
        parsed['doi_field_path'] = ('html:meta[name=citation_doi]@content' if 'citation_doi' in CVFHTML(body.decode('utf-8-sig')).meta else 'html:div.bibref.text')
        observations.append({**parsed, 'paper_id': item['paper_id'], 'owner': config['owner'],
            'conference': config['conference'], 'conference_year': config['conference_year'],
            'track': 'main', 'scope': 'core', 'venue_id': f'venue:{config["conference"]}:{config["conference_year"]}:main',
            'source_record_id': source['source_record_id'], 'captured_at': meta['fetched_at']})
        sources.append(source)
        if progress:
            try:
                progress([p['paper_id'] for p in observations], cache.network_requests)
            except OSError as exc:
                exc.validated_papers = len(observations)
                raise
    selection['candidate_count'] = len(candidates)
    return export_records(observations, sources, listing), selection, cache.network_requests


def snapshot_payload(manifest):
    return {key: manifest[key] for key in ('project_id','schema_version','code_version','normalization_version',
        'parser_versions','rule_versions','dictionary_versions','applied_decision_ids','graph_ready','node_count','edge_count','files')}


def run(root: Path, config_path=DEFAULT_CONFIG, offline=True):
    root = root.resolve()
    config = load_config(root, config_path)
    checkpoint = within(root, config.get('checkpoint_file', config['raw_dir'] + '/collector_checkpoint.json'))
    fingerprint = sha256(canonical_json(config).encode() + within(root, config['registry_input']).read_bytes())
    batch_size = config.get('batch_size', 25)
    def cvf_progress(completed, requests):
        atomic_json(checkpoint, {'config_sha256':fingerprint, 'phase':'CVF',
            'validated_papers':len(completed), 'completed_paper_ids':completed,
            'network_requests':requests, 'errors':[]})
        if len(completed) % batch_size == 0 or len(completed) == config['target_count']:
            print(f'CVF valid {len(completed)}/{config["target_count"]}; requests {requests}', flush=True)
    try:
        records, selection, cvf_requests = build_records(root, config, offline, cvf_progress)
    except (RuntimeError, OSError) as exc:
        errors = [{'source':'CVF','reason':str(exc),'retry_at':getattr(exc,'retry_at',None)}]
        validated = getattr(exc,'validated_papers',0)
        atomic_json(checkpoint, {'config_sha256':fingerprint,'phase':'CVF','validated_papers':validated,'errors':errors})
        result = {'collection_complete':False,'papers':validated,'target_papers':config['target_count'],
                  'source_errors':errors,'graph_ready':False,'manifest':None}
        atomic_json(within(root,config['output_dir']+'/summary.json'),result)
        return result
    cache = OpenAlexCache(root, config, offline)
    audits, errors, completed, available_affiliation = [], [], [], 0
    if config.get('openalex_enabled', True):
        for paper in records['papers.jsonl']:
            try:
                work, sources, audit = collect_work(cache, paper)
            except SourceFailure as exc:
                errors.append({'paper_id': paper['paper_id'], 'source': 'OpenAlex', 'reason': str(exc), 'retry_at': exc.retry_at})
                atomic_json(checkpoint, {'config_sha256': fingerprint, 'completed_paper_ids': completed,
                    'pending_paper_ids': [p['paper_id'] for p in records['papers.jsonl'] if p['paper_id'] not in completed], 'errors': errors})
                break
            records['source_records.jsonl'].extend(sources)
            enrich(records, paper, work, sources, audit)
            if work and any(a.get('institutions') for a in work.get('authorships', [])):
                available_affiliation += 1
            audits.append(audit)
            completed.append(paper['paper_id'])
            atomic_json(checkpoint, {'config_sha256': fingerprint, 'completed_paper_ids': completed,
                'pending_paper_ids': [p['paper_id'] for p in records['papers.jsonl'] if p['paper_id'] not in completed], 'errors': []})
            if len(completed) % batch_size == 0 or len(completed) == len(records['papers.jsonl']):
                print(f'OpenAlex completed {len(completed)}/{len(records["papers.jsonl"])}; requests {cache.network_requests}', flush=True)
    by_id = {p['paper_id']:p for p in records['papers.jsonl']}
    for row in records['paper_registry.csv']:
        row['doi'] = by_id[row['paper_id']]['doi']
    # Same query can support more than one paper. Store it once; field bindings
    # identify the consuming paper, rather than duplicating a source primary key.
    source_map = {}
    for source in records['source_records.jsonl']:
        sid = source['source_record_id']
        if sid in source_map and source_map[sid]['paper_id'] != source['paper_id']:
            source_map[sid]['paper_id'] = None
        else:
            source_map.setdefault(sid, source)
    records['source_records.jsonl'] = list(source_map.values())
    spec = contract()
    contents = {}
    for name, rows in records.items():
        validate_records(name, rows)
        contents[name] = record_bytes(name, spec['files'][name]['fields'], rows)
    digest = sha256(canonical_json({'code_version':CODE_VERSION,'files':{n:sha256(b) for n,b in contents.items()}}).encode())
    directory = config['processed_dir'] + '/snapshots/' + digest
    files = [{'path': directory+'/'+n, 'sha256':sha256(b), 'record_count':len(records[n]), 'role':spec['files'][n]['stage']} for n,b in contents.items()]
    manifest = {'project_id':spec['project_id'], 'schema_version':'2.0.0', 'code_version':CODE_VERSION,
        'normalization_version':NORMALIZATION_VERSION, 'parser_versions':[PARSER_VERSION, 'openalex-json-1.0.0'],
        'rule_versions':{'openalex-work-match':RULE_VERSION}, 'dictionary_versions':{}, 'applied_decision_ids':[],
        'graph_ready':False, 'node_count':None, 'edge_count':None, 'files':files}
    manifest['snapshot_id'] = 'snapshot:v2:' + sha256(canonical_json(snapshot_payload(manifest)).encode())
    manifest['source_snapshot_id'] = selection['source_snapshot_id']
    archive_manifest = within(root, directory+'/snapshot_manifest.json')
    manifest['created_at'] = json.loads(archive_manifest.read_text())['created_at'] if archive_manifest.exists() else now_utc()
    output_files = {within(root, directory+'/'+n):b for n,b in contents.items()}
    output_files[archive_manifest] = json_bytes(manifest)
    publish(output_files)
    from .verify import verify
    verified = verify(root, archive_manifest.relative_to(root).as_posix())
    atomic_json(within(root, config['processed_dir']+'/snapshot_manifest.json'), manifest)
    atomic_json(within(root, config['processed_dir']+'/selection_manifest.json'), {
        'owner':config['owner'], 'conference':config['conference'], 'conference_year':config['conference_year'],
        'seed':config['seed'], 'target_count':config['target_count'], 'selected_count':len(by_id),
        'selected_paper_ids':list(by_id), 'listing_source_record_id':records['source_records.jsonl'][0]['source_record_id']})
    total = len(by_id)
    def coverage(n, denominator=total):
        return {'numerator':n, 'denominator':denominator, 'percent':round(100*n/denominator, 2) if denominator else None}
    summary = {**verified, 'collection_complete':not errors, 'target_papers':config['target_count'],
        'openalex_status_counts':{status:sum(p['openalex_status']==status for p in by_id.values()) for status in ('matched','not_found','needs_review','not_collected')},
        'coverage':{'abstract':coverage(sum(p['abstract'] is not None for p in by_id.values())),
                    'affiliation_verified_papers':coverage(0), 'affiliation_verified_authorships':coverage(0,len(records['authorships.csv'])),
                    'affiliation_available_in_matched_openalex_work':coverage(available_affiliation),
                    'references_checked':coverage(sum(p['references_status']=='verified' for p in by_id.values())),
                    'references_nonempty':coverage(sum(bool(p['referenced_works']) for p in by_id.values()))},
        'source_errors':errors, 'unresolved_authorships':len(records['authorships.csv']),
        'network_requests':{'CVF':cvf_requests, 'OpenAlex':cache.network_requests}, 'offline':offline,
        'manifest':config['processed_dir']+'/snapshot_manifest.json'}
    atomic_json(within(root, config['output_dir']+'/summary.json'), summary)
    atomic_json(within(root, config['output_dir']+'/matching.json'), audits)
    print(f'CVF valid {total}/{config["target_count"]}; OpenAlex completed {len(completed)}/{total}', flush=True)
    return summary
