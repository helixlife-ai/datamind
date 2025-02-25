import sys
from pathlib import Path
import asyncio
import logging
import time
from typing import Optional

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from datamind import setup_logging
from datamind.core.artifact import ArtifactGenerator
from datamind.core.reasoning import ReasoningEngine
from datamind.llms.model_manager import ModelManager, ModelConfig
from datamind.config.settings import (
    DEFAULT_REASONING_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE
)

class ArtifactProgressMonitor:
    """制品生成进度监控器"""
    
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.start_time = None
        self.last_update = 0
        
    def start(self):
        """开始监控"""
        self.start_time = time.time()
        print("\n=== 开始监控制品生成进度 ===")
        print("时间     | 状态 | 临时文件大小 | 详情")
        print("-" * 50)
    
    def check_progress(self, artifact_dir: Optional[Path]) -> bool:
        """检查生成进度
        
        Args:
            artifact_dir: 制品目录路径
            
        Returns:
            bool: 是否需要继续监控
        """
        if not artifact_dir or not artifact_dir.exists():
            return True
            
        current_time = time.time()
        if current_time - self.last_update < 1:  # 限制更新频率
            return True
            
        self.last_update = current_time
        elapsed = int(current_time - self.start_time)
        
        # 检查临时HTML文件
        temp_html = artifact_dir / "temp_content.html"
        if temp_html.exists():
            size = temp_html.stat().st_size
            print(f"{elapsed:02d}s      | 生成中 | {size:6d}B     | 正在生成HTML内容")
            
        # 检查是否已完成
        final_html = list(artifact_dir.glob("*.html"))
        if final_html and not any(f.name.endswith('_error.html') for f in final_html):
            print(f"{elapsed:02d}s      | 完成   | {final_html[0].stat().st_size:6d}B     | 生成成功")
            return False
            
        # 检查是否出错
        error_file = artifact_dir / "generation_error.json"
        if error_file.exists():
            print(f"{elapsed:02d}s      | 失败   | -          | 生成失败，查看错误日志")
            return False
            
        return True

async def demo_artifact_generator():
    """演示 ArtifactGenerator 的主要功能"""
    
    logger = logging.getLogger(__name__)
    logger.info("开始 ArtifactGenerator 演示")
    
    try:
        # 初始化 ModelManager 和 ReasoningEngine
        model_manager = ModelManager()
        model_manager.register_model(ModelConfig(
            name=DEFAULT_REASONING_MODEL,
            model_type="api",
            api_base=DEFAULT_LLM_API_BASE,
            api_key=DEFAULT_LLM_API_KEY
        ))
        
        reasoning_engine = ReasoningEngine(model_manager, model_name=DEFAULT_REASONING_MODEL)
        
        # 创建工作目录
        work_dir = project_root / "work_dir"
        work_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化 ArtifactGenerator
        generator = ArtifactGenerator(
            work_dir=str(work_dir),
            reasoning_engine=reasoning_engine,
            logger=logger
        )
        
        # 准备示例文件
        example_files = [
            script_dir / "test_basic_search.py",
            script_dir / "reasoning_engine_demo.py"
        ]
        
        print("\n=== 开始生成代码分析制品 ===")
        
        # 创建进度监控器
        monitor = ArtifactProgressMonitor(work_dir)
        monitor.start()
        
        # 启动异步任务
        generation_task = asyncio.create_task(generator.generate_artifact(
            context_files=example_files,
            output_name="code_analysis",
            query="Python代码分析报告",
            is_primary=True,
            metadata={
                "analysis_type": "code_review",
                "files_analyzed": [f.name for f in example_files],
                "title": "Python代码分析报告"  # 保留title作为元数据
            }
        ))
        
        # 监控生成进度
        artifact_dir = None
        while True:
            if not artifact_dir:
                # 查找最新的制品目录
                artifacts = list(work_dir.glob("artifacts/code_analysis_*"))
                if artifacts:
                    artifact_dir = max(artifacts, key=lambda p: p.stat().st_mtime)
            
            if not monitor.check_progress(artifact_dir):
                break
                
            await asyncio.sleep(1)
        
        # 等待生成完成
        output_path = await generation_task
        
        if output_path:
            print(f"\n✓ 成功生成HTML制品: {output_path}")
            print("\n制品内容包括:")
            print("- 代码结构分析")
            print("- 主要功能说明")
            print("- 代码质量评估")
            print("- 改进建议")
            
            # 显示生成统计信息
            success_file = Path(output_path).parent / "generation_success.json"
            if success_file.exists():
                import json
                stats = json.loads(success_file.read_text(encoding='utf-8'))
                print("\n生成统计:")
                print(f"- 总响应长度: {stats.get('total_chunks', 0)} 字符")
                print(f"- 最终HTML大小: {stats.get('final_html_size', 0)} 字符")
                print(f"- 生成时间: {stats.get('timestamp', '')}")
        else:
            print("\n✗ 制品生成失败，请查看日志了解详细信息")
        
        # 演示错误处理
        print("\n=== 测试错误处理 ===")
        monitor.start()  # 重置监控器
        
        non_existent_file = script_dir / "non_existent.py"
        error_output = await generator.generate_artifact(
            context_files=[non_existent_file],
            output_name="error_test",
            query="错误处理测试",
            is_primary=False,
            metadata={
                "test_type": "error_handling",
                "title": "错误处理测试"  # 保留title作为元数据
            }
        )
        
        if not error_output:
            print("\n✓ 错误处理测试成功 - 正确处理了不存在的文件")
        
        logger.info("ArtifactGenerator 演示完成")
        
    except Exception as e:
        logger.error(f"演示过程中出现错误: {str(e)}")
        logger.exception("详细错误信息:")
        raise

async def async_main():
    """异步主函数"""
    logger = setup_logging()
    logger.info("开始运行 ArtifactGenerator 演示程序")
    
    try:
        await demo_artifact_generator()
        logger.info("演示程序运行完成")
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}")
        raise

def main():
    """同步主函数入口"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main() 