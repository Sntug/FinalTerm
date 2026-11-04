# ICCV 2023 B pilot graph

This is a provisional, isolated B-only import. It uses the 30 CVF records in `data/raw/iccv2023/pilot_papers.json`, preserving their provisional CVF IDs. It creates `Paper` and one main-track `VenueEdition`, connected by `PUBLISHED_IN`; each relationship records the CVF evidence URL, also used as a directly resolvable provisional evidence ID. The paper records conference year separately from publication date, which is not asserted. Author names remain ordered paper properties pending identity resolution. This is not the agreed shared schema or the 700-paper graph. The provisional B-only registry and matching evidence records are `data/processed/b_iccv2023_pilot_registry.csv` and `data/processed/b_iccv2023_pilot_evidence.jsonl`; blank DOI means unverified. Evidence points to CVF pages, not a locally captured page or independently verified field. See the raw source manifest for the incomplete candidate pool and source-access limitations. Replace provisional IDs and reconcile these records when the shared contract is agreed.

Use a dedicated Neo4j instance at `bolt://127.0.0.1:17687`, database `neo4j`, with the Neo4j Python driver 5.x installed in a virtual environment. Set `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` in the environment without committing credentials, then from the project root run:

```sh
python src/graph/b_pilot.py
python src/graph/b_pilot.py
```

Both runs should print 30 papers, 30 publications and one edition. The loader rejects other targets, malformed or duplicate records and pre-existing non-pilot nodes; it never clears the database. It creates uniqueness constraints and merges the data in one write transaction. Do not point the dedicated port at a shared database. Changing the input set does not delete old pilot records; start a fresh isolated instance for a different snapshot.

For review, run in the isolated database:

```cypher
MATCH (n) RETURN labels(n) AS labels, count(*) AS count;
MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count;
MATCH (p:Paper)-[r:PUBLISHED_IN]->(v:VenueEdition)
RETURN p.id, p.title, r.evidence_url, v.id ORDER BY p.id LIMIT 5;
```

Run the local validation checks with `python -m unittest discover -s src/graph -p 'test_b_pilot.py'`.
