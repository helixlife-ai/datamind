"""
反馈优化工作流模块，用于处理用户反馈并生成优化后的交付物
"""
from typing import Dict, List, Optional, Any, Tuple
import json
from pathlib import Path
import logging
from datetime import datetime
import numpy as np
import asyncio

from .delivery_generator import DeliveryGenerator

logger = logging.getLogger(__name__)

class FeedbackAnalyzer:
    """用户反馈分析器"""
    
    def analyze(self, feedback_text: str) -> Dict[str, Any]:
        """分析用户反馈，提取关键信息和优化方向
        
        Args:
            feedback_text: 用户提供的反馈文本
            
        Returns:
            包含分析结果的字典，包括操作类型、目标章节、内容需求等
        """
        # TODO: 后续可以接入更复杂的NLP模型
        analysis = {
            'operation_type': self._detect_operation_type(feedback_text),
            'target_sections': self._extract_sections(feedback_text),
            'content_requests': self._extract_requests(feedback_text),
            'format_preferences': self._extract_formats(feedback_text)
        }
        return analysis
    
    def _detect_operation_type(self, text: str) -> str:
        """检测反馈中的操作类型"""
        # 简单的关键词匹配
        if any(word in text for word in ['增加', '添加', '补充']):
            return 'add'
        elif any(word in text for word in ['删除', '移除', '去掉']):
            return 'remove'
        elif any(word in text for word in ['修改', '调整', '更新']):
            return 'modify'
        return 'enhance'  # 默认为增强
    
    def _extract_sections(self, text: str) -> List[str]:
        """提取反馈中提到的目标章节"""
        sections = []
        # 简单的章节关键词匹配
        section_keywords = ['章节', '部分', '段落', '小节']
        words = text.split()
        for i, word in enumerate(words):
            if word in section_keywords and i > 0:
                sections.append(words[i-1])
        return sections
    
    def _extract_requests(self, text: str) -> List[str]:
        """提取具体的内容需求"""
        requests = []
        # 简单的需求关键词匹配
        request_keywords = ['需要', '希望', '应该', '建议']
        words = text.split()
        for i, word in enumerate(words):
            if word in request_keywords and i < len(words) - 1:
                requests.append(words[i+1])
        return requests
    
    def _extract_formats(self, text: str) -> List[str]:
        """提取格式相关的偏好"""
        formats = []
        # 简单的格式关键词匹配
        format_keywords = ['格式', '样式', '排版', '布局']
        words = text.split()
        for i, word in enumerate(words):
            if word in format_keywords and i < len(words) - 1:
                formats.append(words[i+1])
        return formats

