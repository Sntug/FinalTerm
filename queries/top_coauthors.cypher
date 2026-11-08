// Top 20 cặp đồng tác giả (COAUTHORED_WITH, vô hướng) theo số bài core chung.
MATCH (a:Author {project_id: 'mxh_cv_700'})-[r:COAUTHORED_WITH]->(b:Author)
RETURN a.name AS author_1, b.name AS author_2, r.weight AS shared_papers, r.paper_ids AS paper_ids
ORDER BY shared_papers DESC, author_1, author_2
LIMIT 20;
