MATCH (:Paper {project_id: 'mxh_cv_700'})-[c:CITES]->(p:Paper)
RETURN p.name AS title, p.conference AS conference, count(c) AS cited_by_core
ORDER BY cited_by_core DESC, title
LIMIT 15;
