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
        self.last_content = ""
    
    def _process_stream_message(self, content):
        """处理流式消息的内部方法"""
        new_content = content[len(self.last_content):]
        self.last_content = content       
        return new_content
    
    def emit(self, record):
        try:
            msg = self.format(record)
            
            with open(self.filename, 'a', encoding='utf-8') as f:
                if record.getMessage().startswith('\r'):
                    content = record.getMessage().replace('\r', '')
                    new_content = self._process_stream_message(content)
                    f.write(new_content)
                else:
                    f.write(msg + '\n')
                    self.last_content = ""
                    
        except Exception:
            self.handleError(record)

async def demo_stream_reasoning():
    """演示 ReasoningEngine 的流式输出功能"""
    
    output_dir = project_root / "work_dir" / "output" / "stream_demo"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    async def handle_stream_output(question, logger, engine):
        """处理流式输出的辅助函数"""
        logger.info(f"提问: {question}")

        current_line = ""
        
        async for chunk in engine.get_stream_response(temperature=0.7):
            current_line += chunk
            logger.info(f"\r{current_line}")
        
        logger.info("-" * 50)

    async def setup_logging_handler(output_dir):
        """设置日志处理器"""
        log_file = output_dir / "stream_demo.log"
        handler = StreamLineHandler(log_file)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        
        logger = logging.getLogger(__name__)
        logger.addHandler(handler)
        logger.info(f"开始流式输出演示，使用模型: {DEFAULT_REASONING_MODEL}")
        logger.info(f"日志文件路径: {log_file}")
        
        return logger, handler

    async def setup_reasoning_engine():
        """初始化推理引擎"""
        model_manager = ModelManager()
        model_manager.register_model(ModelConfig(
            name=DEFAULT_REASONING_MODEL,
            model_type="api",
            api_base=DEFAULT_LLM_API_BASE,
            api_key=DEFAULT_LLM_API_KEY
        ))
        return ReasoningEngine(model_manager, model_name=DEFAULT_REASONING_MODEL)

    async def run_demo_examples(logger, engine):
        """运行演示示例"""
        examples = [
            {
                "title": "流式代码分析",
                "question": """请分析这段Python代码的实现思路，性能特点和改进建议：
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)""",
                "metadata": {
                    "code_type": "python",
                    "topic": "algorithm",
                    "analysis_type": "code_review"
                }
            },
            {
                "title": "流式算法设计",
                "question": """请设计一个高效的算法来解决以下问题：
给定一个整数数组，找出其中和为特定值的所有不重复数字对。
请详细解释算法思路，并提供Python实现。""",
                "metadata": {
                    "topic": "algorithm_design",
                    "difficulty": "medium"
                }
            }
        ]
        
        for example in examples:
            logger.info(f"开始{example['title']}示例")
            logger.info("-" * 50)
            print(f"\n=== {example['title']} ===")
            
            engine.add_message(
                role="user",
                content=example["question"],
                metadata=example["metadata"]
            )
            
            await handle_stream_output(example["question"], logger, engine)

    try:
        logger, handler = await setup_logging_handler(output_dir)
        engine = await setup_reasoning_engine()
        
        # 运行主要示例
        await run_demo_examples(logger, engine)
        
        # 运行交互式对话示例
        logger.info("开始流式交互式对话示例")
        logger.info("-" * 50)
        print("\n=== 示例3：流式交互式对话 ===")
        
        follow_up_questions = [
            "在上面的算法中，如果要处理重复元素，需要做什么修改？",
            "如果输入数组非常大，如何优化性能？",
        ]
        
        for question in follow_up_questions:
            print(f"\n问题: {question}")
            engine.add_message("user", question)
            await handle_stream_output(question, logger, engine)
        
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
        logger.removeHandler(handler)

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