"""
反馈优化工作流模块，用于处理用户反馈并生成优化后的交付物
"""
from typing import Dict, List, Optional, Any
import json
from pathlib import Path
import logging
from datetime import datetime
import numpy as np

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
        
    def set_search_engine(self, search_engine):
        """设置搜索引擎实例"""
        self.search_engine = search_engine
        
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
            
            # 在原始计划目录下创建新的迭代子目录
            original_plan_dir = Path(original_plan['_file_paths']['base_dir'])
            iteration_dir = original_plan_dir / f"iteration_{iteration + 1}"
            iteration_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                # 执行优化后的查询
                search_results = self.search_engine.execute_structured_query({
                    'type': 'text',
                    'content': optimized_query['query']
                })
                
                # 执行向量搜索
                vector_results = self.search_engine.execute_vector_search(
                    optimized_query['reference_text']
                )
                
                # 整合结果
                results = {
                    'structured': search_results.to_dict('records') if not search_results.empty else [],
                    'vector': vector_results,
                    'stats': {
                        'total': len(search_results) + len(vector_results),
                        'structured_count': len(search_results),
                        'vector_count': len(vector_results)
                    },
                    'insights': {},
                    'context': {}
                }
                
                # 创建新的迭代计划
                iteration_plan = {
                    'original_plan_id': original_plan_id,
                    'iteration': iteration + 1,
                    'feedback': feedback,
                    'analysis': analysis,
                    'query_params': optimized_query,
                    'delivery_config': original_plan['delivery_config'],
                    'search_results': results,
                    '_file_paths': {
                        'base_dir': str(iteration_dir),
                        'delivery_plan': str(iteration_dir / 'delivery_plan.json'),
                        'search_results': str(iteration_dir / 'search_results.json'),
                        'reasoning_process': str(iteration_dir / 'reasoning_process.md')
                    }
                }
                
                # 先保存迭代计划
                new_plan_id = f"{original_plan_id}_iteration_{iteration + 1}"
                if not self._save_delivery_plan(new_plan_id, iteration_plan):
                    return {'status': 'error', 'message': '保存迭代计划失败'}
                
                # 更新原始计划以包含迭代信息
                if 'iterations' not in original_plan:
                    original_plan['iterations'] = []
                original_plan['iterations'].append({
                    'iteration': iteration + 1,
                    'feedback': feedback,
                    'plan_id': new_plan_id,
                    'directory': str(iteration_dir)
                })
                if not self._save_delivery_plan(original_plan_id, original_plan):
                    return {'status': 'error', 'message': '更新原始计划失败'}
                
                try:
                    # 生成新的交付物
                    new_deliverables = await self.delivery_generator.generate_deliverables(
                        plan_id=str(iteration_dir),
                        search_results=results,
                        delivery_config=original_plan.get('delivery_config')
                    )
                    
                    # 更新迭代计划以包含交付物信息
                    iteration_plan['deliverables'] = new_deliverables
                    if not self._save_delivery_plan(new_plan_id, iteration_plan):
                        return {'status': 'error', 'message': '更新迭代计划交付物信息失败'}
                    
                    return {
                        'status': 'success',
                        'plan_id': new_plan_id,
                        'deliverables': new_deliverables,
                        'iteration_dir': str(iteration_dir)
                    }
                    
                except Exception as e:
                    logger.error(f"生成交付物失败: {str(e)}")
                    return {'status': 'error', 'message': str(e)}
                
            except Exception as e:
                logger.error(f"搜索过程中发生错误: {str(e)}")
                return {'status': 'error', 'message': str(e)}
            
        except Exception as e:
            logger.error(f"处理反馈失败: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _load_delivery_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """加载交付计划
        
        Args:
            plan_id: 计划ID
            
        Returns:
            Optional[Dict[str, Any]]: 交付计划数据，如果加载失败则返回None
        """
        try:
            # 构建计划目录路径
            plan_base_dir = Path(self.work_dir) / 'output' / 'intelligent_search' / 'delivery_plans'
            plan_dir = plan_base_dir / plan_id
            plan_file = plan_dir / 'delivery_plan.json'
            
            if not plan_file.exists():
                logger.error(f"交付计划文件不存在: {plan_file}")
                return None
            
            # 加载计划数据
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
                
                # 保存更新后的计划数据
                with open(plan_file, 'w', encoding='utf-8') as f:
                    json.dump(plan_data, f, ensure_ascii=False, indent=2)
            
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
            # 构建计划目录路径
            plan_base_dir = Path(self.work_dir) / 'output' / 'intelligent_search' / 'delivery_plans'
            plan_dir = plan_base_dir / plan_id
            plan_dir.mkdir(parents=True, exist_ok=True)
            
            # 确保计划数据包含文件路径信息
            if '_file_paths' not in plan_data:
                plan_data['_file_paths'] = {
                    'base_dir': str(plan_dir),
                    'delivery_plan': str(plan_dir / 'delivery_plan.json'),
                    'search_results': str(plan_dir / 'search_results.json'),
                    'reasoning_process': str(plan_dir / 'reasoning_process.md')
                }
            
            # 转换numpy类型为Python原生类型
            def convert_numpy_types(obj):
                if isinstance(obj, dict):
                    return {key: convert_numpy_types(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy_types(item) for item in obj]
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
            
            # 转换数据中的numpy类型
            converted_data = convert_numpy_types(plan_data)
            
            # 保存计划文件
            with open(plan_dir / 'delivery_plan.json', 'w', encoding='utf-8') as f:
                json.dump(converted_data, f, ensure_ascii=False, indent=2)
                
            return True
            
        except Exception as e:
            logger.error(f"保存交付计划失败: {str(e)}", exc_info=True)
            return False 