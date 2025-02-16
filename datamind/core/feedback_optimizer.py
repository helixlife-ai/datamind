"""
反馈优化工作流模块，用于处理用户反馈并生成新的查询
"""
from typing import Dict, List, Optional, Any
import json
from pathlib import Path
import logging
from datetime import datetime

from ..core.reasoning import ReasoningEngine
from ..config.settings import (
    DEFAULT_REASONING_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE
)

logger = logging.getLogger(__name__)

class FeedbackOptimizer:
    """反馈优化工作流管理器"""
    
    def __init__(self, work_dir: str, reasoning_engine: Optional[ReasoningEngine] = None, logger: Optional[logging.Logger] = None):
        """初始化反馈优化工作流管理器
        
        Args:
            work_dir: 工作目录
            reasoning_engine: 推理引擎实例，用于生成优化查询
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.work_dir = Path(work_dir)
        self.reasoning_engine = reasoning_engine
        self.feedback_stack = []  # 改为栈结构记录待处理反馈
        
        if not self.reasoning_engine:
            self.logger.warning("未提供推理引擎实例，部分功能可能受限")
                
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

    async def feedback_to_query(self, alchemy_dir: str, feedback: str) -> Dict[str, Any]:
        """将用户反馈转换为新的查询"""
        try:
            if not self.reasoning_engine:
                raise ValueError("未配置推理引擎，无法处理反馈")
                
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
            
            # 获取响应
            response = await self.reasoning_engine.get_response(
                temperature=0.7,
                metadata={'stage': 'feedback_optimization'}
            )
            
            if response:
                new_query = response.strip()
                
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
                    "chat_history": self.reasoning_engine.get_chat_history()
                }
                
                with open(log_file, 'w', encoding='utf-8') as f:
                    json.dump(log_data, f, ensure_ascii=False, indent=2)
                
                return {
                    'status': 'success',
                    'message': 'Successfully generated new query',
                    'query': new_query
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

    def _load_current_context(self, alchemy_dir: str) -> dict:
        """加载当前迭代上下文
        
        从alchemy_dir/context.json加载上下文信息，如果文件不存在或加载失败，
        则认为是第1次迭代。
        
        Args:
            alchemy_dir: 炼丹工作流运行目录
            
        Returns:
            dict: 包含上下文信息的字典
            {
                'iteration': int,
                'original_query': str,
                'previous_feedbacks': List[Dict]
            }
        """
        try:
            # context.json现在位于run_xxxx目录内
            context_file = Path(alchemy_dir) / "context.json"  
            
            # 如果文件不存在，返回初始上下文
            if not context_file.exists():
                return {
                    'iteration': 1,
                    'original_query': self._get_original_query(Path(alchemy_dir)),
                    'previous_feedbacks': []
                }
            
            # 读取并解析context.json
            with open(context_file, 'r', encoding='utf-8') as f:
                context_data = json.load(f)
                
            # 确保context_data包含所需字段
            if not context_data or not isinstance(context_data, dict):
                raise ValueError("Invalid context data format")
                
            return {
                'iteration': context_data.get('metadata', {}).get('iteration', 1),
                'original_query': context_data.get('original_query', ''),
                'previous_feedbacks': context_data.get('feedback_history', [])
            }
            
        except Exception as e:
            self.logger.error(f"加载上下文失败: {str(e)}", exc_info=True)
            return {
                'iteration': 1,  # 出错时默认为第1次迭代
                'original_query': self._get_original_query(Path(alchemy_dir)),
                'previous_feedbacks': []
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