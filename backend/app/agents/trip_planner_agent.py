"""多智能体旅行规划系统 (LangGraph 版)

将原 HelloAgents 串行多智能体编排改造为 LangGraph StateGraph:

- 景点搜索 / 天气查询 / 酒店推荐 三个搜索任务通过 Send 并行扇出,
  每个任务复用同一个高德 MCP 工具(hello_agents.MCPTool)。
- 行程规划节点整合三路结果,使用 JSON mode 生成结构化输出。
- 失败时经 conditional edge 走备用计划(fallback),保证请求总能返回。

说明:
- DeepSeek 等推理模型不支持 response_format=json_schema(即 with_structured_output
  不可用),因此规划节点使用 response_format={"type":"json_object"} + 正则提取兜底。
- hello_agents.MCPTool.run() 为同步阻塞调用,节点内通过 asyncio.to_thread 包装。
"""

import asyncio
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from ..config import get_settings
from ..models.schemas import (
    TripRequest,
    TripPlan,
    DayPlan,
    Attraction,
    Meal,
    WeatherInfo,
    Location,
    Hotel,
)
from ..services.llm_service import get_llm

# ============ Agent 提示词 ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市和用户偏好搜索合适的景点。

**重要提示:**
你必须使用 maps_text_search 工具搜索景点,不要编造景点信息!
工具会自动调用,你只需根据用户输入确定搜索关键词。

**示例:**
用户: "搜索北京的历史文化景点"
搜索关键词: 历史文化,城市: 北京

用户: "搜索上海的公园"
搜索关键词: 公园,城市: 上海
"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。你的任务是通过 maps_weather 工具查询指定城市的天气信息。

**重要提示:**
必须使用工具查询,不要编造天气信息!
工具会自动调用,你只需确定要查询的城市。
"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。你的任务是通过 maps_text_search 工具搜索指定城市的酒店。

**重要提示:**
必须使用工具搜索酒店,不要编造酒店信息!
工具会自动调用,你只需确定搜索关键词(建议"酒店"或"宾馆")和城市。
"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息、天气信息和酒店信息,生成详细的旅行计划。

