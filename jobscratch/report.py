#!/usr/bin/env python3
"""阶段③:可视化 — 读 stats_*.json 生成交互式技能图谱静态 HTML。

数据内嵌 HTML,双击即开,零服务器。ECharts 走 CDN。

设计要点(2026-09-10 重做):
- 图数据在前端构建 → 页面内可切换最低频次、重新布局,无需重跑 Python
- 节点面积 ∝ 频次(而非 symbolSize 线性缩放),比例不再失真
- 边长为窄区间 [90,170] 且高频技能更靠近职业节点,距离比例稳定
- 技能按「主导职业大类」着色,悬停聚焦邻接边;边频次仅悬停显示
"""

import json
import os
import sys
from collections import Counter
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


def graph_summary(stats: dict, min_count: int = 2) -> tuple[int, int]:
    """按 min_count 过滤后返回 (技能节点数, 关联边数)。与前端过滤规则一致。"""
    freq = Counter()
    for s in stats.get("stats", []):
        freq[s["skill"]] += s["count"]
    skills = sum(1 for f in freq.values() if f >= min_count)
    links = sum(1 for s in stats.get("stats", []) if freq[s["skill"]] >= min_count)
    return skills, links


def _format_generated(stats: dict) -> str:
    raw = stats.get("generated_at")
    if not raw:
        return datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(raw)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>技能 × 职业 关系图谱</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
