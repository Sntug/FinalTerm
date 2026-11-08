"""Evidence-backed links into v2 identities; ambiguous canonical merges require review."""
from collections import Counter, defaultdict
from copy import deepcopy
from difflib import SequenceMatcher
import json

from src.collect.contract import contract, validate_records
from src.collect.openalex import comparable
from .normalize import clean_text, clean_url, doi, openalex, arxiv, orcid, ror
from .text import canonical_json, evidence_id, identifier, text_record

RULE = 'a3-exact-source-link'
VERSION = '1.0.0'


class Audit:
    def __init__(self, records, snapshot, decided_at):
        self.records, self.snapshot, self.decided_at = records, snapshot, decided_at
        self.sources = {s['source_record_id']: s for s in records['source_records.jsonl']}
        self.aliases = {}
        self.nodes = {}

    def evidence(self, paper, sid, path, value=None):
        source = self.sources[sid]
        row = dict.fromkeys(contract()['files']['evidence.jsonl']['fields'])
        row.update(evidence_kind='metadata', paper_id=paper['paper_id'], source_record_id=sid,
                   source_url=source['url'], field_path=path, evidence_text=value,
                   rule_id=RULE, rule_version=VERSION, captured_at=source['fetched_at'],
                   supporting_evidence_ids=[], owner=paper['owner'])
        row['evidence_id'] = evidence_id(row)
        self.records['evidence.jsonl'].append(row)
        return row['evidence_id']

    def review(self, paper, entity, entity_id, issue, reason, candidates, evidence):
        self.records['needs_review.csv'].append(dict(
            review_id=identifier('review', RULE, paper['paper_id'], entity_id or '', issue),
            paper_id=paper['paper_id'], entity_type=entity, entity_id=entity_id, field_name=issue,
            reason=reason, candidate_ids=sorted(set(candidates)), evidence_ids=sorted(set(evidence)),
            review_status='open', assigned_to=paper['owner'], resolution_decision_id=None))

    def decision(self, paper, entity, inputs, outputs, evidence, reason, aid=None):
        did = identifier('decision', RULE, VERSION, self.snapshot, entity, canonical_json(inputs),
                         canonical_json(outputs), canonical_json(sorted(evidence)), aid or '')
        row = dict(decision_id=did, action='link', entity_type=entity, input_ids=inputs,
                   output_ids=outputs, affected_paper_ids=[paper['paper_id']],
                   affected_authorship_ids=[aid] if aid else [], changes=[], reason=reason,
                   evidence_ids=sorted(set(evidence)), proposed_by=paper['owner'], reviewed_by=RULE + '-' + VERSION,
                   review_mode='rule', decided_at=self.decided_at, snapshot_before=self.snapshot,
                   reverts_decision_id=None)
        self.records['merge_log.jsonl'].append(row)
        return row

    def alias(self, paper, entity, source, external, canonical, evidence):
        key = (entity, source, external)
        if key in self.aliases:
            old = self.aliases[key]
            if old['canonical_id'] != canonical:
                raise ValueError('Alias conflict was not quarantined: ' + str(key))
            return old['decision_id']
        row = dict(alias_id=identifier('alias', *key), entity_type=entity, source=source,
                   external_id=external, canonical_id=canonical, decision_id='')
        dec = self.decision(paper, entity, [external], [canonical], evidence,
                            'Exact source identifier linked to canonical entity; no name-only merge.')
        row['decision_id'] = dec['decision_id']
        dec['changes'] = [dict(table='alias_map.csv', record_key={'alias_id': row['alias_id']},
                               field='$row', before=None, after=deepcopy(row))]
        self.aliases[key] = row
        self.records['alias_map.csv'].append(row)
        return dec['decision_id']

    def node(self, paper, entity, cid, name, sid, properties):
        # Entity metadata uses the existing node contract, without graph edges/import.
        if cid not in self.nodes:
            self.nodes[cid] = dict(id=cid, label=entity, name=name, owner=paper['owner'],
                source_origin=['OpenAlex'], source_record_ids=[], validation_status='accepted',
                project_id=contract()['project_id'], properties_json={**properties, 'aliases': []})
        row = self.nodes[cid]
        row['source_record_ids'] = sorted(set(row['source_record_ids'] + [sid]))
        row['properties_json']['aliases'] = sorted(set(row['properties_json']['aliases'] + [name]))
        for key, value in properties.items():
            if value is not None:
                row['properties_json'][key] = value


