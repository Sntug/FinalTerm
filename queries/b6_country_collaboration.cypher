MATCH (a:Institution {project_id: 'mxh_cv_700'})-[r:COLLABORATED_WITH]->(b:Institution)
MATCH (a)-[:BASED_IN]->(ca:Country)
MATCH (b)-[:BASED_IN]->(cb:Country)
WHERE ca <> cb
WITH CASE WHEN ca.country_code < cb.country_code THEN ca.country_code ELSE cb.country_code END AS country_1,
     CASE WHEN ca.country_code < cb.country_code THEN cb.country_code ELSE ca.country_code END AS country_2,
     r.paper_ids AS paper_ids
UNWIND paper_ids AS paper_id
RETURN country_1, country_2, count(DISTINCT paper_id) AS distinct_papers
ORDER BY distinct_papers DESC, country_1, country_2
LIMIT 15;
