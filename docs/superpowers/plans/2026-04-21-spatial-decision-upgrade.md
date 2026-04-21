# rent-ops v0.3 空间决策工具升级 — 执行 Plan

Spec: [docs/superpowers/specs/2026-04-21-spatial-decision-design.md](../specs/2026-04-21-spatial-decision-design.md)

5 个切片 D1-D5，每片独立可 commit。

---

## D1: anchors schema + runtime builder + 多锚点 commute CLI (0.5 天)

### 任务

1. **`config/profile.example.yml`**: 新 schema 示例（anchors 数组），注释说明向后兼容
2. **`config/profile.yml`**（用户本地，gitignored）: 迁移当前 `work_location: "南山区-深圳湾口岸"` 为单锚点
3. **`scripts/build_city_runtime.py`**: 
   - 新增 `_build_anchors(profile)` 函数：读 anchors 数组 或 从 work_location 迁移
   - 推断 icon（见 spec）
   - 输出 `anchors: []` 到 city-runtime.json
   - `schema_version` 升 2
4. **`scripts/amap_query.py` commute 模式**:
   - `--to "X"` + 无 `--from` + profile 有 anchors → 多锚点聚合模式
   - 循环每个锚点调 route_transit/driving/walking/bicycling
   - 按 importance 加权聚合
   - 输出 spec 里定义的 JSON
5. **`modes/_shared.md`**: 通勤评分小节加一段"多锚点加权"说明
6. **`modes/auto-evaluate.md`**: 通勤步骤里补一句"支持多锚点，分数为加权聚合"

### 验收
- `python3 scripts/amap_query.py commute --to "后海花园" --pretty` 输出含 anchors 数组 + aggregate_score_5
- `python3 scripts/build_city_runtime.py` 输出 city-runtime.json 有 `anchors: []`
- 旧 profile 只有 work_location 也能正常工作（print deprecation warning）

---

## D2: map 多锚点可视化 (1 天)

### 任务

改 `data/map-view.html`：

1. **JS**: 
   - 移除 `WORK` 全局，改 `ANCHORS: []` 全局
   - 启动时 `resolveAnchors()`：遍历 RUNTIME.anchors → Geocoder 解析坐标（或用 address 里的 lat,lng 如果有）
   - `renderAnchors()`：每锚点一个 Marker，内容 `<div class="anchor-wrap"><div class="anchor-icon">{icon}</div></div>`，颜色按 importance 深浅
   - `drawIsochroneCircle(anchor)`：AMap.Circle，半径按 mode × max_minutes 换算，fill 同色 opacity=0.08
2. **CSS**:
   - `.anchor-wrap` / `.anchor-icon`：圆形白底，icon 居中
   - Importance 5 边框 3px，1 边框 1px
3. **Legend**:
   - 按 anchors 动态生成（不再硬编码"工作地"）
4. **Panel 距离显示**:
   - 占位符，D4 做完整的

### 验收
- 打开地图：每个锚点一个带 icon 的标记
- 每锚点一个透明色圆（等时圈近似）
- Legend 显示每个锚点名
- 点房源：面板只显示"多锚点评估待 D4"占位

---

## D3: POI 图层切换 (1 天)

### 任务

1. **HTML**:
   - 顶部第二行 `#poi-toggles` — 7 个 chip
2. **JS**:
   - `POI_TYPES = { supermarket: {code:'060200', color:'#34a853', icon:'🛒'}, ... }`
   - `togglePoiLayer(type)`: 按钮 active/inactive 切换
   - `loadPoisInBbox(type, bbox)`: 读 sessionStorage 缓存；miss 时调 `AMap.PlaceSearch({city, types, pageSize:40})` with current map center + radius
   - 渲染：每个 POI 一个小 AMap.Marker，颜色按类型
   - `map.on('moveend')`: 若有 active POI 层，reload
3. **CSS**:
   - `.poi-dot`: 6x6 圆点 + 类型色
4. **缓存**:
   - Key: `poi:{type}:${Math.round(bbox)}` 到 0.01 度
   - TTL: sessionStorage，关闭 tab 就清

### 验收
- 点"超市"chip → 地图上出现超市小点
- 拖动地图 → 新区域的超市加载
- 再点一下关闭 → 小点消失
- 同样区域再开 → 瞬返（缓存命中）

---

## D4: 房源面板大改 (1 天)

### 任务

改 `openPanel(l)` 函数。新结构：

