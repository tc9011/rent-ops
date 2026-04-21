# rent-ops v0.3 — 空间决策工具升级（Spec）

## 动机

当前 rent-ops 是"房源评估 CLI"：单个工作地、地图只标房源点、POI 只进评分不上图。
对中国家庭 / 情侣 / 合租场景**天然不够**——每个人的生活锚点不同，单工作地评分强行
折叠了这个信息。

## 目标

从"评估工具"升级为"空间决策视觉工具"：
1. **多锚点通勤** — 支持任意数量的锚点（公司/学校/家/合作方/...），每个有权重
2. **POI 图层化** — 超市/餐饮/地铁/医院/菜市场/学校/健身房 可视化，不再只是分数
3. **房源面板重做** — 每锚点通勤表 + 周边 top POI + 风险 signal
4. **多房源对比** — 勾选 2-5 套横向对比

## 非目标

- 多人协同评分（P3，社交功能）
- 多时段通勤（早高峰 vs 平峰，Amap 支持但 API 复杂，P2）
- 爬虫层升级（数据源扩充走 v0.4 roadmap）
- 等时圈精确绘制（Amap Isochrone 是付费 API，用直线距离圆近似）

## 架构

### profile.yml schema 升级

```yaml
# 新（推荐）
anchors:
  - name: 我的公司
    address: "南山区-深圳湾口岸"
    mode: transit              # transit / driving / walking / bicycling
    max_minutes: 30
    importance: 5              # 1-5，通勤分加权用
    icon: 🏢                   # 可选，不填则按 name 推断
  - name: 女朋友公司
    address: "福田-车公庙"
    mode: transit
    max_minutes: 40
    importance: 4
  - name: 父母家
    address: "宝安区-西乡"
    mode: driving
    max_minutes: 60
    importance: 2

# 旧（保留支持，自动迁移）
work_location: "南山区-深圳湾口岸"
```

**向后兼容**：
- 有 `anchors` → 用 anchors
- 无 `anchors` 但有 `work_location` → 自动生成单锚点 `[{name: "工作地", address: work_location, mode: transit, max_minutes: 30, importance: 5}]`
- 两者都有 → anchors 胜，print warning

### anchor.icon 推断规则

按 `name` 包含的关键词分派（不区分大小写）：

| 关键词 | icon |
|--------|------|
| 公司 / 工作 / office / work / 办公室 | 🏢 |
| 学校 / 大学 / 小学 / 幼儿园 / school | 🏫 |
| 家 / 父母 / 老家 / home | 🏠 |
| 医院 / 诊所 / hospital | 🏥 |
| 健身 / gym / 瑜伽 | 💪 |
| 合作 / 客户 / partner | 💼 |
| 商场 / 超市 / shopping | 🛍️ |
| （无匹配） | 📍 |

用户显式写 `icon: 🏢` 覆盖推断。

### 多锚点通勤评分

**算法**：
```
per_anchor_score = 标准映射(duration_min, transfers)   # _shared.md 口径
total_weight = sum(a.importance for a in anchors)
aggregate_score = sum(per_anchor_score * a.importance) / total_weight
                  [rounded to 0.1]
```

若某锚点 API 失败（disabled / empty），该锚点不计入 total_weight。
若全部锚点失败 → 返回 `status: error`，让 agent 走 WebSearch 兜底。

### 近似等时圈半径

不调 Isochrone 付费 API。用步行/公交/骑行/驾车的经验速率：

| mode | 经验速率 (m/min) | 示例：30 分钟半径 |
|------|-----|------|
| walking | 80 | 2.4 km |
| bicycling | 250 | 7.5 km |
| transit | 500（含步行+候车） | 15 km |
| driving | 600（城内拥堵） | 18 km |

圆是直线距离近似，地图上标注 "≈" 前缀 + 透明度低（提示不精确）。

### city-runtime.json 新结构

```json
{
  "schema_version": 2,
  "city": {...},
  "areas": {...},
  "anchors": [
    {
      "name": "我的公司",
      "address": "南山区-深圳湾口岸",
      "mode": "transit",
      "max_minutes": 30,
      "importance": 5,
      "icon": "🏢",
      "pos": null
    }
  ],
  "profile": {...}
}
```

`pos` 字段在 build 时 **不** 预先 geocode（为了保持 build 快，且 Amap key 可能未配）。
map-view.html 启动时用 AMap.Geocoder 客户端 geocode，结果缓存到 sessionStorage。

### scripts/amap_query.py commute 多锚点模式

```bash
# 新（无 --from）：读 profile anchors，多锚点聚合
amap_query.py commute --to "后海花园" --pretty

# 旧（有 --from）：单点 legacy，不变
amap_query.py commute --from "南山区-深圳湾口岸" --to "后海花园" --pretty
```

