# jobscratch 设计文档(初稿)

> 状态:草稿 v0.1,基于 boss-zhipin-scraper v2.2.0 二次设计
> 目的:作为 agent 协作练习项目的骨架文档

---

## 1. 目标与边界

### 1.1 项目定位

`jobscratch` 是基于 `boss-zhipin-scraper` 新建的 CLI 工具,核心目的有两个:

1. 复现原项目的核心抓取能力(CDP + Chrome 隔离 + 登录探测 + 列表/详情抓取)
2. 作为 **agent 协作练习** 的项目骨架:把"经验密集型代码"原样搬过来,把"持久化与分析"留作练习场

### 1.2 范围

- 数据源:**仅 BOSS 直聘**(zhipin.com)
- 形态:CLI + 本地 SQLite 持久化
- 用户:个人求职研究,单机使用

### 1.3 非目标

- 不做多源聚合(拉勾/猎聘/LinkedIn)
- 不做长期运行服务 / Web API
- 不做生产级部署、监控、限流熔断
- 不为他人提供抓取服务
- 不替代原项目,不和上游版本同步

---

## 2. 架构总览

### 2.1 分层

```
┌─────────────────────────────────────────┐
│  cli.py          命令行入口、子命令路由     │
└─────────────────────────────────────────┘
            │
   ┌────────┴────────┐
   │                 │
┌──▼──────────┐  ┌───▼──────────┐
│ scraper.py  │  │ analyzer.py  │
│  抓取逻辑    │  │  分析逻辑     │
└─────────────┘  └──────────────┘
   │      │              │
   │      │              │
   │   ┌──▼──────────────▼───┐
   │   │   storage.py       │
   │   │  SQLite 持久化       │
   └───►  入库 / 查询          │
       └──────────────────────┘
              │
       ┌──────▼──────┐
       │  cdp.py     │  ◄── 原样搬
       │  CDP 协议    │
       └─────────────┘
              │
       ┌──────▼──────┐
       │ profile.py  │  ◄── 原样搬
       │ Chrome 隔离  │
       └─────────────┘
              │
       ┌──────▼──────┐
       │  Chrome     │
       │ (用户已登录) │
       └─────────────┘
```

### 2.2 数据流

```
用户启动 --setup-chrome
    → profile.py 准备隔离 profile + 启动 Chrome
    → 登录探测直到 AVAILABLE
    ─────────────────────────
用户启动 --scrape
    → cdp.py 连接 CDP
    → scraper.scrape_list 走 wapi
        → 每页 flush_jobs 到 storage
    → scraper.scrape_details(可选)
        → 每条 upsert 到 storage
    ─────────────────────────
用户启动 --analyze
    → storage 读取 jobs/details
    → analyzer 计算维度
    → CLI 报告 / Markdown 输出
    ─────────────────────────
用户启动 --stop-chrome
    → profile.stop_cdp_chrome 按 user-data-dir 关闭
```

---

## 3. 模块设计

### 3.1 cdp.py(原样搬)

**职责**:CDP 协议封装

**关键 API**:

```python
class CDPSession:
    def __init__(self, cdp_port: int = 9222): ...
    def send(self, method: str, params: dict | None = None,
             sid: str | None = None, timeout: int = 30) -> dict: ...
    def eval_js(self, js: str, sid: str) -> Any: ...
    def close(self) -> None: ...

def create_page_session(cdp: CDPSession, background: bool = True) -> tuple[str, str]:
    """默认后台 + 注入 visibility override。仅 wait_for_login 显式 background=False"""

BACKGROUND_VISIBILITY_SCRIPT = "..."  # Object.defineProperty document.hidden...
```

**不变量**:`send` 必须按 mid 匹配响应,跳过不匹配的事件通知;`recv` 超时分级(WebSocketTimeoutException vs 总超时)。

### 3.2 profile.py(原样搬)

**职责**:Chrome 隔离 profile 生命周期管理

**关键 API**:

