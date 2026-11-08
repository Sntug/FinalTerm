"""A3 identity safety, multi-affiliation provenance, offline replay and ICCV reuse."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from src.clean.normalize import clean_text, clean_url, doi, openalex, arxiv, orcid, ror
from src.clean.pipeline import load_input, run, summarize
from src.clean.resolution import resolve, paper_candidates
from src.clean.text import identifier, sha256
from src.clean.verify import validate_integrity, verify
from src.collect.common import REPO_ROOT, json_bytes
from src.collect.contract import load_records
from src.collect.export import export_records
from src.collect.openalex import enrich
from src.collect.pilot import run as collect
from test_a2_collector import setup, work, response
from test_a2_support import temporary_workspace

STAMP = '2026-11-08T00:00:00Z'


def observation(pid='cvf:CVPR2024:fixture', names=('Alice Smith', 'Bob Jones')):
    return dict(paper_id=pid, owner='A', scope='core', track='main', conference='CVPR',
        conference_year=2024, venue_id='venue:CVPR2024', title='A paper', title_raw='A paper',
        abstract='An abstract', abstract_raw='An abstract', doi=None,
        cvf_url='https://openaccess.thecvf.com/content/CVPR2024/html/fixture_paper.html',
        pdf_url=None, arxiv_url=None, publication_date='2024-06', date_precision='month',
        citation_publication_date_raw='2024', source_record_id='source:cvf:fixture', captured_at=STAMP,
        authors=[dict(name=n, name_raw=n, author_order=i) for i,n in enumerate(names, 1)],
        openalex_id=None, openalex_status='not_collected', citation_count=None,
        referenced_works=None, references_status='not_collected')


def source(sid, pid, kind='CVF'):
    return dict(schema_version='2.0.0', source_record_id=sid, paper_id=pid, source=kind,
        source_kind='detail' if kind == 'CVF' else 'work_detail', source_id=sid, source_version=None,
        url='https://openaccess.thecvf.com/fixture' if kind == 'CVF' else 'https://api.openalex.org/works/W1',
        fetched_at=STAMP, http_status=200, content_sha256='a'*64, content_type='application/json',
        etag=None, last_modified=None, raw_path='data/raw/fixture.json.gz')


def institution(number=1, name='Example University'):
    return dict(id=f'https://openalex.org/I{number}', display_name=name, ror=None, country_code='VN')


def fixture(names=('Alice Smith', 'Bob Jones')):
    old=observation(names=names)
    src=source(old['source_record_id'], old['paper_id'])
    listing=source('source:listing', None)
    records=export_records([old],[src,listing],listing)
    w=dict(id='https://openalex.org/W1', display_name='A paper', doi='https://doi.org/10.1234/example',
        publication_year=2024, locations=[{'source':{'display_name':'CVPR'}}], referenced_works=[],
        cited_by_count=0, authorships=[dict(raw_author_name=n,
            author=dict(id=f'https://openalex.org/A{i}',display_name=n,orcid=None),
            institutions=[institution()], raw_affiliation_strings=['Department, Example University'],
            affiliations=[dict(raw_affiliation_string='Department, Example University',institution_ids=['https://openalex.org/I1'])])
            for i,n in enumerate(names,1)])
    os=source('source:openalex:fixture',old['paper_id'],'OpenAlex')
    records['source_records.jsonl'].append(os)
    enrich(records,records['papers.jsonl'][0],w,[os],{'status':'matched'})
    records['paper_registry.csv'][0]['doi']=records['papers.jsonl'][0]['doi']
    return records, w


def clean(records, w):
    return resolve(records, {'source:openalex:fixture':json.dumps(w).encode()}, 'snapshot:fixture', STAMP)


class NormalizeTests(unittest.TestCase):
    def test_metadata_and_identifiers(self):
        self.assertEqual(clean_text('\ufeff  Hu\u0300ng &amp; A\u00a0 B\x00 '), 'Hùng & A B')
        self.assertEqual(clean_url(' HTTPS://EXAMPLE.ORG/a?q=1&amp;b=2#fragment '), 'https://example.org/a?q=1&b=2')
        self.assertEqual(doi('https://doi.org/10.1234/ABC%2Fdef'), '10.1234/abc/def')
        self.assertIsNone(doi('not a DOI'))
        self.assertEqual(openalex('A123','A'),'https://openalex.org/A123')
        self.assertIsNone(openalex('https://evil.example/A123','A'))
        self.assertEqual(arxiv('https://arxiv.org/pdf/2401.12345v3.pdf'),'2401.12345')
        self.assertEqual(arxiv('https://arxiv.org/abs/cs/9901001v2'),'cs/9901001')
        self.assertIsNone(arxiv('https://example.org/abs/2401.12345'))
        self.assertEqual(orcid('https://orcid.org/0000-0002-1825-0097'),'0000-0002-1825-0097')
        self.assertIsNone(orcid('0000-0002-1825-0098'))
        self.assertEqual(ror('https://ror.org/012tb2g32'),'012tb2g32')
        self.assertIsNone(ror('012tb2g33'))


class ResolutionTests(unittest.TestCase):
    def test_exact_ids_and_multiple_affiliations_preserve_order_and_raw(self):
        records,w=fixture()
        a=w['authorships'][0]
        a['institutions'].append(institution(2,'Example University Laboratory'))
        a['raw_affiliation_strings'].append('Lab, Example University')
        a['affiliations'].append(dict(raw_affiliation_string='Lab, Example University',institution_ids=['https://openalex.org/I2']))
        result=clean(records,w)
        validate_integrity(result)
        rows=result['authorships.csv']
        self.assertEqual(len(rows),3)
        self.assertEqual([r['author_order'] for r in rows],[1,1,2])
        self.assertEqual([r['institution_id'] for r in rows[:2]],['institution:openalex:I1','institution:openalex:I2'])
        self.assertEqual(json.loads(rows[1]['affiliation_raw']),['Lab, Example University'])
        self.assertTrue(all(r['source_record_id']=='source:cvf:fixture' and r['affiliation_source_record_id']=='source:openalex:fixture' for r in rows))
        self.assertEqual(len([n for n in result['nodes.csv'] if n['label']=='Institution']),2)
        self.assertFalse(result['edges.csv'])

    def test_homonyms_with_distinct_ids_are_not_merged(self):
        records,w=fixture(('Alex Li','Alex Li'))
        result=clean(records,w)
        self.assertEqual(len({r['author_id'] for r in result['authorships.csv']}),2)
        self.assertTrue(all(r['identity_status']=='resolved' for r in result['authorships.csv']))

    def test_repeated_author_id_in_one_work_is_quarantined(self):
        records,w=fixture()
        w['authorships'][1]['author']['id']='https://openalex.org/A1'
        result=clean(records,w)
        self.assertTrue(all(r['author_id'] is None and r['identity_status']=='needs_review' for r in result['authorships.csv']))
        self.assertFalse(result['nodes.csv'])

    def test_profile_name_mismatch_is_not_treated_as_verified_alias(self):
        records,w=fixture()
        w['authorships'][0]['author']['display_name']='A different person'
        result=clean(records,w)
        self.assertIsNone(result['authorships.csv'][0]['author_id'])
        self.assertEqual(result['authorships.csv'][0]['identity_status'],'needs_review')

    def test_byline_reordering_blocks_all_positional_links(self):
        records,w=fixture()
        w['authorships'].reverse()
        result=clean(records,w)
        self.assertTrue(all(r['author_id'] is None for r in result['authorships.csv']))

    def test_orcid_collision_does_not_merge_distinct_openalex_ids(self):
        records,w=fixture()
        for a in w['authorships']:a['author']['orcid']='https://orcid.org/0000-0002-1825-0097'
        result=clean(records,w)
        self.assertTrue(all(r['author_id'] is None for r in result['authorships.csv']))

    def test_raw_orcid_conflict_blocks_identity(self):
        records,w=fixture()
        w['authorships'][0]['raw_orcid']='0000-0002-1825-0098'
        result=clean(records,w)
        self.assertIsNone(result['authorships.csv'][0]['author_id'])

    def test_raw_orcid_only_fallback_and_collision(self):
        records,w=fixture()
        a=w['authorships'][0]
        a['author']['id']=None
        a['raw_orcid']='0000-0002-1825-0097'
        result=clean(records,w)
        self.assertEqual(result['authorships.csv'][0]['author_id'],'author:orcid:0000-0002-1825-0097')
        w['authorships'][1]['author']['orcid']='0000-0002-1825-0097'
        result=clean(records,w)
        self.assertTrue(all(r['author_id'] is None for r in result['authorships.csv']))

    def test_same_author_on_two_papers_reuses_id_without_merging_names(self):
        records,w=fixture()
        pid='cvf:CVPR2024:second'
        # Use exporter for the second CVF occurrence and retain independently ordered IDs.
        obs=observation(pid)
        obs.update(source_record_id='source:cvf:second',title='Second title',title_raw='Second title',
                   cvf_url=obs['cvf_url'].replace('fixture','second'))
        src=source('source:cvf:second',pid)
        listing=records['source_records.jsonl'][1]
        second=export_records([obs],[src],listing)
        os=source('source:openalex:second',pid,'OpenAlex')
        second['source_records.jsonl'].append(os)
        w2=deepcopy(w);w2.update(id='https://openalex.org/W2',display_name='Second title',doi='https://doi.org/10.1234/second')
        enrich(second,second['papers.jsonl'][0],w2,[os],{'status':'matched'})
        second['paper_registry.csv'][0]['doi']=second['papers.jsonl'][0]['doi']
        for key in records:records[key].extend(second[key])
        result=resolve(records,{'source:openalex:fixture':json.dumps(w).encode(), 'source:openalex:second':json.dumps(w2).encode()},'snapshot:fixture',STAMP)
        validate_integrity(result)
        self.assertEqual(len({r['author_id'] for r in result['authorships.csv']}),2)
        self.assertEqual(len(result['papers.jsonl']),2)

    def test_missing_affiliation_does_not_invalidate_paper_or_author(self):
        records,w=fixture()
        w['authorships'][0].update(institutions=[],raw_affiliation_strings=[],affiliations=[])
        result=clean(records,w)
        row=result['authorships.csv'][0]
        self.assertEqual(row['identity_status'],'resolved')
        self.assertEqual(row['affiliation_status'],'missing_in_source')
        self.assertEqual(result['paper_registry.csv'][0]['status'],'cvf_verified')

    def test_missing_abstract_is_valid_core_metadata(self):
        records,w=fixture()
        records['papers.jsonl'][0].update(abstract=None,abstract_text_version_id=None)
        result=clean(records,w)
        validate_integrity(result)
        self.assertEqual(summarize(records,result,1)['valid_core_papers'],1)

    def test_ror_fallback_cannot_bypass_conflicting_openalex_institution(self):
        records,w=fixture(('Alice Smith','Bob Jones','Claire Moore'))
        for a in w['authorships']:
            a['institutions'][0]['ror']='https://ror.org/012tb2g32'
        w['authorships'][1]['institutions'][0]['country_code']='US'
        w['authorships'][2]['institutions'][0]['id']=None
        result=clean(records,w)
        self.assertTrue(all(r['institution_id'] is None for r in result['authorships.csv']))

    def test_unmapped_raw_affiliation_is_retained_alongside_verified_one(self):
        records,w=fixture()
        w['authorships'][0]['raw_affiliation_strings'].append('Independent Lab')
        result=clean(records,w)
        rows=[r for r in result['authorships.csv'] if r['author_order']==1]
        self.assertEqual(len(rows),2)
        self.assertEqual(json.loads(rows[1]['affiliation_raw']),['Independent Lab'])
        self.assertEqual(rows[1]['affiliation_status'],'needs_review')
        validate_integrity(result)

    def test_ror_collision_and_parent_names_are_not_merged(self):
        records,w=fixture()
        w['authorships'][0]['institutions'][0]['ror']='https://ror.org/012tb2g32'
        w['authorships'][1]['institutions']=[{**institution(2,'Example University Lab'),'ror':'https://ror.org/012tb2g32'}]
        result=clean(records,w)
        self.assertTrue(all(r['institution_id'] is None for r in result['authorships.csv']))

    def test_title_candidates_and_identifier_collisions_require_manual_review(self):
        records,w=fixture()
        p=records['papers.jsonl'][0]; q=deepcopy(p)
        q.update(paper_id='cvf:CVPR2024:second',cvf_url=p['cvf_url'].replace('fixture','second'))
        q['doi']=None; q['openalex_id']=None
        claims,conflicts,pairs=paper_candidates([p,q])
        self.assertFalse(conflicts)
        self.assertEqual(pairs[0][1],'title_candidate')
        q['doi']=p['doi']
        self.assertEqual(len(paper_candidates([p,q])[1]),2)

    def test_html_cleaning_mints_text_version_and_preserves_original(self):
        records,w=fixture()
        p=records['papers.jsonl'][0]
        p['abstract']='A &amp; B'
        old_tid=p['abstract_text_version_id']
        result=clean(records,w)
        self.assertEqual(result['papers.jsonl'][0]['abstract'],'A & B')
        self.assertNotEqual(result['papers.jsonl'][0]['abstract_text_version_id'],old_tid)
        self.assertIn(old_tid,{t['text_version_id'] for t in result['text_versions.jsonl']})

    def test_unmatched_work_does_not_resolve_author(self):
        records,w=fixture()
        records['papers.jsonl'][0].update(openalex_id=None,openalex_status='needs_review')
        result=clean(records,w)
        self.assertTrue(all(r['author_id'] is None and r['identity_status']=='unresolved' for r in result['authorships.csv']))

    def test_decision_before_after_restores_authorship_and_checks_tampering(self):
        records,w=fixture()
        result=clean(records,w)
        for d in result['merge_log.jsonl']:
            if d['affected_authorship_ids']:
                change=d['changes'][0]
                old=[r for r in records['authorships.csv'] if r['authorship_id']==d['affected_authorship_ids'][0]]
                new=[r for r in result['authorships.csv'] if r['authorship_id']==d['affected_authorship_ids'][0]]
                self.assertEqual(change['before'],old)
                self.assertEqual(change['after'],new)
        result['authorships.csv'][0]['identity_source_record_id']=None
        with self.assertRaisesRegex(ValueError,'missing source'):validate_integrity(result)


class PipelineTests(unittest.TestCase):
    def prepare(self, root, conference='CVPR'):
        config=setup(root,conference,True)
        w=work()
        w['publication_year']=config['conference_year']
        w['locations'][0]['source']['display_name']=conference
        w['authorships'][0]['author']['display_name']='Hùng Nguyễn'
        w['authorships'][0]['institutions'][0].update(display_name='Example University',ror=None,country_code='VN')
        w['authorships'][1]['author']={'id':'https://openalex.org/A2','display_name':'Jane Smith'}
        def request(req,timeout):
            return response(req.full_url, {'meta':{'count':1},'results':[w]} if '?' in req.full_url else w)
        with patch('src.collect.cache.urlopen',side_effect=request):
            source_result=collect(root,'config/fixture.json',offline=False)
        c=dict(input_manifest=source_result['manifest'],processed_dir=config['processed_dir'].replace('/pilot','/a3'),
               owner=config['owner'],conference=conference,conference_year=config['conference_year'],target_count=1)
        (root/'config/a3.json').write_bytes(json_bytes(c))
        return c

    def test_offline_replay_is_byte_identical_and_input_is_unchanged(self):
        with temporary_workspace() as root, patch('socket.socket.connect',side_effect=AssertionError('network')):
            config=self.prepare(root)
            before={p:sha256(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
            with patch('src.collect.cache.urlopen',side_effect=AssertionError('network')):
                first=run(root,'config/a3.json')
                self.assertTrue(verify(root,'config/a3.json')['passed'])
                after={p:sha256(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
                self.assertEqual(run(root,'config/a3.json'),first)
                self.assertEqual(after,{p:sha256(p.read_bytes()) for p in root.rglob('*') if p.is_file()})
            self.assertTrue(all(sha256(p.read_bytes())==digest for p,digest in before.items()))
            self.assertEqual(first['distinct_authorships'],2)
            self.assertEqual(first['network_requests'],0)
            manifest=json.loads((root/first['manifest']).read_text())
            self.assertTrue(next(f for f in manifest['files'] if f['path'].endswith('source_records.jsonl'))['path'].startswith(config['input_manifest'].rsplit('/',1)[0]))

    def test_iccv_B_uses_same_pipeline(self):
        with temporary_workspace() as root:
            self.prepare(root,'ICCV')
            result=run(root,'config/a3.json')
            self.assertEqual(result['valid_core_papers'],1)
            self.assertTrue(verify(root,'config/a3.json')['passed'])
            self.assertFalse((root/'data/raw/cvpr2024').exists())

    def test_tampered_output_is_preserved_and_verifier_rejects(self):
        with temporary_workspace() as root:
            c=self.prepare(root)
            run(root,'config/a3.json')
            path=root/c['processed_dir']/'authorships.csv'
            path.write_bytes(b'user edit\n')
            with self.assertRaisesRegex(ValueError,'Refusing to overwrite'):run(root,'config/a3.json')
            self.assertEqual(path.read_bytes(),b'user edit\n')
            with self.assertRaisesRegex(ValueError,'hash/path mismatch'):verify(root,'config/a3.json')

    def test_target_discrepancy_is_reported_without_padding(self):
        with temporary_workspace() as root:
            c=self.prepare(root)
            c['target_count']=2
            (root/'config/a3.json').write_bytes(json_bytes(c))
            result=run(root,'config/a3.json')
            self.assertFalse(result['delivery_complete'])
            self.assertEqual(result['output_target_delta'],-1)
            self.assertEqual(result['output_papers'],1)

    def test_interrupted_publish_recovers_original_timestamp(self):
        with temporary_workspace() as root:
            self.prepare(root)
            first=run(root,'config/a3.json')
            path=root/first['manifest'];original=path.read_bytes();path.unlink()
            with patch('src.clean.pipeline.now_utc',return_value='2099-01-01T00:00:00Z'):
                self.assertEqual(run(root,'config/a3.json'),first)
            self.assertEqual(path.read_bytes(),original)

    def test_wrong_owner_or_input_output_overlap_is_rejected(self):
        with temporary_workspace() as root:
            c=self.prepare(root)
            for change in ({'owner':'B'}, {'processed_dir':c['input_manifest'].rsplit('/',1)[0]}, {'processed_dir':'../outside'}):
                (root/'config/a3.json').write_bytes(json_bytes({**c,**change}))
                with self.assertRaises(ValueError):run(root,'config/a3.json')


if __name__ == '__main__':
    unittest.main()
