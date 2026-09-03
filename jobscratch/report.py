#!/usr/bin/env python3
"""阶段③:可视化 — 读 stats_*.json 生成 ECharts 力导向图静态 HTML。

数据内嵌 HTML,双击即开,零服务器。ECharts 走 CDN。
"""

import json
import os
import sys
from datetime import datetime

DEFAULT_RESULT_DIR = os.path.expanduser("~/.boss-zhipin-scraper/job-result")

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def load_latest_stats(result_dir=DEFAULT_RESULT_DIR):
    files = sorted(os.path.join(result_dir, f) for f in os.listdir(result_dir)
                   if f.startswith("stats_") and f.endswith(".json"))
    if not files:
        return None
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def build_graph_data(stats: dict, min_count: int = 2) -> dict:
    """把 stats 转成力导向图 nodes + links。

    - 节点大小 ∝ 全局频率(该技能在所有职业中的出现次数总和)
    - 低频噪音(全局频率 < min_count)直接过滤,图更清爽
    """
    from collections import Counter

    # 全局频率:每个技能在所有职业的 count 之和
    skill_freq = Counter()
    for s in stats.get("stats", []):
        skill_freq[s["skill"]] += s["count"]
    cat_jobs = Counter()  # 每个职业关联的岗位数(由 stats 统计阶段算,这里用关系数近似)

    nodes, links = [], []
    cat_relation = Counter()
    for s in stats.get("stats", []):
        cat_relation[s["category"]] += 1

    # 职业节点:圆形,固定大小(突出技能频率差异,职业本身不缩放)
    for c in stats.get("categories", []):
        n = cat_relation.get(c, 0)
        nodes.append({
            "id": f"cat:{c}", "name": c, "category": "职业", "value": n,
            "symbol": "circle",
            "symbolSize": 60,
        })

    # 技能节点:方形,大小 ∝ 全局频率(拉开差距)
    for t, freq in skill_freq.items():
        if freq < min_count:
            continue
        nodes.append({
            "id": f"skill:{t}", "name": t, "category": "技能", "value": freq,
            "symbol": "rect",
            "symbolSize": 14 + freq * 9,
        })

    node_ids = {n["id"] for n in nodes}
    for s in stats.get("stats", []):
        src, tgt = f"cat:{s['category']}", f"skill:{s['skill']}"
        if src in node_ids and tgt in node_ids:
            links.append({
                "source": src, "target": tgt, "value": s["count"],
                "label": {"show": True},
            })
    return {"nodes": nodes, "links": links}


def render_html(stats: dict, graph: dict) -> str:
    """生成 HTML 页面(数据内嵌 + ECharts 力导向图)。"""
    nodes_json = json.dumps(graph["nodes"], ensure_ascii=False)
    links_json = json.dumps(graph["links"], ensure_ascii=False)
    total_jobs = stats.get("total_jobs", 0)
    generated = stats.get("generated_at", datetime.now().isoformat())

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>技能-职业关系图</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  body {{ margin: 0; font-family: "Microsoft YaHei", sans-serif; background: #f7f8fa; }}
  #header {{ padding: 16px 24px; background: #fff; border-bottom: 1px solid #e5e6eb; }}
  #header h1 {{ margin: 0 0 6px; font-size: 20px; }}
  #header .meta {{ color: #86909c; font-size: 13px; }}
  #chart {{ width: 100%; height: calc(100vh - 110px); }}
  #legend {{ padding: 8px 24px; font-size: 13px; color: #4e5969; }}
  #legend span {{ margin-right: 16px; }}
  #legend .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; }}
</style>
</head>
<body>
<div id="header">
  <h1>技能点 × 职业 关系图</h1>
  <div class="meta">
    共 {total_jobs} 个岗位 · {len(stats.get("categories", []))} 个职业大类 ·
    {stats.get("total_skill_terms", 0)} 个技能点 · {len(graph["links"])} 条关联 ·
    生成时间 {generated}
  </div>
</div>
<div id="legend">
  <span><span class="dot" style="background:#5470c6"></span>职业大类(圆形)</span>
  <span><span class="dot" style="background:#91cc75"></span>技能点(方形)</span>
  <span>连线粗细 = 出现频次,悬停查看详情,滚轮缩放</span>
</div>
<div id="chart"></div>
<script>
const GRAPH = {{
  nodes: {nodes_json},
  links: {links_json},
}};
const chart = echarts.init(document.getElementById('chart'));
const option = {{
  tooltip: {{
    formatter: function (p) {{
      if (p.dataType === 'edge') {{
        const s = GRAPH.nodes.find(n => n.id === p.data.source);
        const t = GRAPH.nodes.find(n => n.id === p.data.target);
        return `${{s.name}} → ${{t.name}}<br/>出现频次: ${{p.data.value}}`;
      }}
      return p.data.name + ' (频次 ' + p.data.value + ')';
    }}
  }},
  series: [{{
    type: 'graph',
    layout: 'force',
    roam: true,
    draggable: true,
    data: GRAPH.nodes,
    links: GRAPH.links,
    categories: [
      {{ name: '职业', itemStyle: {{ color: '#5470c6' }} }},
      {{ name: '技能', itemStyle: {{ color: '#91cc75' }} }},
    ],
    label: {{
      show: true,
      fontSize: function (d) {{ return d.symbolSize > 40 ? 14 : 11; }},
      color: '#333',
    }},
    force: {{
      repulsion: 260,
      edgeLength: [40, 260],
      gravity: 0.08,
      friction: 0.6,
    }},
    edgeSymbol: ['none', 'arrow'],
    edgeLabel: {{
      show: true,
      fontSize: 10,
      color: '#666',
    }},
    lineStyle: {{
      color: 'source',
      curveness: 0.1,
      opacity: 0.7,
      width: function (e) {{ return Math.max(1, Math.min(e.value * 2, 10)); }},
    }},
  }}],
}};
chart.setOption(option);
window.addEventListener('resize', () => chart.resize());
</script>
</body>
</html>"""


def save_report(stats: dict, graph: dict, result_dir=DEFAULT_RESULT_DIR) -> str:
    os.makedirs(result_dir, exist_ok=True)
    path = os.path.join(result_dir, "report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html(stats, graph))
    return path


def run_report(result_dir=DEFAULT_RESULT_DIR, min_count: int = 2) -> str:
    """阶段③入口:读最新 stats → 生成 report.html。

    min_count: 全局频率低于该值的低频技能不显示(默认 2,过滤噪音)。
    """
    stats = load_latest_stats(result_dir)
    if not stats:
        raise RuntimeError("没有 stats 数据,请先跑 --stats")
    graph = build_graph_data(stats, min_count=min_count)
    if not graph["nodes"]:
        raise RuntimeError("stats 数据为空,无法生成图表")
    path = save_report(stats, graph, result_dir)
    print(f"✅ 报告已生成: {path} (技能节点 {len([n for n in graph['nodes'] if n['category']=='技能'])} 个,过滤频率<{min_count})")
    return path


if __name__ == "__main__":
    run_report()