```python
def prepare_cdp_profile(copy_login_state: bool = False, reset: bool = False) -> dict: ...
def is_cdp_ready(cdp_port: int) -> bool: ...
def chrome_pids_for_user_data_dir(user_data_dir: str) -> list[int]: ...
def stop_cdp_chrome(cdp_data_dir: str) -> int:
    """SIGTERM → 5s 轮询 → 升级 SIGKILL。绝不按端口/进程名 kill"""
def run_setup_chrome(...) -> int: ...
def run_stop_chrome() -> int: ...
```

**不变量**:`stop_cdp_chrome` 必须按 `--user-data-dir` 精准匹配,绝不能误伤用户主 Chrome(测试见 `test_stop_cdp_chrome_terminates_only_matching_profile`)。

### 3.3 scraper.py(原样搬主体)

**职责**:列表 / 详情抓取 + 登录探测

**关键 API**:

```python
# 列表
def scrape_list(keyword: str, city_input: str, max_pages: int,
                filters: dict, output_path: str | None,
                cdp_port: int = 9222, fmt: str = "json",
                allow_dom_fallback: bool = False) -> dict: ...

# 详情
def scrape_details(list_data: dict, max_details: int | None,
                   output_path: str | None,
                   cdp_port: int = 9222, fmt: str = "json") -> list[dict]: ...

# 登录探测 5 态
class LoginProbeStatus(Enum):
    AVAILABLE = "available"
    UNAUTHENTICATED = "unauthenticated"
    RESTRICTED = "restricted"
    EMPTY = "empty"
    RESPONSE_ERROR = "response_error"

def probe_login_state(cdp, sid, query, city_code) -> LoginProbeResult: ...
def wait_for_login(cdp_port, timeout, interval) -> bool: ...
```

**注入脚本**(作为模块级常量原样搬):
- `FETCH_API_JS_TEMPLATE`:列表 wapi 调用
- `EXTRACT_DETAIL_JS`:详情页提取
- `EXTRACT_LIST_JS`:DOM fallback(默认禁用)
- `DETAIL_LOGIN_MARKER` / `DETAIL_DESCRIPTION_MARKER` / `DETAIL_COMPETITIVENESS_MARKER` / `DETAIL_SAFETY_MARKER`:详情页校验锚点

**校验函数**:
- `extract_detail_fields(extracted, min_length=120)`:三段校验(登录墙 / 导航页 / 太短正文)+ 招聘卡片剥离
- `extract_job_description(extracted)`:简化版,只返回 JD 文本

### 3.4 storage.py(自己设计,练习场 1)

**职责**:SQLite 持久化、增量 upsert、schema 版本

**关键 API**:

```python
class Storage:
    def __init__(self, db_path: str | None = None): ...  # 默认 ~/.jobscratch/data/jobs.db
    def init_schema(self) -> None: ...                    # 应用 migrations
    def create_run(self, keyword, city, city_code, filters) -> int: ...
    def finalize_run(self, run_id, status="completed") -> None: ...
    def upsert_jobs(self, run_id, jobs: list[dict]) -> int: ...
    def upsert_details(self, run_id, details: list[dict]) -> int: ...
    def load_jobs(self, run_id: int | None = None,
                  keyword: str | None = None, since: str | None = None) -> list[dict]: ...
    def load_details(self, job_ids: list[str]) -> list[dict]: ...
    def list_runs(self, limit: int = 20) -> list[dict]: ...
```

**schema 见第 4 节**。

### 3.5 analyzer.py(自己设计,练习场 2)

**职责**:聚合分析

**关键 API**:

```python
def build_summary(jobs: list[dict], details: list[dict] | None = None,
                  search_keyword: str = "", city: str = "", top: int = 10) -> dict: ...

def analyze_salary(jobs) -> dict:        # 分布 + 分位数(阶段 1+)
def analyze_skills(jobs, details) -> dict:  # Counter + 词频
def analyze_trends(runs: list[dict]) -> dict:  # 跨 runs 对比(阶段 2+)
def format_summary(summary: dict) -> str: ...
def build_prompt(summary: dict) -> str: ...
```

**MVP 范围**:仅 `build_summary` + `format_summary` + `build_prompt`(对应原 `job_summary.py`)。

### 3.6 cli.py

**职责**:argparse 路由