**新输出**：
```json
{
  "status": "ok",
  "mode": "multi-anchor",
  "destination": "后海花园",
  "anchors": [
    {"name": "我的公司", "mode": "transit", "duration_min": 24.8,
     "transfers": 0, "score_5": 4.0, "importance": 5},
    {"name": "女朋友公司", "mode": "transit", "duration_min": 55.2,
     "transfers": 2, "score_5": 1.5, "importance": 4},
    {"name": "父母家", "mode": "driving", "duration_min": 68.0,
     "score_5": 1.0, "importance": 2}
  ],
  "aggregate_score_5": 2.6
}
```

## map-view.html 结构变化

### 新增 UI 区块

- `#anchors-panel` — 左侧可折叠 drawer，展示所有锚点
- `#poi-toggles` — 顶部第二行 chip 栏，7 个 POI 类别开关
- `#compare-toolbar` — 底部浮动条，"X 套已选 | 对比"
- `#compare-drawer` — 右侧 drawer，对比表
- 房源标记 hover 增加 checkbox

### JS 模块组织（仍单文件但分段）

```
<script>
  // ────── 1. 配置加载 ──────
  let RUNTIME, ANCHORS, POI_LAYERS;

  // ────── 2. 地图初始化 ──────
  function boot() { ... }

  // ────── 3. 锚点渲染（D2）──────
  function renderAnchors() { ... }
  function inferIcon(name) { ... }
  function drawIsochroneCircle(anchor, meters) { ... }

  // ────── 4. 房源标记（不变+checkbox）──────
  function addMarker(l) { ... }

  // ────── 5. POI 图层（D3）──────
  const POI_TYPES = { supermarket: {code:'060200', ...}, ... };
  async function togglePoiLayer(type) { ... }
  async function loadPoisInBbox(type, bbox) { ... }

  // ────── 6. 房源面板（D4）──────
  async function openPanel(l) { ... }
  function renderCommuteTable(l) { ... }
  function renderPoiTable(l) { ... }

  // ────── 7. 对比 drawer（D5）──────
  const selected = new Set();
  function toggleCompareSelect(l) { ... }
  function openCompareDrawer() { ... }
</script>
```

## POI 层的数据源

Amap `/v3/place/around` 按当前 bbox 中心 + 半径调，每次最多 20 条。
对大的可视区域，按 map center 取半径 = bbox 对角线 / 2，page_size 40。

缓存策略：
- Key: `poi:{type}:{bbox_rounded_to_0.01}`
- Value: POI list
- Store: `sessionStorage`
- TTL: 会话级（刷新清空）

## 对比表列

| 列 | 来源 | 排序 | 高亮 |
|---|------|-----|------|
| 小区名 | listing.name | — | — |
| 平台 | listing.platform | — | — |
| 月租 | listing.price | 升序 | 最低绿 / 最高红 |
| 户型 | listing.rooms | — | — |
| 面积 | listing.size | — | — |
| 综合分 | computed | 降序 | 最高绿 / 最低红 |
| 通勤 aggregate | amap commute | 降序 | 同上 |
| 便利 | amap convenience | 降序 | 同上 |
| 风险 | verify | — | RED 红底 / YELLOW 黄底 |

导出：markdown 表格复制到剪贴板。

## 交付切片

| 切片 | 改动 | 预估 | 独立发布 |
|------|------|------|---------|
| D1 | profile schema + build_city_runtime.py + amap_query.py commute | 0.5 天 | ✅ |
| D2 | map 多锚点渲染 + 等时圈 | 1 天 | ✅ |
| D3 | POI 图层 toggle | 1 天 | ✅ |
| D4 | 房源面板重做 | 1 天 | ✅ |
| D5 | 对比 drawer | 1 天 | ✅ |
| 文档+smoke | SKILL.md / README.md / modes 更新 + 整体 smoke | 0.5 天 | - |
| **合计** | ~1000 行增量 | **5 天** | 逐切片 commit |

## 风险

1. **map-view.html 膨胀到 1200+ 行** — 保持单文件但严格分段；考虑后续拆分到多文件（非本次）
2. **Amap POI 配额** — POI layer 会明显多调；bbox 缓存必须做，不然一个会话可能 200+ 次
3. **geocode 客户端延迟** — 锚点页面启动时 geocode 会慢；给"加载中"占位
4. **对比 drawer 混乱** — 超过 5 套对比表就难看，硬限 5 套

## 非侵入性

v0.3 对老用户的影响：
- profile.yml 不改也能工作（auto-migrate）
- amap_query.py 旧 `--from/--to` 用法不变
- auto-evaluate.md 的 agent 调用不变（CLI 返回新字段，旧字段仍在）
