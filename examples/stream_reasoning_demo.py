import os
import sys
from pathlib import Path
import asyncio
import logging

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from datamind import setup_logging
from datamind.core.reasoning import ReasoningEngine
from datamind.llms.model_manager import ModelManager, ModelConfig
from datamind.config.settings import (
    DEFAULT_REASONING_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE
)

class StreamLineHandler(logging.Handler):
    """处理流式输出的自定义日志处理器"""
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.stream_position = None
        self.last_content = ""
    
    def emit(self, record):
        try:
            msg = self.format(record)
            
            # 处理流式消息
            if record.getMessage().startswith('\r'):
                # 提取实际内容，移除时间戳和日志级别等信息
                content = record.getMessage().replace('\r', '')
                
                # 只处理新增的内容
                new_content = content[len(self.last_content):]
                self.last_content = content
                
                with open(self.filename, 'a', encoding='utf-8') as f:
                    f.write(new_content)
            else:
                # 普通日志消息
                with open(self.filename, 'a', encoding='utf-8') as f:
                    f.write(msg + '\n')
                # 重置流式输出状态
                self.last_content = ""
                
        except Exception:
            self.handleError(record)

async def demo_stream_reasoning():
    """演示 ReasoningEngine 的流式输出功能"""
    
    # 设置输出目录和日志文件
    output_dir = project_root / "work_dir" / "output" / "stream_demo"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = output_dir / "stream_demo.log"
    stream_handler = StreamLineHandler(log_file)
    stream_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    
    logger = logging.getLogger(__name__)
    logger.addHandler(stream_handler)
    logger.info(f"开始流式输出演示，使用模型: {DEFAULT_REASONING_MODEL}")
    logger.info(f"日志文件路径: {log_file}")
    
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
        engine = ReasoningEngine(model_manager, model_name=DEFAULT_REASONING_MODEL)
        
        # 示例1：流式代码分析
        logger.info("开始流式代码分析示例")
        logger.info("-" * 50)
        print(f"\n=== 示例1：使用 {DEFAULT_REASONING_MODEL} 进行流式代码分析 ===")
        
        question = "请分析这段Python代码的实现思路，性能特点和改进建议：\n" \
                  "def fibonacci(n):\n" \
                  "    if n <= 1:\n" \
                  "        return n\n" \
                  "    return fibonacci(n-1) + fibonacci(n-2)"
        
        engine.add_message(
            role="user",
            content=question,
            metadata={
                "code_type": "python",
                "topic": "algorithm",
                "analysis_type": "code_review"
            }
        )
        
        logger.info(f"提问: {question}")
        print("\n实时分析结果:")
        current_line = ""
        thinking_content = ""
        in_thinking = False
        
        async for chunk in engine.get_stream_response(
            temperature=0.7
        ):
            print(chunk, end="", flush=True)
            current_line += chunk
            
            # 处理推理内容
            if "<think>" in chunk:
                in_thinking = True
                thinking_content = ""
            elif "</think>" in chunk:
                in_thinking = False
                if thinking_content:
                    logger.info(f"\n推理过程:\n{thinking_content}\n")
            elif in_thinking:
                thinking_content += chunk
            
            # 只发送增量更新
            logger.info(f"\r{current_line}")
        
        logger.info("-" * 50)
        print("\n")
        
        # 示例2：流式算法设计
        logger.info("开始流式算法设计示例")
        logger.info("-" * 50)
        print("\n=== 示例2：流式算法设计讨论 ===")
        
        question = "请设计一个高效的算法来解决以下问题：\n" \
                  "给定一个整数数组，找出其中和为特定值的所有不重复数字对。\n" \
                  "请详细解释算法思路，并提供Python实现。"
        
        engine.add_message(
            role="user",
            content=question,
            metadata={
                "topic": "algorithm_design",
                "difficulty": "medium"
            }
        )
        
        logger.info(f"提问: {question}")
        print("\n实时输出算法设计方案:")
        current_line = ""
        thinking_content = ""
        in_thinking = False
        
        async for chunk in engine.get_stream_response(
            temperature=0.7
        ):
            print(chunk, end="", flush=True)
            current_line += chunk
            
            # 处理推理内容
            if "<think>" in chunk:
                in_thinking = True
                thinking_content = ""
            elif "</think>" in chunk:
                in_thinking = False
                if thinking_content:
                    logger.info(f"\n推理过程:\n{thinking_content}\n")
            elif in_thinking:
                thinking_content += chunk
            
            # 只发送增量更新
            logger.info(f"\r{current_line}")
        
        logger.info("-" * 50)
        print("\n")
        
        # 示例3：流式交互式对话
        logger.info("开始流式交互式对话示例")
        logger.info("-" * 50)
        print("\n=== 示例3：流式交互式对话 ===")
        
        questions = [
            "在上面的算法中，如果要处理重复元素，需要做什么修改？",
            "如果输入数组非常大，如何优化性能？",
        ]
        
        for question in questions:
            print(f"\n问题: {question}")
            engine.add_message("user", question)
            
            logger.info(f"提问: {question}")
            print("实时回答:")
            current_line = ""
            thinking_content = ""
            in_thinking = False
            
            async for chunk in engine.get_stream_response(
                temperature=0.7
            ):
                print(chunk, end="", flush=True)
                current_line += chunk
                
                # 处理推理内容
                if "<think>" in chunk:
                    in_thinking = True
                    thinking_content = ""
                elif "</think>" in chunk:
                    in_thinking = False
                    if thinking_content:
                        logger.info(f"\n推理过程:\n{thinking_content}\n")
                elif in_thinking:
                    thinking_content += chunk
                
                # 只发送增量更新
                logger.info(f"\r{current_line}")
            
            logger.info("-" * 50)
            print("\n")
        
        # 保存对话历史
        save_path = output_dir / "stream_chat_history.json"
        
        if engine.save_chat_history_to_json(str(save_path)):
            logger.info(f"对话历史已保存至: {save_path}")
            print(f"\n完整对话历史已保存至: {save_path}")
        
        logger.info("流式输出完成")
        
    except Exception as e:
        logger.error(f"演示过程中出现错误: {str(e)}")
        logger.exception("详细错误信息:")
        raise
    finally:
        logger.removeHandler(stream_handler)

async def async_main():
    """异步主函数"""
    logger = setup_logging()
    logger.info("开始运行流式输出演示程序")
    
    try:
        await demo_stream_reasoning()
        logger.info("演示程序运行完成")
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}")
        raise

def main():
    """同步主函数入口"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main() 