**子命令**(沿用原项目命名):
- `--setup-chrome` / `--stop-chrome` / `--check` / `--smoke-test`
- `--list-cities [关键词]`
- `--version`
- 默认子命令:`scrape`(列表 + 详情) → `analyze`(入库即分析)

**关键参数**:`--keyword` `--city` `--pages` `--cdp-port` `--scale` `--stage` `--salary` `--experience` `--degree` `--industry` `--detail / --no-detail` `--max-details` `--copy-login-state` `--reset-chrome-profile` `--no-wait-login` `--login-timeout` `--close-chrome` `--allow-dom-fallback`

---

## 4. 数据模型

### 4.1 SQLite Schema

```sql
-- schema 版本(用于 migrations)
CREATE TABLE schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT,
    applied_at  TEXT NOT NULL
);

-- 每次抓取一个 run(便于跨时间对比)
CREATE TABLE runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword       TEXT    NOT NULL,
    city          TEXT    NOT NULL,
    city_code     TEXT    NOT NULL,
    filters_json  TEXT,             -- JSON
    started_at    TEXT    NOT NULL,
    finished_at   TEXT,
    job_count     INTEGER DEFAULT 0,
    detail_count  INTEGER DEFAULT 0,
    status        TEXT    DEFAULT 'running'  -- running / completed / failed
);

-- 岗位列表(按 job_id 去重,关联到 run)
CREATE TABLE jobs (
    job_id             TEXT PRIMARY KEY,  -- md5(job_link)[:16]
    run_id             INTEGER NOT NULL,
    title              TEXT,
    salary             TEXT,
    salary_source      TEXT,             -- api / api_empty / dom_untrusted
    location           TEXT,
    tags               TEXT,             -- "3-5年 | 本科" 形式
    boss_name          TEXT,
    boss_title         TEXT,
    boss_active_status TEXT,             -- "今日活跃" / "在线"
    company_scale      TEXT,
    company_stage      TEXT,
    company_industry   TEXT,
    skills             TEXT,
    job_labels         TEXT,
    job_link           TEXT NOT NULL,
    company_link       TEXT,
    welfare            TEXT,
    scraped_at         TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- 详情(每个 job_id 唯一,upsert 覆盖)
CREATE TABLE details (
    job_id             TEXT PRIMARY KEY,
    title              TEXT,
    company            TEXT,
    salary             TEXT,
    salary_source      TEXT,
    location           TEXT,
    boss_active_status TEXT,
    tags_list          TEXT,
    skill_tags_json    TEXT,             -- JSON 数组
    jd                 TEXT,
    job_link           TEXT,
    scraped_at         TEXT NOT NULL
);

CREATE INDEX idx_jobs_run_id         ON jobs(run_id);
CREATE INDEX idx_jobs_keyword_city   ON jobs(keyword, city);
CREATE INDEX idx_runs_started_at     ON runs(started_at);
```

### 4.2 增量策略

- **每次 scrape 创建新 run**:同一 (keyword, city) 不合并,保留历史
- **upsert 行为**:`jobs.job_id` 主键冲突时**更新**(覆盖旧值,因为同一 job 在不同时间的 salary/tags 可能变化)
- **跨 runs 查询**:通过 `runs.id` 关联

### 4.3 Schema 版本管理

`schema_version` 表记录已应用的 migration,启动时检查当前版本,自动应用未应用的 migrations(migrations 写在代码里,简单列表即可,不引 alembic)。

---

## 5. 关键流程

### 5.1 首次启动(`--setup-chrome`)

```
prepare_cdp_profile(reset=False)
    → 创建 ~/.jobscratch/chrome-profile/(Default/)
    → 默认不复制主 Chrome 登录态
    ↓
is_cdp_ready(port)?
    ├─ True → 检查端口是否被 scraper profile 占用
    │        ├─ 是 → 复用,直接 wait_for_login
    │        └─ 否 → 报错(端口被其他 Chrome 占用)
    └─ False → stop_cdp_chrome(cdp_data_dir) 关闭旧 scraper Chrome
    ↓
subprocess.Popen([chrome, --remote-debugging-port=9222, --user-data-dir=...])
    ↓
wait_for_cdp(port)  轮询 /json/version 直到 200
    ↓
wait_for_login
    → create_page_session(cdp, background=False)  ← 唯一前台页面
    → Page.navigate https://www.zhipin.com/web/user/
    → 轮询 probe_login_state(轮换 keyword × city_code 三个组合)
    → 直到 AVAILABLE 或 RESTRICTED 或超时
```