class QueryOptimizer:
    """查询优化器"""
    
    def optimize(self, original_query: Dict[str, Any], feedback_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """基于反馈分析优化原始查询
        
        Args:
            original_query: 原始查询参数
            feedback_analysis: 反馈分析结果
            
        Returns:
            优化后的查询参数
        """
        optimized_query = original_query.copy()
        
        # 根据操作类型调整查询策略
        operation_type = feedback_analysis['operation_type']
        if operation_type == 'add':
            self._expand_query(optimized_query, feedback_analysis)
        elif operation_type == 'modify':
            self._adjust_weights(optimized_query, feedback_analysis)
        elif operation_type == 'remove':
            self._remove_content(optimized_query, feedback_analysis)
        else:  # enhance
            self._enhance_query(optimized_query, feedback_analysis)
            
        return optimized_query
    
    def _expand_query(self, query: Dict[str, Any], analysis: Dict[str, Any]):
        """扩展查询范围"""
        if 'keywords' in query:
            new_keywords = analysis.get('content_requests', [])
            query['keywords'].extend([k for k in new_keywords if k not in query['keywords']])
        
        if 'filters' in query and analysis.get('target_sections'):
            query['filters']['sections'] = list(set(
                query['filters'].get('sections', []) + analysis['target_sections']
            ))
    
    def _adjust_weights(self, query: Dict[str, Any], analysis: Dict[str, Any]):
        """调整查询权重"""
        if 'weights' not in query:
            query['weights'] = {}
            
        # 根据反馈调整权重
        for request in analysis.get('content_requests', []):
            query['weights'][request] = query['weights'].get(request, 1.0) + 0.2
    
    def _remove_content(self, query: Dict[str, Any], analysis: Dict[str, Any]):
        """移除内容"""
        if 'exclude_keywords' not in query:
            query['exclude_keywords'] = []
            
        query['exclude_keywords'].extend(analysis.get('content_requests', []))
    
    def _enhance_query(self, query: Dict[str, Any], analysis: Dict[str, Any]):
        """增强查询"""
        self._expand_query(query, analysis)
        self._adjust_weights(query, analysis)

class FeedbackOptimizer:
    """反馈优化工作流管理器"""
    
    def __init__(self, work_dir: str, search_engine=None):
        self.work_dir = Path(work_dir)
        self.search_engine = search_engine
        self.delivery_generator = DeliveryGenerator()
        self.feedback_analyzer = FeedbackAnalyzer()
        self.query_optimizer = QueryOptimizer()
        self.max_iterations = 5
        self.max_retries = 5
        self.retry_interval = 1  # 秒
        
        # 默认的必需文件
        self.required_files = [
            'delivery_plan.json',
            'search_results.json',
            'reasoning_process.md'
        ]
        
    def set_search_engine(self, search_engine):
        """设置搜索引擎实例"""
        self.search_engine = search_engine
        
    async def wait_for_files(self, plan_dir: Path, required_files: List[str] = None) -> bool:
        """等待必需文件生成完成
        
        Args:
            plan_dir: 计划目录
            required_files: 需要等待的文件列表，如果为None则使用默认列表
            
        Returns:
            bool: 文件是否就绪
        """
        if required_files is None:
            required_files = self.required_files
            
        file_paths = [plan_dir / f for f in required_files]
        
        for retry in range(self.max_retries):
            if all(f.exists() for f in file_paths):
                logger.info("所需文件已就绪")
                return True
                
            if retry < self.max_retries - 1:
                logger.info(f"等待文件生成完成，{self.retry_interval}秒后重试...")
                await asyncio.sleep(self.retry_interval)
                
        logger.warning("等待文件超时")
        return False
        
    def _get_plan_dir(self, plan_id: str) -> Path:
        """获取计划目录路径
        
        Args:
            plan_id: 计划ID
            
        Returns:
            Path: 计划目录路径
        """
        return Path(self.work_dir) / 'output' / 'delivery_plans' / plan_id
        
    def _convert_numpy_types(self, obj: Any) -> Any:
        """转换numpy类型为Python原生类型
        
        Args:
            obj: 需要转换的对象
            
        Returns:
            转换后的对象
        """
        if isinstance(obj, dict):
            return {key: self._convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_numpy_types(item) for item in obj]
        elif isinstance(obj, (np.int8, np.int16, np.int32, np.int64,
                            np.uint8, np.uint16, np.uint32, np.uint64)):
            return int(obj)
        elif isinstance(obj, (np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif hasattr(obj, 'dtype') and np.isscalar(obj):
            return obj.item()
        return obj
        
    def _load_delivery_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """加载交付计划
        
        Args:
            plan_id: 计划ID
            
        Returns:
            Optional[Dict[str, Any]]: 交付计划数据，如果加载失败则返回None
        """
        try:
            plan_dir = self._get_plan_dir(plan_id)
            plan_file = plan_dir / 'delivery_plan.json'
            
            if not plan_file.exists():
                logger.error(f"交付计划文件不存在: {plan_file}")
                return None
            
            with open(plan_file, 'r', encoding='utf-8') as f:
                plan_data = json.load(f)
                
            # 确保计划数据包含必要的文件路径信息
            if '_file_paths' not in plan_data:
                plan_data['_file_paths'] = {
                    'base_dir': str(plan_dir),
                    'delivery_plan': str(plan_file),
                    'search_results': str(plan_dir / 'search_results.json'),
                    'reasoning_process': str(plan_dir / 'reasoning_process.md')
                }
                self._save_delivery_plan(plan_id, plan_data)
            
            return plan_data
            
        except Exception as e:
            logger.error(f"加载交付计划失败: {str(e)}", exc_info=True)
            return None

    def _save_delivery_plan(self, plan_id: str, plan_data: Dict[str, Any]) -> bool:
        """保存交付计划
        
        Args:
            plan_id: 计划ID
            plan_data: 计划数据
            
        Returns:
            bool: 保存是否成功
        """
        try:
            plan_dir = self._get_plan_dir(plan_id)
            plan_dir.mkdir(parents=True, exist_ok=True)
            
            # 确保计划数据包含文件路径信息
            if '_file_paths' not in plan_data:
                plan_data['_file_paths'] = {
                    'base_dir': str(plan_dir),
                    'delivery_plan': str(plan_dir / 'delivery_plan.json'),
                    'search_results': str(plan_dir / 'search_results.json'),
                    'reasoning_process': str(plan_dir / 'reasoning_process.md')
                }
            
            # 转换数据中的numpy类型
            converted_data = self._convert_numpy_types(plan_data)
            
            # 保存计划文件
            with open(plan_dir / 'delivery_plan.json', 'w', encoding='utf-8') as f:
                json.dump(converted_data, f, ensure_ascii=False, indent=2)
                
            return True
            
        except Exception as e:
            logger.error(f"保存交付计划失败: {str(e)}", exc_info=True)
            return False

    async def process_feedback(self, 
                             original_plan_id: str,
                             feedback: str,
                             iteration: int = 0) -> Dict[str, Any]:
        """处理用户反馈并生成优化后的交付物"""
        try:
            if iteration >= self.max_iterations:
                logger.warning(f"达到最大迭代次数 {self.max_iterations}")
                return {'status': 'max_iterations_reached'}
                
            if not self.search_engine:
                return {'status': 'error', 'message': 'Search engine not initialized'}
                
            # 加载原始计划
            original_plan = self._load_delivery_plan(original_plan_id)
            if not original_plan:
                return {'status': 'error', 'message': 'Original plan not found'}
                
            # 分析反馈
            analysis = self.feedback_analyzer.analyze(feedback)
            logger.info(f"反馈分析结果: {analysis}")
            
            # 优化查询
            optimized_query = self.query_optimizer.optimize(
                original_plan['query_params'],
                analysis
            )
            
            # 创建新的迭代计划
            iteration_plan = await self._create_iteration_plan(
                original_plan_id, 
                original_plan,
                iteration,
                feedback,
                analysis,
                optimized_query
            )
            
            if not iteration_plan:
                return {'status': 'error', 'message': '创建迭代计划失败'}
                
            return {
                'status': 'success',
                'plan_id': iteration_plan['plan_id'],
                'deliverables': iteration_plan.get('deliverables', []),
                'iteration_dir': iteration_plan['_file_paths']['base_dir']
            }
            
        except Exception as e:
            logger.error(f"处理反馈失败: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e)
            }

    async def run_test_optimization(self, delivery_plan: Dict) -> None:
        """运行反馈优化测试流程
        
        Args:
            delivery_plan: 原始交付计划
        """
        print("\n=== 开始反馈优化流程测试 ===")
        
        # 等待原始交付文件生成完成
        plan_dir = Path(delivery_plan['_file_paths']['base_dir'])
        if not await self.wait_for_files(plan_dir):
            print("等待交付文件超时，跳过反馈优化流程")
            return
            
        print("交付文件已就绪，开始反馈优化流程")
        
        # 示例反馈
        test_feedbacks = [
            "请在AI趋势分析中增加更多关于大模型发展的内容",
            "建议删除过时的技术参考",
            "希望在报告中补充更多实际应用案例"
        ]
        
        # 获取计划ID
        plan_id = plan_dir.name
        
        # 执行多轮反馈优化
        for i, feedback in enumerate(test_feedbacks, 1):
            print(f"\n第{i}轮反馈优化:")
            print(f"用户反馈: {feedback}")
            
            # 处理反馈
            feedback_result = await self.process_feedback(plan_id, feedback)
            
            if feedback_result['status'] == 'success':
                print(f"反馈处理成功！新计划ID: {feedback_result['plan_id']}")
                print("已生成优化后的交付物:")
                for deliverable in feedback_result['deliverables']:
                    print(f"- {deliverable}")
                # 更新计划ID用于下一轮优化
                plan_id = feedback_result['plan_id']
            else:
                print(f"反馈处理失败: {feedback_result.get('message', '未知错误')}")
                break
                
        print("\n反馈优化流程测试完成") 