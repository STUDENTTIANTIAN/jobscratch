# 思路记录

> 状态:活跃思考,每次大决策前更新
> 目的:把"为什么这么做"沉淀下来,避免后面忘了初衷

---

## 项目目标

用 boss-zhipin-scraper 的核心抓取能力作为骨架,搭建一个 **agent 协作练习项目**。

**重点是 agent 练习,不是生产级工具。**

---

## 第一性原则(从 AGENTS.md 引申)

- 时间有限
- 跑通优先于完美
- 遇到 bug 不深究
- 接受"丑但能用"的代码
- 不为生产标准写文档/测试
- 不追求分层、解耦、设计模式

---

## MVP-0 思路

**目标**:5 分钟做出"最小可跑通版本",让 agent 立刻有代码可练习。

### 步骤

1. **建包结构**
   - `jobscratch/__init__.py`(空)
   - `jobscratch/jobscratch.py`(拷自 boss_cdp_raw.py,改名)

2. **改版本号**:`__version__ = "0.1.0"`

3. **写 `pyproject.toml`** —— 极简,只有依赖 + entry point
   ```toml
   [project]
   name = "jobscratch"
   version = "0.1.0"
   requires-python = ">=3.10"
   dependencies = [
       "websocket-client>=1.6.0,<2.0.0",
       "requests>=2.28.0,<3.0.0",
   ]
   [project.scripts]
   jobscratch = "jobscratch.jobscratch:main"
   ```

4. **验证**:`python -m jobscratch.jobscratch --version` 输出 `jobscratch 0.1.0`

### 不做什么(MVP-0 阶段)

- ❌ 分层(cdp.py / profile.py / scraper.py 拆文件)—— 单文件就够
- ❌ SQLite 持久化 —— 先用 JSON 落盘(原项目方式)
- ❌ 单元测试 —— 暂不写(写测试不会让 agent 跑得更快)
- ❌ city_codes.json 迁移 —— 暂不拷
- ❌ README / CHANGELOG —— 暂不写
- ❌ 设计文档落地 —— design.md 是参考,不是行动清单

### 为什么这样设计

- **单文件**:让 agent 看一眼懂整体结构,改一行就生效,不跨文件跳转
- **JSON 落盘**:和原项目一致,迁移成本最低,后续要 SQLite 时再加
- **不写测试**:违反"跑通优先"原则,真要写也只覆盖关键不变量

---

## 演进路径(避免后续大改)

```
MVP-0       → MVP-1       → MVP-2         → 阶段 1        → 阶段 2
单文件        + .venv         + 城市码表       + SQLite          + 分析层
跑通 --version 验证依赖     支持中文城市     持久化入数据库    趋势/技能
```

每阶段独立,**完成前一个再进下一个**。任何阶段觉得"该停了"就停,不要硬推。

---

## 关键决策记录

| # | 决策 | 选择 | 不选 | 理由 |
|---|---|---|---|---|
| 1 | 项目位置 | 新建 D:\agent\jobscratch | fork boss-zhipin-scraper | "agent 练习" 需要决策空间,fork 改的话练习价值低 |
| 2 | 抓取层处理 | 原样搬 | 重写 | CDP/Chrome 隔离/登录探测是经验密集型,白嫖 |
| 3 | 数据持久化 | JSON(MVP) → SQLite(阶段 1) | 直接 SQLite | MVP 跑通优先,JSON 零依赖 |
| 4 | 代码组织 | 单文件(MVP) → 分层(阶段 1+) | 一开始就分层 | 单文件适合 agent 练习,后续真有需要再拆 |
| 5 | 虚拟环境 | uv venv(B 方案) | 全局 Python / uv sync | 隔离干净,30 秒搞定,uv 自动管 Python |
| 6 | Python 版本 | 3.12.13(uv 管理) | 系统 3.10.9 | uv 自动下载,版本新,`>=3.10` 满足 |
| 7 | 依赖 | requests + websocket-client | + pandas/sqlalchemy | MVP 不需要,后面再引 |
| 8 | 包名/模块名 | 都叫 `jobscratch` | `jobscratch/cli.py` | 减少目录层级,适合练习 |

---

## 边界提醒(防止我(或 agent)越界)

- **不要**为了"看起来更专业"去加 README badge、CI 配置、type hints 100% 覆盖
- **不要**在 MVP 阶段做 SQLite 迁移
- **不要**写超过 200 行的测试
- **不要**重构拷过来的代码 —— 它能跑就让它跑
- **不要**讨论"未来可能需要 X 功能" —— 真需要时再说

如果发现自己(或 agent)在做上面任何一件事,**先停下来,问"这有助于 agent 练习吗?"** 如果答案是否,放弃。