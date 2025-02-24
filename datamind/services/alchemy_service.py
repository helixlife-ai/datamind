import json
import time
import logging
import shutil
from pathlib import Path
from typing import Dict
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

class DataMindAlchemy:
    """数据炼丹工作流封装类"""
    
    def __init__(self, work_dir: Path = None, model_manager: ModelManager = None, logger: logging.Logger = None, alchemy_id: str = None):
        """初始化数据炼丹工作流
        
        Args:
            work_dir: 工作目录，默认为None时会使用默认路径
            model_manager: 模型管理器实例，用于推理引擎
            logger: 日志记录器实例，用于记录日志
            alchemy_id: 炼丹ID，默认为None时会自动生成
        """
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
            # 确定当前迭代版本
            iteration = self._get_next_iteration()
            current_iter_dir = self.iterations_dir / f"iter{iteration}"
            current_iter_dir.mkdir(exist_ok=True)
            
            # 更新工作目录到当前迭代目录
            self.current_work_dir = current_iter_dir
            
            # 处理上下文
            if context:
                context_file = current_iter_dir / "context.json"
                with open(context_file, 'w', encoding='utf-8') as f:
                    json.dump(context, f, ensure_ascii=False, indent=2)
            
            # 准备数据目录
            source_data = current_iter_dir / "source_data"
            source_data.mkdir(exist_ok=True)
            
            # 复制上级source_data
            if context:
                await self._copy_parent_source_data(source_data)
                
            # 复制输入目录
            if input_dirs:
                await self._copy_input_dirs(input_dirs, source_data)
            
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
            
            # 初始化组件
            self.components = self._init_components(str(db_path))
            
            # 执行工作流
            results = await self._execute_workflow(query)
            
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

            return results
            
        except Exception as e:
            self.logger.error(f"数据炼丹工作流失败: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e),
                'results': None
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
            # 获取推理引擎实例
            reasoning_engine = self.components['reasoning_engine']

            # 解析用户搜索意图
            parsed_intent = await self.components['intent_parser'].parse_query(query)
            results['results']['parsed_intent'] = parsed_intent

            # 构建搜索计划
            parsed_plan = self.components['planner'].build_search_plan(parsed_intent)
            results['results']['search_plan'] = parsed_plan
            
            # 执行搜索计划
            search_results = await self.components['executor'].execute_plan(parsed_plan)
            results['results']['search_results'] = search_results

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
                    
                    # 获取制品生成的优化建议
                    optimization_query = await self.components['feedback_optimizer'].get_latest_artifact_suggestion(self.alchemy_id)
                    if optimization_query:
                        self.logger.info(f"获取到制品优化建议: {optimization_query}")
                        
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
            return results 