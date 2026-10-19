"""LLM服务模块

为 LangGraph 多智能体编排提供 LangChain 兼容的 LLM 实例。
兼容现有 .env 配置(LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_ID)。
"""

import os
from typing import Optional

from ..config import get_settings

# 全局 LLM 实例
_llm_instance = None


def _read_env() -> dict:
    """从 .env / 环境变量读取 LLM 配置(与 HelloAgentsLLM 的读取逻辑保持一致)

    注意: 某些 .env 里 LLM_BASE_URL 可能配置为 Anthropic 格式端点
    (例如 https://api.deepseek.com/anthropic),而本服务使用 OpenAI 协议,
    因此仅保留 OpenAI 兼容的 base_url,否则请求会 404。
    """
    settings = get_settings()
    raw_base_url = os.getenv("LLM_BASE_URL") or settings.openai_base_url

    # 去掉 Anthropic 兼容端点后缀(本服务走 OpenAI 协议)
    base_url = raw_base_url.replace("/anthropic", "").replace("/v1/", "/").rstrip("/")
    if base_url.endswith("/anthropic"):
        base_url = base_url[: -len("/anthropic")]

    return {
        "api_key": os.getenv("LLM_API_KEY") or settings.openai_api_key or None,
        "base_url": base_url,
        "model": os.getenv("LLM_MODEL_ID") or settings.openai_model,
    }


def get_llm() -> "ChatOpenAI":
    """
    获取 LangChain ChatOpenAI 实例(单例模式)

    ChatOpenAI 使用 OpenAI 兼容协议,可连接 OpenAI / DeepSeek / 通义 等
    提供 OpenAI 格式端点的服务。

    注意: deepseek-v4-pro 等推理模型需要较大的 max_tokens 预算
    (思考过程会消耗大量 token),否则回答会被截断。
    """
    global _llm_instance

    if _llm_instance is None:
        # 延迟导入,确保 langchain 已安装
        from langchain_openai import ChatOpenAI

        cfg = _read_env()
        if not cfg["api_key"]:
            raise ValueError("LLM_API_KEY 未配置,请在 .env 文件中设置")

        _llm_instance = ChatOpenAI(
            model=cfg["model"],
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            temperature=0.7,
            timeout=60,
            max_retries=2,
            max_tokens=8192,  # 推理模型思考消耗大,给足预算
        )

        print(f"✅ LangChain LLM 服务初始化成功")
        print(f"   模型: {cfg['model']}")
        print(f"   Base URL: {cfg['base_url']}")

    return _llm_instance


def get_helloagents_llm() -> Optional[object]:
    """
    获取 HelloAgentsLLM 实例(兼容旧版,供非 LangGraph 模块使用)

    Returns:
        HelloAgentsLLM 实例;若未安装 hello-agents 则返回 None
    """
    try:
        from hello_agents import HelloAgentsLLM

        return HelloAgentsLLM()
    except ImportError:
        return None


def reset_llm():
    """重置 LLM 实例(用于测试或重新配置)"""
    global _llm_instance
    _llm_instance = None
