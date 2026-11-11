MATCH (p:Paper {project_id: 'mxh_cv_700'})-[s:STUDIES_TASK]->(t:Task {project_id: 'mxh_cv_700', id: 'task:object-detection'})
OPTIONAL MATCH (p)-[:USES_METHOD]->(m:Method)
RETURN p.name AS title, p.conference AS conference, s.evidence_ids AS evidence_ids, collect(DISTINCT m.name) AS methods
ORDER BY title;
