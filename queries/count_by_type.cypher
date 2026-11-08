// Đếm node theo nhãn và cạnh theo loại của project mxh_cv_700 (tiêu chí B3).
// Snapshot B3: 4.126 node, 7.748 cạnh — phải khớp outputs/b_iccv2023/graph/last_import.json.
MATCH (n {project_id: 'mxh_cv_700'})
RETURN 'node' AS kind, labels(n)[0] AS type, count(*) AS count
UNION ALL
MATCH ()-[r {project_id: 'mxh_cv_700'}]->()
RETURN 'edge' AS kind, type(r) AS type, count(*) AS count;
