MATCH (a:Paper {project_id: 'mxh_cv_700'})-[:CITES]->(b:Paper)
RETURN a.conference AS citing_conference, b.conference AS cited_conference, count(*) AS citations
ORDER BY citing_conference, cited_conference;
