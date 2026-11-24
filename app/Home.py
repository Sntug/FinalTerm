import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import THEME, apply_theme, run_cypher
from lib.data import ROOT

apply_theme()
st.title(f"{THEME['icon']} {THEME['title']}")
st.write("Xu hướng nghiên cứu Computer Vision từ đồ thị CVPR/ICCV: chủ đề nào tăng, giảm, mới nổi; nhóm nào đang làm gì; ai nghiên cứu chủ đề nào.")

st.subheader("Snapshot")
check = ROOT / "outputs/trend/snapshot_check.json"
if check.exists():
    info = json.loads(check.read_text(encoding="utf-8"))
    st.write({k: info[k] for k in ("snapshot_id", "content_hash") if k in info} or "snapshot_check.json không có snapshot_id")
else:
    st.info("Chưa có outputs/trend/snapshot_check.json (H8 chưa khóa).")
try:
    rows = run_cypher("count_by_type")
    st.success("Neo4j: kết nối được")
    st.dataframe(rows, hide_index=True)
except Exception as exc:
    st.warning(f"Neo4j không khả dụng: {exc}")

st.subheader("Trang")
pages = sorted((Path(__file__).parent / "pages").glob("*.py"))
for p in pages:
    st.page_link(f"pages/{p.name}", label=p.stem.split("_", 1)[-1].replace("_", " "))
if not pages:
    st.caption("Chưa có trang nào.")