### 5.2 抓取主流程

```
cli 解析参数
    ↓
check_login_state(args.cdp_port)
    → AVAILABLE → 继续
    → UNAUTHENTICATED → 提示 --setup-chrome
    → RESTRICTED → 提示风控,停止
    → EMPTY → 警告但继续
    → RESPONSE_ERROR → 停止
    ↓
storage.create_run(keyword, city, city_code, filters) → run_id
    ↓
scrape_list(keyword, city_code, pages, filters, ...)
    → create_page_session(cdp)  ← 默认后台
    → Page.navigate 搜索页(仅第一页)
    → 循环每页:
        → eval_js FETCH_API_JS → 解析 jobs
        → 按 job_link 计算 job_id (md5[:16])
        → storage.upsert_jobs(run_id, jobs)  ← 每页立即入库
        → random.uniform(12, 22) 翻页间隔
    ↓
scrape_details(...)  ← 可选,默认开
    → 每个详情 create_page_session(cdp)  ← 默认后台
    → Page.navigate build_detail_url(job) 带 lid/securityId
    → 模拟滚动 3-7 次
    → eval_js EXTRACT_DETAIL_JS
    → extract_detail_fields(d) 三段校验
    → storage.upsert_details(run_id, details)
    → random.uniform(10, 25) 详情间隔
    ↓
storage.finalize_run(run_id, status="completed")
    ↓
[可选] storage.load_jobs(run_id) + analyzer.build_summary() → 输出报告
```

### 5.3 分析主流程

```
analyze --latest | --run-id N | --since YYYY-MM-DD
    ↓
storage.load_jobs / load_details
    ↓
analyzer.build_summary(jobs, details, keyword, city, top)
    → 薪资区间、经验、学历、地区、公司、技能、JD 高频词
    ↓
format_summary(summary)  → CLI 输出
build_prompt(summary)    → 可复制提示词
```

### 5.4 关闭(`--stop-chrome`)

```
prepare_cdp_profile(copy_login_state=False, reset=False)  ← 只定位,不动 profile
    ↓
stop_cdp_chrome(cdp_data_dir)
    → chrome_pids_for_user_data_dir 找 scraper profile 的 PID
    → SIGTERM 每个 PID
    → 5s 轮询,空了退出
    → 否则 SIGKILL 升级
```

---

## 6. 关键不变量(从原项目继承)

> 这些是经验踩坑沉淀,违反会导致抓取失败、封号风险或误伤主 Chrome。

| # | 不变量 | 来源 | 违反后果 |
|---|--------|------|---------|
| 1 | `create_page_session` 默认 `background=True` + 注入 `BACKGROUND_VISIBILITY_SCRIPT` | 原 issue #18 | `document.hidden=true` 触发 BOSS 反爬,详情页不渲染 |
| 2 | `wait_for_login` 是**唯一**显式 `background=False` 的场景 | 原 wait_for_login | 用户无法在登录页操作 |
| 3 | `stop_cdp_chrome` 按 `--user-data-dir` 精准匹配,绝不按端口/进程名 | 原 stop_cdp_chrome | 误伤用户主 Chrome、Gmail、GitHub |
| 4 | 登录探测 5 态(AVAILABLE/UNAUTHENTICATED/RESTRICTED/EMPTY/RESPONSE_ERROR) | 原 classify_login_probe_response | 错误状态被吞,排查困难 |
| 5 | `code: 31` / `code: 37` + 关键词("环境存在异常"、"访问频繁"等)兜底识别风控 | 原 issue #33 + LOGIN_RESTRICTED_MESSAGE_KEYWORDS | 已登录但被风控被误判为登录失败 |
| 6 | `extract_detail_fields` 三段校验(登录墙 / 导航页 / 太短正文)+ 招聘卡片剥离 | 原 extract_detail_fields | 截断正文、招聘者信息被当 JD 保存 |
| 7 | 列表走 wapi,`--allow-dom-fallback` 默认关 | 原 should_use_dom_fallback | 字体反爬数据污染结果 |
| 8 | 每页 `flush_jobs` 立即持久化 | 原 flush_jobs | 异常退出丢失全部 |
| 9 | `MAX_API_REQUESTS=500` 全局预算,登录探测也算 | 原 incr_request | 触发 BOSS 限流 |
| 10 | 列表 API 返回 `security_id` / `lid` 必须带进详情页 URL | 原 build_detail_url | 详情页触发反爬 |

