"""高德地图MCP服务封装"""

from typing import List, Dict, Any, Optional
import os

from hello_agents.tools import MCPTool
from ..config import get_settings
from ..models.schemas import Location, POIInfo, WeatherInfo

# 全局MCP工具实例
_amap_mcp_tool = None


def get_amap_mcp_tool() -> MCPTool:
    """
    获取高德地图MCP工具实例(单例模式)
    
    Returns:
        MCPTool实例
    """
    global _amap_mcp_tool
    
    if _amap_mcp_tool is None:
        settings = get_settings()
        
        if not settings.amap_api_key:
            raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")
        
        # 创建MCP工具
        _amap_mcp_tool = MCPTool(
            name="amap",
            description="高德地图服务,支持POI搜索、路线规划、天气查询等功能",
            # amap-mcp-server 依赖的 mcp 包缺少 pydantic 上限约束,需固定 pydantic<2.12
            server_command=["uvx", "--with", "pydantic<2.12", "amap-mcp-server"],
            env={
                "AMAP_MAPS_API_KEY": settings.amap_api_key,
                # MCPTool 子进程为干净环境,uvx 默认写 ~/.local/share/uv/tools,
                # 部分环境该目录不可写,这里显式重定向到用户缓存目录
                "UV_TOOL_DIR": os.path.expanduser("~/.cache/uv-tools"),
            },
            auto_expand=True  # 自动展开为独立工具
        )
        
        print(f"✅ 高德地图MCP工具初始化成功")
        print(f"   工具数量: {len(_amap_mcp_tool._available_tools)}")
        
        # 打印可用工具列表
        if _amap_mcp_tool._available_tools:
            print("   可用工具:")
            for tool in _amap_mcp_tool._available_tools[:5]:  # 只打印前5个
                print(f"     - {tool.get('name', 'unknown')}")
            if len(_amap_mcp_tool._available_tools) > 5:
                print(f"     ... 还有 {len(_amap_mcp_tool._available_tools) - 5} 个工具")
    
    return _amap_mcp_tool


