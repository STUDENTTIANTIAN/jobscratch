#!/usr/bin/env python3
"""Agent 层(LangGraph) — 阶段①:JD 技能描述拆解。

分工:LLM 干判断(拆解/归类),统计与渲染交给确定性代码(不进图)。
图结构(阶段①):
    START → collect(读详情数据)
          → decompose(LLM: 每条 JD 拆技能点)
          → END
"""

import json
import os
import re
import sys
import glob
from datetime import datetime
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from .llm_client import llm_chat
from .llm_config import LLMConfig

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

DEFAULT_RESULT_DIR = os.path.expanduser("~/.boss-zhipin-scraper/job-result")
JD_MAX_CHARS = 3000  # 单条 JD 送入 LLM 的截断上限


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

class AgentState(TypedDict):
    keyword: str
    details: list[dict]        # 原始详情(job_id/title/jd)
    skills: list[dict]         # 拆解结果 [{job_id, title, skills: [{term, importance, evidence}]}]
    categories: list[dict]     # 归类结果 [{title, category}]
    failed: list[dict]         # 失败条目(供重试/报告)


# ------------------------------------------------------------
# 拆解 Prompt(防望文生义铁律)
# ------------------------------------------------------------

DECOMPOSE_SYSTEM_PROMPT = """你是职位技能拆解器。任务:从职位描述(JD)中提取技能要求。

铁律:
1. 只提取 JD 中明确出现的技能,禁止联想或补充 JD 里没有的内容;JD 无技能就返回空数组,不硬凑
2. 术语原样保留:技术名词/缩写/框架名必须一字不改(RAG 就是 RAG,禁止翻译成"检索增强生成";LangChain 就是 LangChain)
3. 不翻译、不解释、不猜测缩写含义;不确定含义的术语保留原文
4. 岗位主题词不是技能:岗位标题里的核心词(如岗位是"AI Agent 开发",则"AI Agent"/"Agent"不算技能)不得提取
5. 每个技能必须附 evidence:从 JD 中摘录包含该技能的原始句子(最多 60 字)
6. importance 取值:core(硬性/核心要求) / required(明确要求) / plus(加分项/偏好)
7. 输出纯 JSON 数组,不要 markdown 代码块包裹,不要任何多余文字

输出格式:
[{"term": "技能术语原文", "importance": "core|required|plus", "evidence": "原句摘录"}]"""


