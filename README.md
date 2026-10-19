# 智能旅行助手 🌍✈️

基于 **LangGraph 多智能体框架** 构建的智能旅行规划助手,集成高德地图 MCP 服务,提供个性化的旅行计划生成。

## ✨ 功能特点

- 🤖 **AI 驱动的旅行规划**: 基于 LangGraph 多智能体编排 (StateGraph),智能生成详细的多日旅程
- 🗺️ **高德地图集成**: 通过 MCP 协议接入高德地图服务,支持景点搜索、路线规划、天气查询
- ⚡ **并行工具调用**: 景点搜索 / 天气查询 / 酒店推荐三个任务通过 `Send` 并行扇出,大幅缩短等待时间
- 🧠 **结构化输出**: 使用 JSON mode 生成结构化旅行计划,可靠解析
- 🎨 **现代化前端**: Vue3 + TypeScript + Vite,响应式设计,流畅的用户体验
- 📱 **完整功能**: 包含住宿、交通、餐饮、天气和景点游览时间推荐,以及预算明细

## 🏗️ 技术栈

### 后端
- **编排框架**: LangGraph (StateGraph 多智能体编排 + Send 并行扇出)
- **API**: FastAPI + Uvicorn
- **LLM**: LangChain ChatOpenAI (兼容 OpenAI / DeepSeek 等 OpenAI 格式端点,支持推理模型)
- **MCP 工具**: amap-mcp-server (高德地图,通过 hello_agents.MCPTool 复用)
- **数据校验**: Pydantic v2

### 前端
- **框架**: Vue 3 + TypeScript (Composition API)
- **构建工具**: Vite
- **UI 组件库**: Ant Design Vue
- **地图服务**: 高德地图 JavaScript API (JSAPI 2.0)
- **HTTP 客户端**: Axios
- **路由**: Vue Router

## 📁 项目结构

```
helloagents-trip-planner/
├── backend/                        # 后端服务
│   ├── app/
│   │   ├── agents/                # 多智能体实现(LangGraph)
│   │   │   └── trip_planner_agent.py   # StateGraph 图: search/plan/fallback
│   │   ├── api/                   # FastAPI 路由
│   │   │   ├── main.py            # 应用入口,注册 CORS 与路由
│   │   │   └── routes/
│   │   │       ├── trip.py        # POST /api/trip/plan 生成旅行计划
│   │   │       ├── poi.py         # POI 详情 / 搜索 / Unsplash 图片
│   │   │       └── map.py         # 地图服务(高德 MCP 封装)
│   │   ├── services/              # 服务层
│   │   │   ├── llm_service.py     # LangChain ChatOpenAI 单例
│   │   │   ├── amap_service.py    # 高德 MCP 工具封装
│   │   │   └── unsplash_service.py# Unsplash 图片搜索
│   │   ├── models/                # 数据模型
│   │   │   └── schemas.py         # TripRequest / TripPlan 等 Pydantic 模型
│   │   └── config.py              # 配置管理(读取 .env)
│   ├── requirements.txt
│   ├── .env                       # 环境变量(API密钥)
│   └── .gitignore
├── frontend/                       # 前端应用
│   ├── src/
│   │   ├── services/              # API 服务(Axios)
│   │   │   └── api.ts
│   │   ├── types/                 # TypeScript 类型定义
│   │   │   └── index.ts
│   │   ├── views/                 # 页面视图
│   │   │   ├── Home.vue           # 旅行信息表单
│   │   │   └── Result.vue         # 行程展示 + 高德地图 + 编辑/导出
│   │   ├── App.vue                # 根组件(导航栏 + 页脚)
│   │   └── main.ts                # 应用入口
│   ├── .env                       # 前端环境变量(高德 JS API Key)
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## 🚀 快速开始

### 前提条件

- Python 3.10+
- Node.js 16+
- 高德地图 API 密钥(需要**两个不同类型的 Key**):
  - **Web 服务 Key** — 用于后端调用高德 Web 服务接口(景点搜索、天气查询)
  - **Web 端(JS API) Key** — 用于前端地图展示
- LLM API 密钥(OpenAI / DeepSeek 等,支持 OpenAI 兼容端点)

### 后端安装

1. 进入后端目录
```bash
cd backend
```

2. 创建虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件,填入你的 API 密钥
```

