"""Lock a deterministic extension of a pilot before fetching paper details."""
import argparse
import csv
import io
import json
from pathlib import Path

from src.clean.text import canonical_json, sha256
from .cache import HTTPCache, source_record
from .common import REPO_ROOT, json_bytes, load_config, load_selection, now_utc, paper_id_from_url, publish, within
from .cvf import parse_listing, rank_urls


def prepare(root, config_path):
    root = Path(root).resolve()
    config = load_config(root, config_path)
    lock_path = within(root, config['selection_file'])
    if lock_path.exists():
        return load_selection(root, config)
    pilot_path = within(root, config['preserve_selection_file'])
    pilot = json.loads(pilot_path.read_text(encoding='utf-8'))
    if pilot['seed'] != config['seed']:
        raise ValueError('Preserved pilot seed differs')
    # Preparing a lock never fetches metadata, including on an accidental rerun.
    body, meta = HTTPCache(root, config['raw_dir'], offline=True).get(config['listing_url'])
    listing = source_record(meta, None, 'listing')
    if pilot['listing_source_record_id'] != listing['source_record_id']:
        raise ValueError('Preserved pilot listing differs')
    ranked = rank_urls(parse_listing(body, config['conference'], config['conference_year']), config['seed'])
    preserved = pilot['papers']
    urls = [p['cvf_url'] for p in preserved]
    if len(set(urls)) != len(urls) or any(u not in ranked for u in urls):
        raise ValueError('Pilot duplicate or absent from main listing')
    if any(paper_id_from_url(p['cvf_url']) != p['paper_id'] for p in preserved):
        raise ValueError('Pilot ID differs from URL')
    target = config['target_count']
    if not len(preserved) <= target <= len(ranked):
        raise ValueError('Target cannot preserve pilot or exceeds main listing')
    remaining = [u for u in ranked if u not in set(urls)]
    selected = urls + remaining[:target-len(urls)]
    old = {p['cvf_url']:p for p in preserved}
    papers = [{'paper_id':paper_id_from_url(url), 'cvf_url':url,
               'selection_rank':i, 'ranking_position':ranked.index(url)+1,
               'source_record_id':old.get(url, {}).get('source_record_id', '')}
              for i,url in enumerate(selected,1)]
    stream = io.StringIO(newline='')
    fields = ['paper_id','cvf_url','owner','conference','conference_year','doi','source_record_id']
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for p in papers:
        writer.writerow({**{k:p[k] for k in ('paper_id','cvf_url','source_record_id')},
                         **{k:config[k] for k in ('owner','conference','conference_year')}, 'doi':''})
    registry = stream.getvalue().encode('utf-8-sig')
    lock = {'owner':config['owner'], 'conference':config['conference'], 'conference_year':config['conference_year'],
            'seed':config['seed'], 'target_count':target, 'locked_at':now_utc(),
            'selection_algorithm':'preserve pilot order; remaining sha256(seed + newline + canonical_url), ascending, then URL',
            'candidate_count':len(ranked), 'candidate_ranking_sha256':sha256(canonical_json(ranked).encode()),
            'listing_source_record_id':listing['source_record_id'], 'listing_content_sha256':meta['content_sha256'],
            'listing_raw_path':meta['raw_path'], 'preserved_selection_path':config['preserve_selection_file'],
            'preserved_selection_sha256':sha256(pilot_path.read_bytes()), 'preserved_paper_ids':[p['paper_id'] for p in preserved],
            'registry_input':config['registry_input'], 'registry_sha256':sha256(registry),
            'source_snapshot_id':'selection:'+sha256(canonical_json(papers).encode()),
            'excluded_candidates':[], 'papers':papers}
    publish({within(root,config['registry_input']):registry,
             lock_path:json_bytes(lock), within(root,config['selection_lock_copy']):json_bytes(lock)})
    return load_selection(root, config)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=REPO_ROOT)
    parser.add_argument('--config',required=True)
    args=parser.parse_args()
    result=prepare(args.root,args.config)
    print(json.dumps({'selected':len(result['papers']), 'preserved':len(result['preserved_paper_ids']),
                      'seed':result['seed'], 'source_snapshot_id':result['source_snapshot_id']}))


if __name__ == '__main__':
    main()
