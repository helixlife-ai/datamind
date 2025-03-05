import os
import sys
from pathlib import Path
import asyncio
import logging
import json

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

async def demo_reasoning_engine():
    """演示 ReasoningEngine 的主要功能"""
    
    logger = logging.getLogger(__name__)
    logger.info(f"开始 ReasoningEngine 演示，使用模型: {DEFAULT_REASONING_MODEL}")
    
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
        output_dir = script_dir.parent / "work_dir" / "output" / "reasoning_demo"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 示例1：代码分析
        logger.info("开始代码分析示例")
        print(f"\n=== 示例1：使用 {DEFAULT_REASONING_MODEL} 进行代码分析 ===")
        engine.add_message(
            role="user",
            content="请分析这段代码的实现思路和可能存在的问题：\n"
                    "def find_duplicates(arr):\n"
                    "    seen = []\n"
                    "    duplicates = []\n"
                    "    for num in arr:\n"
                    "        if num in seen:\n"
                    "            duplicates.append(num)\n"
                    "        seen.append(num)\n"
                    "    return duplicates",
            metadata={
                "code_type": "python",
                "topic": "algorithm",
                "analysis_type": "code_review",
                "model": DEFAULT_REASONING_MODEL
            }
        )
        
        response = await engine.get_response(
            temperature=0.6
        )
        print("\n分析结果:")
        # 直接打印响应内容
        print(response)
        
        # 示例2：性能优化
        logger.info("开始性能优化示例")
        print("\n=== 示例2：性能优化建议 ===")
        engine.add_message(
            role="user",
            content="请提供一个优化后的实现，重点考虑：\n"
                    "1. 时间复杂度\n"
                    "2. 空间效率\n"
                    "3. 代码可读性",
            metadata={
                "request_type": "optimization",
                "focus": ["performance", "readability"],
                "model": DEFAULT_REASONING_MODEL
            }
        )
        
        response = await engine.get_response(
            temperature=0.6
        )
        print("\n优化建议:")
        # 直接打印响应内容
        print(response)
        
        # 保存对话历史
        save_path = output_dir / "code_analysis_history.json"
        engine.save_chat_history_to_json(str(save_path))
        logger.info(f"对话历史已保存至: {save_path}")
        print(f"\n对话历史已保存至: {save_path}")
        
        # 展示如何加载和查看历史
        print("\n=== 加载历史对话 ===")
        engine.clear_history()
        if engine.load_chat_history_from_json(str(save_path)):
            print("\n已加载的对话历史:")
            for msg in engine.get_chat_history():
                print(f"\n[{msg['role']}] ({msg['timestamp']})")
                print("内容:", msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content'])
                if msg['metadata']:
                    print("元数据:", msg['metadata'])
                    
        logger.info("ReasoningEngine 演示完成")
        
    except Exception as e:
        logger.error(f"演示过程中出现错误: {str(e)}")
        logger.exception("详细错误信息:")
        raise

async def async_main():
    """异步主函数"""
    logger = setup_logging()
    logger.info("开始运行 ReasoningEngine 演示程序")
    
    try:
        await demo_reasoning_engine()
        logger.info("演示程序运行完成")
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}")
        raise

def main():
    """同步主函数入口"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main() 