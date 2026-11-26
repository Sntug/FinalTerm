CALL () {
  MATCH (p:Paper {project_id: $project_id})
  WHERE $venue_edition IS NULL OR p.conference + toString(p.conference_year) = $venue_edition
  RETURN count(p) AS n_total_papers
}
CALL () {
  UNWIND $author_ids AS author_id
  MATCH (:Author {project_id: $project_id, id: author_id})-[:AUTHORED]->(p:Paper {project_id: $project_id})
  WHERE $venue_edition IS NULL OR p.conference + toString(p.conference_year) = $venue_edition
  RETURN collect(DISTINCT p) AS group_papers
}
OPTIONAL MATCH (core:Author {project_id: $project_id, id: $core_author_id})
WITH n_total_papers, core, size(group_papers) AS n_group_papers,
     [p IN group_papers WHERE trim(coalesce(p.abstract, '')) <> ''] AS text_papers
CALL (text_papers) {
  UNWIND text_papers AS p
  MATCH (p)-[r:STUDIES_TASK|USES_METHOD|EVALUATED_ON]->(t)
  WITH CASE type(r) WHEN 'STUDIES_TASK' THEN 'Task' WHEN 'USES_METHOD' THEN 'Method' ELSE 'Dataset' END AS kind, t, p, r
  ORDER BY p.id
  WITH kind, t, collect({paper_id: p.id, title: p.name, venue_edition: p.conference + toString(p.conference_year),
                         cvf_url: p.cvf_url, evidence_ids: r.evidence_ids}) AS papers
  ORDER BY size(papers) DESC, t.id
  WITH kind, collect({kind: kind, id: t.id, name: t.name, papers: papers})[0..$limit] AS ranked
  UNWIND ranked AS topic
  RETURN collect(topic) AS topics
}
UNWIND CASE WHEN size(topics) = 0 THEN [null] ELSE topics END AS topic
RETURN topic.kind AS topic_type,
       topic.id AS topic_id,
       topic.name AS topic_name,
       size(coalesce(topic.papers, [])) AS n_topic_papers,
       size(text_papers) AS n_group_text_papers,
       n_group_papers,
       n_total_papers,
       core.id AS core_author_id,
       core.name AS core_author_name,
       coalesce(topic.papers, []) AS source_papers
ORDER BY topic_type, n_topic_papers DESC, topic_id