5. 启动后端服务
```bash
# Windows 下建议设置 UTF-8 编码,避免中文输出乱码
PYTHONIOENCODING=utf-8 uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```
> 启动后访问 `http://localhost:8000/docs` 查看 API 文档。

### 前端安装

1. 进入前端目录
```bash
cd frontend
```

2. 安装依赖
```bash
npm install
```

3. 配置环境变量
```bash
# 创建 .env 文件,填入高德地图 Web 端 JS API Key
cp .env.example .env
```

4. 启动开发服务器
```bash
npm run dev
```

5. 打开浏览器访问 `http://localhost:5173`

## 📝 使用指南

1. 在首页填写旅行信息:
   - 目的地城市
   - 旅行日期和天数
   - 交通方式偏好
   - 住宿偏好
   - 旅行风格标签

2. 点击"生成旅行计划"按钮

3. 系统将:
   - LangGraph 并行调用高德地图 MCP 工具搜索景点 / 查询天气 / 搜索酒店
   - 整合所有信息,由 LLM 生成结构化旅行计划(JSON mode)
   - 失败时自动降级为备用计划,保证请求总能返回

4. 查看结果:
   - 每日详细行程(景点、餐饮、酒店)
   - 景点信息与地图标记
   - 天气预报
   - 预算明细
   - 支持在线编辑行程、导出为图片 / PDF

## 🔧 核心实现

### LangGraph 多智能体编排

```
                    ┌─────────────────────────────┐
                    │        TripState            │
                    │  request / 搜索结果 / 计划    │
                    └─────────────┬───────────────┘
                                  │  Send 并行扇出
          ┌──────────────┬────────┴────────┬──────────────┐
          ▼              ▼                 ▼
     search节点       search节点        search节点
     (景点搜索)       (天气查询)        (酒店搜索)
     maps_text_search maps_weather    maps_text_search
          └──────────────┴────────┬────────┴──────────────┘
                                  ▼
                        plan 节点 (JSON mode)
                                  │
                     ┌────────────┴────────────┐
                     ▼                         ▼
                成功 → END                失败 → fallback → END
```

```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

# 三个搜索任务并行扇出
def fan_out(state):
    return [
        Send("search", {"request": state["request"], "task_type": "attractions"}),
        Send("search", {"request": state["request"], "task_type": "weather"}),
        Send("search", {"request": state["request"], "task_type": "hotels"}),
    ]

graph = StateGraph(TripState)
graph.add_node("search", search_node)      # 并行: 景点 / 天气 / 酒店
graph.add_node("plan", plan_node)          # JSON mode 结构化规划
graph.add_node("fallback", fallback_node)  # 失败兜底

graph.add_edge(START, "search")
graph.add_edge("search", "plan")
graph.add_conditional_edges("plan", _route_after_plan, {"fallback": "fallback", END: END})
graph.add_edge("fallback", END)

app = graph.compile()
```

### 关键设计说明

- **并行搜索**: 三个搜索任务通过 `Send` 并行执行,每个任务写入独立状态字段(`attractions_result` / `weather_result` / `hotels_result`),避免并发写同一字段互相覆盖。
- **结构化输出**: 由于 DeepSeek 等推理模型不支持 `response_format=json_schema`,规划节点使用 `response_format={"type": "json_object"}` + 正则提取兜底。
- **LLM 配置**: `llm_service.py` 会自动将 `.env` 中的 Anthropic 格式 base_url(如 `https://api.deepseek.com/anthropic`)归一化为 OpenAI 格式,并对推理模型设置足够的 `max_tokens`(8192)。
- **fallback 兜底**: 当搜索或规划任一环节失败时,自动生成备用计划,保证 API 稳定返回。

### 高德地图 MCP 工具

Agent 可以自动调用以下高德地图 MCP 工具:
- `maps_text_search`: 搜索景点 POI / 酒店
- `maps_weather`: 查询天气
- `maps_geo`: 地址转经纬度(地理编码)
- `maps_regeocode`: 经纬度转地址(逆地理编码)
- `maps_direction_walking_by_address`: 步行路线规划
- `maps_direction_driving_by_address`: 驾车路线规划
- `maps_direction_transit_integrated_by_address`: 公共交通路线规划

## 📄 API 文档

