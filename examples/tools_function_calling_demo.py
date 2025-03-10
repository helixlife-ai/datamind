import os
import sys
from pathlib import Path
import asyncio
import logging
import json
from typing import Dict, List, Any, Optional

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from datamind import setup_logging
from datamind.core.reasoningLLM import ReasoningLLMEngine
from datamind.llms.model_manager import ModelManager, ModelConfig
from datamind.config.settings import (
    DEFAULT_REASONING_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE
)

# 定义一些简单的工具函数
def get_current_weather(location: str, unit: str = "celsius") -> Dict[str, Any]:
    """获取指定位置的当前天气情况"""
    # 这里只是模拟数据，实际应用中应该调用实际的天气API
    weather_data = {
        "北京": {"temperature": 22, "condition": "晴天", "humidity": 40},
        "上海": {"temperature": 26, "condition": "多云", "humidity": 65},
        "广州": {"temperature": 30, "condition": "小雨", "humidity": 80},
        "深圳": {"temperature": 29, "condition": "晴天", "humidity": 70},
        # 默认情况
        "default": {"temperature": 25, "condition": "未知", "humidity": 50},
    }
    
    # 获取天气数据，如果没有指定位置的数据则使用默认值
    result = weather_data.get(location, weather_data["default"])
    
    # 温度单位转换
    if unit == "fahrenheit":
        result["temperature"] = (result["temperature"] * 9/5) + 32
    
    return {
        "location": location,
        "temperature": result["temperature"],
        "unit": unit,
        "condition": result["condition"],
        "humidity": result["humidity"]
    }

def search_database(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """搜索数据库中的信息"""
    # 这里只是模拟数据，实际应用中应该查询实际的数据库
    database = [
        {"id": 1, "title": "Python编程基础", "content": "Python是一种易于学习的高级编程语言...", "category": "编程"},
        {"id": 2, "title": "机器学习入门", "content": "机器学习是人工智能的一个分支...", "category": "AI"},
        {"id": 3, "title": "数据分析方法", "content": "数据分析是从数据中提取有用信息的过程...", "category": "数据科学"},
        {"id": 4, "title": "自然语言处理", "content": "自然语言处理(NLP)是人工智能的一个子领域...", "category": "AI"},
        {"id": 5, "title": "深度学习框架比较", "content": "常见的深度学习框架包括TensorFlow、PyTorch等...", "category": "AI"},
        {"id": 6, "title": "Web开发基础", "content": "Web开发包括前端和后端开发两个方面...", "category": "编程"},
        {"id": 7, "title": "数据可视化技术", "content": "数据可视化是将数据以图形方式展示的技术...", "category": "数据科学"},
    ]
    
    # 简单的关键词搜索
    results = []
    for item in database:
        if (query.lower() in item["title"].lower() or 
            query.lower() in item["content"].lower() or
            query.lower() in item["category"].lower()):
            results.append(item)
    
    # 返回结果，最多返回limit个
    return results[:limit]

def calculator(operation: str, x: float, y: float) -> Dict[str, Any]:
    """执行简单的数学运算"""
    operations = {
        "add": lambda a, b: a + b,
        "subtract": lambda a, b: a - b,
        "multiply": lambda a, b: a * b,
        "divide": lambda a, b: a / b if b != 0 else "错误：除数不能为零"
    }
    
    if operation not in operations:
        return {"error": f"不支持的操作: {operation}", "result": None}
    
    result = operations[operation](x, y)
    return {
        "operation": operation,
        "x": x,
        "y": y,
        "result": result
    }

# 定义工具配置
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "获取指定位置的当前天气情况",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市名称，例如：北京、上海、广州等"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "温度单位，celsius（摄氏度）或 fahrenheit（华氏度）"
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_database",
            "description": "搜索数据库中的信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回的结果数量"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "执行简单的数学运算",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "要执行的操作类型"
                    },
                    "x": {
                        "type": "number",
                        "description": "第一个数值"
                    },
                    "y": {
                        "type": "number",
                        "description": "第二个数值"
                    }
                },
                "required": ["operation", "x", "y"]
            }
        }
    }
]

# 工具调用处理函数
def handle_tool_calls(tool_calls):
    """处理工具调用请求并返回结果"""
    results = []
    
    for tool_call in tool_calls:
        function_call = tool_call.function
        function_name = function_call.name
        
        try:
            arguments = json.loads(function_call.arguments)
            
            if function_name == "get_current_weather":
                location = arguments.get("location")
                unit = arguments.get("unit", "celsius")
                result = get_current_weather(location, unit)
            elif function_name == "search_database":
                query = arguments.get("query")
                limit = arguments.get("limit", 5)
                result = search_database(query, limit)
            elif function_name == "calculator":
                operation = arguments.get("operation")
                x = float(arguments.get("x"))
                y = float(arguments.get("y"))
                result = calculator(operation, x, y)
            else:
                result = {"error": f"未知的函数: {function_name}"}
                
            results.append({
                "tool_call_id": tool_call.id,
                "function_name": function_name,
                "result": result
            })
        except Exception as e:
            results.append({
                "tool_call_id": tool_call.id,
                "function_name": function_name,
                "error": str(e)
            })
    
    return results