请严格按照以下JSON结构返回旅行计划:
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "景点名称",
          "address": "详细地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "visit_duration": 120,
          "description": "景点详细描述",
          "category": "景点类别",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "早餐推荐", "description": "早餐描述", "estimated_cost": 30},
        {"type": "lunch", "name": "午餐推荐", "description": "午餐描述", "estimated_cost": 50},
        {"type": "dinner", "name": "晚餐推荐", "description": "晚餐描述", "estimated_cost": 80}
      ]
    }
  ],
  "weather_info": [
    {
      "date": "YYYY-MM-DD",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}

**重要提示:**
1. weather_info 数组必须包含每一天的天气信息
2. 温度必须是纯数字(不要带°C等单位)
3. 每天安排2-3个景点
4. 考虑景点之间的距离和游览时间
5. 每天必须包含早中晚三餐
6. 提供实用的旅行建议
7. **必须包含预算信息**:
   - 景点门票价格(ticket_price)
   - 餐饮预估费用(estimated_cost)
   - 酒店预估费用(estimated_cost)
   - 预算汇总(budget)包含各项总费用
"""

# ============ LangGraph 状态定义 ============


class TripState(TypedDict):
    """旅行规划图状态

    三个搜索任务并行执行,各自写入独立字段,避免并发写同一字段互相覆盖。
    """

    request: Optional[TripRequest]          # 用户请求
    attractions_result: Optional[str]       # 景点搜索结果
    weather_result: Optional[str]           # 天气查询结果
    hotels_result: Optional[str]            # 酒店搜索结果
    planner_error: Optional[str]            # 行程规划失败原因(用于走 fallback)
    trip_plan: Optional[TripPlan]           # 生成的旅行计划


class SearchTask(TypedDict):
    """并行搜索子任务状态"""

    request: Optional[TripRequest]
    task_type: str


# ============ MCP 工具(复用原项目已验证的实现) ============

_uvx_path: Optional[str] = None


def _resolve_uvx() -> str:
    """解析 uvx 可执行文件路径(Windows 下可能不在系统 PATH)"""
    global _uvx_path
    if _uvx_path:
        return _uvx_path

    # 1. 系统 PATH
    found = shutil.which("uvx")
    if found:
        _uvx_path = found
        return _uvx_path

    # 2. 当前虚拟环境的 Scripts 目录(Windows) / bin 目录(POSIX)
    for candidate in (
        os.path.join(os.path.dirname(sys.executable), "uvx.exe"),
        os.path.join(os.path.dirname(sys.executable), "uvx"),
    ):
        if os.path.exists(candidate):
            _uvx_path = candidate
            return _uvx_path

    raise FileNotFoundError("未找到 uvx 可执行文件,请安装 uv 或将其加入 PATH")


def _get_amap_tool():
    """创建高德地图 MCP 工具实例"""
    from hello_agents.tools import MCPTool

    settings = get_settings()
    if not settings.amap_api_key:
        raise ValueError("高德地图 API Key 未配置,请在 .env 文件中设置 AMAP_API_KEY")

    return MCPTool(
        name="amap",
        description="高德地图服务",
        server_command=[_resolve_uvx(), "amap-mcp-server"],
        env={"AMAP_MAPS_API_KEY": settings.amap_api_key},
        auto_expand=True,
    )


# ============ 工具调用 ============

_amap_tool_instance = None


def get_amap_tool():
    """获取(缓存)高德地图 MCP 工具实例(单例)"""
    global _amap_tool_instance
    if _amap_tool_instance is None:
        _amap_tool_instance = _get_amap_tool()
    return _amap_tool_instance


async def _call_amap(tool_name: str, arguments: Dict[str, Any]) -> str:
    """通过 asyncio.to_thread 调用同步 MCP 工具"""
    tool = get_amap_tool()
    result = await asyncio.to_thread(
        tool.run,
        {
            "action": "call_tool",
            "tool_name": tool_name,
            "arguments": arguments,
        },
    )
    return str(result)


# ============ 图节点 ============

async def search_node(state: SearchTask) -> Dict[str, Any]:
    """搜索节点: 根据 task_type 执行不同的搜索任务,写回独立字段"""
    request = state.get("request")
    if request is None:
        return {}

    task_type = state.get("task_type", "attractions")
    result_text = ""

    try:
        if task_type == "attractions":
            keywords = request.preferences[0] if request.preferences else "景点"
            result_text = await _call_amap("maps_text_search", {
                "keywords": keywords,
                "city": request.city,
                "citylimit": "true",
            })
            return {"attractions_result": result_text}

        elif task_type == "weather":
            result_text = await _call_amap("maps_weather", {"city": request.city})
            return {"weather_result": result_text}

        elif task_type == "hotels":
            keywords = f"{request.accommodation} 酒店"
            result_text = await _call_amap("maps_text_search", {
                "keywords": keywords,
                "city": request.city,
                "citylimit": "true",
            })
            return {"hotels_result": result_text}

    except Exception as e:
        print(f"⚠️  {task_type} 搜索失败: {type(e).__name__}: {str(e)}")
        result_text = f"[{task_type} 搜索失败]: {type(e).__name__}: {str(e)}"

    return {f"{task_type}_result": result_text}


async def plan_node(state: TripState) -> Dict[str, Any]:
    """行程规划节点: 整合三路结果,生成结构化 JSON 计划"""
    request = state.get("request")
    if request is None:
        return {"planner_error": "缺少请求", "trip_plan": None}

    attractions = state.get("attractions_result") or "无景点信息"
    weather = state.get("weather_result") or "无天气信息"
    hotels = state.get("hotels_result") or "无酒店信息"

    query = _build_planner_query(request, attractions, weather, hotels)

    try:
        llm = get_llm()
        response = await llm.ainvoke(
            _planner_messages(query),
            response_format={"type": "json_object"},
        )
        plan = _parse_plan(response.content, request)
        return {"planner_error": None, "trip_plan": plan}
    except Exception as e:
        print(f"⚠️  行程规划失败: {type(e).__name__}: {str(e)}")
        import traceback

        traceback.print_exc()
        return {"planner_error": f"{type(e).__name__}: {str(e)}", "trip_plan": None}


def fallback_node(state: TripState) -> Dict[str, Any]:
    """备用计划节点"""
    request = state.get("request")
    if request is None:
        return {"planner_error": "缺少请求", "trip_plan": None}
    return {"planner_error": None, "trip_plan": _fallback_plan(request)}


def _planner_messages(query: str) -> List[Dict[str, str]]:
    """构造规划 LLM 消息(JSON mode 需要 system 提示)"""
    return [
        {
            "role": "system",
            "content": "你是一个行程规划助手,只输出合法的 JSON 对象,不要包含其他文字。"
            + PLANNER_AGENT_PROMPT,
        },
        {"role": "user", "content": query},
    ]


def _build_planner_query(request: TripRequest, attractions: str, weather: str, hotels: str = "") -> str:
    """构建行程规划查询(与原有逻辑保持一致)"""
    query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions}

**天气信息:**
{weather}

**酒店信息:**
{hotels}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
4. 考虑景点之间的距离和交通方式
5. 返回完整的JSON格式数据
6. 景点的经纬度坐标要真实准确
"""
    if request.free_text_input:
        query += f"\n**额外要求:** {request.free_text_input}"

    return query


def _parse_plan(text: str, request: TripRequest) -> TripPlan:
    """解析 JSON,转为 TripPlan;失败则走 fallback"""
    try:
        data = _extract_json(text)
        # 强制补全必要的字段(天气/酒店等可空)
        data.setdefault("weather_info", [])
        data.setdefault("overall_suggestions", "")
        return TripPlan(**data)
    except Exception as e:
        print(f"⚠️  JSON 解析失败: {str(e)}, 使用备用计划")
        return _fallback_plan(request)


def _extract_json(text: str) -> Dict[str, Any]:
    """从 LLM 响应中提取 JSON 对象(兼容代码块 / 纯文本 / 前后杂讯)"""
    text = text.strip()

    # 1. 代码块
    code_block = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1).strip()

    # 2. 直接 JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # 3. 提取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass

    raise ValueError("响应中未找到有效的 JSON")


