#!/usr/bin/env python3
"""LLM 编排层(agent) — 把抓到的岗位详情组装成 prompt → 调 LLM → 写技能学习报告。

只依赖配置层(llm_config)和连接层(llm_client),不碰抓取代码。
"""

import os
import re
import json
import glob
from datetime import datetime

from .llm_client import llm_chat
from .llm_config import LLMConfig

DEFAULT_REPORT_DIR = os.path.expanduser("~/.boss-zhipin-scraper/job-result")
DEFAULT_RESULT_DIR = os.path.expanduser("~/.boss-zhipin-scraper/job-result")
JD_MAX_CHARS = 2000  # 单条 JD 截断上限,控制 token


def load_all_details(result_dir=DEFAULT_RESULT_DIR):
    """合并目录下全部 boss_details_*.json,按 job_id 去重。

    详情分散在多次抓取的多个文件里,只读最新一个会漏数据。
    """
    merged = {}
    for path in sorted(glob.glob(os.path.join(result_dir, "boss_details_*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                details = json.load(f)
        except (json.JSONDecodeError, OSError, ValueError) as e:
            print(f"⚠️  跳过详情文件 {os.path.basename(path)}: {e}")
            continue
        if not isinstance(details, list):
            continue
        for d in details:
            merged[d.get("job_id") or id(d)] = d
        print(f"加载详情文件: {os.path.basename(path)} ({len(details)} 条)")
    return list(merged.values())


# ------------------------------------------------------------
# 数据准备
# ------------------------------------------------------------

def _normalize_jd(text):
    """去多余空行/空白,和 jobscratch 的 _normalize_detail_whitespace 同思路。"""
    if not text:
        return ""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate_jd(jd, max_chars=JD_MAX_CHARS):
    """JD 截断:前 max_chars 字 + 提示,够大模型看核心要求即可。"""
    jd = _normalize_jd(jd)
    if len(jd) <= max_chars:
        return jd
    return jd[:max_chars] + f"\n...(已截断,共 {len(jd)} 字)"


def _dedupe_details(details):
    """按 job_id 去重(保留最后一条)。"""
    seen = {}
    for d in details:
        seen[d.get("job_id") or id(d)] = d
    return list(seen.values())


def _enrich_with_jobs(details, jobs):
    """用 jobs 补全 title/company/salary(按 job_id 关联),缺失则用详情自带字段。"""
    by_id = {j.get("job_id"): j for j in (jobs or [])}
    for d in details:
        j = by_id.get(d.get("job_id"))
        if j:
            d.setdefault("title", j.get("title", ""))
            d.setdefault("company", j.get("boss_name", j.get("company", "")))
            d.setdefault("salary", j.get("salary", ""))
    return details


# ------------------------------------------------------------
# Prompt 组装
# ------------------------------------------------------------

SYSTEM_PROMPT = """你是一位资深的技术就业分析师。用户提供一批真实岗位的职位描述(JD)。
请分析这些岗位对技术技能的要求,帮助求职者规划学习方向。

要求:
1. 提炼出这些岗位最需要/最看重的前 N 项技能,按重要性排序
2. 每项技能说明:出现在多少岗位、常见于哪些岗位类型(标题)、薪资水平
3. 指出技能组合(哪些技能经常一起出现,如 LLM+RAG+Agent)
4. 给出学习优先级建议(先学什么、后学什么)

请用 Markdown 输出,结构如下:
## 技能总榜
1. **技能名** - 出现在 X/N 岗位 · 常见薪资区间 - 一句话说明为什么重要
## 技能组合
- 组合 A + B + C:说明
## 学习路径建议
1. 入门:...
2. 进阶:...

只输出 Markdown,不要多余解释。"""


def _format_one_job(d, index):
    return (
        f"---\n"
        f"岗位: {d.get('title', d.get('job_title', '(未知)'))}\n"
        f"公司: {d.get('company', '(未知)')}\n"
        f"薪资: {d.get('salary', '(未标注)')}\n"
        f"要求/技能标签: {'、'.join(d.get('skill_tags', []) or []) or '(无)'}\n"
        f"职位描述:\n{_truncate_jd(d.get('jd', ''))}\n"
    )


def build_skill_analysis_prompt(details, keyword="") -> list[dict]:
    """把岗位详情列表组装成 messages(system + user)。"""
    if not details:
        raise ValueError("没有可分析的岗位详情,请先 --detail 抓取")

    jobs_block = "\n".join(
        _format_one_job(d, i + 1) for i, d in enumerate(details)
    )
    user_prompt = (
        f"岗位领域:{keyword or '未指定'}\n"
        f"共 {len(details)} 条岗位,每条格式:\n"
        f"{jobs_block}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# ------------------------------------------------------------
# 编排入口
# ------------------------------------------------------------

def default_report_path():
    return os.path.join(
        DEFAULT_REPORT_DIR, f"skill_report_{datetime.now():%Y%m%d_%H%M}.md"
    )


def run_llm_skill_analysis(details, jobs=None, keyword="",
                           output_path=None, config=None) -> str:
    """入口:准备数据 → 组装 prompt → 调 LLM → 写报告文件。

    返回报告文件路径。LLM 调用失败时抛异常,由调用方决定是否降级。
    """
    details = _dedupe_details(details or [])
    if jobs:
        details = _enrich_with_jobs(details, jobs)
    if not details:
        raise ValueError("没有可分析的岗位详情,请先 --detail 抓取")

    messages = build_skill_analysis_prompt(details, keyword=keyword)
    cfg = config or LLMConfig()
    report = llm_chat(messages, cfg)

    output_path = output_path or default_report_path()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 技能学习报告\n\n")
        f.write(f"- 数据来源: BOSS直聘抓取\n")
        f.write(f"- 岗位领域: {keyword or '未指定'}\n")
        f.write(f"- 岗位数: {len(details)}\n")
        f.write(f"- 生成时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"- 模型: {cfg.model}\n")
        f.write(f"\n---\n\n")
        f.write(report)

    print(f"✅ 技能报告已生成: {output_path}")
    return output_path


if __name__ == "__main__":
    # 快速自测(需要有详情 JSON,否则抛错提示)
    from .llm_config import LLMConfig  # noqa: F401
    from . import skill_analysis  # noqa: F401
    print("这是编排层模块,请通过 --llm-analyze 或 import 使用")