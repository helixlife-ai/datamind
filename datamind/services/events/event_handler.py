import json
import logging
import asyncio
from pathlib import Path
from .event_types import AlchemyEventType

class AlchemyEventHandler:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    async def on_process_started(self, data):
        """处理开始事件"""
        self.logger.info(f"=== 炼丹开始 [ID: {data['alchemy_id']}] ===")
        self.logger.info(f"当前迭代: {data['iteration']}")
        self.logger.info(f"处理查询: {data['query']}")
        
        # 添加输入目录信息
        if 'input_dirs' in data and data['input_dirs']:
            self.logger.info(f"使用输入目录: {', '.join(data['input_dirs'])}")

    async def on_intent_parsed(self, data):
        """意图解析事件"""
        self.logger.info("\n=== 意图解析完成 ===")
        self.logger.info("解析结果:\n%s", 
            json.dumps(data['parsed_intent'], indent=2, ensure_ascii=False))

    async def on_plan_built(self, data):
        """计划构建事件"""
        self.logger.info("\n=== 检索计划已构建 ===")
        self.logger.info("检索计划:\n%s", 
            json.dumps(data['search_plan'], indent=2, ensure_ascii=False))

    async def on_search_executed(self, data):
        """搜索执行事件"""
        self.logger.info("\n=== 搜索已执行 ===")
        stats = data.get('search_results', {}).get('stats', {})
        self.logger.info(f"搜索结果: 总计 {stats.get('total', 0)} 条记录")

    async def on_artifact_generated(self, data):
        """制品生成事件"""
        self.logger.info("\n=== 制品已生成 ===")
        self.logger.info(f"制品文件: {Path(data['artifact_path']).name}")

    async def on_optimization_suggested(self, data):
        """优化建议事件"""
        self.logger.info("\n=== 收到优化建议 ===")
        self.logger.info(f"原始查询: {data['original_query']}")
        self.logger.info(f"优化建议: {data['optimization_query']}")

    async def on_process_completed(self, data):
        """处理完成事件"""
        self.logger.info("\n=== 炼丹流程完成 [ID: {data['alchemy_id']}] ===")
        results = data.get('results', {})
        
        if results.get('status') == 'success':
            artifacts = results.get('results', {}).get('artifacts', [])
            if artifacts:
                self.logger.info("\n生成的制品文件:")
                for artifact_path in artifacts:
                    self.logger.info(f"- {Path(artifact_path).name}")
                    
            optimization_suggestions = results.get('results', {}).get('optimization_suggestions', [])
            if optimization_suggestions:
                self.logger.info("\n优化建议和结果:")
                for suggestion in optimization_suggestions:
                    self.logger.info(f"- 优化建议: {suggestion['suggestion']}")
                    self.logger.info(f"  来源: {suggestion['source']}")
                    self.logger.info(f"  生成时间: {suggestion['timestamp']}")
                    if suggestion.get('artifacts'):
                        self.logger.info("  生成的制品:")
                        for artifact in suggestion['artifacts']:
                            self.logger.info(f"    - {Path(artifact).name}")
                    self.logger.info("---")

    async def on_error_occurred(self, data):
        """错误事件"""
        self.logger.error(f"\n=== 处理过程中发生错误 ===")
        self.logger.error(f"错误信息: {data['error']}")
        self.logger.error(f"查询内容: {data['query']}")

    async def on_cancellation_requested(self, data):
        """取消请求事件"""
        self.logger.info(f"\n=== 收到取消请求 [ID: {data['alchemy_id']}] ===")
        self.logger.info(f"时间: {data['timestamp']}")

    async def on_process_cancelled(self, data):
        """处理取消事件"""
        self.logger.info(f"\n=== 处理已取消 [ID: {data['alchemy_id']}] ===")
        self.logger.info(f"当前步骤: {data['current_step']}")
        self.logger.info(f"时间: {data['timestamp']}")

    async def on_process_checkpoint(self, data):
        """检查点事件"""
        self.logger.info(f"\n=== 已创建检查点 [ID: {data['alchemy_id']}] ===")
        self.logger.info(f"当前步骤: {data['current_step']}")
        self.logger.info(f"时间: {data['timestamp']}")

    async def handle_keyboard_interrupt(self, alchemy):
        """处理键盘中断事件"""
        self.logger.info("处理键盘中断，尝试保存检查点...")
        
        try:
            # 请求取消处理
            await alchemy.cancel_process()
            
            # 显示任务目录结构，帮助调试
            work_dir = Path(alchemy.work_dir)
            self.logger.info(f"工作目录: {work_dir}")
            
            # 使用正确的任务目录路径 - alchemy_dir在DataMindAlchemy中定义
            task_dir = alchemy.alchemy_dir
            self.logger.info(f"任务目录: {task_dir}")
            
            # 检查任务目录是否存在
            if task_dir.exists():
                self.logger.info(f"任务目录存在: {task_dir}")
                # 列出任务目录内容
                task_files = list(task_dir.glob("*"))
                self.logger.info(f"任务目录文件: {[str(f.name) for f in task_files]}")
                
                # 打印目录路径以确认正确结构
                self.logger.info(f"目录结构: {str(task_dir.relative_to(work_dir.parent))}")
                
                # 尝试从resume_info.json读取额外信息
                resume_info_path = task_dir / "resume_info.json"
                if resume_info_path.exists():
                    with open(resume_info_path, 'r', encoding='utf-8') as f:
                        resume_info = json.load(f)
                        self.logger.info(f"恢复信息: {resume_info}")
            else:
                self.logger.warning(f"任务目录不存在: {task_dir}")
                
            self.logger.info("中断处理完成")
            return True
        except Exception as e:
            self.logger.error(f"处理中断时发生错误: {str(e)}")
            return False

    def register_events(self, alchemy: "DataMindAlchemy"):
        """注册所有事件处理函数"""
        alchemy.subscribe(AlchemyEventType.PROCESS_STARTED, lambda data: asyncio.create_task(self.on_process_started(data)))
        alchemy.subscribe(AlchemyEventType.INTENT_PARSED, lambda data: asyncio.create_task(self.on_intent_parsed(data)))
        alchemy.subscribe(AlchemyEventType.PLAN_BUILT, lambda data: asyncio.create_task(self.on_plan_built(data)))
        alchemy.subscribe(AlchemyEventType.SEARCH_EXECUTED, lambda data: asyncio.create_task(self.on_search_executed(data)))
        alchemy.subscribe(AlchemyEventType.ARTIFACT_GENERATED, lambda data: asyncio.create_task(self.on_artifact_generated(data)))
        alchemy.subscribe(AlchemyEventType.OPTIMIZATION_SUGGESTED, lambda data: asyncio.create_task(self.on_optimization_suggested(data)))
        alchemy.subscribe(AlchemyEventType.PROCESS_COMPLETED, lambda data: asyncio.create_task(self.on_process_completed(data)))
        alchemy.subscribe(AlchemyEventType.ERROR_OCCURRED, lambda data: asyncio.create_task(self.on_error_occurred(data)))
        alchemy.subscribe(AlchemyEventType.CANCELLATION_REQUESTED, lambda data: asyncio.create_task(self.on_cancellation_requested(data)))
        alchemy.subscribe(AlchemyEventType.PROCESS_CANCELLED, lambda data: asyncio.create_task(self.on_process_cancelled(data)))
        alchemy.subscribe(AlchemyEventType.PROCESS_CHECKPOINT, lambda data: asyncio.create_task(self.on_process_checkpoint(data))) 