启动后端服务后,访问 `http://localhost:8000/docs` 查看完整的 API 文档。

主要端点:
- `POST /api/trip/plan` - 生成旅行计划(核心接口)
- `GET /api/trip/health` - 旅行规划服务健康检查
- `GET /api/map/poi` - 搜索 POI
- `GET /api/map/weather` - 查询天气
- `POST /api/map/route` - 规划路线
- `GET /api/poi/detail/{poi_id}` - 获取 POI 详情
- `GET /api/poi/photo` - 获取景点图片(Unsplash)
- `GET /health` - 服务健康检查

### 请求示例

```json
POST /api/trip/plan
{
  "city": "北京",
  "start_date": "2026-08-11",
  "end_date": "2026-08-13",
  "travel_days": 3,
  "transportation": "公共交通",
  "accommodation": "经济型酒店",
  "preferences": ["历史文化"],
  "free_text_input": ""
}
```

### 响应示例

```json
{
  "success": true,
  "message": "旅行计划生成成功",
  "data": {
    "city": "北京",
    "start_date": "2026-08-11",
    "end_date": "2026-08-13",
    "days": [
      {
        "date": "2026-08-11",
        "day_index": 0,
        "description": "第1天行程概述",
        "transportation": "公共交通",
        "accommodation": "经济型酒店",
        "hotel": { "name": "如家快捷酒店(北京天安门店)", "address": "..." },
        "attractions": [{ "name": "故宫博物院", "address": "景山前街4号", "visit_duration": 120 }],
        "meals": [{ "type": "breakfast", "name": "北京特色早餐" }]
      }
    ],
    "weather_info": [{ "date": "2026-08-11", "day_weather": "晴", "day_temp": 35 }],
    "overall_suggestions": "建议提前预约故宫门票...",
    "budget": { "total_attractions": 130, "total_hotels": 1200, "total_meals": 530, "total_transportation": 200, "total": 2060 }
  }
}
```

## ⚙️ 环境变量说明

### 后端 (`backend/.env`)

| 变量 | 说明 | 必需 |
|---|---|---|
| `LLM_API_KEY` | LLM API 密钥(OpenAI / DeepSeek 等) | ✅ |
| `LLM_BASE_URL` | LLM API 地址(支持 OpenAI 格式,自动兼容 Anthropic 后缀) | ✅ |
| `LLM_MODEL_ID` | 模型名称(如 `deepseek-v4-pro`) | ✅ |
| `AMAP_API_KEY` | 高德地图 **Web 服务** Key | ✅ |
| `UNSPLASH_ACCESS_KEY` | Unsplash API Key(可选,景点图片) | 可选 |
| `UNSPLASH_SECRET_KEY` | Unsplash Secret Key(可选) | 可选 |
| `PORT` / `HOST` | 后端监听地址(默认 8000 / 0.0.0.0) | 可选 |

> ⚠️ **高德 Key 注意**: 后端需要的是「**Web 服务**」平台的 Key。如果使用 JS API 平台的 Key 调用 Web 服务接口,会返回 `USERKEY_PLAT_NOMATCH` 错误。

### 前端 (`frontend/.env`)

| 变量 | 说明 | 必需 |
|---|---|---|
| `VITE_API_BASE_URL` | 后端 API 地址(默认 `http://localhost:8000`) | ✅ |
| `VITE_AMAP_WEB_JS_KEY` | 高德地图 **Web 端(JS API)** Key,用于前端地图 | ✅ |

## 🤝 贡献指南

欢迎提交 Pull Request 或 Issue!

## 📜 开源协议

CC BY-NC-SA 4.0

## 🙏 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 多智能体编排框架
- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用框架
- [HelloAgents](https://github.com/datawhalechina/Hello-Agents) - 智能体教程
- [HelloAgents 框架](https://github.com/jjyaoao/HelloAgents) - 智能体框架(提供 MCP 工具复用)
- [高德地图开放平台](https://lbs.amap.com/) - 地图服务
- [amap-mcp-server](https://github.com/sugarforever/amap-mcp-server) - 高德地图 MCP 服务器
- [FastAPI](https://fastapi.tiangolo.com/) - 后端 API 框架
- [Vue.js](https://vuejs.org/) - 前端框架

---

**智能旅行助手** - 让旅行计划变得简单而智能 🌈
