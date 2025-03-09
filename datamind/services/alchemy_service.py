import json
import time
import logging
import shutil
from pathlib import Path
from typing import Dict, Callable, Any
from ..core.search import SearchEngine
from ..core.planner import SearchPlanner
from ..core.executor import SearchPlanExecutor
from ..core.processor import DataProcessor, FileCache
from ..core.parser import IntentParser
from ..core.feedback_optimizer import FeedbackOptimizer
from ..core.artifact import ArtifactGenerator
from ..llms.model_manager import ModelManager, ModelConfig
from ..config.settings import (
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE,
    DEFAULT_REASONING_MODEL,
    DEFAULT_GENERATOR_MODEL
)
from datetime import datetime

from .events.event_types import AlchemyEventType
from .events.event_bus import EventBus


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
        self.logger = logging.getLogger(f"datamind.alchemy.{self.alchemy_id}")
        self.logger.setLevel(logging.INFO)
        
        # 创建日志处理器（如果没有）
        if not self.logger.handlers:
            # 创建日志目录
            log_dir = self.work_dir / "logs"
            log_dir.mkdir(exist_ok=True, parents=True)
            
            # 创建控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
            
            # 创建文件日志处理器
            log_file = log_dir / f"alchemy_{self.alchemy_id}.log"
            file_handler = logging.FileHandler(str(log_file), encoding='utf-8')
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(file_handler)
            
            self.logger.info(f"已初始化日志记录器，日志文件: {log_file}")
        
        # 初始化模型管理器 - 确保传递日志记录器
        if model_manager is None:
            self.model_manager = ModelManager(logger=self.logger)
            self.logger.info("已创建新的模型管理器实例")
        else:
            self.model_manager = model_manager
            # 如果外部提供的model_manager没有logger，设置它
            if not hasattr(self.model_manager, 'logger') or self.model_manager.logger is None:
                self.model_manager.logger = self.logger
                self.logger.info("已为外部提供的模型管理器设置日志记录器")
        
        # 注册默认推理模型配置
        if self.model_manager:  
            self.model_manager.register_model(ModelConfig(
                name=DEFAULT_REASONING_MODEL,
                model_type="api",
                api_base=DEFAULT_LLM_API_BASE,
                api_key=DEFAULT_LLM_API_KEY
            ))
            self.model_manager.register_model(ModelConfig(
                name=DEFAULT_GENERATOR_MODEL,
                model_type="api",
                api_base=DEFAULT_LLM_API_BASE,
                api_key=DEFAULT_LLM_API_KEY
            ))
        
        # 初始化所有必要的目录结构
        self.alchemy_dir = self.work_dir / "alchemy_runs" / f"alchemy_{self.alchemy_id}"
        self.iterations_dir = self.alchemy_dir / "iterations"
        self.artifacts_dir = self.alchemy_dir / "artifacts"  # 添加制品目录
        
        # 创建所有必要的目录
        for directory in [self.alchemy_dir, self.iterations_dir, self.artifacts_dir]:
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
            
        # 初始化时保存一次恢复信息
        self._save_resume_info()

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
        # 其他组件初始化
        search_engine = SearchEngine(
            db_path=db_path,
            logger=self.logger
        )
        
        intent_parser = IntentParser(
            work_dir=str(self.current_work_dir),  # 修改为当前迭代目录
            model_manager=self.model_manager,
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
            model_manager=self.model_manager,
            logger=self.logger
        )
        
        feedback_optimizer = FeedbackOptimizer(
            work_dir=str(self.current_work_dir),  # 修改为当前迭代目录
            logger=self.logger
        )
        
        # 记录组件配置
        components_config = {
            "iteration": self._get_next_iteration() - 1,  # 当前迭代号
            "work_dir": str(self.current_work_dir),
            "components": {
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
            # 初始验证查询参数
            if query is None:
                self.logger.warning("传入的查询为None，将尝试从配置文件或恢复信息中获取")
            elif not query.strip():
                self.logger.warning("传入的查询为空字符串，将尝试从配置文件或恢复信息中获取")
                query = None  # 将空字符串转换为None，以便后续逻辑处理
                
            # 首先检查是否存在next_iteration_config.json文件并读取配置
            next_config_path = self.alchemy_dir / "next_iteration_config.json"
            config_input_dirs = None
            if next_config_path.exists():
                try:
                    with open(next_config_path, 'r', encoding='utf-8') as f:
                        next_config = json.load(f)
                    
                    # 优先使用配置文件中的query，无论是否提供了query参数
                    if "query" in next_config and next_config["query"]:
                        # 确保配置文件中的查询不为空
                        if not next_config["query"] or next_config["query"].strip() == "":
                            self.logger.warning("配置文件中的查询为空，将忽略")
                        else:
                            # 如果提供了query参数且与配置不同，记录日志
                            if query is not None and query != next_config["query"]:
                                self.logger.info(f"提供的查询文本 '{query}' 将被配置文件中的查询 '{next_config['query']}' 覆盖")
                            query = next_config["query"]
                            self.logger.info(f"使用配置文件中的查询: {query}")
                    elif not query:
                        self.logger.warning("配置文件中没有有效的查询，且未提供查询参数")
                    
                    # 优先使用配置文件中的input_dirs，无论是否提供了input_dirs参数
                    if "input_dirs" in next_config and next_config["input_dirs"]:
                        # 如果提供了input_dirs参数且与配置不同，记录日志
                        if input_dirs is not None and input_dirs != next_config["input_dirs"]:
                            self.logger.info(f"提供的输入目录 {input_dirs} 将被配置文件中的输入目录 {next_config['input_dirs']} 覆盖")
                        config_input_dirs = next_config["input_dirs"]
                        # 更新input_dirs参数，确保后续处理使用配置文件中的值
                        input_dirs = config_input_dirs
                        self.logger.info(f"使用配置文件中的输入目录: {config_input_dirs}")
                        
                    # 记录已读取配置文件
                    self.logger.info(f"已从配置文件读取下一轮迭代配置")
                    
                    # 记录元数据信息（如果存在）
                    if "metadata" in next_config:
                        metadata = next_config["metadata"]
                        if "previous_step" in metadata:
                            self.logger.debug(f"配置文件中的上一步骤: {metadata['previous_step']}")
                        if "previous_iteration" in metadata:
                            self.logger.debug(f"配置文件中的上一迭代: {metadata['previous_iteration']}")
                    
                    # 记录备注信息（如果存在）
                    if "notes" in next_config and next_config["notes"]:
                        self.logger.info(f"配置文件中的备注: {next_config['notes']}")
                except Exception as e:
                    self.logger.error(f"读取下一轮迭代配置失败: {str(e)}")
            
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
            
            # 确保查询不为None
            if query is None:
                error_msg = "查询文本为None，无法执行工作流"
                self.logger.error(error_msg)
                
                # 发布错误事件
                await self.event_bus.publish(
                    AlchemyEventType.ERROR_OCCURRED,
                    {
                        "alchemy_id": self.alchemy_id,
                        "error": error_msg,
                        "query": None,
                        "current_step": self._current_step
                    }
                )
                
                return {
                    'status': 'error',
                    'message': error_msg,
                    'results': None,
                    'checkpoint': {
                        'alchemy_id': self.alchemy_id,
                        'current_step': self._current_step
                    }
                }
            
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
            
            # 首先执行原有的数据复制逻辑
            if not context:
                # 在炼金运行目录中创建source_data目录
                alchemy_source_data = self.alchemy_dir / "source_data"
                alchemy_source_data.mkdir(exist_ok=True)
                
                # 复制用户指定的目录到炼金运行目录的source_data
                if input_dirs:
                    await self._copy_input_dirs(input_dirs, alchemy_source_data)
                    
                # 然后将炼金运行目录的source_data复制到当前迭代目录
                for item in alchemy_source_data.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, source_data / item.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, source_data / item.name)
                
                self.logger.info(f"已将炼金运行目录的source_data复制到当前迭代目录: {source_data}")
            else:
                # 复制上级source_data
                await self._copy_parent_source_data(source_data)
                
            # 复制输入目录（如果在优化模式下还有额外输入）
            if input_dirs and context:
                await self._copy_input_dirs(input_dirs, source_data)
            
            # 注意：不再需要单独处理config_input_dirs，因为已经合并到input_dirs中
            # 如果仍然存在config_input_dirs且与input_dirs不同，则记录警告
            if config_input_dirs and config_input_dirs != input_dirs:
                self.logger.warning(f"检测到config_input_dirs与input_dirs不一致，这可能是代码逻辑错误")
            
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
            
            # 发布处理完成事件
            await self.event_bus.publish(
                AlchemyEventType.PROCESS_COMPLETED,
                {
                    "alchemy_id": self.alchemy_id,
                    "iteration": iteration,
                    "results": results
                }
            )

            # 保存结果到文件，方便后续恢复
            try:
                results_file = self.current_work_dir / "results.json"
                with open(results_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                self.logger.info(f"已保存处理结果到文件: {results_file}")
            except Exception as e:
                self.logger.error(f"保存结果文件失败: {str(e)}")

            # 在每一步完成后保存恢复信息
            self._save_resume_info(query, input_dirs)

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
            
            # 更新任务状态为错误
            if self.alchemy_manager:
                self.alchemy_manager.update_task(self.alchemy_id, {
                    "status": "error",
                    "error_message": str(e)
                })
            
            # 保存恢复信息，以便从错误中恢复
            self._save_resume_info(query, input_dirs)
            
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
        """复制上一次迭代的源数据到当前迭代目录"""
        self.logger.info("开始复制上一次迭代的源数据")
        
        try:
            # 获取上一次迭代的信息
            previous_iteration = None
            
            # 从状态信息中获取最新的迭代号
            status_path = self.alchemy_dir / "status.json"
            if status_path.exists():
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        status_info = json.load(f)
                        if 'latest_iteration' in status_info:
                            previous_iteration = status_info['latest_iteration']
                            self.logger.info(f"从status.json获取到上一次迭代号: {previous_iteration}")
                except Exception as e:
                    self.logger.error(f"读取status.json失败: {str(e)}")
            
            if previous_iteration is not None:
                # 构建上一次迭代的源数据目录路径
                previous_source_data = self.iterations_dir / f"iter{previous_iteration}" / "source_data"
                
                if previous_source_data.exists() and previous_source_data.is_dir():
                    self.logger.info(f"找到上一次迭代(iter{previous_iteration})的源数据目录: {previous_source_data}")
                    
                    # 清空当前源数据目录（如果有内容）
                    if source_data.exists() and any(source_data.iterdir()):
                        shutil.rmtree(source_data)
                        source_data.mkdir()
                    
                    # 复制上一次迭代的源数据
                    for item in previous_source_data.iterdir():
                        if item.is_dir():
                            shutil.copytree(item, source_data / item.name, dirs_exist_ok=True)
                        else:
                            shutil.copy2(item, source_data / item.name)
                    
                    self.logger.info(f"已成功复制上一次迭代的源数据到: {source_data}")
                    return
                else:
                    self.logger.warning(f"上一次迭代的源数据目录不存在或为空: {previous_source_data}")
            
            # 如果没有找到上一次迭代的源数据，尝试使用炼金运行目录的source_data
            alchemy_source_data = self.alchemy_dir / "source_data"
            if alchemy_source_data.exists() and alchemy_source_data.is_dir() and any(alchemy_source_data.iterdir()):
                self.logger.info(f"使用炼金运行目录的source_data: {alchemy_source_data}")
                
                # 清空当前源数据目录（如果有内容）
                if source_data.exists() and any(source_data.iterdir()):
                    shutil.rmtree(source_data)
                    source_data.mkdir()
                
                # 复制炼金运行目录的source_data
                for item in alchemy_source_data.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, source_data / item.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, source_data / item.name)
                
                self.logger.info(f"已复制炼金运行目录的source_data到: {source_data}")
                return
            
            # 如果上述都失败，尝试使用工作目录的父目录中的source_data（兼容旧逻辑）
            parent_source = self.work_dir.parent / "source_data"
            if parent_source.exists() and parent_source.is_dir():
                self.logger.info("未找到上一次迭代的源数据，使用父目录中的source_data")
                
                # 清空当前源数据目录（如果有内容）
                if source_data.exists() and any(source_data.iterdir()):
                    shutil.rmtree(source_data)
                    source_data.mkdir()
                
                # 复制父目录中的source_data
                for item in parent_source.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, source_data / item.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, source_data / item.name)
                
                self.logger.info(f"已复制父目录中的source_data到: {source_data}")
            else:
                self.logger.warning("未找到任何可用的源数据目录")
            
        except Exception as e:
            self.logger.error(f"复制源数据失败: {str(e)}", exc_info=True)
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
        # 添加查询验证，确保查询不为None
        if query is None:
            self.logger.error("查询文本为None，无法执行工作流")
            return {
                'status': 'error',
                'message': '查询文本为None，无法执行工作流',
                'results': {
                    'query': None,
                    'parsed_intent': None,
                    'search_plan': None,
                    'search_results': None,
                    'artifacts': [],
                    'optimization_suggestions': []
                }
            }
            
        results = {
            'status': 'success',
            'message': '',
            'results': {
                'query': query,
                'parsed_intent': None,
                'search_plan': None,
                'search_results': None,
                'artifacts': [],
                'optimization_suggestions': []
            },
            'components': self.components
        }
        
        try:
            # 在迭代之前更新状态信息
            status_info = {
                "alchemy_id": self.alchemy_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "latest_iteration": self._get_next_iteration() - 1,  # 当前迭代号
                "iterations": []
            }
            
            status_path = self.alchemy_dir / "status.json"
            if status_path.exists():
                with open(status_path, "r", encoding="utf-8") as f:
                    status_info = json.load(f)
            
            # 更新迭代信息
            iteration_info = {
                "iteration": self._get_next_iteration() - 1,  # 当前迭代号
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "path": str(self.current_work_dir.relative_to(self.alchemy_dir)) if self.current_work_dir else "",
                "artifacts": [],
                "optimization_suggestions": []
            }
            
            status_info["iterations"].append(iteration_info)
            status_info["latest_iteration"] = self._get_next_iteration() - 1  # 当前迭代号
            status_info["updated_at"] = datetime.now().isoformat()
            
            with open(status_path, "w", encoding="utf-8") as f:
                json.dump(status_info, f, ensure_ascii=False, indent=2)
            
            # 设置当前步骤
            self._current_step = "parse_intent"
            await self._save_checkpoint()
            
            # 检查是否请求取消
            await self._check_cancellation()

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
                    search_results_files=[search_results['saved_files']['final_results']],
                    output_name='artifact',
                    query=query
                )
                if search_artifact_path:
                    results['results']['artifacts'].append(str(search_artifact_path))
                    
                    # 更新状态文件中的制品信息
                    if status_path.exists():
                        with open(status_path, "r", encoding="utf-8") as f:
                            status_info = json.load(f)
                        
                        # 更新最新迭代的制品信息
                        if status_info.get('iterations'):
                            status_info['iterations'][-1]['artifacts'] = results['results']['artifacts']
                            
                        with open(status_path, "w", encoding="utf-8") as f:
                            json.dump(status_info, f, ensure_ascii=False, indent=2)
                    
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
                    optimization_query = None
                    
                    # 首先尝试从next_iteration_config.json获取优化查询
                    next_config_path = self.alchemy_dir / "next_iteration_config.json"
                    if next_config_path.exists():
                        try:
                            with open(next_config_path, 'r', encoding='utf-8') as f:
                                next_config = json.load(f)
                            
                            if "query" in next_config:
                                # 检查配置文件中的查询是否与原始查询不同
                                if next_config["query"] != query:
                                    optimization_query = next_config["query"]
                                    self.logger.info(f"从配置文件获取到优化查询: {optimization_query}")
                                else:
                                    self.logger.info(f"配置文件中的查询与原始查询相同，将尝试使用feedback_optimizer生成新的优化建议")
                        except Exception as e:
                            self.logger.error(f"读取next_iteration_config.json失败: {str(e)}")
                    
                    # 如果配置文件中没有查询或查询与原始查询相同，则使用feedback_optimizer生成
                    if not optimization_query:
                        optimization_query = await self.components['feedback_optimizer'].get_latest_artifact_suggestion(self.alchemy_id)
                        self.logger.info(f"使用feedback_optimizer生成优化建议: {optimization_query}")
                    
                    # 确保优化查询不为None或空
                    if optimization_query and optimization_query.strip():
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
                            
                            # 更新状态文件中的优化建议信息
                            if status_path.exists():
                                with open(status_path, "r", encoding="utf-8") as f:
                                    status_info = json.load(f)
                                
                                # 更新最新迭代的优化建议信息
                                if status_info.get('iterations'):
                                    status_info['iterations'][-1]['optimization_suggestions'] = results['results']['optimization_suggestions']
                                    status_info['iterations'][-1]['artifacts'] = results['results']['artifacts']
                                    
                                with open(status_path, "w", encoding="utf-8") as f:
                                    json.dump(status_info, f, ensure_ascii=False, indent=2)
                        else:
                            self.logger.warning(f"优化建议处理失败: {optimization_result['message']}")
            
            # 保存工作流结果到文件，方便后续恢复
            try:
                workflow_results_file = self.current_work_dir / "workflow_results.json"
                with open(workflow_results_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                self.logger.info(f"已保存工作流结果到文件: {workflow_results_file}")
            except Exception as e:
                self.logger.error(f"保存工作流结果文件失败: {str(e)}")
            
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
        resume_info = {
            "alchemy_id": self.alchemy_id,
            "timestamp": datetime.now().isoformat(),
            "current_step": self._current_step,
            "has_components": hasattr(self, 'components'),
            "current_work_dir": str(self.current_work_dir) if self.current_work_dir else None,
            "iteration": self._get_next_iteration() - 1 if hasattr(self, '_get_next_iteration') else None
        }
        
        if query:
            resume_info["query"] = query
        
        if input_dirs:
            resume_info["input_dirs"] = input_dirs
        
        # 如果没有提供query，尝试从任务状态中获取
        if not query and self.status_info:
            for iteration in self.status_info.get('iterations', []):
                if 'query' in iteration:
                    resume_info["query"] = iteration['query']
                    break
        
        # 添加文件状态信息
        file_status = {}
        if self.current_work_dir:
            # 检查各种关键文件是否存在
            file_status["checkpoint_exists"] = (self.current_work_dir / "checkpoint.json").exists()
            file_status["results_exists"] = (self.current_work_dir / "results.json").exists()
            file_status["workflow_results_exists"] = (self.current_work_dir / "workflow_results.json").exists()
            file_status["context_exists"] = (self.current_work_dir / "context.json").exists()
            
            # 检查数据库文件
            data_dir = self.current_work_dir / "data"
            if data_dir.exists():
                file_status["database_exists"] = (data_dir / "unified_storage.duckdb").exists()
                file_status["file_cache_exists"] = (data_dir / "file_cache.pkl").exists()
            
            # 检查源数据目录
            source_data = self.current_work_dir / "source_data"
            if source_data.exists():
                file_status["has_source_data"] = any(source_data.iterdir())
        
        resume_info["file_status"] = file_status
        
        try:
            # 使用alchemy_dir作为唯一的任务目录
            task_dir = self.alchemy_dir
            
            # 记录目录信息，帮助诊断
            self.logger.debug(f"保存恢复信息 - alchemy_id: {self.alchemy_id}")
            self.logger.debug(f"保存恢复信息 - 工作目录: {self.work_dir}")
            self.logger.debug(f"保存恢复信息 - 任务目录: {task_dir}")
            
            
            task_resume_path = task_dir / "resume_info.json"
            with open(task_resume_path, 'w', encoding='utf-8') as f:
                json.dump(resume_info, f, ensure_ascii=False, indent=2)
            
            # 同时保存下一轮迭代配置文件
            next_iteration_config = {
                "timestamp": datetime.now().isoformat()
            }
            
            # 保留previous_step和previous_iteration字段，但将它们放在metadata子对象中
            # 这样可以清晰区分核心配置和元数据
            next_iteration_config["metadata"] = {
                "previous_step": self._current_step,
                "previous_iteration": resume_info.get("iteration")
            }
            
            # 只有当查询不为None时才添加到配置中
            if query is not None:
                next_iteration_config["query"] = query
            else:
                self.logger.warning("保存恢复信息时查询为None，将不保存查询信息")
                
            # 只有当输入目录不为None时才添加到配置中
            if input_dirs is not None:
                next_iteration_config["input_dirs"] = input_dirs
            else:
                next_iteration_config["input_dirs"] = []
                
            # 添加notes字段，初始为空字符串或保留现有值
            next_config_path = task_dir / "next_iteration_config.json"
            if next_config_path.exists():
                # 如果配置文件已存在，读取现有的notes
                try:
                    with open(next_config_path, 'r', encoding='utf-8') as f:
                        existing_config = json.load(f)
                        if "notes" in existing_config:
                            next_iteration_config["notes"] = existing_config["notes"]
                        else:
                            next_iteration_config["notes"] = ""
                except Exception as e:
                    self.logger.warning(f"读取现有配置文件失败，将使用空notes: {str(e)}")
                    next_iteration_config["notes"] = ""
                
            with open(next_config_path, 'w', encoding='utf-8') as f:
                json.dump(next_iteration_config, f, ensure_ascii=False, indent=2)
            
            self.logger.debug(f"已保存恢复信息到任务目录")
            self.logger.debug(f"任务恢复文件: {task_resume_path}")
            self.logger.debug(f"下一轮迭代配置文件: {next_config_path}")
        except Exception as e:
            self.logger.error(f"保存恢复信息失败: {str(e)}")
            self.logger.exception(e)
    
    async def cancel_process(self):
        """取消当前处理过程"""
        self._cancel_requested = True
        
        # 获取当前任务的最新状态
        status_info = self._load_status()
        query = None
        
        # 如果状态存在，尝试获取最新查询
        if status_info and 'iterations' in status_info and status_info['iterations']:
            latest_iter = status_info['iterations'][-1]
            query = latest_iter.get('query')
        
        # 发送取消请求事件
        await self._emit_event(AlchemyEventType.CANCELLATION_REQUESTED, {
            "alchemy_id": self.alchemy_id,
            "timestamp": datetime.now().isoformat()
        })
        
        # 保存恢复信息，确保可以在中断后恢复
        self._save_resume_info(query=query)
        
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
            raise Exception(f"处理被用户取消 (alchemy_id={self.alchemy_id})")
            
    async def _save_checkpoint(self):
        """保存当前处理状态到检查点文件"""
        if not self.current_work_dir:
            return
            
        checkpoint_file = self.current_work_dir / "checkpoint.json"
        checkpoint_data = {
            "alchemy_id": self.alchemy_id,
            "timestamp": datetime.now().isoformat(),
            "current_step": self._current_step,
            "iteration": self._get_next_iteration() - 1,  # 当前迭代号
            "work_dir": str(self.current_work_dir),
            "status": "in_progress",
            "components_initialized": hasattr(self, 'components'),
            "has_source_data": (self.current_work_dir / "source_data").exists() and any((self.current_work_dir / "source_data").iterdir()),
            "has_database": (self.current_work_dir / "data" / "unified_storage.duckdb").exists() if (self.current_work_dir / "data").exists() else False
        }
        
        # 添加当前步骤的详细信息
        step_details = {}
        if self._current_step == "parse_intent" and hasattr(self, 'components'):
            # 记录意图解析相关信息
            step_details["reasoning_engine_initialized"] = 'reasoning_engine' in self.components
            step_details["intent_parser_initialized"] = 'intent_parser' in self.components
        elif self._current_step == "build_plan" and hasattr(self, 'components'):
            # 记录计划构建相关信息
            step_details["planner_initialized"] = 'planner' in self.components
            step_details["parsed_intent_available"] = True  # 如果到了这一步，意图已解析
        elif self._current_step == "execute_workflow" and hasattr(self, 'components'):
            # 记录执行工作流相关信息
            step_details["executor_initialized"] = 'executor' in self.components
            step_details["search_plan_available"] = True  # 如果到了这一步，搜索计划已构建
        
        checkpoint_data["step_details"] = step_details
        
        # 记录全局状态信息
        global_state = {
            "total_iterations": self._get_next_iteration() - 1,
            "alchemy_dir": str(self.alchemy_dir),
            "has_status_file": (self.alchemy_dir / "status.json").exists(),
            "has_resume_info": (self.alchemy_dir / "resume_info.json").exists(),
            "has_next_config": (self.alchemy_dir / "next_iteration_config.json").exists()
        }
        checkpoint_data["global_state"] = global_state
        
        # 保存检查点文件
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
            
        # 同时在alchemy_dir中保存一个最新检查点的副本，方便恢复
        latest_checkpoint_file = self.alchemy_dir / "latest_checkpoint.json"
        with open(latest_checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
            
        # 发布检查点事件
        await self.event_bus.publish(
            AlchemyEventType.PROCESS_CHECKPOINT,
            checkpoint_data
        )
        
        self.logger.info(f"已保存检查点，current_step={self._current_step}, iteration={checkpoint_data['iteration']}")
        
        # 同时更新恢复信息
        self._save_resume_info()

    async def resume_process(self, query: str = None, input_dirs: list = None, context: Dict = None) -> Dict:
        """从上次中断的位置继续处理
        
        Args:
            query: 查询文本，如果为None则使用上次的查询
            input_dirs: 输入目录列表
            context: 上下文数据
            
        Returns:
            Dict: 处理结果
        """
        # 初始化resume_info
        resume_info = None
        resume_info_path = self.alchemy_dir / "resume_info.json"
        
        if resume_info_path.exists():
            try:
                with open(resume_info_path, 'r', encoding='utf-8') as f:
                    resume_info = json.load(f)
                self.logger.info(f"已从恢复信息文件加载数据: {resume_info_path}")
            except Exception as e:
                self.logger.error(f"加载恢复信息文件失败: {str(e)}")
        
        # 首先尝试从next_iteration_config.json加载配置，优先级最高
        next_config_path = self.alchemy_dir / "next_iteration_config.json"
        if next_config_path.exists():
            try:
                with open(next_config_path, 'r', encoding='utf-8') as f:
                    next_config = json.load(f)
                
                # 优先使用配置文件中的query，无论是否提供了query参数
                if "query" in next_config and next_config["query"]:
                    # 确保配置文件中的查询不为空
                    if not next_config["query"] or next_config["query"].strip() == "":
                        self.logger.warning("配置文件中的查询为空，将忽略")
                    else:
                        # 如果提供了query参数且与配置不同，记录日志
                        if query is not None and query != next_config["query"]:
                            self.logger.info(f"提供的查询文本 '{query}' 将被配置文件中的查询 '{next_config['query']}' 覆盖")
                        query = next_config["query"]
                        self.logger.info(f"使用配置文件中的查询: {query}")
                elif not query:
                    self.logger.warning("配置文件中没有有效的查询，且未提供查询参数")
                
                # 优先使用配置文件中的input_dirs，无论是否提供了input_dirs参数
                if "input_dirs" in next_config and next_config["input_dirs"]:
                    # 如果提供了input_dirs参数且与配置不同，记录日志
                    if input_dirs is not None and input_dirs != next_config["input_dirs"]:
                        self.logger.info(f"提供的输入目录 {input_dirs} 将被配置文件中的输入目录 {next_config['input_dirs']} 覆盖")
                    input_dirs = next_config["input_dirs"]
                    self.logger.info(f"使用配置文件中的输入目录: {input_dirs}")
                
                # 记录元数据信息（如果存在）
                if "metadata" in next_config:
                    metadata = next_config["metadata"]
                    if "previous_step" in metadata:
                        self.logger.debug(f"恢复时使用的上一步骤: {metadata['previous_step']}")
                    if "previous_iteration" in metadata:
                        self.logger.debug(f"恢复时使用的上一迭代: {metadata['previous_iteration']}")
                
                # 记录备注信息（如果存在）
                if "notes" in next_config and next_config["notes"]:
                    self.logger.info(f"配置文件中的备注: {next_config['notes']}")
                
                self.logger.info(f"已从配置文件读取下一轮迭代配置")
            except Exception as e:
                self.logger.error(f"读取下一轮迭代配置失败: {str(e)}")
        
        # 如果配置文件中没有设置，再尝试从恢复信息中获取
        if resume_info:
            # 如果没有提供查询文本，使用恢复信息中的查询文本
            if query is None and "query" in resume_info:
                query = resume_info["query"]
                self.logger.info(f"使用原任务的查询文本: {query}")
            
            # 如果没有提供输入目录，使用恢复信息中的输入目录
            if input_dirs is None and "input_dirs" in resume_info:
                input_dirs = resume_info["input_dirs"]
                self.logger.info(f"使用原任务的输入目录: {input_dirs}")
        
        # 查找检查点文件
        checkpoint_file = None
        checkpoint_data = None
        
        # 首先尝试从alchemy_dir中的latest_checkpoint.json加载
        latest_checkpoint_file = self.alchemy_dir / "latest_checkpoint.json"
        if latest_checkpoint_file.exists():
            try:
                with open(latest_checkpoint_file, 'r', encoding='utf-8') as f:
                    checkpoint_data = json.load(f)
                self.logger.info(f"从最新检查点文件加载: {latest_checkpoint_file}")
                checkpoint_file = latest_checkpoint_file
            except Exception as e:
                self.logger.error(f"加载最新检查点文件失败: {str(e)}")
                checkpoint_data = None
        
        # 如果没有找到最新检查点，则在上次迭代目录中查找
        if not checkpoint_data and self.status_info and 'latest_iteration' in self.status_info:
            latest_iter = self.status_info['latest_iteration']
            iter_dir = self.iterations_dir / f"iter{latest_iter}"
            if iter_dir.exists():
                checkpoint_path = iter_dir / "checkpoint.json"
                if checkpoint_path.exists():
                    try:
                        with open(checkpoint_path, 'r', encoding='utf-8') as f:
                            checkpoint_data = json.load(f)
                        self.logger.info(f"从迭代目录加载检查点: {checkpoint_path}")
                        checkpoint_file = checkpoint_path
                    except Exception as e:
                        self.logger.error(f"加载迭代目录检查点失败: {str(e)}")
                        checkpoint_data = None
        
        # 如果仍然没有找到，则在整个alchemy目录中查找最新的检查点
        if not checkpoint_data:
            checkpoints = list(self.alchemy_dir.glob("**/checkpoint.json"))
            if checkpoints:
                # 按修改时间排序，找到最新的检查点
                checkpoint_file = max(checkpoints, key=lambda p: p.stat().st_mtime)
                try:
                    with open(checkpoint_file, 'r', encoding='utf-8') as f:
                        checkpoint_data = json.load(f)
                    self.logger.info(f"从全局搜索加载检查点: {checkpoint_file}")
                except Exception as e:
                    self.logger.error(f"加载全局搜索检查点失败: {str(e)}")
                    checkpoint_data = None
        
        # 如果没有找到有效的检查点，则重新开始处理
        if not checkpoint_data:
            self.logger.warning(f"未找到有效的检查点，将重新开始处理")
            return await self.process(query, input_dirs, context)
        
        # 设置当前步骤和工作目录
        self._current_step = checkpoint_data.get('current_step', 'unknown')
        
        # 恢复工作目录
        if 'work_dir' in checkpoint_data:
            self.current_work_dir = Path(checkpoint_data['work_dir'])
            self.logger.info(f"恢复工作目录: {self.current_work_dir}")
        elif 'iteration' in checkpoint_data:
            iteration = checkpoint_data['iteration']
            self.current_work_dir = self.iterations_dir / f"iter{iteration}"
            self.logger.info(f"根据迭代号恢复工作目录: {self.current_work_dir}")
        
        # 检查工作目录是否存在
        if not self.current_work_dir.exists():
            self.logger.warning(f"恢复的工作目录不存在: {self.current_work_dir}，将重新开始处理")
            return await self.process(query, input_dirs, context)
        
        # 根据检查点的步骤决定如何恢复
        self.logger.info(f"准备从步骤 '{self._current_step}' 恢复处理")
        
        # 检查是否需要重新初始化组件
        if checkpoint_data.get('components_initialized', False) and not hasattr(self, 'components'):
            # 尝试重新初始化组件
            db_path = self.current_work_dir / "data" / "unified_storage.duckdb"
            if db_path.exists():
                self.logger.info(f"重新初始化组件，使用数据库: {db_path}")
                self.components = self._init_components(str(db_path))
            else:
                self.logger.warning("无法重新初始化组件，数据库文件不存在")
        
        # 根据当前步骤决定如何恢复
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
            
        elif self._current_step == "initialize_components":
            # 如果是在初始化组件阶段中断
            self.logger.info("从初始化组件阶段继续")
            return await self.process(query, input_dirs, context)
            
        elif self._current_step in ["parse_intent", "build_plan", "execute_workflow"]:
            # 如果是在工作流执行阶段中断，可以尝试从该步骤继续
            self.logger.info(f"从工作流执行阶段继续: {self._current_step}")
            
            # 检查组件是否已初始化
            if not hasattr(self, 'components') or not self.components:
                self.logger.warning("组件未初始化，尝试重新初始化")
                db_path = self.current_work_dir / "data" / "unified_storage.duckdb"
                if db_path.exists():
                    self.components = self._init_components(str(db_path))
                    self.logger.info("已重新初始化组件")
                else:
                    self.logger.error("无法重新初始化组件，数据库文件不存在")
                    return await self.process(query, input_dirs, context)
            
            # 根据中断的步骤决定如何继续
            if self._current_step == "parse_intent":
                # 如果是在解析意图阶段中断，从工作流开始执行
                self.logger.info("从解析意图阶段继续执行工作流")
                
                # 确保查询不为None
                if query is None:
                    error_msg = "恢复处理时查询文本为None，无法执行工作流"
                    self.logger.error(error_msg)
                    return {
                        'status': 'error',
                        'message': error_msg,
                        'results': None
                    }
                
                results = await self._execute_workflow(query)
                return {
                    'status': 'resumed',
                    'message': f'从{self._current_step}阶段恢复处理',
                    'results': results
                }
            
            elif self._current_step == "build_plan":
                # 如果是在构建计划阶段中断
                self.logger.info("从构建计划阶段继续执行工作流")
                
                # 确保查询不为None
                if query is None:
                    error_msg = "恢复处理时查询文本为None，无法执行工作流"
                    self.logger.error(error_msg)
                    return {
                        'status': 'error',
                        'message': error_msg,
                        'results': None
                    }
                
                # 检查组件是否已初始化
                if not hasattr(self, 'components') or not self.components:
                    self.logger.warning("组件未初始化，尝试重新初始化")
                    db_path = self.current_work_dir / "data" / "unified_storage.duckdb"
                    if db_path.exists():
                        self.components = self._init_components(str(db_path))
                        self.logger.info("已重新初始化组件")
                    else:
                        self.logger.error("无法重新初始化组件，数据库文件不存在")
                        return await self.process(query, input_dirs, context)
                
                # 根据中断的步骤决定如何继续
                if self._current_step == "build_plan":
                    # 如果是在构建计划阶段中断
                    self.logger.info("从构建计划阶段继续执行工作流")
                    
                    # 检查是否有工作流结果文件
                    workflow_results_file = self.current_work_dir / "workflow_results.json"
                    if workflow_results_file.exists():
                        try:
                            with open(workflow_results_file, 'r', encoding='utf-8') as f:
                                workflow_results = json.load(f)
                            self.logger.info("已从工作流结果文件恢复处理结果")
                            return {
                                'status': 'resumed',
                                'message': '从构建计划阶段恢复处理，已找到工作流结果文件',
                                'results': workflow_results
                            }
                        except Exception as e:
                            self.logger.error(f"加载工作流结果文件失败: {str(e)}")
                    
                    # 如果没有工作流结果文件，重新执行工作流
                    self.logger.info("未找到工作流结果文件，重新执行工作流")
                    results = await self._execute_workflow(query)
                    return {
                        'status': 'resumed',
                        'message': f'从{self._current_step}阶段恢复处理',
                        'results': results
                    }
            
            elif self._current_step == "execute_workflow":
                # 如果是在执行工作流阶段中断
                self.logger.info("从执行工作流阶段继续")
                
                # 检查是否有工作流结果文件
                workflow_results_file = self.current_work_dir / "workflow_results.json"
                if workflow_results_file.exists():
                    try:
                        with open(workflow_results_file, 'r', encoding='utf-8') as f:
                            workflow_results = json.load(f)
                        self.logger.info("已从工作流结果文件恢复处理结果")
                        return {
                            'status': 'resumed',
                            'message': '从执行工作流阶段恢复处理，已找到工作流结果文件',
                            'results': workflow_results
                        }
                    except Exception as e:
                        self.logger.error(f"加载工作流结果文件失败: {str(e)}")
                
                # 如果没有工作流结果文件，重新执行工作流
                self.logger.info("未找到工作流结果文件，重新执行工作流")
                
                # 确保查询不为None
                if query is None:
                    error_msg = "恢复处理时查询文本为None，无法执行工作流"
                    self.logger.error(error_msg)
                    return {
                        'status': 'error',
                        'message': error_msg,
                        'results': None
                    }
                
                results = await self._execute_workflow(query)
                return {
                    'status': 'resumed',
                    'message': f'从{self._current_step}阶段恢复处理',
                    'results': results
                }
        
        elif self._current_step == "finalize":
            # 如果是在最终阶段中断，可能已经完成大部分工作
            self.logger.info("从最终阶段继续，可能已经完成大部分工作")
            # 检查是否有结果文件
            results_file = self.current_work_dir / "results.json"
            if results_file.exists():
                try:
                    with open(results_file, 'r', encoding='utf-8') as f:
                        results = json.load(f)
                    self.logger.info("已从结果文件恢复处理结果")
                    return {
                        'status': 'resumed',
                        'message': '从最终阶段恢复处理，已找到结果文件',
                        'results': results
                    }
                except Exception as e:
                    self.logger.error(f"加载结果文件失败: {str(e)}")
            
            # 如果没有结果文件，重新执行工作流
            self.logger.info("未找到结果文件，重新执行工作流")
            
            # 确保查询不为None
            if query is None:
                error_msg = "恢复处理时查询文本为None，无法执行工作流"
                self.logger.error(error_msg)
                return {
                    'status': 'error',
                    'message': error_msg,
                    'results': None
                }
            
            results = await self._execute_workflow(query)
            return {
                'status': 'resumed',
                'message': '从最终阶段恢复处理，重新执行工作流',
                'results': results
            }
            
        # 默认情况：无法精确恢复，重新开始处理
        self.logger.warning(f"无法从步骤{self._current_step}精确恢复，将重新开始处理")
        return await self.process(query, input_dirs, context)

    async def _emit_event(self, event_type: AlchemyEventType, data: Any = None):
        """发出事件（内部方法）"""
        await self.event_bus.publish(event_type, data)