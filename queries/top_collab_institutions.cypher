// Top 20 cặp tổ chức hợp tác (COLLABORATED_WITH, vô hướng) theo số bài core chung.
MATCH (a:Institution {project_id: 'mxh_cv_700'})-[r:COLLABORATED_WITH]->(b:Institution)
RETURN a.name AS institution_1, b.name AS institution_2, r.weight AS shared_papers, r.paper_ids AS paper_ids
ORDER BY shared_papers DESC, institution_1, institution_2
LIMIT 20;
