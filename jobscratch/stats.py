#!/usr/bin/env python3
"""阶段②:频率统计(确定性代码,不进 LangGraph)。

输入:skills_*.json(拆解结果) + categories_*.json(title → 职业大类)
输出:stats_*.json(职业 × 技能 × 频次)
"""

import json
import os
import re
from collections import Counter
from datetime import datetime

DEFAULT_RESULT_DIR = os.path.expanduser("~/.boss-zhipin-scraper/job-result")

# 噪音词:非技能、来自 BOSS 页面 UI 的词,统计时过滤
NOISE_TERMS = {"直聘", "BOSS", "boss", "BOSS直聘", "微信扫码", "举报", "职位描述", "任职要求"}


def _normalize(text: str) -> str:
    """去空白/分隔符并小写,用于标题核心词比对。"""
    return re.sub(r"[\s\-/()（）·,，、]+", "", text or "").lower()


def is_title_theme_term(term: str, title: str) -> bool:
    """判断 term 是否为岗位标题的主题词(如 title 含"AI Agent",则"AI Agent"不算技能)。"""
    t, tt = _normalize(term), _normalize(title)
    return bool(t) and len(t) >= 2 and t in tt


def load_latest_skills(result_dir=DEFAULT_RESULT_DIR):
    """读取最新 skills_*.json,返回 skills 列表 + payload。"""
    files = sorted(os.path.join(result_dir, f) for f in os.listdir(result_dir)
                   if f.startswith("skills_") and f.endswith(".json"))
    if not files:
        return [], {}
    with open(files[-1], encoding="utf-8") as f:
        data = json.load(f)
    return data.get("skills", []), data


def load_latest_categories(result_dir=DEFAULT_RESULT_DIR):
    """读取最新 categories_*.json,返回 {title: category}。"""
    files = sorted(os.path.join(result_dir, f) for f in os.listdir(result_dir)
                   if f.startswith("categories_") and f.endswith(".json"))
    if not files:
        return {}
    with open(files[-1], encoding="utf-8") as f:
        data = json.load(f)
    return {c["title"]: c["category"] for c in data.get("categories", [])}


def is_noise_term(term: str) -> bool:
    return term in NOISE_TERMS or len(term.strip()) < 2


def compute_stats(skills: list[dict], category_map: dict) -> dict:
    """统计 职业大类 × 技能点 频次。同一条 JD 内重复技能只计 1 次。"""
    counter = Counter()
    for item in skills:
        category = category_map.get(item.get("title", ""), "未归类")
        title = item.get("title", "")
        seen = set()
        for s in item.get("skills", []):
            term = (s.get("term") or "").strip()
            if not term or is_noise_term(term) or term in seen:
                continue
            if is_title_theme_term(term, title):
                continue  # 岗位标题主题词(如 AI Agent)不是技能
            seen.add(term)
            counter[(category, term)] += 1

    stats = [{"category": c, "skill": t, "count": n}
             for (c, t), n in sorted(counter.items(), key=lambda kv: -kv[1])]

    skill_total = Counter()
    for (c, t), n in counter.items():
        skill_total[t] += n

    return {
        "categories": sorted({c for c, _ in counter}),
        "skills": sorted(skill_total, key=lambda t: -skill_total[t]),
        "stats": stats,
        "total_jobs": len(skills),
        "total_skill_terms": len(skill_total),
    }


def save_stats(payload: dict, result_dir=DEFAULT_RESULT_DIR) -> str:
    os.makedirs(result_dir, exist_ok=True)
    path = os.path.join(result_dir, f"stats_{datetime.now():%Y%m%d_%H%M}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"✅ 统计结果已落盘: {path}")
    return path


def run_stats(result_dir=DEFAULT_RESULT_DIR) -> str:
    """阶段②入口:读最新 skills + categories → 统计 → 落盘 stats_*.json。"""
    skills, _ = load_latest_skills(result_dir)
    category_map = load_latest_categories(result_dir)
    if not skills:
        raise RuntimeError("没有 skills 数据,请先跑 --decompose")
    if not category_map:
        raise RuntimeError("没有 categories 数据,请先跑 --categorize")

    result = compute_stats(skills, category_map)
    payload = {
        "generated_at": datetime.now().isoformat(),
        **result,
    }
    path = save_stats(payload, result_dir)
    print(f"📊 职业大类 {len(result['categories'])} 个,技能点 {result['total_skill_terms']} 个,共 {len(result['stats'])} 条关系")
    return path


if __name__ == "__main__":
    run_stats()