import streamlit.components.v1 as components
from pyvis.network import Network

from .theme import THEME

CLICK_JS = (
    "<script>network.on('click',function(p){if(p.nodes.length){"
    "var n=nodes.get(p.nodes[0]);if(n&&n.href){window.open(n.href,'_blank');}}});</script>"
)


def _props(obj):
    return dict(obj.items())


def _collect(value, nodes, edges):
    if isinstance(value, (list, tuple)):
        for v in value:
            _collect(v, nodes, edges)
    elif hasattr(value, "relationships") and hasattr(value, "nodes"):
        _collect(list(value.nodes), nodes, edges)
        _collect(list(value.relationships), nodes, edges)
    elif hasattr(value, "start_node") and hasattr(value, "end_node"):
        _collect([value.start_node, value.end_node], nodes, edges)
        edges.append((value.start_node.element_id, value.end_node.element_id, value.type))
    elif hasattr(value, "labels") and hasattr(value, "element_id"):
        p = _props(value)
        label = next(iter(sorted(value.labels)), "")
        nodes.setdefault(value.element_id, dict(p, label=label, name=p.get("name", p.get("id", value.element_id))))
    elif isinstance(value, dict):
        if "source" in value and "target" in value:
            edges.append((value["source"], value["target"], value.get("type", "")))
        elif "id" in value:
            nodes.setdefault(value["id"], dict(value, label=value.get("label", (value.get("labels") or [""])[0])))
        else:
            _collect(list(value.values()), nodes, edges)


def build_network(records, height=600):
    nodes, edges = {}, []
    _collect(list(records), nodes, edges)
    net = Network(height=f"{height - 20}px", width="100%", directed=True, cdn_resources="in_line", bgcolor="#FFFFFF")
    for nid, n in nodes.items():
        label = n["label"]
        url = n.get("cvf_url") or n.get("url")
        title = "\n".join([f"{label}: {n['name']}"] + [f"{k}: {v}" for k, v in n.items() if k in ("id", "year", "doi", "cvf_url", "url") and v])
        kw = {"href": url} if label == "Paper" and url else {}
        net.add_node(nid, label=str(n["name"])[:40], title=title, color=THEME["label_colors"].get(label, THEME["default_node_color"]), **kw)
    for s, t, ty in dict.fromkeys(edges):
        if s in nodes and t in nodes:
            net.add_edge(s, t, label=ty, title=ty, color=THEME["edge_color"], arrows="to")
    return net


def subgraph_html(records, height=600):
    return build_network(records, height).generate_html().replace("</body>", CLICK_JS + "</body>")


def render_subgraph(records, height=600):
    components.html(subgraph_html(records, height), height=height, scrolling=False)
