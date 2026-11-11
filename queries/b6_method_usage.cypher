MATCH (p:Paper {project_id: 'mxh_cv_700'})-[:USES_METHOD]->(m:Method)
RETURN m.name AS method, count(DISTINCT p) AS papers
ORDER BY papers DESC, method;