---

## 7. 依赖与配置

### 7.1 pyproject.toml

```toml
[project]
name = "jobscratch"
version = "0.1.0"
description = "BOSS直聘抓取 + 持久化分析 — 练习项目"
requires-python = ">=3.10"

dependencies = [
    "websocket-client>=1.6.0,<2.0.0",
    "requests>=2.28.0,<3.0.0",
]

[project.optional-dependencies]
analysis = [
    "pandas>=2.0",   # analyzer 阶段 1+ 可选
]

[project.scripts]
jobscratch = "jobscratch.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["jobscratch"]
force-include = { "data/city_codes.json" = "data/city_codes.json" }
```

**MVP 不引 SQLAlchemy**:用标准库 `sqlite3` 裸写,简单可控。阶段 1+ 再考虑。

### 7.2 路径常量

| 常量 | 值 | 说明 |
|------|----|----|
| `DEFAULT_CDP_DATA_DIR` | `~/.jobscratch/chrome-profile/` | 隔离 Chrome profile |
| `DEFAULT_STORAGE_PATH` | `~/.jobscratch/data/jobs.db` | SQLite 数据库 |
| `CITY_DATA_FILENAME` | `city_codes.json` | 城市码表(从原项目拷) |
| `DEFAULT_RESULT_DIR` | `~/.jobscratch/exports/` | 兼容原项目:JSON/CSV 导出 |

### 7.3 CLI 参数

完整列表见第 3.6 节。命名沿用原项目,降低迁移成本。

---

## 8. 测试策略

### 8.1 必须覆盖

沿用原项目 unittest + mock 风格,**无需 Chrome / 网络**。

| 模块 | 测试重点 |
|------|---------|
| cdp | `create_page_session` 默认 background + visibility override;`send` 按 mid 匹配 |
| profile | `stop_cdp_chrome` 按 user-data-dir 匹配;SIGTERM → SIGKILL 升级 |
| scraper | 登录探测 5 态;`code: 31/37` 兜底;`extract_detail_fields` 登录墙/导航页/招聘卡片剥离;JD 太短拒绝 |
| scraper | 城市码表三级查询链(本地 → live → 9 位裸码) |
| storage | upsert 去重;run 创建/结束;schema 迁移 |
| analyzer | `build_summary` 各 Counter;`build_prompt` 模板完整性 |

### 8.2 不必覆盖

| 模块 | 跳过原因 |
|------|---------|
| `human_scroll` 随机参数 | 本身就是随机 |
| `format_summary` 字符串拼接 | 纯展示 |
| Windows PowerShell `ps` 解析 | mock 整个 `subprocess.run` 即可,不必逐字段 |
| `get_default_chrome_path` 路径查找 | 平台分支,集成测试覆盖 |

**估计规模**:MVP 测试 400-600 行,不必追求原项目 1412 行。

---

## 9. 演进路线

### 9.1 MVP(目标:跑通主路径)

- 6 个模块全部可导入,最小可用实现
- storage:sqlite3 裸写 + 基础 upsert + 不引 ORM
- analyzer:仅 `build_summary` + `format_summary` + `build_prompt`
- CLI:`--setup-chrome` / `--scrape` / `--analyze` / `--stop-chrome` / `--check`
- 数据流:`--scrape` → 自动入库 → 立即出摘要
- 测试:必须覆盖的边界(估计 400-600 行)
- AGENTS.md:项目元规则,给未来 agent 的指南

**MVP 验收**:
- `jobscratch --version` 有输出
- `jobscratch --check` 能连真实 Chrome 并探测登录态
- `jobscratch --scrape --keyword AI Agent --city 上海 --pages 2` 能跑通,SQLite 里有数据
- `jobscratch --analyze` 能基于最新 run 输出报告

### 9.2 阶段 1(练习决策点 1-2)

- storage:`schema_version` + 真正 migrations 机制
- analyzer:薪资分位数(25/50/75)
- analyzer:增量分析(对比上次 run 的薪资 / 技能变化)
- CLI:`--analyze --run-id N` / `--analyze --since YYYY-MM-DD`

### 9.3 阶段 2(练习决策点 3-4)

- analyzer:跨多 runs 趋势分析
- analyzer:技能提取引入 jieba 分词 + 简单聚类
- 报告导出:Markdown / HTML

### 9.4 阶段 3+(可选,不做也行)

- 抓取配置化(关键词/城市持久化,不用每次传参)
- 调度器(定时抓)
- 简单 Web UI(Flask / FastAPI)
- 多关键词批量抓取

---

## 10. 风险与合规

### 10.1 反爬风险

- BOSS 可能更新 wapi 路径 → `API_JOB_LIST_PATH` 常量集中管理,改一处生效
- 字体反爬可能升级 → DOM fallback 路径保留但默认禁用
- 风控码可能新增 → `LOGIN_RESTRICTED_CODES` + `LOGIN_RESTRICTED_MESSAGE_KEYWORDS` 兜底识别
- 详情页可能加 CAPTCHA → `extract_detail_fields` 失败时报错退出,不写脏数据

### 10.2 登录态风险

- 依赖用户本人已登录的 Chrome,封号责任在用户
- 绝不批量注册、切换账号、自动化登录
- 登录态探测算入 500 预算,避免被识别为探测攻击

### 10.3 数据准确度

- API 优先(salary_source=api),DOM fallback 标 `dom_untrusted`
- 详情 JD 必须过三段校验,登录墙/导航页/太短正文拒绝写入
- 招聘者卡片、竞争力分析、安全提示碎句**不写入 JD**

### 10.4 合规边界

- 仅个人求职研究,符合原 boss-zhipin-scraper CONTRIBUTING 合规章节
- 单次限额:`MAX_PAGES=10`, `MAX_API_REQUESTS=500`
- 翻页间隔 12-22s,详情间隔 10-25s(随机化)

### 10.5 已知技术债

- city_codes.json 来自原项目,可能滞后于 BOSS 实时码表 → 运行时 fallback 拉 BOSS `cityGroup.json` 自愈(沿用 `load_live_city_maps`)
- Windows 平台代码分支已保留但未实测 → 文档标注"未实测"

---

## 附录 A:文件结构(目标态)

```
D:\agent\jobscratch\
├── AGENTS.md
├── README.md
├── pyproject.toml
├── requirements.txt
├── data/
│   └── city_codes.json                 ← 从原项目拷
├── src/                                ← 或 jobscratch/ 直接放根
│   └── jobscratch/
│       ├── __init__.py
│       ├── cdp.py                      ← 原样搬自 boss_cdp_raw.py
│       ├── profile.py                  ← 原样搬
│       ├── scraper.py                  ← 原样搬(列表/详情/登录探测)
│       ├── storage.py                  ← 自己设计(MVP 重点)
│       ├── analyzer.py                 ← 自己设计(MVP 重点)
│       └── cli.py                      ← argparse 路由
├── tests/
│   ├── test_cdp.py
│   ├── test_profile.py
│   ├── test_scraper.py
│   ├── test_storage.py
│   └── test_analyzer.py
└── doc/
    └── design.md                       ← 本文档
```

## 附录 B:开放问题(留给迭代时讨论)

1. SQLite schema 是否要加 `tags_json` 字段,把 `tags` 拆成结构化数组?(目前用 `" | "` 字符串拼接)
2. `runs` 表是否需要 `config_json` 字段记录本次抓取的完整 CLI 参数?(便于复现)
3. analyzer 的"趋势对比"具体维度:薪资中位数变化?新增技能?消失技能?
4. Markdown 报告的模板:固定?还是 analyzer 输出 JSON + 单独 template?
5. 是否需要 `--watch` 子命令监听 SQLite 变化实时分析?(阶段 3+)