"""Transport, configurable ICCV and interruption/resume integration tests."""
import csv
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError
from src.collect.common import REPO_ROOT, json_bytes, load_config, load_selection, paper_id_from_url
from src.collect.cache import OpenAlexCache, SourceFailure, retry_after
from src.collect.openalex import assessment
from src.collect.pilot import run
from src.collect.verify import verify
from src.clean.text import sha256
from test_a2_support import temporary_workspace
from test_a2_cvf import CVPR, ICCV, fixture_html


def setup(root, conference='CVPR', enabled=True):
    config=json.loads((REPO_ROOT/'config/a_cvpr2024_pilot.json').read_text())
    year=2024 if conference=='CVPR' else 2023
    owner='A' if conference=='CVPR' else 'B'
    corpus=conference.lower()+str(year)
    config.pop('selection_file',None)
    config.update(owner=owner, conference=conference, conference_year=year, target_count=1,
        registry_input='config/registry.csv', raw_dir='data/raw/'+corpus,
        processed_dir='data/processed/'+corpus+'/pilot', output_dir='outputs/test',
        listing_url=f'https://openaccess.thecvf.com/{conference}{year}?day=all',
        openalex_enabled=enabled, openalex_delay_seconds=0, retries=0)
    (root/'config').mkdir()
    (root/'config/fixture.json').write_bytes(json_bytes(config))
    url=CVPR if conference=='CVPR' else ICCV
    with (root/'config/registry.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['paper_id','cvf_url','owner','conference','conference_year','doi'])
        writer.writeheader();writer.writerow(dict(paper_id=paper_id_from_url(url),cvf_url=url,owner=owner,conference=conference,conference_year=year,doi=''))
    body=fixture_html().replace(b'2024',str(year).encode())
    if conference=='ICCV':body=body.replace(b'Conference on Computer Vision and Pattern Recognition',b'International Conference on Computer Vision')
    for link,raw in [(url,body),(config['listing_url'],f'<a href="{url}">paper</a>'.encode())]:
        directory=root/config['raw_dir']/'http';directory.mkdir(parents=True,exist_ok=True)
        file=directory/(sha256(raw)+'.html.gz');file.write_bytes(gzip.compress(raw,mtime=0))
        meta=dict(url=link,fetched_at='2026-11-05T00:00:00Z',http_status=200,content_sha256=sha256(raw),content_type='text/html',etag=None,last_modified=None,raw_path=file.relative_to(root).as_posix())
        (directory/(sha256(link.encode())+'.json')).write_bytes(json_bytes(meta))
    return config


def work():
    return {'id':'https://openalex.org/W123','display_name':'A & B','publication_year':2024,
        'doi':'https://doi.org/10.1234/test','authorships':[{'raw_author_name':'Hùng Nguyễn','author':{'id':'https://openalex.org/A1'},'institutions':[{'id':'https://openalex.org/I1'}]}, {'raw_author_name':'Jane Smith','institutions':[]}],
        'locations':[{'source':{'display_name':'CVPR'},'landing_page_url':CVPR}],
        'referenced_works':['https://openalex.org/W456'],'cited_by_count':99,'abstract_inverted_index':None}


def response(url,value):
    result=MagicMock();result.__enter__.return_value=result;result.status=200
    result.geturl.return_value=url;result.read.return_value=json.dumps(value).encode()
    result.headers={'Content-Type':'application/json'}
    return result


class CollectorTests(unittest.TestCase):
    def test_iccv_config_runs_in_temporary_workspace(self):
        with temporary_workspace() as root, patch('src.collect.cache.urlopen',side_effect=AssertionError('network')):
            setup(root,'ICCV',False)
            result=run(root,'config/fixture.json',offline=True)
            self.assertEqual(result['papers'],1)
            self.assertFalse((root/'data/raw/cvpr2024').exists())
            self.assertTrue(verify(root,result['manifest'])['passed'])

    def test_duplicate_registry_and_wrong_edition_rejected(self):
        with temporary_workspace() as root:
            config=setup(root,enabled=False)
            path=root/config['registry_input'];old=path.read_text()
            path.write_text(old+old.splitlines()[1]+'\n',encoding='utf-8');config['target_count']=2
            with self.assertRaisesRegex(ValueError,'Duplicate'):load_selection(root,config)
            path.write_text(old.replace('CVPR2024','CVPR2024W'),encoding='utf-8');config['target_count']=1
            with self.assertRaises(ValueError):load_selection(root,config)

    def test_resume_after_detail_failure_and_offline_repeat(self):
        with temporary_workspace() as root:
            setup(root)
            failed=[False]
            def request(req,timeout):
                url=req.full_url
                if '?' in url:return response(url,{'meta':{'count':1},'results':[work()]})
                if not failed[0]:failed[0]=True;raise URLError('secret URL must not appear')
                return response(url,work())
            with patch('src.collect.cache.urlopen',side_effect=request) as net:
                first=run(root,'config/fixture.json',offline=False)
                self.assertFalse(first['collection_complete'])
                second=run(root,'config/fixture.json',offline=False)
                self.assertTrue(second['collection_complete']);self.assertEqual(net.call_count,3)
            manifest=(root/second['manifest']).read_bytes()
            with patch('src.collect.cache.urlopen',side_effect=AssertionError('offline')):
                third=run(root,'config/fixture.json',offline=True)
            self.assertEqual(manifest,(root/third['manifest']).read_bytes())
            self.assertEqual(third['openalex_status_counts'],{'matched':1,'not_found':0,'needs_review':0,'not_collected':0})
            self.assertEqual(third['raw_sources_checked'],4)
            self.assertEqual(third['coverage']['affiliation_verified_papers']['numerator'],0)
            self.assertEqual(third['coverage']['references_nonempty']['numerator'],1)

    def test_matching_requires_byline_and_venue_or_link(self):
        paper={'title':'A & B','authors':[{'name':'Hùng Nguyễn'},{'name':'Jane Smith'}], 'cvf_url':CVPR,'conference':'CVPR','conference_year':2024,'doi':None}
        self.assertTrue(assessment(paper,work())['accepted'])
        for key,value in [('display_name','A similar B'),('authorships',[]),('locations',[])]:
            self.assertFalse(assessment(paper,{**work(),key:value})['accepted'])

    def test_retry_after_quota_gate_and_key_not_persisted(self):
        with temporary_workspace() as root:
            config=setup(root)
            url='https://api.openalex.org/works?search=test'
            with patch.dict('os.environ',{'OPENALEX_API_KEY':'fixture-secret'}), patch('src.collect.cache.urlopen',side_effect=HTTPError(url,429,'quota',{'Retry-After':'3600'},None)):
                cache=OpenAlexCache(root,config)
                with self.assertRaises(SourceFailure):cache.get(url)
            with patch('src.collect.cache.urlopen') as net:
                with self.assertRaises(SourceFailure):OpenAlexCache(root,config).get(url)
                net.assert_not_called()
            for p in root.rglob('*.json'):self.assertNotIn('fixture-secret',p.read_text())
            self.assertEqual(retry_after('3'),3)

    def test_json_cache_hash_offline_and_authorization_header(self):
        with temporary_workspace() as root:
            config=setup(root);url='https://api.openalex.org/works/W123'
            with patch.dict('os.environ',{'OPENALEX_API_KEY':'fixture-secret'}), patch('src.collect.cache.urlopen',side_effect=lambda req,timeout:response(req.full_url,work())) as net:
                value,meta=OpenAlexCache(root,config).get(url)
                req=net.call_args.args[0]
                self.assertEqual(req.get_header('Authorization'),'Bearer fixture-secret')
                self.assertNotIn('fixture-secret',req.full_url)
            with patch('src.collect.cache.urlopen') as net:
                self.assertEqual(OpenAlexCache(root,config,True).get(url)[0],value)
                (root/meta['raw_path']).write_bytes(gzip.compress(b'{}'))
                with self.assertRaises(ValueError):OpenAlexCache(root,config).get(url)
                net.assert_not_called()

    def test_verifier_rejects_raw_corruption(self):
        with temporary_workspace() as root:
            config=setup(root,enabled=False);result=run(root,'config/fixture.json')
            next((root/config['raw_dir']).rglob('*.gz')).write_bytes(gzip.compress(b'changed'))
            with self.assertRaises(ValueError):verify(root,result['manifest'])

    def test_cvf_quota_persists_progress_and_honors_gate(self):
        with temporary_workspace() as root:
            config=setup(root)
            path=root/config['raw_dir']/'http'/(sha256(config['listing_url'].encode())+'.json')
            path.unlink()
            with patch('src.collect.cache.urlopen',side_effect=HTTPError(config['listing_url'],429,'quota',{'Retry-After':'3600'},None)) as net:
                result=run(root,'config/fixture.json',offline=False)
                self.assertFalse(result['collection_complete'])
                self.assertEqual(result['papers'],0)
                run(root,'config/fixture.json',offline=False)
                self.assertEqual(net.call_count,1)

    def test_openalex_short_retry_after_is_waited(self):
        with temporary_workspace() as root:
            config=setup(root);config['retries']=1
            url='https://api.openalex.org/works/W123'
            with patch('src.collect.cache.urlopen',side_effect=[HTTPError(url,429,'rate',{'Retry-After':'2'},None),response(url,work())]), patch('src.collect.cache.time.sleep') as sleep:
                self.assertEqual(OpenAlexCache(root,config).get(url)[0]['id'],work()['id'])
                self.assertIn(unittest.mock.call(2),sleep.call_args_list)

    def test_manifest_cannot_escape_repo_even_with_recomputed_digest(self):
        from src.collect.pilot import snapshot_payload
        from src.clean.text import canonical_json
        with temporary_workspace() as root:
            setup(root,enabled=False);result=run(root,'config/fixture.json')
            path=root/result['manifest'];manifest=json.loads(path.read_text())
            manifest['files'][0]['path']='../outside.csv'
            manifest['snapshot_id']='snapshot:v2:'+sha256(canonical_json(snapshot_payload(manifest)).encode())
            path.write_bytes(json_bytes(manifest))
            with self.assertRaises(ValueError):verify(root,result['manifest'])

    def test_verifier_rejects_dangling_paper_source_after_rehash(self):
        from src.collect.pilot import snapshot_payload
        from src.clean.text import canonical_json
        with temporary_workspace() as root:
            setup(root,enabled=False);result=run(root,'config/fixture.json')
            path=root/result['manifest'];manifest=json.loads(path.read_text())
            entry=next(f for f in manifest['files'] if f['path'].endswith('/papers.jsonl'))
            table=root/entry['path'];paper=json.loads(table.read_text())
            paper['representative_source_record_id']='missing'
            table.write_text(canonical_json(paper)+'\n',encoding='utf-8',newline='\n')
            entry['sha256']=sha256(table.read_bytes())
            manifest['snapshot_id']='snapshot:v2:'+sha256(canonical_json(snapshot_payload(manifest)).encode())
            path.write_bytes(json_bytes(manifest))
            with self.assertRaisesRegex(ValueError,'Paper/source'):verify(root,result['manifest'])

if __name__=='__main__':unittest.main()
