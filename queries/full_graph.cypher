// Hiện toàn bộ graph mxh_cv_700 (4.126 node, 7.748 cạnh với snapshot B3).
// OPTIONAL MATCH để giữ cả node không có cạnh ra.
// Neo4j Browser: Settings → Visualization node limit ≥ 5000, Record limit ≥ 10000 (mặc định 1000 sẽ cắt bớt).
MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m;
