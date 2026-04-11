<p align="center">
  <img src="docs/banner.png" alt="rent-ops banner" width="100%">
</p>

<h1 align="center">rent-ops</h1>
<p align="center">AI 租房助手 — Claude Code Skill</p>
<p align="center">自动爬取各平台房源 · 高德地图可视化 · 八维度智能评分 · 风险预警</p>

---

## 功能

| 命令 | 功能 |
|------|------|
| `/rent {链接}` | 粘贴房源链接，自动评估打分 |
| `/rent scrape` | 爬取豆瓣租房小组 + 小红书房源 |
| `/rent map` | 高德地图可视化所有房源 |
| `/rent scan` | WebSearch 扫描各平台 |
| `/rent risk {小区}` | 搜集社交媒体避雷信息 |
| `/rent visit` | 看房准备（路线 + checklist + 砍价话术） |
| `/rent tracker` | 管理房源跟踪表 |

## 技术栈

- **爬虫**: Playwright + playwright-stealth（豆瓣）、MediaCrawler + xhshow 签名（小红书）
- **反检测**: CDP 接管真实浏览器 / stealth 补丁 / Arc cookie 注入
- **地图**: 高德地图 JS API v2.0 + PlaceSearch 地理编码
- **评估**: 八维度评分体系（性价比/通勤/房况/安全/便利/信誉/风险/灵活性）
- **交互**: Claude Code Skill，纯对话式操作

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/BENZEMA216/rent-ops.git
cd rent-ops

# 2. 安装依赖
pip3 install playwright playwright-stealth
playwright install chromium

# 3. 在 Claude Code 中使用
/rent
```

首次运行会引导你配置城市、预算、户型等租房需求。

## 数据架构

```
data/
├── listings.md          # 房源跟踪表（single source of truth）
├── listings.json        # 结构化数据（地图用）
├── pipeline.md          # 待评估队列
├── map-view.html        # 高德地图可视化
├── douban_raw.jsonl     # 豆瓣原始数据
└── douban_filtered.jsonl # 豆瓣筛选数据

config/
└── profile.yml          # 你的租房需求配置

modes/
├── _shared.md           # 评分规则（系统层）
├── _profile.md          # 个人画像（用户层）
├── auto-evaluate.md     # 自动评估
├── scan.md              # 平台扫描
├── scrape.md            # 专用爬虫
├── map.md               # 地图可视化
├── risk.md              # 风险检测
└── visit.md             # 看房准备
```

## License

MIT