async def demo_tool_functions():
    """演示 LLM 工具调用功能"""
    
    logger = logging.getLogger(__name__)
    logger.info(f"开始 LLM 工具调用演示，使用模型: {DEFAULT_REASONING_MODEL}")
    
    try:
        # 初始化 ModelManager
        model_manager = ModelManager()
        
        # 注册推理模型配置
        model_manager.register_model(ModelConfig(
            name=DEFAULT_REASONING_MODEL,
            model_type="api",
            api_base=DEFAULT_LLM_API_BASE,
            api_key=DEFAULT_LLM_API_KEY
        ))
        
        # 初始化推理引擎
        engine = ReasoningLLMEngine(model_manager, model_name=DEFAULT_REASONING_MODEL)       
        
        # 创建输出目录
        output_dir = script_dir.parent / "work_dir" / "output" / "tools_demo"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置系统提示词，告诉模型它可以使用工具
        engine.set_system_prompt(
            "你是一个智能助手，可以使用提供的工具来帮助用户解决问题。"
            "当需要获取信息或执行操作时，应该优先使用可用的工具，而不是生成可能不准确的回答。"
            "请在回答中使用中文。"
        )
        
        # 示例1：天气查询
        logger.info("开始天气查询示例")
        print(f"\n=== 示例1：使用工具查询天气 ===")
        engine.add_message(
            role="user",
            content="北京今天天气怎么样？顺便也告诉我上海的天气，并把温度转换成华氏度。",
            metadata={"request_type": "weather_query"}
        )
        
        # 使用工具调用参数
        response = await engine.get_response(
            temperature=0.6,
            tools=tools,  # 传递工具配置
            tool_choice="auto"  # 让模型自动决定是否使用工具
        )
        
        print("\n回答结果:")
        print(response)
        
        # 处理模型的工具调用请求
        last_message = engine.messages[-1]  # 获取最后一条消息
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            print("\n检测到工具调用请求，正在处理...")
            tool_results = handle_tool_calls(last_message.tool_calls)
            
            # 将工具调用结果发送回模型
            print("\n工具调用结果:")
            for result in tool_results:
                print(f"- {result['function_name']}: {result['result']}")
            
            # 添加工具响应消息
            engine.add_message(
                role="tool",
                content=json.dumps(tool_results, ensure_ascii=False, indent=2),
                metadata={"tools_used": [result["function_name"] for result in tool_results]}
            )
            
            # 获取模型的最终回答
            final_response = await engine.get_response(temperature=0.6)
            print("\n最终回答:")
            print(final_response)
        
        # 示例2：数据库搜索和计算
        logger.info("开始数据库搜索和计算示例")
        print("\n=== 示例2：数据库搜索和计算 ===")
        engine.add_message(
            role="user",
            content="我想找一些关于机器学习的资料，另外，帮我计算15乘以27等于多少？",
            metadata={"request_type": "search_and_calculate"}
        )
        
        # 使用工具调用
        response = await engine.get_response(
            temperature=0.6,
            tools=tools,
            tool_choice="auto"
        )
        
        print("\n回答结果:")
        print(response)
        
        # 处理模型的工具调用请求
        last_message = engine.messages[-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            print("\n检测到工具调用请求，正在处理...")
            tool_results = handle_tool_calls(last_message.tool_calls)
            
            # 将工具调用结果发送回模型
            print("\n工具调用结果:")
            for result in tool_results:
                print(f"- {result['function_name']}: {result['result']}")
            
            # 添加工具响应消息
            engine.add_message(
                role="tool",
                content=json.dumps(tool_results, ensure_ascii=False, indent=2),
                metadata={"tools_used": [result["function_name"] for result in tool_results]}
            )
            
            # 获取模型的最终回答
            final_response = await engine.get_response(temperature=0.6)
            print("\n最终回答:")
            print(final_response)
        
        # 示例3：多轮对话
        logger.info("开始多轮对话示例")
        print("\n=== 示例3：多轮对话 ===")
        engine.add_message(
            role="user",
            content="我还想知道更多关于自然语言处理的内容",
            metadata={"request_type": "follow_up_search"}
        )
        
        # 使用工具调用
        response = await engine.get_response(
            temperature=0.6,
            tools=tools,
            tool_choice="auto"
        )
        
        print("\n回答结果:")
        print(response)
        
        # 处理多轮对话中的工具调用
        last_message = engine.messages[-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            print("\n检测到工具调用请求，正在处理...")
            tool_results = handle_tool_calls(last_message.tool_calls)
            
            # 将工具调用结果发送回模型
            print("\n工具调用结果:")
            for result in tool_results:
                print(f"- {result['function_name']}: {result['result']}")
            
            # 添加工具响应消息
            engine.add_message(
                role="tool",
                content=json.dumps(tool_results, ensure_ascii=False, indent=2),
                metadata={"tools_used": [result["function_name"] for result in tool_results]}
            )
            
            # 获取模型的最终回答
            final_response = await engine.get_response(temperature=0.6)
            print("\n最终回答:")
            print(final_response)
        
        # 保存对话历史
        save_path = output_dir / "tools_chat_history.json"
        engine.save_chat_history_to_json(str(save_path))
        logger.info(f"对话历史已保存至: {save_path}")
        print(f"\n对话历史已保存至: {save_path}")
        
        logger.info("LLM 工具调用演示完成")
        
    except Exception as e:
        logger.error(f"演示过程中出现错误: {str(e)}")
        logger.exception("详细错误信息:")
        raise

async def async_main():
    """异步主函数"""
    logger = setup_logging()
    logger.info("开始运行 LLM 工具调用演示程序")
    
    try:
        await demo_tool_functions()
        logger.info("演示程序运行完成")
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}")
        raise

def main():
    """同步主函数入口"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main() 