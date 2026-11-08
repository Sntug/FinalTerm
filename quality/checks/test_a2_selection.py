"""Selection lock precedes detail I/O and remains reusable across corpora."""
import gzip
import json
import unittest
from unittest.mock import patch

from src.clean.text import sha256
from src.collect.cache import source_record
from src.collect.common import atomic_json, json_bytes, load_selection, paper_id_from_url
from src.collect.cvf import rank_urls
from src.collect.pilot import run
from src.collect.selection import prepare
from test_a2_collector import setup
from test_a2_support import temporary_workspace


def configure(root, conference='CVPR'):
    config=setup(root, conference, enabled=False)
    directory=root/config['raw_dir']/'http'
    meta_path=directory/(sha256(config['listing_url'].encode())+'.json')
    meta=json.loads(meta_path.read_text())
    old_body=gzip.decompress((root/meta['raw_path']).read_bytes()).decode()
    import re
    url=re.search('href="([^"]+)"',old_body)[1]
    urls=[url, url.replace('_paper.html','_Second_paper.html'),url.replace('_paper.html','_Third_paper.html')]
    body=''.join(f'<a href="{u}">paper</a>' for u in reversed(urls)).encode()
    raw=directory/(sha256(body)+'.html.gz');raw.write_bytes(gzip.compress(body,mtime=0))
    meta.update(content_sha256=sha256(body),raw_path=raw.relative_to(root).as_posix())
    meta_path.write_bytes(json_bytes(meta))
    detail_meta=json.loads((directory/(sha256(url.encode())+'.json')).read_text())
    pilot={'seed':config['seed'],'listing_source_record_id':source_record(meta,None,'listing')['source_record_id'],
           'papers':[{'paper_id':paper_id_from_url(url),'cvf_url':url,
                      'source_record_id':source_record(detail_meta,paper_id_from_url(url),'paper_detail')['source_record_id']}]}
    (root/'config/preserved.json').write_bytes(json_bytes(pilot))
    config.update(target_count=3, preserve_selection_file='config/preserved.json',
                  registry_input='config/expanded.csv',selection_file='config/selection.json',
                  selection_lock_copy=config['processed_dir']+'/selection_lock.json',
                  checkpoint_file=config['raw_dir']+'/checkpoints/expanded.json')
    (root/'config/fixture.json').write_bytes(json_bytes(config))
    return config,urls


class SelectionTests(unittest.TestCase):
    def test_checkpoint_retries_transient_windows_file_lock(self):
        import os
        with temporary_workspace() as root:
            destination=root/'checkpoint.json'
            destination.write_bytes(b'{"completed":1}')
            real_replace=os.replace
            attempts=[]
            def replace(source,target):
                attempts.append(1)
                if len(attempts)<3:
                    self.assertEqual(destination.read_bytes(),b'{"completed":1}')
                    raise PermissionError('temporary sharing violation')
                real_replace(source,target)
            with patch('src.collect.common.os.name','nt'), patch('src.collect.common.os.replace',side_effect=replace), patch('src.collect.common.time.sleep'):
                atomic_json(destination,{'completed':2})
            self.assertEqual(json.loads(destination.read_text()),{'completed':2})
            self.assertEqual(len(attempts),3)

    def test_lock_preserves_pilot_and_deterministic_remaining_without_network(self):
        for conference in ('CVPR','ICCV'):
            with self.subTest(conference=conference), temporary_workspace() as root:
                config,urls=configure(root,conference)
                with patch('src.collect.cache.urlopen',side_effect=AssertionError('network')):
                    result=prepare(root,'config/fixture.json')
                    selected=[p['cvf_url'] for p in result['papers']]
                    self.assertEqual(selected,[urls[0]]+rank_urls(urls[1:],config['seed']))
                    before=(root/config['selection_file']).read_bytes()
                    self.assertEqual(result,prepare(root,'config/fixture.json'))
                self.assertEqual(before,(root/config['selection_lock_copy']).read_bytes())
                self.assertEqual(result['preserved_paper_ids'],[paper_id_from_url(urls[0])])
                self.assertEqual(result['excluded_candidates'],[])
                self.assertEqual(len(list((root/config['raw_dir']/'http').glob('*.json'))),2)

    def test_lock_tampering_is_rejected_before_collection(self):
        with temporary_workspace() as root:
            config,_=configure(root);prepare(root,'config/fixture.json')
            path=root/config['registry_input'];path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'hash changed'):
                load_selection(root,config)

    def test_checkpoint_is_scoped_and_resume_reuses_cache(self):
        with temporary_workspace() as root:
            config=setup(root,enabled=False)
            config['checkpoint_file']=config['raw_dir']+'/checkpoints/expanded.json'
            (root/'config/fixture.json').write_bytes(json_bytes(config))
            original=root/config['raw_dir']/'collector_checkpoint.json'
            original.write_bytes(b'{"pilot":"unchanged"}')
            with patch('src.collect.cache.urlopen',side_effect=AssertionError('network')):
                first=run(root,'config/fixture.json',offline=True)
                before=(root/first['manifest']).read_bytes()
                second=run(root,'config/fixture.json',offline=True)
            self.assertEqual(original.read_bytes(),b'{"pilot":"unchanged"}')
            self.assertEqual(before,(root/second['manifest']).read_bytes())
            self.assertTrue((root/config['checkpoint_file']).is_file())


if __name__=='__main__':unittest.main()