```
┌──────────────────────────────┐
│ 平台 badge + 推荐             │
│ ───────────────────────────── │
│ 小区名（大）                 │
│ 月租（巨大） + 综合 X.X/5     │
│ 户型 面积 地铁 tags          │
│ ───────────────────────────── │
│ 通勤                         │
│ ▪ 🏢 我的公司   transit 18m ⭐5│
│ ▪ 🏫 女友公司   transit 35m ⭐3│
│ ▪ 🏠 父母家     driving 45m ⭐4│
│ → 加权 4.2                   │
│ ───────────────────────────── │
│ 周边 500m                    │
│ 🛒 超市    5 家  最近 120m   │
│ 🚇 地铁    14 个 最近 197m   │
│ 🍜 餐饮    20+  最近 24m    │
│ 🏥 医院    0                 │
│ ───────────────────────────── │
│ 风险                         │
│ ⚠️ 1 YELLOW  发帖人 3 城市    │
│ ───────────────────────────── │
│ [原帖 →]  [对比 +]           │
└──────────────────────────────┘
```

### 实现

1. 点房源时异步调用:
   - `amap_query.py commute --to {l.name}`（单 fetch HTTP 到本地 Python？）→ **否**，在 map-view.html 里用 AMap JS API 直接调，省掉本地 Python 依赖
   - 循环 anchors，每个算一条路径（AMap.Driving / Transit / Walking / Riding）
   - 并行等 Promise.all
2. POI 表：读当前 POI layer 结果 filter by 距离 < 500m 的
3. 风险：如果 listing 有 `verify` 字段（后续爬虫结果带），展示

### 验收
- 点房源 → 面板弹出，500ms 内加载完所有 anchor 通勤（并行）
- 加权分正确
- 切到不同锚点 profile 后刷新 → 新面板对应新锚点

---

## D5: 多房源对比 drawer (1 天)

### 任务

1. **勾选**:
   - 每个 marker 右上角小 checkbox（点击独立 event，不触发 openPanel）
   - 状态存 `selected: Set<l.key>` where `l.key = l.url || l.name+l.price`
2. **Toolbar**:
   - 底部浮动：`N 套已选 [对比] [清空]`
   - N=0 时隐藏
3. **Drawer**:
   - 右侧 slide-in 宽 600px
   - 表格按 spec 定义列
   - 每列 min/max 高亮
   - Footer 按钮：`[复制 markdown] [关闭]`
4. **Markdown 导出**:
   - 标准 GFM 表格

### 验收
- 勾选 3 套 → toolbar 显示 "3 套已选"
- 点对比 → drawer 弹出
- 表格每列分数最优行背景绿，最差红
- 点复制 → 剪贴板拿到 markdown

---

## 文档 + smoke test (0.5 天)

1. **SKILL.md** 主要文件表加 `amap_query.py commute` multi-anchor 行为说明
2. **README.md** 加"多锚点通勤 + POI 图层"小节
3. **modes/map.md** 加第 5 节"多锚点 + POI 图层"
4. **config/profile.example.yml** 的 anchors 示例要有 3 个（公司 + 学校 + 家）
5. **Smoke test**:
   - 切换单锚点 ↔ 多锚点 profile，build_city_runtime 都 OK
   - 地图加载 3 个锚点不卡
   - POI 层 7 个都能打开/关闭
   - 对比 drawer 3 套房源正常

---

## Git 策略

每切片一个 commit：
- `feat(profile): add anchors schema for multi-anchor commute (D1)`
- `feat(map): render multi-anchor markers + isochrone circles (D2)`
- `feat(map): add POI layer toggles for supermarket/metro/etc (D3)`
- `feat(map): redesign listing panel with per-anchor commute + POI breakdown (D4)`
- `feat(map): add multi-listing comparison drawer with markdown export (D5)`

最后合并一个 `docs: update SKILL/README for v0.3 spatial decision` 提交。

然后 push + 开 PR（或直接 push main，按用户偏好）。

---

## 不确定点 & 决策

| 问题 | 决策 |
|------|-----|
| 客户端 geocode 慢？| 用 sessionStorage 缓存 per-address 结果 |
| POI 图层会不会耗尽配额？| 默认 7 类都 OFF；用户主动开；严格 bbox 缓存 |
| 多锚点评分和老的 score_5 字段兼容？| commute 输出加 `aggregate_score_5`，旧 `score_5` 只在单锚点模式时有 |
| 等时圈用真 isochrone？| 否，付费 API；直线圆够用 + 注"≈" |
| 对比超过 5 套？| 硬限 5，第 6 勾选时提示 |