<style>
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0;
    font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
    background: #eef1f6;
    color: #1f2937;
    -webkit-font-smoothing: antialiased;
  }
  .app { height: 100vh; display: flex; flex-direction: column; gap: 14px; padding: 18px 22px 20px; }

  .topbar { display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap; }
  .brand { display: flex; align-items: center; gap: 14px; }
  .logo {
    width: 44px; height: 44px; border-radius: 13px; flex: none;
    background: linear-gradient(135deg, #4C7DF0 0%, #7A5CF0 100%);
    color: #fff; display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 15px; letter-spacing: .5px;
    box-shadow: 0 8px 18px rgba(76, 125, 240, .32);
  }
  .brand h1 { margin: 0; font-size: 19px; font-weight: 650; letter-spacing: .2px; }
  .brand .sub { margin: 3px 0 0; font-size: 12.5px; color: #7b8794; }
  .stats { display: flex; gap: 10px; flex-wrap: wrap; }
  .stat {
    min-width: 88px; padding: 8px 16px; text-align: center;
    background: #fff; border: 1px solid #e6eaf1; border-radius: 13px;
    box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
  }
  .stat b { display: block; font-size: 19px; font-weight: 700; color: #243b6b; font-variant-numeric: tabular-nums; }
  .stat span { font-size: 11.5px; color: #8a94a6; }

  .main { flex: 1; display: flex; gap: 14px; min-height: 0; }
  .card {
    background: #fff; border: 1px solid #e6eaf1; border-radius: 16px;
    box-shadow: 0 10px 30px rgba(23, 43, 77, .06);
  }
  .chart-card { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }

  .toolbar {
    display: flex; align-items: center; justify-content: space-between; gap: 14px;
    padding: 12px 16px; border-bottom: 1px solid #eef1f6; flex-wrap: wrap;
  }
  .legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12.5px; color: #4b5563; }
  .legend .item { display: flex; align-items: center; gap: 6px; }
  .legend .dot { width: 10px; height: 10px; border-radius: 3px; }
  .legend .cnt { color: #9aa4b2; font-size: 11.5px; }
  .actions { display: flex; align-items: center; gap: 12px; font-size: 12.5px; color: #4b5563; }
  .actions label { display: flex; align-items: center; gap: 6px; }
  .zoom-group { display: flex; gap: 6px; }
  .zoom-group button { min-width: 34px; padding: 6px 9px; }
  select, button {
    font: inherit; border-radius: 9px; border: 1px solid #d8dee9; background: #fff;
    padding: 6px 10px; color: #334155; cursor: pointer; outline: none;
  }
  select:focus, button:focus { border-color: #4C7DF0; }
  button.primary {
    background: #4C7DF0; border-color: #4C7DF0; color: #fff;
    box-shadow: 0 4px 10px rgba(76, 125, 240, .3);
  }
  button.primary:hover { background: #3f6fe0; }

  #chart {
    flex: 1; min-height: 0;
    background:
      radial-gradient(circle at 1px 1px, #e4e9f2 1px, transparent 0) 0 0 / 22px 22px,
      linear-gradient(180deg, #fbfcfe 0%, #f3f6fb 100%);
  }

  .side { width: 302px; flex: none; display: flex; flex-direction: column; gap: 10px; padding: 16px; overflow: auto; }
  .side h2 { margin: 6px 0 0; font-size: 14px; font-weight: 650; color: #243b6b; }
  .side h2:first-child { margin-top: 0; }
  .side .hint { margin: 0; font-size: 11.5px; line-height: 1.75; color: #9aa4b2; }
  .bar { padding: 7px 8px; border-radius: 9px; cursor: pointer; transition: background .15s; }
  .bar:hover { background: #f3f7ff; }
  .bar .row { display: flex; align-items: center; gap: 7px; margin-bottom: 5px; }
  .bar .dot { width: 8px; height: 8px; border-radius: 2px; flex: none; }
  .bar .name { font-size: 12.5px; color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar .val { margin-left: auto; font-size: 12px; color: #64748b; font-variant-numeric: tabular-nums; }
  .bar .track { height: 6px; border-radius: 3px; background: #eef1f6; overflow: hidden; }
  .bar .track i { display: block; height: 100%; border-radius: 3px; }

  .fallback {
    display: none; position: fixed; inset: 0; z-index: 99;
    align-items: center; justify-content: center; text-align: center;
    background: rgba(238, 241, 246, .96); color: #b45309; font-size: 14px; line-height: 2;
  }
</style>
</head>
<body>
<div class="app">
  <header class="topbar">
    <div class="brand">
      <div class="logo">JS</div>
      <div>
        <h1>技能 × 职业 关系图谱</h1>
        <p class="sub">BOSS直聘岗位 JD 技能拆解 · 生成于 __GENERATED__</p>
      </div>
    </div>
    <div class="stats">
      <div class="stat"><b>__TOTAL_JOBS__</b><span>岗位</span></div>
      <div class="stat"><b>__TOTAL_CATS__</b><span>职业大类</span></div>
      <div class="stat"><b>__TOTAL_SKILLS__</b><span>技能点</span></div>
      <div class="stat"><b id="statNodes">-</b><span>入图技能</span></div>
    </div>
  </header>

  <main class="main">
    <section class="card chart-card">
      <div class="toolbar">
        <div class="legend" id="legend"></div>
        <div class="actions">
          <label>最低频次 <select id="minCount"></select></label>
          <div class="zoom-group">
            <button id="zoomOut" title="缩小">−</button>
            <button id="zoomIn" title="放大">＋</button>
            <button id="fitView">适应画布</button>
          </div>
          <button class="primary" id="relayout">重新布局</button>
        </div>
      </div>
      <div id="chart"></div>
    </section>

    <aside class="card side">
      <h2>TOP 技能</h2>
      <p class="hint">按全局频次排序 · 点击定位高亮</p>
      <div id="topList"></div>
      <h2>看图说明</h2>
      <p class="hint">
        圆形 = 职业大类,圆角方块 = 技能点<br>
        节点面积 ∝ 出现频次,连线越粗共现越多<br>
        悬停节点可聚焦全部关联<br>
        滚轮缩放 · 拖拽平移(像地图一样看细节)
      </p>
    </aside>
  </main>
</div>
<div class="fallback" id="fallback">
  ECharts CDN 加载失败,图表无法渲染。<br>请联网后刷新页面。
</div>

<script>
const STATS = __STATS_JSON__;
const MIN_COUNT = __MIN_COUNT__;
const PALETTE = ['#4C7DF0', '#12B5A5', '#F2A33C', '#B25DE0', '#E5626E', '#3FA7D6', '#8FBF3F', '#6B7A90'];

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
}

/* ---------- 聚合 ---------- */
const skillFreq = {}, skillByCat = {}, catMentions = {}, catSkills = {}, catRel = {};
(STATS.stats || []).forEach(function (s) {
  skillFreq[s.skill] = (skillFreq[s.skill] || 0) + s.count;
  (skillByCat[s.skill] = skillByCat[s.skill] || {})[s.category] = s.count;
  catMentions[s.category] = (catMentions[s.category] || 0) + s.count;
  catSkills[s.category] = (catSkills[s.category] || 0) + 1;
  catRel[s.category] = (catRel[s.category] || 0) + 1;
});
const cats = (STATS.categories || []).slice().sort(function (a, b) { return catMentions[b] - catMentions[a]; });
const catColor = {};
cats.forEach(function (c, i) { catColor[c] = PALETTE[i % PALETTE.length]; });
const maxCatRel = Math.max.apply(null, cats.map(function (c) { return catRel[c] || 1; }).concat([1]));

/* 面积 ∝ 频次:symbolSize = k * sqrt(freq);职业节点按关联数平方根插值 */
function skillSize(f) { return Math.max(20, Math.round(13 * Math.sqrt(f))); }
function catSize(rel) { return Math.round(42 + 34 * Math.sqrt(Math.max(rel, 1) / maxCatRel)); }
function dominantCat(skill) {
  const m = skillByCat[skill]; let best = '', bv = -1;
  for (const c in m) { if (m[c] > bv) { bv = m[c]; best = c; } }
  return best;
}
function catLabel(name) {
  const i = name.indexOf(' ');
  if (name.length > 7 && i > 0 && i < name.length - 1) return name.slice(0, i) + '\n' + name.slice(i + 1);
  if (name.length > 7) {
    const mid = Math.ceil(name.length / 2);
    return name.slice(0, mid) + '\n' + name.slice(mid);
  }
  return name;
}

/* ---------- 构建节点/边 ---------- */
function buildGraph(minCount) {
  const nodes = [], links = [];
  cats.forEach(function (c) {
    const size = catSize(catRel[c] || 0);
    nodes.push({
      id: 'cat:' + c, name: c, category: c,
      symbol: 'circle', symbolSize: size, value: catMentions[c],
      itemStyle: {
        color: catColor[c], borderColor: '#ffffff', borderWidth: 2.5,
        shadowBlur: 20, shadowColor: hexA(catColor[c], .35)
      },
      label: {
        show: true, position: 'inside', color: '#fff', fontWeight: 600,
        fontSize: size >= 66 ? 14 : 12, lineHeight: 15, formatter: catLabel(c)
      },
      _kind: 'cat', _skills: catSkills[c] || 0, _mentions: catMentions[c] || 0
    });
  });
  Object.keys(skillFreq).forEach(function (t) {
    const f = skillFreq[t];
    if (f < minCount) return;
    const dom = dominantCat(t), size = skillSize(f);
    nodes.push({
      id: 'skill:' + t, name: t, category: dom,
      symbol: 'roundRect', symbolSize: size, value: f,
      itemStyle: {
        color: hexA(catColor[dom], .92), borderColor: '#ffffff', borderWidth: 1.5,
        borderRadius: Math.min(8, size * .22), shadowBlur: 8, shadowColor: 'rgba(23,43,77,.12)'
      },
      label: { show: true, position: 'right', distance: 5, color: '#3f4b5e', fontSize: 11 },
      _kind: 'skill', _byCat: skillByCat[t]
    });
  });
  (STATS.stats || []).forEach(function (s) {
    if ((skillFreq[s.skill] || 0) < minCount) return;
    links.push({
      source: 'cat:' + s.category, target: 'skill:' + s.skill, value: s.count,
      lineStyle: {
        color: hexA(catColor[s.category], .42),
        width: Math.min(8, .8 + 1.5 * Math.sqrt(s.count)),
        curveness: .08
      },
      _catName: s.category, _skillName: s.skill
    });
  });
  return { nodes: nodes, links: links };
}

/* ---------- 图表配置 ---------- */
function baseOption() {
  return {
    tooltip: {
      confine: true,
      backgroundColor: 'rgba(255,255,255,.98)',
      borderColor: '#e2e8f0',
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: '#334155', fontSize: 12.5 },
      extraCssText: 'box-shadow: 0 10px 30px rgba(23,43,77,.14); border-radius: 10px;',
      formatter: function (p) {
        if (p.dataType === 'edge') {
          return '<b>' + p.data._catName + '</b> → <b>' + p.data._skillName + '</b>' +
            '<div style="color:#64748b;margin-top:4px">出现频次 <b style="color:#1e293b">' + p.data.value + '</b></div>';
        }
        const d = p.data;
        if (d._kind === 'cat') {
          return '<div style="font-weight:600">' + d.name + '</div>' +
            '<div style="color:#64748b;margin-top:4px">关联技能 ' + d._skills + ' 个 · 提及 ' + d._mentions + ' 次</div>';
        }
        const rows = Object.keys(d._byCat || {})
          .sort(function (a, b) { return d._byCat[b] - d._byCat[a]; })
          .map(function (c) {
            return '<div style="display:flex;align-items:center;gap:6px;margin-top:3px;min-width:180px">' +
              '<span style="width:8px;height:8px;border-radius:2px;background:' + catColor[c] + '"></span>' +
              '<span style="color:#475569">' + c + '</span>' +
              '<b style="margin-left:auto;color:#1e293b">' + d._byCat[c] + '</b></div>';
          }).join('');
        return '<div style="font-weight:600">' + d.name + '</div>' +
          '<div style="color:#64748b;margin:3px 0 6px">总频次 <b style="color:#1e293b">' + d.value + '</b></div>' + rows;
      }
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      selectedMode: false,
      scaleLimit: { min: .25, max: 8 },
      left: 30, right: 30, top: 24, bottom: 24,
      data: [],
      links: [],
      categories: cats.map(function (c) { return { name: c, itemStyle: { color: catColor[c] } }; }),
      labelLayout: { hideOverlap: true },
      label: { show: true },
      edgeSymbol: ['none', 'none'],
      edgeLabel: {
        show: false, fontSize: 11, color: '#334155',
        backgroundColor: 'rgba(255,255,255,.92)', padding: [2, 6],
        borderRadius: 5, borderColor: '#e2e8f0', borderWidth: 1,
        formatter: function (p) { return p.data.value; }
      },
      lineStyle: { opacity: .75 },
      emphasis: {
        focus: 'adjacency',
        scale: 1.08,
        label: { show: true },
        edgeLabel: { show: true },
        lineStyle: { opacity: 1 }
      },
      blur: {
        itemStyle: { opacity: .18 },
        label: { opacity: .2 },
        edgeLabel: { opacity: 0 },
        lineStyle: { opacity: .06 }
      },
      force: {
        initLayout: 'circular',
        repulsion: [800, 4800],
        edgeLength: [130, 240],
        gravity: .075,
        friction: .6,
        layoutAnimation: true
      }
    }]
  };
}

/* ---------- 页面装配 ---------- */
const fallback = document.getElementById('fallback');
if (typeof echarts === 'undefined') {
  fallback.style.display = 'flex';
} else {
  const chart = echarts.init(document.getElementById('chart'));
  window.__chart = chart;
  let currentNodes = [];
  const measureCtx = document.createElement('canvas').getContext('2d');

  function renderTop(nodes) {
    const skills = nodes.filter(function (n) { return n._kind === 'skill'; })
      .sort(function (a, b) { return b.value - a.value; }).slice(0, 12);
    const max = skills.length ? skills[0].value : 1;
    const box = document.getElementById('topList');
    box.innerHTML = '';
    skills.forEach(function (n) {
      const idx = nodes.indexOf(n);
      const row = document.createElement('div');
      row.className = 'bar';
      row.innerHTML =
        '<div class="row">' +
          '<span class="dot" style="background:' + n.itemStyle.color + '"></span>' +
          '<span class="name">' + n.name + '</span>' +
          '<span class="val">' + n.value + '</span>' +
        '</div>' +
        '<div class="track"><i style="width:' + Math.round(n.value / max * 100) + '%;background:' + n.itemStyle.color + '"></i></div>';
      row.addEventListener('click', function () {
        chart.dispatchAction({ type: 'downplay', seriesIndex: 0 });
        chart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: idx });
        chart.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: idx });
        const sm = chart.getModel().getSeriesByIndex(0);
        const view = sm && sm.coordinateSystem;
        const pos = sm && sm.getData().getItemLayout(idx);
        if (view && pos) {
          const p = view.dataToPoint(pos);
          const rect = view.getBoundingRect();
          chart.dispatchAction({
            type: 'graphRoam', seriesIndex: 0,
            dx: rect.x + rect.width / 2 - p[0],
            dy: rect.y + rect.height / 2 - p[1]
          });
        }
      });
      box.appendChild(row);
    });
  }

  /* 视图控制:像地图一样缩放/平移(graphRoam 只改视图,不触发重新布局) */
  function layoutBBox(seriesModel) {
    const data = seriesModel.getData();
    const n = data.count();
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (let i = 0; i < n; i++) {
      const p = data.getItemLayout(i);
      if (!p || isNaN(p[0]) || isNaN(p[1])) continue;
      let sz = data.getItemVisual(i, 'symbolSize');
      if (sz == null) sz = 10;
      const half = (typeof sz === 'number' ? sz : Math.max(sz[0], sz[1])) / 2;
      let right = half;
      const node = currentNodes[i];
      if (node && node._kind === 'skill') {
        measureCtx.font = '11px "Segoe UI", "Microsoft YaHei", sans-serif';
        right = half + 5 + measureCtx.measureText(node.name).width;
      }
      minX = Math.min(minX, p[0] - half); maxX = Math.max(maxX, p[0] + right);
      minY = Math.min(minY, p[1] - half); maxY = Math.max(maxY, p[1] + half);
    }
    if (!isFinite(minX) || !isFinite(minY)) return null;
    return { minX: minX, maxX: maxX, minY: minY, maxY: maxY };
  }

  function zoomBy(factor) {
    const sm = chart.getModel().getSeriesByIndex(0);
    const view = sm && sm.coordinateSystem;
    if (!view) return;
    const rect = view.getBoundingRect();
    chart.dispatchAction({
      type: 'graphRoam', seriesIndex: 0, zoom: factor,
      originX: rect.x + rect.width / 2, originY: rect.y + rect.height / 2
    });
  }

  function fitView() {
    const sm = chart.getModel().getSeriesByIndex(0);
    const view = sm && sm.coordinateSystem;
    if (!view) return;
    const rect = view.getBoundingRect();
    const bb = layoutBBox(sm);
    if (!bb) return;
    const z0 = view.getZoom() || 1;
    const z1 = Math.min(
      rect.width * .9 / Math.max(bb.maxX - bb.minX, 1),
      rect.height * .9 / Math.max(bb.maxY - bb.minY, 1)
    );
    const bc = [(bb.minX + bb.maxX) / 2, (bb.minY + bb.maxY) / 2];
    const p0 = view.dataToPoint(bc);
    chart.dispatchAction({ type: 'graphRoam', seriesIndex: 0, zoom: z1 / z0, originX: p0[0], originY: p0[1] });
    const p1 = view.dataToPoint(bc);
    chart.dispatchAction({
      type: 'graphRoam', seriesIndex: 0,
      dx: rect.x + rect.width / 2 - p1[0],
      dy: rect.y + rect.height / 2 - p1[1]
    });
  }

  function apply(minCount, fresh) {
    const g = buildGraph(minCount);
    currentNodes = g.nodes;
    if (fresh) chart.clear();
    const opt = baseOption();
    opt.series[0].data = g.nodes;
    opt.series[0].links = g.links;
    chart.setOption(opt);
    renderTop(g.nodes);
    document.getElementById('statNodes').textContent =
      g.nodes.filter(function (n) { return n._kind === 'skill'; }).length;
  }

  const legend = document.getElementById('legend');
  cats.forEach(function (c) {
    const item = document.createElement('span');
    item.className = 'item';
    item.innerHTML = '<span class="dot" style="background:' + catColor[c] + '"></span>' + c +
      '<span class="cnt">' + (catSkills[c] || 0) + ' 技能</span>';
    legend.appendChild(item);
  });

  const sel = document.getElementById('minCount');
  const options = Array.from(new Set([2, 3, 4, 5, 8, 10, 15, MIN_COUNT])).sort(function (a, b) { return a - b; });
  options.forEach(function (v) {
    const o = document.createElement('option');
    o.value = v;
    o.textContent = '≥ ' + v;
    if (v === MIN_COUNT) o.selected = true;
    sel.appendChild(o);
  });
  sel.addEventListener('change', function () { apply(parseInt(sel.value, 10), false); });

  document.getElementById('relayout').addEventListener('click', function () {
    apply(parseInt(sel.value, 10), true);
  });
  document.getElementById('zoomIn').addEventListener('click', function () { zoomBy(1.35); });
  document.getElementById('zoomOut').addEventListener('click', function () { zoomBy(1 / 1.35); });
  document.getElementById('fitView').addEventListener('click', fitView);

  apply(MIN_COUNT, true);
  let resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { chart.resize(); }, 180);
  });
}
</script>
</body>
</html>"""


def render_html(stats: dict, min_count: int = 2) -> str:
    """生成 HTML 页面(数据内嵌 + 前端构建图数据)。"""
    stats_json = json.dumps(stats, ensure_ascii=False).replace("</", "<\\/")
    return (HTML_TEMPLATE
            .replace("__STATS_JSON__", stats_json)
            .replace("__MIN_COUNT__", str(int(min_count)))
            .replace("__GENERATED__", _format_generated(stats))
            .replace("__TOTAL_JOBS__", str(stats.get("total_jobs", 0)))
            .replace("__TOTAL_CATS__", str(len(stats.get("categories", []))))
            .replace("__TOTAL_SKILLS__", str(stats.get("total_skill_terms", 0))))


def save_report(stats: dict, min_count: int = 2, result_dir=DEFAULT_RESULT_DIR) -> str:
    os.makedirs(result_dir, exist_ok=True)
    path = os.path.join(result_dir, "report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html(stats, min_count=min_count))
    return path


def run_report(result_dir=DEFAULT_RESULT_DIR, min_count: int = 2) -> str:
    """阶段③入口:读最新 stats → 生成 report.html。

    min_count: 全局频率低于该值的技能初始不显示(页面内可再调,默认 2)。
    """
    stats = load_latest_stats(result_dir)
    if not stats:
        raise RuntimeError("没有 stats 数据,请先跑 --stats")
    if not stats.get("stats"):
        raise RuntimeError("stats 数据为空,无法生成图表")
    skill_nodes, link_count = graph_summary(stats, min_count)
    path = save_report(stats, min_count=min_count, result_dir=result_dir)
    print(f"✅ 报告已生成: {path} (技能节点 {skill_nodes} 个,关联 {link_count} 条,频次≥{min_count})")
    return path


if __name__ == "__main__":
    run_report()
