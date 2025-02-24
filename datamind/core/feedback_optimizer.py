"""
反馈优化工作流模块，用于处理用户反馈并生成新的查询
"""
from typing import Dict, List, Optional, Any
import json
from pathlib import Path
import logging
from datetime import datetime

from ..core.reasoning import ReasoningEngine

logger = logging.getLogger(__name__)

class FeedbackOptimizer:
    """反馈优化工作流管理器"""
    
    def __init__(self, work_dir: str = "work_dir", reasoning_engine: Optional[ReasoningEngine] = None, logger: Optional[logging.Logger] = None):
        """初始化反馈优化工作流管理器
        
        Args:
            work_dir: 工作目录，现在是迭代目录 (alchemy_runs/alchemy_{id}/search/iterations/iterX)
            reasoning_engine: 推理引擎实例
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.work_dir = Path(work_dir)
        self.reasoning_engine = reasoning_engine
        
        # 从迭代目录计算各个重要路径
        self.iter_dir = self.work_dir  # 当前迭代目录
        self.iterations_dir = self.iter_dir.parent  # iterations目录
        self.search_dir = self.iterations_dir.parent  # search目录
        self.alchemy_dir = self.search_dir.parent  # alchemy_{id}目录
        
        # 获取当前迭代信息
        self.current_iteration = int(self.iter_dir.name.replace('iter', ''))
        self.alchemy_id = self.alchemy_dir.name.split('alchemy_')[-1]
        
        # 设置制品目录
        self.artifacts_dir = self.alchemy_dir / "artifacts"
        
        if not self.reasoning_engine:
            self.logger.warning("未提供推理引擎实例，部分功能可能受限")
            
        # 初始化反馈队列
        self.feedback_stack = []
        
    async def push_feedback(self, feedback: str, alchemy_dir: str):
        """压入新反馈到处理队列"""
        self.feedback_stack.append({
            'alchemy_dir': alchemy_dir,
            'feedback': feedback,
            'status': 'pending'
        })
        
    async def process_next_feedback(self) -> Dict[str, Any]:
        """处理下一个待处理反馈"""
        if not self.feedback_stack:
            return {'status': 'error', 'message': 'No pending feedback'}
            
        current_fb = self.feedback_stack.pop(0)
        result = await self.feedback_to_query(
            current_fb['alchemy_dir'], 
            current_fb['feedback']
        )
        current_fb.update({
            'processed_at': datetime.now().isoformat(),
            'result': result
        })
        return result

    async def get_latest_artifact_suggestion(self, alchemy_id: Optional[str] = None) -> Optional[str]:
        """获取最新制品的优化建议"""
        try:
            alchemy_id = alchemy_id or self.alchemy_id
            
            if not self.artifacts_dir.exists():
                self.logger.warning(f"未找到制品目录: {self.artifacts_dir}")
                return None

            status_path = self.artifacts_dir / "status.json"
            if not status_path.exists():
                self.logger.warning(f"未找到状态文件: {status_path}")
                return None

            with open(status_path, 'r', encoding='utf-8') as f:
                status_info = json.load(f)

            iterations = status_info.get('iterations', [])
            if not iterations:
                self.logger.info("没有找到迭代记录")
                return None

            latest_iteration = iterations[-1]
            suggestion = latest_iteration.get('optimization_suggestion')
            
            if suggestion:
                self.logger.info(f"找到最新的优化建议: {suggestion}")
                return suggestion
            else:
                self.logger.info("最新迭代中没有优化建议")
            
            return None

        except Exception as e:
            self.logger.error(f"获取制品优化建议时发生错误: {str(e)}")
            return None

    async def feedback_to_query(self, alchemy_dir: str, feedback: str) -> Dict[str, Any]:
        """将用户反馈转换为新的查询
        
        现在会优先使用制品生成的优化建议，如果没有才使用用户反馈生成新查询
        """
        try:
            if not self.reasoning_engine:
                raise ValueError("未配置推理引擎，无法处理反馈")
            
            # 首先尝试获取制品的优化建议
            optimization_query = await self.get_latest_artifact_suggestion()
            
            if optimization_query:
                return {
                    'status': 'success',
                    'message': 'Using artifact optimization suggestion',
                    'query': optimization_query,
                    'source': 'artifact_suggestion'
                }

            # 如果没有制品优化建议，则使用用户反馈生成新查询
            feedback_file = Path(alchemy_dir) / "feedback.txt"
            
            if not feedback_file.exists():
                return {
                    'status': 'error',
                    'message': 'Feedback file not found'
                }
                
            with open(feedback_file, 'r', encoding='utf-8') as f:
                feedback_content = f.read().strip()
                
            if not feedback_content:
                return {
                    'status': 'error',
                    'message': 'Feedback content is empty'
                }
            
            # 加载当前迭代上下文
            context = self._load_current_context(alchemy_dir)
            
            # 添加用户消息
            self.reasoning_engine.add_message("user", f"""
                原始查询：{context['original_query']}
                
                用户反馈：{feedback_content}
                
                请生成一个新的查询文本，要求：
                1. 融合原始查询的目标和用户的反馈建议
                2. 使用清晰的自然语言表达
                3. 保持查询的可执行性
            """)
            
            # 使用流式输出获取响应
            full_response = ""
            new_query = ""
            
            async for chunk in self.reasoning_engine.get_stream_response(
                temperature=0.7,
                metadata={'stage': 'feedback_optimization'}
            ):
                if chunk:
                    full_response += chunk
                    self.logger.info(f"\r生成新查询: {full_response}")
                    
                    # 如果发现完整的句子，更新查询
                    if any(chunk.strip().endswith(end) for end in ['。', '？', '!']):
                        new_query = full_response.strip()
            
            if new_query:
                # 记录优化过程
                log_dir = Path(alchemy_dir) / "feedback_logs"
                log_dir.mkdir(exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_file = log_dir / f"feedback_optimization_{timestamp}.json"
                
                log_data = {
                    "timestamp": timestamp,
                    "original_query": context['original_query'],
                    "user_feedback": feedback_content,
                    "new_query": new_query,
                    "source": "user_feedback",
                    "chat_history": self.reasoning_engine.get_chat_history()
                }
                
                with open(log_file, 'w', encoding='utf-8') as f:
                    json.dump(log_data, f, ensure_ascii=False, indent=2)
                
                return {
                    'status': 'success',
                    'message': 'Successfully generated new query from user feedback',
                    'query': new_query,
                    'source': 'user_feedback'
                }
            else:
                return {
                    'status': 'error',
                    'message': 'Failed to generate new query'
                }

        except Exception as e:
            self.logger.error(f"处理反馈失败: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e)
            }

    def _load_current_context(self, iter_dir: Optional[Path] = None) -> Dict:
        """加载当前迭代的上下文
        
        Args:
            iter_dir: 可选，指定迭代目录，默认使用当前迭代目录
            
        Returns:
            Dict: 上下文信息
        """
        try:
            iter_dir = iter_dir or self.iter_dir
            context_file = iter_dir / "context.json"
            
            if not context_file.exists():
                return {
                    'original_query': '',
                    'previous_feedbacks': [],
                    'iteration': self.current_iteration
                }
                
            with open(context_file, 'r', encoding='utf-8') as f:
                context = json.load(f)
                
            # 获取之前的反馈历史
            previous_feedbacks = []
            if self.current_iteration > 1:
                for i in range(1, self.current_iteration):
                    prev_iter_dir = self.iterations_dir / f"iter{i}"
                    prev_context_file = prev_iter_dir / "context.json"
                    if prev_context_file.exists():
                        with open(prev_context_file, 'r', encoding='utf-8') as f:
                            prev_context = json.load(f)
                            if prev_context.get('feedback'):
                                previous_feedbacks.append(prev_context['feedback'])
            
            return {
                'original_query': context.get('original_query', ''),
                'previous_feedbacks': previous_feedbacks,
                'iteration': self.current_iteration
            }
            
        except Exception as e:
            self.logger.error(f"加载上下文失败: {str(e)}")
            return {
                'original_query': '',
                'previous_feedbacks': [],
                'iteration': self.current_iteration
            }

    def _get_original_query(self, alchemy_path: Path) -> str:
        """从炼丹工作流目录获取原始查询"""
        try:
            # 修正交付计划文件路径到当前run目录
            plan_file = alchemy_path / "delivery" / "delivery_plan.json"  # 移除.parent
            
            if not plan_file.exists():
                    raise FileNotFoundError(f"交付计划文件不存在: {plan_file}")

            with open(plan_file, 'r', encoding='utf-8') as f:
                delivery_plan = json.load(f)
                return delivery_plan.get('metadata', {}).get('original_query', '')
            
        except Exception as e:
            self.logger.error(f"获取原始查询失败: {str(e)}")
            return ""

    def _get_feedback_history(self, parent_dir: Path) -> List[Dict]:
        """获取历史反馈记录
        
        从父目录的context.json文件中获取反馈历史。
        
        Args:
            parent_dir: 父目录路径
            
        Returns:
            List[Dict]: 反馈历史记录列表
            [{
                'iteration': int,
                'timestamp': str,
                'feedback': str,
                'original_query': str
            }]
        """
        feedback_history = []
        
        try:
            # 遍历所有run_*目录
            for run_dir in sorted(parent_dir.glob("run_*")):
                context_file = run_dir / "context.json"
                
                if context_file.exists():
                    try:
                        with open(context_file, 'r', encoding='utf-8') as f:
                            context_data = json.load(f)
                            
                        if isinstance(context_data, dict):
                            # 从上下文中提取反馈信息
                            feedback_history.append({
                                'iteration': context_data.get('metadata', {}).get('iteration', 1),
                                'timestamp': context_data.get('metadata', {}).get('timestamp', ''),
                                'feedback': context_data.get('current_feedback', ''),
                                'original_query': context_data.get('original_query', '')
                            })
                            
                    except Exception as e:
                        self.logger.warning(f"加载上下文文件失败 {context_file}: {str(e)}")
                        continue
                        
            # 按迭代次数排序
            feedback_history.sort(key=lambda x: x['iteration'])
            return feedback_history
            
        except Exception as e:
            self.logger.error(f"获取反馈历史失败: {str(e)}")
            return []

    def get_delivery_files(self, alchemy_dir: str) -> Dict[str, list]:
        """获取交付目录中的文件和文件夹列表
        
        Args:
            alchemy_dir: 炼丹工作流运行目录
            
        Returns:
            Dict[str, list]: 包含文件和文件夹列表的字典
            {
                'files': [文件路径列表],
                'dirs': [文件夹路径列表]
            }
        """
        try:
            delivery_dir = Path(alchemy_dir) / "delivery"
            if not delivery_dir.exists():
                self.logger.error(f"交付目录不存在: {delivery_dir}")
                return {'files': [], 'dirs': []}
            
            files = []
            dirs = []
            
            # 遍历目录内容
            for item in delivery_dir.iterdir():
                # 使用相对于delivery目录的路径
                rel_path = item.relative_to(delivery_dir)
                if item.is_file():
                    files.append(str(rel_path))
                elif item.is_dir():
                    dirs.append(str(rel_path))
                    # 递归获取子目录中的文件
                    for sub_item in item.rglob('*'):
                        if sub_item.is_file():
                            files.append(str(sub_item.relative_to(delivery_dir)))
            
            # 排序以保持稳定的顺序
            files.sort()
            dirs.sort()
            
            return {
                'files': files,
                'dirs': dirs
            }
            
        except Exception as e:
            self.logger.error(f"获取交付文件列表失败: {str(e)}", exc_info=True)
            return {'files': [], 'dirs': []}

    def read_delivery_file(self, alchemy_dir: str, file_path: str) -> Dict[str, Any]:
        """读取交付目录中指定文件的内容
        
        Args:
            alchemy_dir: 炼丹工作流运行目录
            file_path: 相对于delivery目录的文件路径
            
        Returns:
            Dict[str, Any]: 包含文件内容的字典
            {
                'status': 'success' | 'error',
                'message': str,
                'content': str,  # 文件内容（文本文件）或 base64 编码（二进制文件）
                'file_type': str,  # 文件类型（扩展名）
                'is_binary': bool  # 是否为二进制文件
            }
        """
        try:
            delivery_dir = Path(alchemy_dir) / "delivery"
            full_path = delivery_dir / file_path
            
            if not full_path.exists():
                return {
                    'status': 'error',
                    'message': f'文件不存在: {file_path}',
                    'content': '',
                    'file_type': '',
                    'is_binary': False
                }
            
            if not full_path.is_file():
                return {
                    'status': 'error',
                    'message': f'不是文件: {file_path}',
                    'content': '',
                    'file_type': '',
                    'is_binary': False
                }
                
            # 获取文件类型
            file_type = full_path.suffix.lstrip('.')
            
            # 定义二进制文件类型列表
            binary_types = {'docx', 'doc', 'pdf', 'xls', 'xlsx', 'zip', 'rar', 'png', 'jpg', 'jpeg', 'gif'}
            is_binary = file_type.lower() in binary_types
            
            # 根据文件类型选择读取模式
            if is_binary:
                import base64
                with open(full_path, 'rb') as f:
                    content = base64.b64encode(f.read()).decode('utf-8')
            else:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
            return {
                'status': 'success',
                'message': 'Successfully read file',
                'content': content,
                'file_type': file_type,
                'is_binary': is_binary
            }
            
        except Exception as e:
            self.logger.error(f"读取文件失败 {file_path}: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e),
                'content': '',
                'file_type': '',
                'is_binary': False
            }

    async def feedback_to_context(self, alchemy_dir: str) -> Dict[str, Any]:
        """基于当前交付物和用户反馈生成下次炼金的上下文
        
        Args:
            alchemy_dir: 炼丹工作流运行目录
            
        Returns:
            Dict[str, Any]: 包含上下文信息的字典
            {
                'status': 'success' | 'error',
                'message': str,
                'context': {
                    'original_query': str,
                    'current_query': str,  # 基于反馈生成的新查询
                    'current_feedback': str,
                    'feedback_history': List[Dict],
                    'delivery_files': {
                        'files': List[str],
                        'dirs': List[str]
                    },
                    'file_contents': {
                        'file_path': {
                            'content': str,
                            'type': str
                        }
                    },
                    'metadata': {
                        'iteration': int,
                        'timestamp': str
                    }
                }
            }
        """
        try:
            # 修正反馈文件路径到当前run目录
            feedback_file = Path(alchemy_dir) / "feedback.txt"  # 移除.parent
            
            if not feedback_file.exists():
                return {
                    'status': 'error',
                    'message': 'Feedback file not found'
                }
                
            with open(feedback_file, 'r', encoding='utf-8') as f:
                current_feedback = f.read().strip()
                
            if not current_feedback:
                return {
                    'status': 'error',
                    'message': 'Feedback content is empty'
                }
            
            # 获取交付文件列表
            delivery_files = self.get_delivery_files(alchemy_dir)
            
            # 读取所有交付文件内容
            file_contents = {}
            for file_path in delivery_files['files']:
                result = self.read_delivery_file(alchemy_dir, file_path)
                if result['status'] == 'success':
                    file_contents[file_path] = {
                        'content': result['content'],
                        'type': result['file_type']
                    }
            
            # 加载历史上下文
            context = self._load_current_context(alchemy_dir)
            
            # 生成新的查询
            query_result = await self.feedback_to_query(alchemy_dir, current_feedback)
            current_query = query_result['query'] if query_result['status'] == 'success' else ''
            
            # 构建完整上下文
            context_data = {
                'original_query': context['original_query'],
                'current_query': current_query,  # 使用生成的新查询
                'current_feedback': current_feedback,
                'feedback_history': context['previous_feedbacks'],
                'delivery_files': delivery_files,
                'file_contents': file_contents,
                'metadata': {
                    'iteration': context['iteration'],
                    'timestamp': datetime.now().isoformat()
                }
            }
            
            return {
                'status': 'success',
                'message': 'Successfully generated context',
                'context': context_data
            }
            
        except Exception as e:
            self.logger.error(f"生成上下文失败: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e),
                'context': None
            } 