# 模式：map — 高德地图可视化

在浏览器中打开房源地图，展示所有已跟踪的房源位置。

## 前提

- 高德地图 JS API Key（Web端类型）— 需在 [console.amap.com](https://console.amap.com) 申请
- API Key 和安全密钥已配置在 `data/map-view.html` 中

## 执行

### 1. 确认数据文件

检查 `data/listings.json` 是否存在且非空。如果不存在或为空：
- 提示用户先运行 `/rent scrape` 或 `/rent scan` 获取房源数据

### 2. 生成 map-view.html

地图 HTML 不直接提交到仓库，而是从模板生成。

#### 2a. 复制模板

```bash
cp templates/map-view.example.html data/map-view.html
```

#### 2b. 替换占位符

读取 `config/profile.yml`，将 `data/map-view.html` 中的占位符替换为用户实际值：

| 占位符 | 来源 | 示例           |
|--------|------|--------------|
| `__AMAP_SECURITY_CODE__` | 用户提供或已有配置 |
| `__AMAP_JS_KEY__` | 用户提供或已有配置 |
| `__CITY__` | `profile.yml → city` | `深圳`         |
| `__WORK_NAME__` | `profile.yml → destinations[0].name`    |
| `__WORK_LNG__` | 工作地 GCJ-02 经度（需转换）    |
| `__WORK_LAT__` | 工作地 GCJ-02 纬度（需转换）    |
| `__BUDGET__` | `profile.yml → budget`  |
| `__RENT_TYPE__` | `profile.yml → type`      |

#### 2c. 填充城市区域数据

模板中有以下需要根据城市填充的区块（标记为 `__AREA_*__` 注释）：

1. **`__AREA_COLORS__`** — JS 对象 `areaColor`：为城市各区分配颜色
2. **`__AREA_CHIP_STYLES__`** — CSS：每个区的 `.chip.active` 背景色
3. **`__AREA_FILTER_CHIPS__`** — HTML：筛选器 chip 元素
4. **`__AREA_LEGEND_ROWS__`** — HTML：图例行
5. **`__AREA_FALLBACK__`** — JS 对象：各区中心坐标（GCJ-02）作为地理编码降级

#### 2d. 高德 API Key 处理

如果用户之前已配置过（旧的 `data/map-view.html` 存在），从中提取 Key 和安全密钥复用。

如果是首次配置，提示用户：

> "地图需要高德 JS API Key。请在 [console.amap.com](https://console.amap.com) 创建应用 → 添加「Web端(JS API)」类型 Key，把 Key 和安全密钥告诉我。"

#### 2e. 坐标

坐标需要使用 **GCJ-02 坐标系**（高德地图使用的国内坐标系）。

### 3. 启动 HTTP 服务

高德地图 JS API 不支持 `file://` 协议，必须通过 HTTP 访问：

```bash
cd data && python3 -m http.server 8765 &
```

检查端口是否已被占用（`lsof -i :8765`），如已占用则跳过启动。

### 4. 打开地图

```bash
open http://localhost:8765/map-view.html
```

## 地图功能

### 标记
- 红色脉冲圆点：工作地点
- 彩色圆点：房源位置，颜色按区域区分
- 大圆（有数字）：有明确价格的房源，数字 = 月租/千元
- 小圆（?）：价格待询

### 筛选器
顶部 chip 筛选：按区域、按价格、按平台（小红书/豆瓣）

### 详情面板
点击圆点弹出右侧面板：
- 平台来源 + 小区名
- 价格 + 户型
- 距工作地直线距离
- 「查看原帖」链接

### 地理编码
新抓取的房源通过高德 PlaceSearch API 自动定位小区坐标：
- 从标题提取小区名（如「云海天城」「万科云城」）→ POI 搜索 → 真实坐标
- 提取失败时降级到区域中心点，面板标注「大致位置」
- 右下角显示定位进度

## 更新地图数据

地图数据来自 `data/listings.json`。更新流程：

1. 运行 `/rent scrape`（爬取新数据）
2. 数据整合脚本会自动更新 `listings.json`
3. 刷新浏览器页面即可看到新房源

## API Key 配置

用户需要在 `data/map-view.html` 中配置两个值：

```html
<script>
window._AMapSecurityConfig = { securityJsCode: '你的安全密钥' };
</script>
<script src="https://webapi.amap.com/maps?v=2.0&key=你的API_Key&plugin=..."></script>
```

获取方式：
1. 访问 [console.amap.com](https://console.amap.com)
2. 创建应用 → 添加 Key → 选择「Web端(JS API)」
3. 复制 Key 和安全密钥到上述位置
