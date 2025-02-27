import json
import time
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional
from ..core.reasoning import ReasoningEngine
from ..llms.model_manager import ModelManager, ModelConfig
from ..core.search import SearchEngine
from ..core.planner import SearchPlanner
from ..core.executor import SearchPlanExecutor
from ..core.processor import DataProcessor, FileCache
from ..core.parser import IntentParser
from ..core.feedback_optimizer import FeedbackOptimizer
from ..core.artifact import ArtifactGenerator
from ..config.settings import (
    DEFAULT_REASONING_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE
)
from ..utils.stream_logger import StreamLineHandler
from datetime import datetime
from enum import Enum, auto
import asyncio

class AlchemyEventType(Enum):
    """炼丹流程事件类型"""
    PROCESS_STARTED = auto()
    INTENT_PARSED = auto()
    PLAN_BUILT = auto()
    SEARCH_EXECUTED = auto()
    ARTIFACT_GENERATED = auto()
    OPTIMIZATION_SUGGESTED = auto()
    PROCESS_COMPLETED = auto()
    ERROR_OCCURRED = auto()
    CANCELLATION_REQUESTED = auto()
    PROCESS_CANCELLED = auto()
    PROCESS_CHECKPOINT = auto()  # 处理过程中的检查点事件

class EventBus:
    """事件总线，用于事件发布和订阅"""
    
    def __init__(self):
        self.subscribers = {}
        
    def subscribe(self, event_type: AlchemyEventType, callback: Callable):
        """订阅事件"""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
        
    def unsubscribe(self, event_type: AlchemyEventType, callback: Callable):
        """取消订阅事件"""
        if event_type in self.subscribers and callback in self.subscribers[event_type]:
            self.subscribers[event_type].remove(callback)
            
    async def publish(self, event_type: AlchemyEventType, data: Any = None):
        """发布事件"""
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)

