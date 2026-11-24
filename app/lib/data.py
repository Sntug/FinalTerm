import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
QUERIES = ROOT / "queries"

TABLES = {
    "communities": "outputs/trend/sna/communities.csv",
    "pagerank_author": "outputs/trend/sna/pagerank_author.csv",
    "pagerank_institution": "outputs/trend/sna/pagerank_institution.csv",
    "kcore": "outputs/trend/sna/kcore.csv",
    "group_ranking": "outputs/trend/sna/group_ranking.csv",
    "topic_share": "outputs/trend/metrics/topic_share.csv",
    "topic_change": "outputs/trend/metrics/topic_change.csv",
    "emerging": "outputs/trend/metrics/emerging.csv",
    "venue_gap_2025": "outputs/trend/metrics/venue_gap_2025.csv",
    "comparability": "outputs/trend/metrics/comparability.csv",
    "topic_leaders": "outputs/trend/metrics/topic_leaders.csv",
    "similar_topics": "outputs/trend/embed/similar_topics.csv",
    "topic_umap": "outputs/trend/embed/topic_umap.csv",
}


def table_path(name):
    if name not in TABLES:
        raise KeyError(f"Unknown table '{name}'. Known: {', '.join(sorted(TABLES))}")
    return ROOT / TABLES[name]


def query_path(name):
    if not isinstance(name, str) or not name.replace("_", "").isalnum():
        raise ValueError(f"Invalid query name '{name}': use letters, digits and underscores only")
    return QUERIES / f"{name}.cypher"


@st.cache_data(show_spinner=False)
def _read_csv(path, mtime):
    return pd.read_csv(path)


def load_table(name):
    path = table_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Table '{name}' is not available yet: {path.relative_to(ROOT)} does not exist")
    return _read_csv(str(path), path.stat().st_mtime)


@st.cache_resource
def _driver():
    sys.path.insert(0, str(ROOT / "src/graph"))
    from load_neo4j import credentials
    from neo4j import GraphDatabase

    uri, user, password = credentials()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
    except Exception as exc:
        driver.close()
        raise ConnectionError(f"Neo4j is not reachable at {uri} ({exc}). Start the database and retry.") from exc
    return driver


def run_cypher(name, **params):
    text = query_path(name).read_text(encoding="utf-8")
    with _driver().session(database="neo4j") as session:
        return session.execute_read(lambda tx: [dict(r) for r in tx.run(text, **params)])