def build_decompose_messages(detail: dict) -> list[dict]:
    """组装单条 JD 的拆解 messages。"""
    jd = detail.get("jd", "")
    if len(jd) > JD_MAX_CHARS:
        jd = jd[:JD_MAX_CHARS] + f"\n...(已截断,共 {len(jd)} 字)"
    user_prompt = (
        f"岗位标题: {detail.get('title', '(未知)')}\n"
        f"职位描述:\n{jd}"
    )
    return [
        {"role": "system", "content": DECOMPOSE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _parse_skills_response(text: str) -> list[dict]:
    """解析 LLM 返回,容错:剥 markdown 代码块,非法 JSON 抛 ValueError。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"返回不是 JSON 数组: {text[:200]}")
    for item in data:
        if not isinstance(item, dict) or not item.get("term"):
            raise ValueError(f"条目缺少 term: {item}")
    return data


def decompose_one_job(detail: dict, config: LLMConfig = None,
                      retries: int = 2, timeout: int = 90) -> list[dict]:
    """拆解单条 JD,返回技能点列表(term/importance/evidence)。

    失败自动重试 retries 次;LLM 超时/解析失败抛最后一次异常。
    """
    cfg = config or LLMConfig()
    messages = build_decompose_messages(detail)
    last_error = None
    for attempt in range(1 + retries):
        try:
            text = llm_chat(messages, cfg, timeout=timeout)
            return _parse_skills_response(text)
        except Exception as e:
            last_error = e
            if attempt < retries:
                print(f"   ⚠️ 第 {attempt + 1} 次失败({e}),重试中...", flush=True)
    raise last_error


# ------------------------------------------------------------
# 归类 Prompt
# ------------------------------------------------------------

CATEGORIZE_SYSTEM_PROMPT = """你是职位归类器。任务:把一批岗位标题归类成少数几个"职业大类"。

规则:
1. 语义相近的岗位必须归到同一大类(如"AI Agent 开发实习生"和"AI Agent应用开发工程师"都归"AI Agent 开发")
2. 大类数量控制在 4-8 个,名称简短(4-8 字)
3. 每个 title 必须归类,不能跳过
4. 输出纯 JSON 数组,不要 markdown 代码块,不要多余文字

输出格式:
[{"title": "原始岗位标题(一字不改)", "category": "职业大类"}]"""


def build_categorize_messages(titles: list[str]) -> list[dict]:
    user_prompt = "请归类以下岗位标题:\n" + "\n".join(f"- {t}" for t in titles)
    return [
        {"role": "system", "content": CATEGORIZE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _parse_categories_response(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"返回不是 JSON 数组: {text[:200]}")
    for item in data:
        if not isinstance(item, dict) or not item.get("title") or not item.get("category"):
            raise ValueError(f"条目缺少 title/category: {item}")
    return data


def categorize_titles(titles: list[str], config: LLMConfig = None,
                      retries: int = 2, timeout: int = 90) -> list[dict]:
    """LLM 把全部 title 归类成职业大类,返回 [{title, category}]。"""
    cfg = config or LLMConfig()
    messages = build_categorize_messages(titles)
    last_error = None
    for attempt in range(1 + retries):
        try:
            text = llm_chat(messages, cfg, timeout=timeout)
            return _parse_categories_response(text)
        except Exception as e:
            last_error = e
            if attempt < retries:
                print(f"   ⚠️ 归类第 {attempt + 1} 次失败({e}),重试中...", flush=True)
    raise last_error


# ------------------------------------------------------------
# LangGraph 节点
# ------------------------------------------------------------

def collect_details(state: AgentState) -> AgentState:
    """Node: 从 state 读取 details,数据已在 main() 里加载。"""
    print(f"📥 待拆解岗位: {len(state['details'])} 条", flush=True)
    return state


def _save_partial(keyword: str, skills: list[dict], failed: list[dict],
                  result_dir=DEFAULT_RESULT_DIR) -> str:
    """把当前进度覆写到固定路径 skills_partial.json(断点续传用)。"""
    os.makedirs(result_dir, exist_ok=True)
    path = os.path.join(result_dir, "skills_partial.json")
    payload = {
        "keyword": keyword,
        "updated_at": datetime.now().isoformat(),
        "total": len(skills),
        "failed": failed,
        "skills": skills,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def load_partial_skills(result_dir=DEFAULT_RESULT_DIR):
    """读取断点续传文件,返回 (skills, failed) 或 (None, None)。"""
    path = os.path.join(result_dir, "skills_partial.json")
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("skills", []), data.get("failed", [])
    except (json.JSONDecodeError, OSError, ValueError):
        return None, None


def decompose_jobs(state: AgentState) -> AgentState:
    """Node: 逐条 JD 调 LLM 拆解,单条失败跳过并记录。

    边拆边落盘(skills_partial.json);重跑时跳过已成功的 job_id,续传失败条目。
    """
    cfg = LLMConfig()
    done_ids = {s.get("job_id") for s in state.get("skills", [])}
    skills = list(state.get("skills", []))
    failed = list(state.get("failed", []))
    total = len(state["details"])
    for i, detail in enumerate(state["details"], 1):
        title = detail.get("title", "(未知)")
        job_id = detail.get("job_id", "")
        if job_id in done_ids:
            print(f"⏭️  [{i}/{total}] 跳过(已拆解): {title}", flush=True)
            continue
        print(f"🔍 [{i}/{total}] 拆解: {title}", flush=True)
        try:
            items = decompose_one_job(detail, cfg)
            skills.append({
                "job_id": job_id,
                "title": title,
                "skills": items,
            })
            failed = [f for f in failed if f.get("job_id") != job_id]
            print(f"   ✅ 提取 {len(items)} 个技能点", flush=True)
        except Exception as e:
            failed.append({"job_id": job_id, "title": title, "error": str(e)})
            print(f"   ❌ 失败: {e}", flush=True)
        _save_partial(state.get("keyword", ""), skills, failed)
    return {"skills": skills, "failed": failed}


def categorize_jobs(state: AgentState) -> AgentState:
    """Node: LLM 把全部去重 title 归类成职业大类。"""
    titles = sorted({s.get("title", "") for s in state.get("skills", [])})
    titles = [t for t in titles if t]
    if not titles:
        return {"categories": []}
    print(f"🏷️  归类 {len(titles)} 个岗位标题...", flush=True)
    try:
        categories = categorize_titles(titles)
        print(f"   ✅ 归类完成,{len({c['category'] for c in categories})} 个大类", flush=True)
        return {"categories": categories}
    except Exception as e:
        print(f"   ❌ 归类失败: {e}", flush=True)
        return {"categories": []}


def build_agent():
    """构建 LangGraph(阶段①:collect → decompose;阶段②:→ categorize)。"""
    g = StateGraph(AgentState)
    g.add_node("collect", collect_details)
    g.add_node("decompose", decompose_jobs)
    g.add_node("categorize", categorize_jobs)
    g.add_edge(START, "collect")
    g.add_edge("collect", "decompose")
    g.add_edge("decompose", "categorize")
    g.add_edge("categorize", END)
    return g.compile()


# ------------------------------------------------------------
# 落盘
# ------------------------------------------------------------

def save_skills(skills: list[dict], failed: list[dict], keyword: str,
                result_dir=DEFAULT_RESULT_DIR) -> str:
    """拆解结果落盘 skills_*.json,返回路径。"""
    os.makedirs(result_dir, exist_ok=True)
    path = os.path.join(result_dir, f"skills_{datetime.now():%Y%m%d_%H%M}.json")
    payload = {
        "keyword": keyword,
        "generated_at": datetime.now().isoformat(),
        "total": len(skills),
        "failed": failed,
        "skills": skills,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"✅ 拆解结果已落盘: {path} (成功 {len(skills)} / 失败 {len(failed)})")
    return path


def save_categories(categories: list[dict], keyword: str,
                    result_dir=DEFAULT_RESULT_DIR) -> str:
    """归类结果落盘 categories_*.json,返回路径。"""
    os.makedirs(result_dir, exist_ok=True)
    path = os.path.join(result_dir, f"categories_{datetime.now():%Y%m%d_%H%M}.json")
    payload = {
        "keyword": keyword,
        "generated_at": datetime.now().isoformat(),
        "categories": categories,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"✅ 归类结果已落盘: {path}")
    return path


def load_latest_categories(result_dir=DEFAULT_RESULT_DIR):
    """读取最新 categories_*.json,返回 [{title, category}] 或 []。"""
    files = sorted(glob.glob(os.path.join(result_dir, "categories_*.json")))
    if not files:
        return []
    try:
        with open(files[-1], encoding="utf-8") as f:
            data = json.load(f)
        return data.get("categories", [])
    except (json.JSONDecodeError, OSError, ValueError):
        return []


def run_categorize(skills: list[dict], keyword: str = "") -> str:
    """阶段②入口:基于拆解结果跑 title 归类并落盘。返回 categories 文件路径。"""
    graph = build_agent()
    result = graph.invoke({
        "keyword": keyword,
        "details": [],
        "skills": skills or [],
        "failed": [],
    })
    categories = result.get("categories") or []
    if not categories:
        raise RuntimeError("归类结果为空(LLM 归类失败或 skills 为空)")
    return save_categories(categories, keyword)


def run_decompose(details: list[dict], keyword: str = "") -> str:
    """阶段①入口:跑 LangGraph 拆解并落盘。返回 skills 文件路径。

    自动续传:已有 skills_partial.json 时跳过已成功的 job_id,只补失败/未拆条目。
    """
    prev_skills, prev_failed = load_partial_skills()
    graph = build_agent()
    result = graph.invoke({
        "keyword": keyword,
        "details": details or [],
        "skills": prev_skills or [],
        "failed": prev_failed or [],
    })
    skills = result.get("skills") or []
    if not skills:
        raise RuntimeError("拆解结果为空(可能详情数据为空或全部失败)")
    return save_skills(skills, result.get("failed", []), keyword)


if __name__ == "__main__":
    print("Agent 层模块,请通过 --decompose 或 import 使用")