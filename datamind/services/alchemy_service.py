import json
import time
import logging
import shutil
from pathlib import Path
from typing import Dict, List

from ..core.search import SearchEngine
from ..core.planner import SearchPlanner
from ..core.executor import SearchPlanExecutor
from ..core.processor import DataProcessor, FileCache
from ..core.parser import IntentParser
from ..core.delivery_planner import DeliveryPlanner
from ..core.delivery_generator import DeliveryGenerator
from ..core.feedback_optimizer import FeedbackOptimizer

class DataMindAlchemy:
    """数据炼丹工作流封装类"""
    
    def __init__(self, work_dir: Path = None):
        """初始化数据炼丹工作流
        
        Args:
            work_dir: 工作目录，默认为None时会使用默认路径
        """
        self.logger = logging.getLogger(__name__)
        self.work_dir = self._init_work_dir(work_dir)
        
    def _init_work_dir(self, work_dir: Path) -> Path:
        """初始化工作目录"""
        if work_dir is None:
            work_dir = Path("output") / "alchemy_runs"
        work_dir.mkdir(exist_ok=True, parents=True)
        return work_dir
        
    def _create_run_dir(self) -> Path:
        """创建运行目录"""
        run_id = time.strftime("%Y%m%d_%H%M%S")
        run_dir = self.work_dir / f"run_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
        
    def _init_components(self, db_path: str):
        """初始化组件"""
        search_engine = SearchEngine(db_path=db_path)
        intent_parser = IntentParser()
        planner = SearchPlanner()
        executor = SearchPlanExecutor(
            search_engine=search_engine,
            work_dir=str(self.run_dir / "search_results")
        )
        delivery_planner = DeliveryPlanner(
            work_dir=str(self.run_dir / "delivery")
        )
        delivery_generator = DeliveryGenerator()
        feedback_optimizer = FeedbackOptimizer(
            work_dir=str(self.run_dir / "feedback")
        )
        
        return {
            'intent_parser': intent_parser,
            'planner': planner,
            'executor': executor,
            'delivery_planner': delivery_planner,
            'delivery_generator': delivery_generator,
            'feedback_optimizer': feedback_optimizer
        }

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
            self.run_dir = self._create_run_dir()
            
            # 处理上下文
            if context:
                context_file = self.run_dir / "context.json"
                with open(context_file, 'w', encoding='utf-8') as f:
                    json.dump(context, f, ensure_ascii=False, indent=2)
            
            # 准备数据目录
            source_data = self.run_dir / "source_data"
            source_data.mkdir(exist_ok=True)
            
            # 复制上级source_data
            if context:
                await self._copy_parent_source_data(source_data)
                
            # 复制输入目录
            if input_dirs:
                await self._copy_input_dirs(input_dirs, source_data)
            
            # 初始化数据处理
            data_dir = self.run_dir / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = data_dir / "unified_storage.duckdb"
            cache_file = str(data_dir / "file_cache.pkl")
            
            # 处理数据
            processor = DataProcessor(db_path=str(db_path))
            processor.file_cache = FileCache(cache_file=cache_file)
            
            if source_data.exists() and any(source_data.iterdir()):
                await self._process_source_data(processor, source_data, db_path)
            
            # 初始化组件
            self.components = self._init_components(str(db_path))
            
            # 执行工作流
            return await self._execute_workflow(query)
            
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
                'parsed_intent': None,
                'search_plan': None,
                'search_results': None,
                'delivery_plan': None,
                'generated_files': []
            },
            'components': self.components
        }
        
        try:
            # 解析查询意图
            parsed_intent = await self.components['intent_parser'].parse_query(query)
            results['results']['parsed_intent'] = parsed_intent

            # 构建搜索计划
            parsed_plan = self.components['planner'].build_search_plan(parsed_intent)
            results['results']['search_plan'] = parsed_plan
            
            # 执行搜索计划
            search_results = await self.components['executor'].execute_plan(parsed_plan)
            results['results']['search_results'] = search_results
            
            if search_results['stats']['total'] > 0:
                # 生成交付计划
                delivery_plan = await self.components['delivery_planner'].generate_plan(
                    search_plan=parsed_plan,
                    search_results=search_results
                )
                
                if delivery_plan:
                    results['results']['delivery_plan'] = delivery_plan
                    delivery_dir = delivery_plan['_file_paths']['base_dir']
                    
                    # 生成交付文件
                    generated_files = await self.components['delivery_generator'].generate_deliverables(
                        delivery_dir,
                        search_results,
                        delivery_plan.get('delivery_config'),
                        test_mode=False
                    )
                    results['results']['generated_files'] = generated_files
                else:
                    results['status'] = 'error'
                    results['message'] = '交付计划生成失败'
            else:
                results['status'] = 'error'
                results['message'] = '未找到检索结果'
                
            return results
                
        except Exception as e:
            self.logger.error(f"处理查询失败: {str(e)}", exc_info=True)
            results['status'] = 'error'
            results['message'] = str(e)
            return results 