class DataMindAlchemy:
    """数据炼丹工作流封装类"""
    
    def __init__(self, work_dir: Path = None, model_manager: ModelManager = None, logger: logging.Logger = None, alchemy_id: str = None, alchemy_manager=None):
        """初始化数据炼丹工作流
        
        Args:
            work_dir: 工作目录，默认为None时会使用默认路径
            model_manager: 模型管理器实例，用于推理引擎
            logger: 日志记录器实例，用于记录日志
            alchemy_id: 炼丹ID，默认为None时会自动生成
        """
        # 初始化事件总线
        self.event_bus = EventBus()
        
        # 初始化工作目录
        if work_dir is None:
            work_dir = Path("work_dir") / "data_alchemy"
        self.work_dir = work_dir
        self.work_dir.mkdir(exist_ok=True, parents=True)
        
        self.alchemy_id = alchemy_id or time.strftime("%Y%m%d_%H%M%S")
        
        # 初始化日志记录器
        self.logger = logger or logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # 创建控制台处理器
        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
        
        # 创建日志目录
        log_dir = self.work_dir / "logs"
        log_dir.mkdir(exist_ok=True, parents=True)
        
        # 只使用流式日志处理器，它已经包含了文件写入功能
        if not any(isinstance(h, StreamLineHandler) for h in self.logger.handlers):
            log_file = log_dir / f"alchemy_{self.alchemy_id}.log"
            stream_handler = StreamLineHandler(str(log_file))
            stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(stream_handler)
        
        # 初始化模型管理器
        self.model_manager = model_manager or ModelManager(logger=self.logger)
        
        # 注册默认推理模型配置
        if not model_manager:  # 只有在没有传入model_manager时才注册
            self.model_manager.register_model(ModelConfig(
                name=DEFAULT_REASONING_MODEL,
                model_type="api",
                api_base=DEFAULT_LLM_API_BASE,
                api_key=DEFAULT_LLM_API_KEY
            ))
        
        # 初始化所有必要的目录结构
        self.alchemy_dir = self.work_dir / "alchemy_runs" / f"alchemy_{self.alchemy_id}"
        self.search_dir = self.alchemy_dir / "search"
        self.iterations_dir = self.search_dir / "iterations"
        
        # 创建所有必要的目录
        for directory in [self.alchemy_dir, self.search_dir, self.iterations_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            
        # 初始化当前工作目录
        self.current_work_dir = None
        
        # 加载已有的状态信息(如果存在)
        self.status_info = self._load_status()
        if self.status_info:
            self.logger.info(f"已加载alchemy_id={self.alchemy_id}的现有数据，最新迭代为{self.status_info['latest_iteration']}")
        
        # 添加取消标志
        self._cancel_requested = False
        self._current_step = None
        
        # 添加alchemy_manager
        self.alchemy_manager = alchemy_manager
        if self.alchemy_manager:
            # 向管理器注册此任务
            self.alchemy_manager.register_task(self.alchemy_id, "", "新建任务")

    def _init_work_dir(self, work_dir: Path) -> Path:
        """初始化工作目录"""
        if work_dir is None:
            work_dir = Path("data_alchemy") 
        work_dir.mkdir(exist_ok=True, parents=True)                
        return work_dir
        
    def _create_alchemy_dir(self) -> Path:
        """创建炼丹目录"""
        alchemy_dir = self.work_dir / "alchemy_runs" / f"alchemy_{self.alchemy_id}"
        alchemy_dir.mkdir(parents=True, exist_ok=True)
        return alchemy_dir
        
    def _init_components(self, db_path: str):
        """初始化组件
        
        现在使用当前迭代目录作为组件的工作目录
        """
        # 首先初始化推理引擎
        reasoning_engine = ReasoningEngine(
            model_manager=self.model_manager,
            model_name=DEFAULT_REASONING_MODEL,
            logger=self.logger,
            history_file=self.current_work_dir / "reasoning_history.json"  # 修改为当前迭代目录
        )
        
        # 其他组件初始化
        search_engine = SearchEngine(
            db_path=db_path,
            logger=self.logger
        )
        
        intent_parser = IntentParser(
            work_dir=str(self.current_work_dir),  # 修改为当前迭代目录
            reasoning_engine=reasoning_engine,
            logger=self.logger
        )
        
        planner = SearchPlanner(
            work_dir=str(self.current_work_dir),  # 修改为当前迭代目录
            logger=self.logger
        )
        
        executor = SearchPlanExecutor(
            search_engine=search_engine,
            work_dir=str(self.current_work_dir),  # 修改为当前迭代目录
            logger=self.logger
        )
        
        # artifact_generator使用alchemy_dir，因为它需要访问artifacts目录
        artifact_generator = ArtifactGenerator(
            alchemy_dir=str(self.alchemy_dir),
            reasoning_engine=reasoning_engine,
            logger=self.logger
        )
        
        feedback_optimizer = FeedbackOptimizer(
            work_dir=str(self.current_work_dir),  # 修改为当前迭代目录
            reasoning_engine=reasoning_engine,
            logger=self.logger
        )        
        
        # 记录组件配置
        components_config = {
            "iteration": self._get_next_iteration() - 1,  # 当前迭代号
            "work_dir": str(self.current_work_dir),
            "components": {
                "reasoning_engine": {
                    "history_file": str(self.current_work_dir / "reasoning_history.json")
                },
                "search_engine": {
                    "db_path": db_path
                },
                "intent_parser": {
                    "work_dir": str(self.current_work_dir)
                },
                "planner": {
                    "work_dir": str(self.current_work_dir)
                },
                "executor": {
                    "work_dir": str(self.current_work_dir)
                },
                "artifact_generator": {
                    "alchemy_dir": str(self.alchemy_dir)
                },
                "feedback_optimizer": {
                    "work_dir": str(self.current_work_dir)
                }
            }
        }
        
        # 保存组件配置
        config_file = self.current_work_dir / "components_config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(components_config, f, ensure_ascii=False, indent=2)
        
        return {
            'reasoning_engine': reasoning_engine,
            'intent_parser': intent_parser,
            'planner': planner,
            'executor': executor,
            'artifact_generator': artifact_generator,
            'feedback_optimizer': feedback_optimizer
        }

    def _get_next_iteration(self) -> int:
        """获取下一个迭代版本号"""
        if not self.iterations_dir.exists():
            return 1
            
        existing_iterations = [int(v.name.split('iter')[-1]) 
                             for v in self.iterations_dir.glob("iter*") 
                             if v.name.startswith('iter')]
        return max(existing_iterations, default=0) + 1

    async def process(
        self,
        query: str,
        input_dirs: list = None,
        context: Dict = None
    ) -> Dict:
        """执行数据炼丹工作流
        
        Args:
            query: 查询文本
            input_dirs: 输入目录列表
            context: 上下文数据
            
        Returns:
            Dict: 处理结果
        """
        try:
            # 重置取消标志
            self._cancel_requested = False
            
            # 确定当前迭代版本
            iteration = self._get_next_iteration()
            current_iter_dir = self.iterations_dir / f"iter{iteration}"
            current_iter_dir.mkdir(exist_ok=True)
            
            # 更新工作目录到当前迭代目录
            self.current_work_dir = current_iter_dir
            
            # 记录当前处理信息
            self.logger.info(f"开始处理 alchemy_id={self.alchemy_id} 的第{iteration}次迭代")
            
            # 设置当前步骤
            self._current_step = "initialization"
            
            # 发布处理开始事件
            await self.event_bus.publish(
                AlchemyEventType.PROCESS_STARTED, 
                {
                    "alchemy_id": self.alchemy_id,
                    "iteration": iteration,
                    "query": query,
                    "context": context
                }
            )
            
            # 检查是否请求取消
            await self._check_cancellation()
            
            # 处理上下文
            if context:
                context_file = current_iter_dir / "context.json"
                with open(context_file, 'w', encoding='utf-8') as f:
                    json.dump(context, f, ensure_ascii=False, indent=2)
            
            # 准备数据目录
            source_data = current_iter_dir / "source_data"
            source_data.mkdir(exist_ok=True)
            
            # 设置当前步骤
            self._current_step = "prepare_source_data"
            await self._save_checkpoint()
            
            # 检查是否请求取消
            await self._check_cancellation()
            
            # 复制上级source_data
            if context:
                await self._copy_parent_source_data(source_data)
                
            # 复制输入目录
            if input_dirs:
                await self._copy_input_dirs(input_dirs, source_data)
            
            # 设置当前步骤
            self._current_step = "process_data"
            await self._save_checkpoint()
            
            # 检查是否请求取消
            await self._check_cancellation()
            
            # 初始化数据处理
            data_dir = current_iter_dir / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = data_dir / "unified_storage.duckdb"
            cache_file = str(data_dir / "file_cache.pkl")
            
            # 处理数据
            processor = DataProcessor(
                db_path=str(db_path),
                logger=self.logger
            )
            processor.file_cache = FileCache(
                cache_file=cache_file,
                logger=self.logger
            )
            
            if source_data.exists() and any(source_data.iterdir()):
                await self._process_source_data(processor, source_data, db_path)
            
            # 设置当前步骤
            self._current_step = "initialize_components"
            await self._save_checkpoint()
            
            # 检查是否请求取消
            await self._check_cancellation()
            
            # 初始化组件
            self.components = self._init_components(str(db_path))
            
            # 设置当前步骤
            self._current_step = "execute_workflow"
            await self._save_checkpoint()
            
            # 检查是否请求取消
            await self._check_cancellation()
            
            # 执行工作流
            results = await self._execute_workflow(query)
            
            # 设置当前步骤
            self._current_step = "finalize"
            await self._save_checkpoint()
            
            # 检查是否请求取消
            await self._check_cancellation()
            
            # 更新状态信息
            status_info = {
                "alchemy_id": self.alchemy_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "latest_iteration": iteration,
                "iterations": []
            }
            
            status_path = self.alchemy_dir / "status.json"
            if status_path.exists():
                with open(status_path, "r", encoding="utf-8") as f:
                    status_info = json.load(f)
            
            # 更新迭代信息
            iteration_info = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "context": context,
                "path": str(current_iter_dir.relative_to(self.alchemy_dir)),
                "artifacts": results['results'].get('artifacts', []),
                "optimization_suggestions": results['results'].get('optimization_suggestions', [])
            }
            
            status_info["iterations"].append(iteration_info)
            status_info["latest_iteration"] = iteration
            status_info["updated_at"] = datetime.now().isoformat()
            
            with open(status_path, "w", encoding="utf-8") as f:
                json.dump(status_info, f, ensure_ascii=False, indent=2)
                
            # 发布处理完成事件
            await self.event_bus.publish(
                AlchemyEventType.PROCESS_COMPLETED,
                {
                    "alchemy_id": self.alchemy_id,
                    "iteration": iteration,
                    "results": results
                }
            )

            return results
            
        except Exception as e:
            self.logger.error(f"数据炼丹工作流失败: {str(e)}", exc_info=True)
            
            # 尝试保存检查点
            try:
                await self._save_checkpoint()
            except Exception as save_error:
                self.logger.error(f"保存检查点失败: {str(save_error)}")
            
            # 发布错误事件
            await self.event_bus.publish(
                AlchemyEventType.ERROR_OCCURRED,
                {
                    "alchemy_id": self.alchemy_id,
                    "error": str(e),
                    "query": query,
                    "current_step": self._current_step
                }
            )
            
            return {
                'status': 'error',
                'message': str(e),
                'results': None,
                'checkpoint': {
                    'alchemy_id': self.alchemy_id,
                    'current_step': self._current_step
                }
            }

    async def _copy_parent_source_data(self, source_data: Path):
        """复制上级source_data目录"""
        parent_source = self.work_dir.parent / "source_data"
        if parent_source.exists() and parent_source.is_dir():
            self.logger.info("开始复制上级source_data")
            try:
                if any(source_data.iterdir()):
                    shutil.rmtree(source_data)
                    source_data.mkdir()
                
                for item in parent_source.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, source_data / item.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, source_data / item.name)
                self.logger.info(f"上级source_data已复制到: {source_data}")
            except Exception as e:
                self.logger.error(f"复制上级source_data失败: {str(e)}", exc_info=True)
                raise

    async def _copy_input_dirs(self, input_dirs: list, source_data: Path):
        """复制输入目录"""
        self.logger.info("开始复制源数据")
        try:
            for input_dir in input_dirs:
                input_path = Path(input_dir)
                if input_path.exists():
                    if input_path.is_dir():
                        for item in input_path.iterdir():
                            if item.is_dir():
                                shutil.copytree(item, source_data / item.name, dirs_exist_ok=True)
                            else:
                                shutil.copy2(item, source_data / item.name)
                    else:
                        shutil.copy2(input_path, source_data / input_path.name)
            self.logger.info(f"源数据已复制到: {source_data}")
        except Exception as e:
            self.logger.error(f"复制源数据失败: {str(e)}", exc_info=True)
            raise

    async def _process_source_data(self, processor: DataProcessor, source_data: Path, db_path: Path):
        """处理源数据"""
        self.logger.info("开始处理源数据")
        try:
            if not db_path.exists():
                self.logger.info("首次运行，执行全量更新")
                db_path.parent.mkdir(parents=True, exist_ok=True)
                stats = processor.process_directory([source_data], incremental=False)
            else:
                self.logger.info("检测到已有数据，执行增量更新")
                stats = processor.process_directory([source_data], incremental=True)
                
            self._log_processing_stats(stats)
            
        except Exception as e:
            self.logger.error(f"数据处理失败: {str(e)}", exc_info=True)
            raise
            
        self.logger.info("源数据处理完成")

    def _log_processing_stats(self, stats: Dict):
        """记录处理统计信息"""
        self.logger.info("\n=== 处理统计 ===")
        self.logger.info(f"更新模式: {stats.get('update_mode', 'unknown')}")
        self.logger.info(f"总文件数: {stats.get('total_files', 0)}")
        self.logger.info(f"成功处理: {stats.get('successful_files', 0)}")
        self.logger.info(f"处理失败: {stats.get('failed_files', 0)}")
        self.logger.info(f"总记录数: {stats.get('total_records', 0)}")
        if 'removed_files' in stats:
            self.logger.info(f"删除记录: {stats['removed_files']}")
        self.logger.info(f"总耗时: {stats.get('total_time', 0):.2f}秒")
        
        if stats.get('errors'):
            self.logger.warning("\n处理过程中的错误:")
            for error in stats['errors']:
                self.logger.warning(f"- {error}")

    async def _execute_workflow(self, query: str) -> Dict:
        """执行工作流程"""
        results = {
            'status': 'success',
            'message': '',
            'results': {
                'query': query,
                'reasoning_history': None,
                'parsed_intent': None,
                'search_plan': None,
                'search_results': None,
                'artifacts': [],
                'optimization_suggestions': []
            },
            'components': self.components
        }
        
        try:
            # 设置当前步骤
            self._current_step = "parse_intent"
            await self._save_checkpoint()
            
            # 检查是否请求取消
            await self._check_cancellation()
            
            # 获取推理引擎实例
            reasoning_engine = self.components['reasoning_engine']

            # 解析用户搜索意图
            parsed_intent = await self.components['intent_parser'].parse_query(query)
            results['results']['parsed_intent'] = parsed_intent
            
            # 发布意图解析事件
            await self.event_bus.publish(
                AlchemyEventType.INTENT_PARSED,
                {
                    "alchemy_id": self.alchemy_id,
                    "query": query,
                    "parsed_intent": parsed_intent
                }
            )
            
            # 设置当前步骤
            self._current_step = "build_plan"
            await self._save_checkpoint()
            
            # 检查是否请求取消
            await self._check_cancellation()

            # 构建搜索计划
            parsed_plan = self.components['planner'].build_search_plan(parsed_intent)
            results['results']['search_plan'] = parsed_plan
            
            # 发布计划构建事件
            await self.event_bus.publish(
                AlchemyEventType.PLAN_BUILT,
                {
                    "alchemy_id": self.alchemy_id,
                    "query": query,
                    "search_plan": parsed_plan
                }
            )
            
            # 执行搜索计划
            search_results = await self.components['executor'].execute_plan(parsed_plan)
            results['results']['search_results'] = search_results
            
            # 发布搜索执行事件
            await self.event_bus.publish(
                AlchemyEventType.SEARCH_EXECUTED,
                {
                    "alchemy_id": self.alchemy_id,
                    "query": query,
                    "search_results": search_results
                }
            )

            # 为搜索结果生成artifact
            if search_results and search_results.get('saved_files', {}).get('final_results'):
                search_artifact_path = await self.components['artifact_generator'].generate_artifact(
                    context_files=[search_results['saved_files']['final_results']],
                    output_name='artifact',
                    query=query,
                    metadata={
                        'source_query': query,
                        'total_results': search_results.get('stats', {}).get('total', 0),
                        'structured_count': search_results.get('stats', {}).get('structured_count', 0),
                        'vector_count': search_results.get('stats', {}).get('vector_count', 0)
                    }
                )
                if search_artifact_path:
                    results['results']['artifacts'].append(str(search_artifact_path))
                    
                    # 发布制品生成事件
                    await self.event_bus.publish(
                        AlchemyEventType.ARTIFACT_GENERATED,
                        {
                            "alchemy_id": self.alchemy_id,
                            "query": query,
                            "artifact_path": str(search_artifact_path)
                        }
                    )
                    
                    # 获取制品生成的优化建议
                    optimization_query = await self.components['feedback_optimizer'].get_latest_artifact_suggestion(self.alchemy_id)
                    if optimization_query:
                        self.logger.info(f"获取到制品优化建议: {optimization_query}")
                        
                        # 发布优化建议事件
                        await self.event_bus.publish(
                            AlchemyEventType.OPTIMIZATION_SUGGESTED,
                            {
                                "alchemy_id": self.alchemy_id,
                                "original_query": query,
                                "optimization_query": optimization_query
                            }
                        )
                        
                        # 使用优化建议执行新一轮工作流
                        optimization_result = await self.process(
                            query=optimization_query,
                            input_dirs=None,  # 使用已有数据
                            context={
                                'original_query': query,
                                'optimization_source': 'artifact_suggestion',
                                'previous_artifacts': results['results']['artifacts']
                            }
                        )
                        
                        if optimization_result['status'] == 'success':
                            self.logger.info("基于制品优化建议的新一轮处理成功")
                            
                            # 记录优化建议和结果
                            optimization_info = {
                                'suggestion': optimization_query,
                                'source': 'artifact_suggestion',
                                'artifacts': optimization_result['results'].get('artifacts', []),
                                'timestamp': datetime.now().isoformat()
                            }
                            results['results']['optimization_suggestions'].append(optimization_info)
                            
                            # 将新生成的制品也添加到结果中
                            results['results']['artifacts'].extend(optimization_result['results'].get('artifacts', []))
                        else:
                            self.logger.warning(f"优化建议处理失败: {optimization_result['message']}")

            # 最后更新推理历史
            chat_history = reasoning_engine.get_chat_history()
            results['results']['reasoning_history'] = chat_history
            
            return results
                
        except Exception as e:
            self.logger.error(f"处理查询失败: {str(e)}", exc_info=True)
            results['status'] = 'error'
            results['message'] = str(e)
            
            # 发布错误事件
            await self.event_bus.publish(
                AlchemyEventType.ERROR_OCCURRED,
                {
                    "alchemy_id": self.alchemy_id,
                    "error": str(e),
                    "query": query
                }
            )
            
            return results

    # 添加事件相关方法
    def subscribe(self, event_type: AlchemyEventType, callback: Callable):
        """订阅事件
        
        Args:
            event_type: 事件类型
            callback: 回调函数，可以是同步或异步函数
        """
        self.event_bus.subscribe(event_type, callback)
        
    def unsubscribe(self, event_type: AlchemyEventType, callback: Callable):
        """取消订阅事件
        
        Args:
            event_type: 事件类型
            callback: 之前注册的回调函数
        """
        self.event_bus.unsubscribe(event_type, callback)

    def _load_status(self) -> Dict:
        """加载已有的状态信息
        
        如果该alchemy_id存在状态文件，则加载并返回，否则返回None
        """
        status_path = self.alchemy_dir / "status.json"
        if status_path.exists():
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    status_info = json.load(f)
                    return status_info
            except Exception as e:
                self.logger.warning(f"加载状态信息失败: {str(e)}")
        return None 

    def _save_resume_info(self, query: str = None, input_dirs: list = None):
        """保存恢复信息到文件，用于后续恢复"""
        # 保存恢复信息到任务自己的目录
        resume_info = {
            "alchemy_id": self.alchemy_id,
            "timestamp": datetime.now().isoformat(),
            "current_step": self._current_step
        }
        
        if query:
            resume_info["query"] = query
        
        if input_dirs:
            resume_info["input_dirs"] = input_dirs
        
        # 在任务自己的目录下保存resume_info.json
        resume_info_path = self.work_dir / self.alchemy_id / "resume_info.json"
        
        try:
            with open(resume_info_path, 'w', encoding='utf-8') as f:
                json.dump(resume_info, f, ensure_ascii=False, indent=2)
            
            # 同时在工作目录的根目录保存一个副本，用于快速恢复最近任务
            global_resume_info_path = self.work_dir.parent / "resume_info.json"
            with open(global_resume_info_path, 'w', encoding='utf-8') as f:
                json.dump(resume_info, f, ensure_ascii=False, indent=2)
                
            self.logger.debug(f"已保存恢复信息到 {resume_info_path}")
        except Exception as e:
            self.logger.error(f"保存恢复信息失败: {str(e)}")
    
    async def cancel_process(self):
        """取消当前处理过程"""
        self._cancel_requested = True
        
        # 发送取消请求事件
        await self._emit_event(AlchemyEventType.CANCELLATION_REQUESTED, {
            "alchemy_id": self.alchemy_id,
            "timestamp": datetime.now().isoformat()
        })
        
        # 保存恢复信息，确保可以在中断后恢复
        self._save_resume_info()
        
        # 如果有alchemy_manager，更新任务状态
        if self.alchemy_manager:
            self.alchemy_manager.update_task(self.alchemy_id, {
                "status": "cancelled",
                "updated_at": datetime.now().isoformat()
            })
            
        self.logger.info("已请求取消处理，将在下一个检查点处中止")
        return True

    def _is_cancellation_requested(self):
        """检查是否请求了取消"""
        return self._cancel_requested
        
    async def _check_cancellation(self):
        """检查是否需要取消并执行取消操作"""
        if self._is_cancellation_requested():
            self.logger.info(f"执行取消操作，alchemy_id={self.alchemy_id}")
            
            # 保存当前状态到检查点文件
            await self._save_checkpoint()
            
            # 发布取消完成事件
            await self.event_bus.publish(
                AlchemyEventType.PROCESS_CANCELLED,
                {
                    "alchemy_id": self.alchemy_id,
                    "current_step": self._current_step,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # 抛出取消异常
            raise CancellationException(f"处理被用户取消 (alchemy_id={self.alchemy_id})")
            
    async def _save_checkpoint(self):
        """保存当前处理状态到检查点文件"""
        if not self.current_work_dir:
            return
            
        checkpoint_file = self.current_work_dir / "checkpoint.json"
        checkpoint_data = {
            "alchemy_id": self.alchemy_id,
            "timestamp": datetime.now().isoformat(),
            "current_step": self._current_step,
            "iteration": self._get_next_iteration() - 1  # 当前迭代号
        }
        
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
            
        # 发布检查点事件
        await self.event_bus.publish(
            AlchemyEventType.PROCESS_CHECKPOINT,
            checkpoint_data
        )
        
        self.logger.info(f"已保存检查点，current_step={self._current_step}")
            
    async def resume_process(self, query: str = None, input_dirs: list = None, context: Dict = None) -> Dict:
        """从上次中断的位置继续处理
        
        Args:
            query: 查询文本，如果为None则使用上次的查询
            input_dirs: 输入目录列表
            context: 上下文数据
            
        Returns:
            Dict: 处理结果
        """
        # 查找检查点文件
        checkpoint_file = None
        checkpoint_data = None
        
        # 首先在上次迭代目录中查找
        if self.status_info and 'latest_iteration' in self.status_info:
            latest_iter = self.status_info['latest_iteration']
            iter_dir = self.iterations_dir / f"iter{latest_iter}"
            if iter_dir.exists():
                checkpoint_path = iter_dir / "checkpoint.json"
                if checkpoint_path.exists():
                    checkpoint_file = checkpoint_path
        
        # 如果没有找到，则在整个alchemy目录中查找最新的检查点
        if not checkpoint_file:
            checkpoints = list(self.alchemy_dir.glob("**/checkpoint.json"))
            if checkpoints:
                # 按修改时间排序，找到最新的检查点
                checkpoint_file = max(checkpoints, key=lambda p: p.stat().st_mtime)
        
        # 如果找到了检查点文件，则加载它
        if checkpoint_file:
            try:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    checkpoint_data = json.load(f)
                self.logger.info(f"找到检查点: {checkpoint_file}, 当前步骤: {checkpoint_data.get('current_step')}")
            except Exception as e:
                self.logger.error(f"加载检查点失败: {str(e)}")
                checkpoint_data = None
        
        # 如果没有找到有效的检查点，则重新开始处理
        if not checkpoint_data:
            self.logger.warning(f"未找到有效的检查点，将重新开始处理")
            return await self.process(query, input_dirs, context)
        
        # 设置当前步骤
        self._current_step = checkpoint_data.get('current_step', 'unknown')
        
        # 根据检查点的步骤决定如何恢复
        if self._current_step == "initialization":
            # 如果是初始化阶段中断，直接重新开始
            self.logger.info("在初始化阶段中断，重新开始处理")
            return await self.process(query, input_dirs, context)
            
        elif self._current_step == "prepare_source_data":
            # 如果是在准备源数据阶段中断，从该步骤继续
            self.logger.info("从准备源数据阶段继续")
            # 可以重用之前的query和context
            return await self.process(query, input_dirs, context)
            
        elif self._current_step == "process_data":
            # 如果是在处理数据阶段中断，从该步骤继续
            self.logger.info("从处理数据阶段继续")
            return await self.process(query, input_dirs, context)
            
        elif self._current_step in ["parse_intent", "build_plan", "execute_search", "generate_artifact"]:
            # 如果是在工作流执行阶段中断，可以尝试从该步骤继续
            self.logger.info(f"从工作流执行阶段继续: {self._current_step}")
            
            # 恢复到上次的迭代目录
            if 'iteration' in checkpoint_data:
                iteration = checkpoint_data['iteration']
                self.current_work_dir = self.iterations_dir / f"iter{iteration}"
                self.logger.info(f"恢复到迭代: {iteration}, 目录: {self.current_work_dir}")
                
                # 重新初始化组件
                if self.current_work_dir.exists():
                    data_dir = self.current_work_dir / "data"
                    if data_dir.exists():
                        db_path = data_dir / "unified_storage.duckdb"
                        if db_path.exists():
                            self.components = self._init_components(str(db_path))
                            self.logger.info("已重新初始化组件")
            
            # 根据中断的步骤决定如何继续
            if self._current_step == "parse_intent":
                # 如果是在解析意图阶段中断，从工作流开始执行
                self.logger.info("从解析意图阶段继续执行工作流")
                results = await self._execute_workflow(query)
                return {
                    'status': 'resumed',
                    'message': f'从{self._current_step}阶段恢复处理',
                    'results': results
                }
                
            # ... 可以添加更多特定步骤的恢复逻辑 ...
            
        # 默认情况：无法精确恢复，重新开始处理
        self.logger.warning(f"无法从步骤{self._current_step}精确恢复，将重新开始处理")
        return await self.process(query, input_dirs, context)

# 添加取消异常类
class CancellationException(Exception):
    """取消处理异常"""
    pass 