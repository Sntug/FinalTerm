MATCH (a:Institution {project_id: 'mxh_cv_700'})-[r:COLLABORATED_WITH]->(b:Institution)
MATCH (a)-[:BASED_IN]->(ca:Country)
MATCH (b)-[:BASED_IN]->(cb:Country)
WHERE ca <> cb
RETURN ca.country_code AS country_1, cb.country_code AS country_2, sum(r.weight) AS institution_pair_weight
ORDER BY institution_pair_weight DESC, country_1, country_2
LIMIT 15;
