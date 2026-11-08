"""Import the isolated ICCV 2023 B pilot into its dedicated local Neo4j instance."""
import json
import os
from pathlib import Path
import re


URI = 'bolt://127.0.0.1:17687'
DATABASE = 'neo4j'
PILOT = 'B-ICCV2023-pilot'
DATA = Path(__file__).resolve().parents[2] / 'data/raw/iccv2023/pilot_papers.json'


def validate_target(uri, database):
    if uri != URI or database != DATABASE:
        raise ValueError('Only the dedicated local B pilot instance is permitted')


def validate_papers(papers):
    if not isinstance(papers, list) or not papers:
        raise ValueError('Expected a nonempty array of papers')
    ids = set()
    for paper in papers:
        if not isinstance(paper, dict):
            raise ValueError('Each paper must be an object')
        paper_id = paper.get('paper_id')
        match = re.fullmatch(r'cvf:ICCV2023:([A-Za-z0-9_-]+)', paper_id or '') if isinstance(paper_id, str) else None
        if (not match or paper_id in ids or
                paper.get('cvf_url') != f'https://openaccess.thecvf.com/content/ICCV2023/html/{match.group(1)}_paper.html' or
                paper.get('conference') != 'ICCV' or type(paper.get('conference_year')) is not int or
                paper['conference_year'] != 2023 or paper.get('owner') != 'B' or
                not isinstance(paper.get('title'), str) or not paper['title'].strip() or
                not isinstance(paper.get('authors'), list) or not paper['authors'] or
                any(not isinstance(a, str) or not a.strip() for a in paper['authors'])):
            raise ValueError(f'Invalid or duplicate ICCV B paper: {paper_id!r}')
        ids.add(paper_id)
    return papers


def import_papers(tx, papers):
    tx.run('''
        MERGE (v:VenueEdition {id: 'ICCV:2023:main'})
        SET v.name = 'ICCV', v.year = 2023, v.track = 'main',
            v.owner = 'B', v.source_origin = 'CVF', v.pilot = $pilot
        WITH v
        UNWIND $papers AS row
        MERGE (p:Paper {id: row.paper_id})
        SET p.title = row.title, p.authors = row.authors, p.cvf_url = row.cvf_url,
            p.year = 2023, p.conference_year = 2023, p.scope = 'core', p.owner = 'B',
            p.source_origin = 'CVF', p.pilot = $pilot
        MERGE (p)-[r:PUBLISHED_IN]->(v)
        SET r.owner = 'B', r.source_origin = 'CVF', r.evidence_url = row.cvf_url, r.evidence_ids = [row.cvf_url], r.pilot = $pilot
    ''', papers=papers, pilot=PILOT).consume()


def main():
    uri = os.environ.get('NEO4J_URI', '')
    database = os.environ.get('NEO4J_DATABASE', DATABASE)
    validate_target(uri, database)
    papers = validate_papers(json.loads(DATA.read_text(encoding='utf-8')))
    if len(papers) != 30:
        raise ValueError('The B pilot must contain exactly 30 papers')
    user = os.environ.get('NEO4J_USER')
    password = os.environ.get('NEO4J_PASSWORD')
    if not user or not password:
        raise ValueError('NEO4J_USER and NEO4J_PASSWORD are required')
    from neo4j import GraphDatabase
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database=database) as session:
            foreign = session.run('MATCH (n) WHERE n.pilot IS NULL OR n.pilot <> $pilot RETURN count(n) AS count', pilot=PILOT).single()['count']
            if foreign:
                raise ValueError('Target contains nodes outside this pilot')
            session.run('CREATE CONSTRAINT b_pilot_paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE').consume()
            session.run('CREATE CONSTRAINT b_pilot_venue_id IF NOT EXISTS FOR (v:VenueEdition) REQUIRE v.id IS UNIQUE').consume()
            session.execute_write(import_papers, papers)
            record = session.run('''
                MATCH (p:Paper {pilot: $pilot})-[r:PUBLISHED_IN {pilot: $pilot}]->(v:VenueEdition {pilot: $pilot})
                RETURN count(DISTINCT p) AS papers, count(r) AS publications, count(DISTINCT v) AS editions
            ''', pilot=PILOT).single()
            print(dict(record))


if __name__ == '__main__':
    main()