class AmapService:
    """高德地图服务封装类"""
    
    def __init__(self):
        """初始化服务"""
        self.mcp_tool = get_amap_mcp_tool()
    
    def search_poi(self, keywords: str, city: str, citylimit: bool = True) -> List[POIInfo]:
        """
        搜索POI
        
        Args:
            keywords: 搜索关键词
            city: 城市
            citylimit: 是否限制在城市范围内
            
        Returns:
            POI信息列表
        """
        try:
            # 调用MCP工具
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_text_search",
                "arguments": {
                    "keywords": keywords,
                    "city": city,
                    "citylimit": str(citylimit).lower()
                }
            })
            
            # 解析结果
            # 注意: MCP工具返回的是字符串,需要解析
            # 这里简化处理,实际应该解析JSON
            print(f"POI搜索结果: {result[:200]}...")  # 打印前200字符

            # 从工具返回文本中提取JSON
            # 注意: maps_text_search 返回的POI不含经纬度(仅 id/name/address/typecode),
            # 需逐条调用 POI 详情补齐 location 与 type
            import json
            import re

            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if not json_match:
                return []

            data = json.loads(json_match.group())
            pois: List[POIInfo] = []
            for item in data.get("pois", []):
                poi_id = str(item.get("id", ""))
                if not poi_id:
                    continue
                try:
                    detail = self.get_poi_detail(poi_id)
                    location_str = str(detail.get("location", ""))
                    if "," not in location_str:
                        print(f"⚠️ 跳过无坐标POI: {item.get('name', poi_id)}")
                        continue
                    longitude, latitude = location_str.split(",", 1)
                    pois.append(POIInfo(
                        id=poi_id,
                        name=str(detail.get("name") or item.get("name", "")),
                        type=str(detail.get("type", "") or item.get("typecode", "")),
                        address=str(detail.get("address") or item.get("address", "") or ""),
                        location=Location(longitude=float(longitude), latitude=float(latitude)),
                        tel=str(detail["tel"]) if detail.get("tel") else None
                    ))
                except (ValueError, TypeError) as e:
                    # 单条数据格式异常时跳过,不影响其余结果
                    print(f"⚠️ 跳过无效POI数据: {e}")
                    continue
            return pois

        except Exception as e:
            print(f"❌ POI搜索失败: {str(e)}")
            return []
    
    def get_weather(self, city: str) -> List[WeatherInfo]:
        """
        查询天气
        
        Args:
            city: 城市名称
            
        Returns:
            天气信息列表
        """
        try:
            # 调用MCP工具
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_weather",
                "arguments": {
                    "city": city
                }
            })
            
            print(f"天气查询结果: {result[:200]}...")

            # 从工具返回文本中提取JSON并转换为WeatherInfo列表
            import json
            import re

            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if not json_match:
                return []

            data = json.loads(json_match.group())
            weather_list: List[WeatherInfo] = []
            for item in data.get("forecasts", []):
                weather_list.append(WeatherInfo(
                    date=item.get("date", ""),
                    day_weather=item.get("dayweather", ""),
                    night_weather=item.get("nightweather", ""),
                    day_temp=item.get("daytemp", 0),
                    night_temp=item.get("nighttemp", 0),
                    wind_direction=item.get("daywind", "") or item.get("daywinddirection", ""),
                    wind_power=item.get("daypower", "")
                ))
            return weather_list

        except Exception as e:
            print(f"❌ 天气查询失败: {str(e)}")
            return []
    
    def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking"
    ) -> Dict[str, Any]:
        """
        规划路线
        
        Args:
            origin_address: 起点地址
            destination_address: 终点地址
            origin_city: 起点城市
            destination_city: 终点城市
            route_type: 路线类型 (walking/driving/transit)
            
        Returns:
            路线信息
        """
        try:
            # 根据路线类型选择工具
            tool_map = {
                "walking": "maps_direction_walking_by_address",
                "driving": "maps_direction_driving_by_address",
                "transit": "maps_direction_transit_integrated_by_address"
            }
            
            tool_name = tool_map.get(route_type, "maps_direction_walking_by_address")
            
            # 构建参数
            arguments = {
                "origin_address": origin_address,
                "destination_address": destination_address
            }
            
            # 公共交通需要城市参数
            if route_type == "transit":
                if origin_city:
                    arguments["origin_city"] = origin_city
                if destination_city:
                    arguments["destination_city"] = destination_city
            else:
                # 其他路线类型也可以提供城市参数提高准确性
                if origin_city:
                    arguments["origin_city"] = origin_city
                if destination_city:
                    arguments["destination_city"] = destination_city
            
            # 调用MCP工具
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": tool_name,
                "arguments": arguments
            })
            
            print(f"路线规划结果: {result[:200]}...")
            
            # TODO: 解析实际的路线数据
            return {}
            
        except Exception as e:
            print(f"❌ 路线规划失败: {str(e)}")
            return {}
    
    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        """
        地理编码(地址转坐标)

        Args:
            address: 地址
            city: 城市

        Returns:
            经纬度坐标
        """
        try:
            arguments = {"address": address}
            if city:
                arguments["city"] = city

            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_geo",
                "arguments": arguments
            })

            print(f"地理编码结果: {result[:200]}...")

            # TODO: 解析实际的坐标数据
            return None

        except Exception as e:
            print(f"❌ 地理编码失败: {str(e)}")
            return None

    def get_poi_detail(self, poi_id: str) -> Dict[str, Any]:
        """
        获取POI详情

        Args:
            poi_id: POI ID

        Returns:
            POI详情信息
        """
        try:
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_search_detail",
                "arguments": {
                    "id": poi_id
                }
            })

            print(f"POI详情结果: {result[:200]}...")

            # 解析结果并提取图片
            import json
            import re

            # 尝试从结果中提取JSON
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data

            return {"raw": result}

        except Exception as e:
            print(f"❌ 获取POI详情失败: {str(e)}")
            return {}


# 创建全局服务实例
_amap_service = None


def get_amap_service() -> AmapService:
    """获取高德地图服务实例(单例模式)"""
    global _amap_service
    
    if _amap_service is None:
        _amap_service = AmapService()
    
    return _amap_service