def identity_conflicts(works):
    """Detect contradictory assignments across the entire batch before linking any row."""
    author_names, author_orcids, orcid_authors = defaultdict(set), defaultdict(set), defaultdict(set)
    inst_rors, ror_insts, inst_countries = defaultdict(set), defaultdict(set), defaultdict(set)
    bad_authors, bad_institutions = set(), set()
    for work in works.values():
        ids = [openalex((a.get('author') or {}).get('id'), 'A') for a in work.get('authorships', [])]
        bad_authors.update(k for k, count in Counter(ids).items() if k and count > 1)
        for a in work.get('authorships', []):
            au = a.get('author') or {}
            aid, oid = openalex(au.get('id'), 'A'), orcid(au.get('orcid'))
            if aid:
                author_names[aid].add(comparable(clean_text(a.get('raw_author_name') or au.get('display_name'))))
                if oid:
                    author_orcids[aid].add(oid)
                    orcid_authors[oid].add(aid)
            for inst in a.get('institutions') or []:
                iid, rid = openalex(inst.get('id'), 'I'), ror(inst.get('ror'))
                if iid and rid:
                    inst_rors[iid].add(rid)
                    ror_insts[rid].add(iid)
                if iid and inst.get('country_code'):
                    inst_countries[iid].add(inst['country_code'])
    bad_authors.update(k for k, v in author_names.items() if len(v) > 1)
    bad_authors.update(k for k, v in author_orcids.items() if len(v) > 1)
    for values in orcid_authors.values():
        if len(values) > 1:
            bad_authors.update(values)
    bad_institutions.update(k for k, v in inst_rors.items() if len(v) > 1)
    bad_institutions.update(k for k, v in inst_countries.items() if len(v) > 1)
    for values in ror_insts.values():
        if len(values) > 1:
            bad_institutions.update(values)
    return bad_authors, bad_institutions


def secondary_identifiers(works):
    """Resolve fallback IDs consistently within the batch, including collision guards."""
    authors, institutions, names = defaultdict(set), defaultdict(set), defaultdict(set)
    repeated = set()
    for work in works.values():
        per_work = []
        for a in work.get('authorships', []):
            au = a.get('author') or {}
            aid = openalex(au.get('id'), 'A')
            oid = orcid(a.get('raw_orcid')) or orcid(au.get('orcid'))
            if oid:
                per_work.append(oid)
                names[oid].add(comparable(clean_text(a.get('raw_author_name') or au.get('display_name'))))
                if aid:
                    authors[oid].add(aid)
            for inst in a.get('institutions') or []:
                iid, rid = openalex(inst.get('id'), 'I'), ror(inst.get('ror'))
                if iid and rid:
                    institutions[rid].add(iid)
        repeated.update(k for k, count in Counter(per_work).items() if count > 1)
    bad_orcids = repeated | {k for k, v in names.items() if len(v) > 1} | {k for k, v in authors.items() if len(v) > 1}
    bad_rors = {k for k, v in institutions.items() if len(v) > 1}
    return ({k: next(iter(v)) for k, v in authors.items() if len(v) == 1},
            {k: next(iter(v)) for k, v in institutions.items() if len(v) == 1}, bad_orcids, bad_rors)


def paper_candidates(papers):
    """Shared strong IDs are conflicts between locked CVF IDs, never implicit merges."""
    claims, conflicts, pairs = defaultdict(set), defaultdict(set), []
    for p in papers:
        for source, value in (('CVF', clean_url(p['cvf_url'])), ('DOI', doi(p['doi'])),
                              ('OpenAlex', openalex(p['openalex_id'], 'W')),
                              ('arXiv', arxiv(p['arxiv_url']))):
            if value:
                claims[(source, value)].add(p['paper_id'])
    for (source, value), pids in claims.items():
        if len(pids) > 1:
            for pid in pids:
                conflicts[pid].add((source, value))
            pairs.append((sorted(pids), 'identifier_collision', source + ':' + value))
    for index, p in enumerate(papers):
        for q in papers[index + 1:]:
            if (p['conference'], p['conference_year']) != (q['conference'], q['conference_year']):
                continue
            title, other = comparable(p['title']), comparable(q['title'])
            same_authors = [comparable(a['name']) for a in p['authors']] == [comparable(a['name']) for a in q['authors']]
            if title == other or (same_authors and SequenceMatcher(None, title, other).ratio() >= .97):
                pairs.append(([p['paper_id'], q['paper_id']], 'title_candidate',
                              'Similar title/byline/year only; no automatic merge.'))
    return claims, conflicts, pairs


