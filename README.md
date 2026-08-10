# jobscratch

BOSS直聘职位抓取 + 分析工具，基于 Chrome DevTools Protocol (CDP) 复用真实浏览器登录态。

## 功能

- 按关键词 + 城市搜索职位
- 筛选：公司规模、融资阶段、薪资、经验、学历、行业
- 抓取列表 + 详情 JD
- 输出 JSON / CSV
- 模拟人类行为（滚动、停顿）绕过 BOSS 风控

## 用法

```powershell
# 1. 首次：启动专用 Chrome 并登录 BOSS
uv run python jobscratch/jobscratch.py --setup-chrome

# 2. 抓取列表 + 详情
uv run python jobscratch/jobscratch.py --keyword "AI Agent" --city 上海 --pages 3

# 3. 只抓详情（基于已有列表 JSON）
uv run python jobscratch/jobscratch.py --input <列表文件.json> --detail
```

## 数据输出

`~/.boss-zhipin-scraper/job-result/`

## 注意事项

- 必须先在专用 Chrome 中登录 zhipin.com
- 控制抓取频率，避免风控

## 致谢

本项目参考自 [eatmoreduck/boss-zhipin-scraper](https://github.com/eatmoreduck/boss-zhipin-scraper)，感谢作者在 CDP / Chrome 隔离 / 登录探测等经验密集型设计上的分享。
