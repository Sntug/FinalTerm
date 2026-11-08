"""Verify any repository-relative v2 metadata manifest, without network access."""
import argparse
import gzip
import json
from pathlib import Path
from src.clean.text import canonical_json, sha256, text_record, identifier, evidence_id, validate_nlp_evidence
from .common import REPO_ROOT, within, paper_id_from_url
from .contract import contract, load_records
from .cvf import parse_detail, parse_listing
from .openalex import assessment


def verify(root, manifest_path):
    from .pilot import snapshot_payload
    root = root.resolve()
    manifest = json.loads(within(root, str(manifest_path)).read_text(encoding='utf-8'))
    spec = contract()
    if set(spec['snapshot_manifest']['required']) - set(manifest):
        raise ValueError('Manifest required keys missing')
    if manifest['schema_version']!='2.0.0' or manifest['project_id']!=spec['project_id']:
        raise ValueError('Wrong contract/project')
    if manifest['snapshot_id'] != 'snapshot:v2:' + sha256(canonical_json(snapshot_payload(manifest)).encode()):
        raise ValueError('Snapshot fingerprint mismatch')
    if manifest['graph_ready'] is not False or manifest['node_count'] is not None or manifest['edge_count'] is not None:
        raise ValueError('Expected metadata-only snapshot')
    files=manifest['files']
    if len(files)!=len(spec['files']) or {Path(f['path']).name for f in files}!=set(spec['files']):
        raise ValueError('Missing/duplicate contract table')
    data={}
    for entry in files:
        path=within(root,entry['path'])
        if not path.is_relative_to(within(root,'data/processed')) or sha256(path.read_bytes())!=entry['sha256']:
            raise ValueError('Table path/hash mismatch')
        rows=load_records(path)
        if len(rows)!=entry['record_count'] or entry['role']!=spec['files'][path.name]['stage']:
            raise ValueError('Count/role mismatch')
        data[path.name]=rows
    sources={s['source_record_id']:s for s in data['source_records.jsonl']}
    papers={p['paper_id']:p for p in data['papers.jsonl']}
    registry={p['paper_id']:p for p in data['paper_registry.csv']}
    texts={t['text_version_id']:t for t in data['text_versions.jsonl']}
    if set(registry)!=set(papers): raise ValueError('Registry foreign keys differ')
    bodies={}
    for sid,s in sources.items():
        path=within(root,s['raw_path'])
        if not path.is_relative_to(within(root,'data/raw')): raise ValueError('Raw outside data/raw')
        body=gzip.decompress(path.read_bytes()); bodies[sid]=body
        if sha256(body)!=s['content_sha256'] or s['http_status']!=200: raise ValueError('Source hash/status mismatch')
        prefix={'CVF':'source:cvf','OpenAlex':'source:openalex'}.get(s['source'])
        if prefix is None or identifier(prefix,s['url'],s['content_sha256'])!=sid: raise ValueError('Source ID mismatch')
        if s['paper_id'] is not None and s['paper_id'] not in papers: raise ValueError('Source Paper missing')
    for t in texts.values():
        if t['paper_id'] not in papers or t['source_record_id'] not in sources: raise ValueError('Text foreign key missing')
        if text_record(t['paper_id'],t['source_record_id'],t['field_path'],t['normalized_text'],t['parser_version'],t['captured_at'])!=t:
            raise ValueError('Text hash/binding mismatch')
    provenance={(r['paper_id'],r['field_name']):r for r in data['field_provenance.csv']}
    for row in provenance.values():
        if row['paper_id'] not in papers or row['source_record_id'] not in sources or any(s not in sources for s in row['candidate_source_record_ids']):
            raise ValueError('Field provenance foreign key missing')
    listings = {}
    for p in papers.values():
        edition = (p['conference'], p['conference_year'])
        if edition not in listings:
            url = f'https://openaccess.thecvf.com/{edition[0]}{edition[1]}?day=all'
            listings[edition] = set().union(*(set(parse_listing(bodies[s], *edition)) for s in sources if sources[s]['source_kind']=='listing' and sources[s]['url']==url))
    for pid,p in papers.items():
        sid=p['representative_source_record_id']
        if sid not in sources or sources[sid]['paper_id']!=pid or pid!=paper_id_from_url(p['cvf_url']): raise ValueError('Paper/source identity mismatch')
        raw=parse_detail(bodies[sid],p['cvf_url'],p['conference'],p['conference_year'])
        if raw['title']!=p['title'] or [{k:a[k] for k in ('name','name_raw','author_order')} for a in p['authors']]!=raw['authors']:
            raise ValueError('CVF title/byline changed')
        if p['cvf_url'] not in listings[(p['conference'],p['conference_year'])]:
            raise ValueError('Main conference membership missing')
        for key in ('owner','doi','conference','conference_year','title','cvf_url','venue_id','scope','track'):
            if registry[pid][key]!=p[key]: raise ValueError('Registry field mismatch')
        for field in ('title','abstract'):
            tid=p[field+'_text_version_id']
            if p[field] is None and tid is None: continue
            if tid not in texts or texts[tid]['paper_id']!=pid or texts[tid]['normalized_text']!=p[field]: raise ValueError('Paper text binding missing')
            t = texts[tid]
            if t['captured_at'] != sources[t['source_record_id']]['fetched_at']:
                raise ValueError('Text capture time differs from raw source')
            if provenance[(pid,field)]['source_record_id'] != t['source_record_id']:
                raise ValueError('Text/provenance source differs')
            if sources[t['source_record_id']]['source'] == 'CVF':
                if t['source_record_id'] != sid or raw[field] != p[field]:
                    raise ValueError('Text differs from CVF raw field')
            else:
                from src.clean.text import normalize
                index = json.loads(bodies[t['source_record_id']])['abstract_inverted_index']
                positions = [(pos,word) for word,offsets in index.items() for pos in offsets]
                if field != 'abstract' or sorted(pos for pos,_ in positions) != list(range(len(positions))) or normalize(' '.join(word for _,word in sorted(positions))) != p[field]:
                    raise ValueError('Abstract differs from OpenAlex raw field')
        if p['openalex_status']=='matched':
            prov=provenance[(pid,'openalex_id')]; osid=prov['source_record_id']
            work=json.loads(bodies[osid])
            original={**p,'doi':raw['doi']}
            if work['id']!=p['openalex_id'] or not assessment(original,work)['accepted']: raise ValueError('Work match cannot be reproduced')
            if p['citation_count'] is not None and (p['citation_count']!=work.get('cited_by_count') or p['citation_count_source_record_id']!=osid or p['citation_count_observed_at']!=sources[osid]['fetched_at']):
                raise ValueError('Citation count provenance mismatch')
            if p['references_status']=='verified' and p['referenced_works']!=work.get('referenced_works'): raise ValueError('References mismatch')
        elif any(p[k] is not None for k in ('openalex_id','citation_count','referenced_works')):
            raise ValueError('Unmatched Work must not enrich metadata')
    authors={}
    for row in data['authorships.csv']:
        pid=row['paper_id']; aid=row['authorship_id']
        if pid not in papers or row['source_record_id'] not in sources: raise ValueError('Authorship foreign key missing')
        if row['author_id'] is not None or row['institution_id'] is not None or row['identity_status']!='unresolved' or row['affiliation_status']!='not_collected':
            raise ValueError('Collector does not resolve Author/affiliation identities')
        authors[aid]=row
    expected_authors={a['authorship_id'] for p in papers.values() for a in p['authors']}
    if set(authors)!=expected_authors: raise ValueError('Paper/authorship keys differ')
    for p in papers.values():
        for a in p['authors']:
            row=authors[a['authorship_id']]
            if a['authorship_id']!=identifier('authorship',p['paper_id'],str(a['author_order'])) or (row['paper_id'],row['author_name'],row['author_order'])!=(p['paper_id'],a['name'],a['author_order']): raise ValueError('Authorship binding mismatch')
    evidence={e['evidence_id']:e for e in data['evidence.jsonl']}
    for e in evidence.values():
        if e['paper_id'] not in papers or e['source_record_id'] not in sources or e['source_url']!=sources[e['source_record_id']]['url'] or evidence_id(e)!=e['evidence_id']: raise ValueError('Evidence source/ID mismatch')
        if e['evidence_kind']=='nlp': validate_nlp_evidence(e,texts[e['text_version_id']])
        elif e['evidence_kind']=='metadata' and any(e[k] is not None for k in ('text_version_id','normalized_text_sha256','normalization_version','start_char','end_char')):
            raise ValueError('Metadata evidence must not claim NLP coordinates')
    for r in data['needs_review.csv']:
        if r['paper_id'] not in papers or any(e not in evidence for e in r['evidence_ids']): raise ValueError('Review foreign key missing')
    if any(data[n] for n in ('nodes.csv','edges.csv','alias_map.csv','merge_log.jsonl')): raise ValueError('Metadata collector must not create graph or merge decisions')
    return {'passed':True,'snapshot_id':manifest['snapshot_id'],'papers':len(papers),'authorship_observations':len(authors),
        'raw_sources_checked':len(sources),'text_versions_checked':len(texts),'tables_checked':len(data),
        'records_checked':sum(len(v) for v in data.values()),'graph_ready':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=REPO_ROOT)
    parser.add_argument('--manifest',required=True,help='Manifest path relative to repo root')
    args=parser.parse_args()
    try: result=verify(args.root,args.manifest)
    except (ValueError,KeyError,OSError) as exc: parser.exit(1,f'ERROR: {exc}\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