def normalize_papers(records, audit):
    provenance = {(r['paper_id'], r['field_name']): r for r in records['field_provenance.csv']}
    texts = {t['text_version_id']: t for t in records['text_versions.jsonl']}
    registry = {r['paper_id']: r for r in records['paper_registry.csv']}
    for p in records['papers.jsonl']:
        for field in ('title', 'abstract'):
            cleaned = clean_text(p[field])
            if cleaned != p[field]:
                old = texts[p[field + '_text_version_id']]
                new = text_record(p['paper_id'], old['source_record_id'], old['field_path'], cleaned,
                                  'a3-metadata-1.0.0', old['captured_at'])
                records['text_versions.jsonl'].append(new)
                p[field], p[field + '_text_version_id'] = cleaned, new['text_version_id']
                provenance[(p['paper_id'], field)]['selection_rule'] = 'a3-html-nfc-ws-1'
        for field in ('doi', 'cvf_url', 'pdf_url', 'arxiv_url', 'openalex_id'):
            old = p[field]
            try:
                cleaned = doi(old) if field == 'doi' else openalex(old, 'W') if field == 'openalex_id' else clean_url(old)
            except ValueError:
                cleaned = None
            if old and not cleaned:
                sid = provenance.get((p['paper_id'], field), {}).get('source_record_id', p['representative_source_record_id'])
                eid = audit.evidence(p, sid, provenance.get((p['paper_id'], field), {}).get('field_path', 'html:head'), old)
                audit.review(p, 'Paper', p['paper_id'], 'invalid_' + field, 'Malformed identifier/URL retained for review.', [old], [eid])
            elif cleaned != old:
                p[field] = cleaned
                if (p['paper_id'], field) in provenance:
                    provenance[(p['paper_id'], field)]['selection_rule'] += ';a3-format-1'
        for a in p['authors']:
            a['name'] = clean_text(a['name'])
        for field in ('title', 'doi', 'cvf_url'):
            registry[p['paper_id']][field] = p[field]


def resolve(records, bodies, snapshot, decided_at):
    records = deepcopy(records)
    audit = Audit(records, snapshot, decided_at)
    normalize_papers(records, audit)
    papers = {p['paper_id']: p for p in records['papers.jsonl']}
    registry = {p['paper_id']: p for p in records['paper_registry.csv']}
    prov = {(r['paper_id'], r['field_name']): r for r in records['field_provenance.csv']}
    works, work_sources = {}, {}
    for pid, p in papers.items():
        if p['openalex_status'] == 'matched':
            sid = prov[(pid, 'openalex_id')]['source_record_id']
            works[pid] = json.loads(bodies[sid])
            work_sources[pid] = sid
    claims, conflicts, candidates = paper_candidates(list(papers.values()))
    for pids, issue, reason in candidates:
        for pid in pids:
            p = papers[pid]
            e = audit.evidence(p, p['representative_source_record_id'], 'html:meta[name=citation_title]@content', p['title'])
            audit.review(p, 'Paper', pid, issue + ':' + identifier('pair', *pids),
                         reason + ' Locked canonical Paper IDs require manual A/B merge approval.', pids, [e])
            if issue == 'identifier_collision':
                registry[pid]['status'] = 'needs_review'
    for p in papers.values():
        pid, sid = p['paper_id'], p['representative_source_record_id']
        for source, value, esid, path in (
            ('CVF', p['cvf_url'], sid, 'html:link[rel=canonical]@href'),
            ('DOI', doi(p['doi']), prov.get((pid, 'doi'), {}).get('source_record_id'), prov.get((pid, 'doi'), {}).get('field_path')),
            ('OpenAlex', openalex(p['openalex_id'], 'W'), work_sources.get(pid), 'json:id'),
            ('arXiv', arxiv(p['arxiv_url']), sid, 'html:a[href*="arxiv.org/abs/"]@href')):
            if value and esid and len(claims[(source, value)]) == 1:
                if source == 'CVF':
                    # A2 represents a detail page by its requested URL; cite its title.
                    path = 'html:meta[name=citation_title]@content'
                ev = audit.evidence(p, esid, path)
                audit.alias(p, 'Paper', source, value, pid, [ev])
    bad_authors, bad_institutions = identity_conflicts(works)
    orcid_ids, ror_ids, bad_orcids, bad_rors = secondary_identifiers(works)
    new_rows = []
    for old in records['authorships.csv']:
        p = papers[old['paper_id']]
        row = deepcopy(old)
        row['author_name'] = clean_text(row['author_name'])
        aid, pid = row['authorship_id'], p['paper_id']
        if pid not in works or pid in conflicts:
            e = audit.evidence(p, row['source_record_id'], 'html:meta[name=citation_author]@content[]', row['author_name_raw'])
            audit.review(p, 'Author', aid, 'identity_unresolved',
                         'No unambiguous verified Work; CVF occurrence kept without global Author ID.', [], [e])
            new_rows.append(row)
            continue
        work, sid = works[pid], work_sources[pid]
        wa = work.get('authorships') or []
        names = [comparable(clean_text(a.get('raw_author_name') or (a.get('author') or {}).get('display_name'))) for a in wa]
        expected = [comparable(a['name']) for a in p['authors']]
        if names != expected:
            row['identity_status'] = row['affiliation_status'] = 'needs_review'
            ev = audit.evidence(p, sid, 'json:authorships')
            audit.review(p, 'Author', aid, 'byline_mismatch', 'Ordered Work byline differs from CVF; positional links withheld.', [], [ev])
            new_rows.append(row)
            continue
        index = row['author_order'] - 1
        observed = wa[index]
        au = observed.get('author') or {}
        external, oid = openalex(au.get('id'), 'A'), orcid(au.get('orcid'))
        raw_oid = orcid(observed.get('raw_orcid'))
        canonical_external = external or orcid_ids.get(raw_oid)
        ev = audit.evidence(p, sid, f'json:authorships[{index}]', canonical_json(observed))
        cvf_ev = audit.evidence(p, row['source_record_id'], 'html:meta[name=citation_author]@content[]', row['author_name_raw'])
        raw_strings = list(dict.fromkeys((observed.get('raw_affiliation_strings') or []) +
            [a['raw_affiliation_string'] for a in observed.get('affiliations') or [] if a.get('raw_affiliation_string')]))
        # JSON array in the existing scalar retains boundaries and every raw string.
        row['affiliation_raw'] = canonical_json(raw_strings) if raw_strings else None
        row['affiliation_source_record_id'] = sid
        problem = None
        if canonical_external in bad_authors or (oid or raw_oid) in bad_orcids:
            problem = 'Conflicting/repeated OpenAlex Author ID, byline names or ORCID in this batch.'
        elif au.get('display_name') and comparable(clean_text(au['display_name'])) != comparable(row['author_name']):
            problem = 'OpenAlex profile name differs from the CVF/Work byline; alias needs manual corroboration.'
        elif observed.get('raw_orcid') and (not raw_oid or (oid and raw_oid != oid)):
            problem = 'Work raw ORCID is invalid or contradicts the Author ORCID.'
        elif not external and not raw_oid:
            problem = 'No valid OpenAlex Author ID or per-work ORCID; profile ORCID alone is insufficient.'
        if problem:
            row['identity_status'] = row['affiliation_status'] = 'needs_review'
            audit.review(p, 'Author', aid, 'identity_conflict', problem, [x for x in (external, oid, raw_oid) if x], [ev, cvf_ev])
            new_rows.append(row)
            continue
        cid = 'author:openalex:' + canonical_external.rsplit('/', 1)[-1] if canonical_external else 'author:orcid:' + raw_oid
        row.update(author_id=cid, identity_status='resolved', identity_source_record_id=sid)
        if external:
            audit.alias(p, 'Author', 'OpenAlex', external, cid, [ev, cvf_ev])
        # ORCID is an alias of this corroborated ID, never a reason to merge two OA IDs.
        if oid or raw_oid:
            audit.alias(p, 'Author', 'ORCID', oid or raw_oid, cid, [ev, cvf_ev])
        elif au.get('orcid'):
            audit.review(p, 'Author', cid, 'invalid_orcid', 'Malformed/checksum-invalid ORCID not linked.', [au['orcid']], [ev])
        audit.node(p, 'Author', cid, row['author_name'], sid, {'openalex_id': external, 'orcid': oid or raw_oid})
        inst_rows, unresolved_raw = [], set(raw_strings)
        institutions = observed.get('institutions') or []
        seen_insts = set()
        for pos, inst in enumerate(institutions):
            iid, rid = openalex(inst.get('id'), 'I'), ror(inst.get('ror'))
            canonical_iid = iid or ror_ids.get(rid)
            name = clean_text(inst.get('display_name'))
            if canonical_iid in bad_institutions or rid in bad_rors or (not iid and not rid) or not name or name.casefold() in ('unknown', 'none', 'nan'):
                audit.review(p, 'Institution', iid or aid, 'institution_conflict',
                             'Invalid/conflicting institution identity or missing name; no placeholder created.',
                             [x for x in (iid, rid) if x], [ev])
                continue
            icid = 'institution:openalex:' + canonical_iid.rsplit('/', 1)[-1] if canonical_iid else 'institution:ror:' + rid
            if icid in seen_insts:
                continue
            seen_insts.add(icid)
            mapped = [a['raw_affiliation_string'] for a in observed.get('affiliations') or []
                      if iid and iid in (a.get('institution_ids') or []) and a.get('raw_affiliation_string')]
            unresolved_raw.difference_update(mapped)
            inst_row = {**row, 'institution_id': icid, 'affiliation_status': 'verified',
                        'affiliation_raw': canonical_json(mapped) if mapped else None}
            inst_rows.append(inst_row)
            ie = audit.evidence(p, sid, f'json:authorships[{index}].institutions[{pos}]', canonical_json(inst))
            if iid:
                audit.alias(p, 'Institution', 'OpenAlex', iid, icid, [ie])
            if rid:
                audit.alias(p, 'Institution', 'ROR', rid, icid, [ie])
            elif inst.get('ror'):
                audit.review(p, 'Institution', icid, 'invalid_ror', 'Malformed/checksum-invalid ROR not linked.', [inst['ror']], [ie])
            audit.node(p, 'Institution', icid, name, sid,
                       {'openalex_id': iid, 'ror': rid, 'country_code': inst.get('country_code')})
        if unresolved_raw or (institutions and not inst_rows):
            audit.review(p, 'Institution', aid, 'affiliation_unresolved',
                         'Raw per-work affiliations could not all be mapped to verified Institution IDs; retained in null row.',
                         [i['id'] for i in institutions if i.get('id')], [ev])
            inst_rows.append({**row, 'affiliation_status': 'needs_review',
                              'affiliation_raw': canonical_json(sorted(unresolved_raw)) if unresolved_raw else row['affiliation_raw']})
        if not inst_rows:
            inst_rows.append({**row, 'affiliation_status': 'missing_in_source'})
        dec = audit.decision(p, 'Author', [aid], [cid], [ev, cvf_ev],
                             'Verified Work, complete ordered CVF byline, unique corroborated Author ID; affiliations from this Work only.', aid)
        for item in inst_rows:
            item['decision_ids'] = [dec['decision_id']]
        # $rows replaces the full logical authorship group, preserving multi-affiliation provenance.
        dec['changes'] = [dict(table='authorships.csv', record_key={'authorship_id': aid},
                               field='$rows', before=[deepcopy(old)], after=deepcopy(inst_rows))]
        new_rows.extend(inst_rows)
    records['authorships.csv'] = new_rows
    records['nodes.csv'] = list(audit.nodes.values())
    # Dedupe evidence/review references, never dedupe people by display name.
    for name in ('evidence.jsonl', 'needs_review.csv'):
        key = contract()['files'][name]['logical_unique_key'][0]
        unique = {}
        for row in records[name]:
            if row[key] in unique and row != unique[row[key]]:
                if name != 'needs_review.csv':
                    raise ValueError('Conflicting evidence ID')
                prior = unique[row[key]]
                prior['evidence_ids'] = sorted(set(prior['evidence_ids'] + row['evidence_ids']))
                prior['candidate_ids'] = sorted(set(prior['candidate_ids'] + row['candidate_ids']))
            else:
                unique[row[key]] = row
        records[name] = list(unique.values())
    for name, rows in records.items():
        validate_records(name, rows)
    return records