def _fallback_plan(request: TripRequest) -> TripPlan:
    """创建备用计划(当 Agent 失败时),与原有逻辑保持一致"""
    start_date = datetime.strptime(request.start_date, "%Y-%m-%d")

    days = []
    for i in range(request.travel_days):
        current_date = start_date + timedelta(days=i)
        day_plan = DayPlan(
            date=current_date.strftime("%Y-%m-%d"),
            day_index=i,
            description=f"第{i+1}天行程",
            transportation=request.transportation,
            accommodation=request.accommodation,
            attractions=[
                Attraction(
                    name=f"{request.city}景点{j+1}",
                    address=f"{request.city}市",
                    location=Location(longitude=116.4 + i * 0.01 + j * 0.005, latitude=39.9 + i * 0.01 + j * 0.005),
                    visit_duration=120,
                    description=f"这是{request.city}的著名景点",
                    category="景点",
                )
                for j in range(2)
            ],
            meals=[
                Meal(type="breakfast", name=f"第{i+1}天早餐", description="当地特色早餐"),
                Meal(type="lunch", name=f"第{i+1}天午餐", description="午餐推荐"),
                Meal(type="dinner", name=f"第{i+1}天晚餐", description="晚餐推荐"),
            ],
        )
        days.append(day_plan)

    return TripPlan(
        city=request.city,
        start_date=request.start_date,
        end_date=request.end_date,
        days=days,
        weather_info=[],
        overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程,建议提前查看各景点的开放时间。",
    )


def _route_after_plan(state: TripState) -> Literal["fallback", "__end__"]:
    """根据规划结果路由: 失败则走 fallback"""
    if state.get("planner_error"):
        return "fallback"
    return END


# ============ LangGraph 图 ============

def _build_graph():
    """构建并编译 LangGraph 图"""
    def fan_out(state: TripState) -> List[Send]:
        """START 后并行扇出三个搜索任务"""
        request = state["request"]
        return [
            Send("search", {"request": request, "task_type": "attractions"}),
            Send("search", {"request": request, "task_type": "weather"}),
            Send("search", {"request": request, "task_type": "hotels"}),
        ]

    graph = StateGraph(TripState)
    graph.add_node("search", search_node)
    graph.add_node("plan", plan_node)
    graph.add_node("fallback", fallback_node)

    graph.add_edge(START, "search")
    graph.add_edge("search", "plan")
    graph.add_conditional_edges(
        "plan",
        _route_after_plan,
        {"fallback": "fallback", END: END},
    )
    graph.add_edge("fallback", END)

    return graph.compile()


# ============ 多智能体系统 ============

_graph_instance = None


def get_graph():
    """获取(缓存)编译后的 LangGraph 图"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = _build_graph()
    return _graph_instance


class MultiAgentTripPlanner:
    """多智能体旅行规划系统 (LangGraph 版)"""

    def __init__(self):
        print("🔄 初始化 LangGraph 多智能体旅行规划系统...")
        try:
            get_llm()  # 验证 LLM 配置
            get_amap_tool()  # 创建 MCP 工具(验证高德配置)
            get_graph()  # 编译图
            print("✅ LangGraph 多智能体系统初始化成功")
        except Exception as e:
            print(f"❌ 多智能体系统初始化失败: {str(e)}")
            import traceback

            traceback.print_exc()
            raise

    async def plan_trip(self, request: TripRequest) -> TripPlan:
        """使用 LangGraph 生成旅行计划"""
        print(f"\n{'='*60}")
        print(f"🚀 开始多智能体协作规划旅行...")
        print(f"目的地: {request.city}")
        print(f"日期: {request.start_date} 至 {request.end_date}")
        print(f"天数: {request.travel_days}天")
        print(f"偏好: {', '.join(request.preferences) if request.preferences else '无'}")
        print(f"{'='*60}\n")

        try:
            graph = get_graph()
            result = await graph.ainvoke(
                {
                    "request": request,
                    "attractions_result": None,
                    "weather_result": None,
                    "hotels_result": None,
                    "planner_error": None,
                    "trip_plan": None,
                }
            )

            plan = result.get("trip_plan")
            if plan is None:
                print(f"⚠️  行程规划失败,使用备用计划")
                return _fallback_plan(request)

            print(f"{'='*60}")
            print(f"✅ 旅行计划生成完成!")
            print(f"{'='*60}\n")
            return plan

        except Exception as e:
            print(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback

            traceback.print_exc()
            return _fallback_plan(request)

    # --- 供 /health 使用的元信息 ---
    @property
    def name(self) -> str:
        return "MultiAgentTripPlanner(LangGraph)"

    @property
    def tools_count(self) -> int:
        try:
            tool = get_amap_tool()
            return len(tool._available_tools) if hasattr(tool, "_available_tools") else 0
        except Exception:
            return 0


# 全局多智能体系统实例
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取多智能体旅行规划系统实例(单例模式)"""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner
