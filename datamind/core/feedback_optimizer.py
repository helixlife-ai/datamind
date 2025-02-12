"""
反馈优化工作流模块，用于处理用户反馈并生成新的查询
"""
from typing import Dict, List, Optional, Any
import json
from pathlib import Path
import logging
from datetime import datetime

from ..models.model_manager import ModelManager, ModelConfig
from ..config.settings import (
    DEFAULT_REASONING_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE
)

logger = logging.getLogger(__name__)

class FeedbackOptimizer:
    """反馈优化工作流管理器"""
    
    def __init__(self, work_dir: str):
        self.work_dir = Path(work_dir)
        self.model_manager = ModelManager()
        self.feedback_stack = []  # 改为栈结构记录待处理反馈
        
        # 注册推理模型配置
        self.model_manager.register_model(ModelConfig(
            name=DEFAULT_REASONING_MODEL,
            model_type="api",
            api_key=DEFAULT_LLM_API_KEY,
            api_base=DEFAULT_LLM_API_BASE
        ))
        
    async def push_feedback(self, feedback: str, delivery_dir: str):
        """压入新反馈到处理队列"""
        self.feedback_stack.append({
            'delivery_dir': delivery_dir,
            'feedback': feedback,
            'status': 'pending'
        })
        
    async def process_next_feedback(self) -> Dict[str, Any]:
        """处理下一个待处理反馈"""
        if not self.feedback_stack:
            return {'status': 'error', 'message': 'No pending feedback'}
            
        current_fb = self.feedback_stack.pop(0)
        result = await self.feedback_to_query(
            current_fb['delivery_dir'], 
            current_fb['feedback']
        )
        current_fb.update({
            'processed_at': datetime.now().isoformat(),
            'result': result
        })
        return result

    async def feedback_to_query(self, delivery_dir: str, feedback: str) -> Dict[str, Any]:
        """将用户反馈转换为新的查询
        
        Args:
            delivery_dir: 原始交付文件目录
            feedback: 用户反馈内容
            
        Returns:
            Dict[str, Any]: 包含新查询的字典
            {
                'status': 'success' | 'error',
                'message': str,
                'query': str  # 新的查询文本
            }
        """
        try:
            # 加载当前迭代上下文
            context = self._load_current_context(delivery_dir)
            
            # 构建包含历史记录的提示语
            messages = [
                {
                    "role": "system",
                    "content": f"""你是一个专业的查询优化专家。当前为第{context['iteration']}次迭代，请基于以下内容生成新查询：
                    1. 原始查询：{context['original_query']}
                    2. 历史反馈：{json.dumps(context['previous_feedbacks'], ensure_ascii=False)}
                    3. 本次反馈：{feedback}"""
                },
                {
                    "role": "user",
                    "content": f"""
                    原始查询：{context['original_query']}
                    
                    用户反馈：{feedback}
                    
                    请生成一个新的查询文本，要求：
                    1. 融合原始查询的目标和用户的反馈建议
                    2. 使用清晰的自然语言表达
                    3. 保持查询的可执行性
                    """
                }
            ]
            
            # 调用推理模型
            response = await self.model_manager.generate_reasoned_response(
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            
            if response and response.choices:
                new_query = response.choices[0].message.content.strip()
                
                # 记录优化过程
                log_dir = Path(delivery_dir) / "feedback_logs"
                log_dir.mkdir(exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_file = log_dir / f"feedback_optimization_{timestamp}.json"
                
                log_data = {
                    "timestamp": timestamp,
                    "original_query": context['original_query'],
                    "user_feedback": feedback,
                    "new_query": new_query,
                    "prompt": messages
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
            logger.error(f"处理反馈失败: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e)
            } 

    def _load_current_context(self, delivery_dir: str) -> dict:
        """加载当前迭代上下文"""
        delivery_path = Path(delivery_dir)
        return {
            'iteration': int(delivery_path.name.split('_')[-1]),  # 从目录名获取迭代次数
            'original_query': self._get_original_query(delivery_path),
            'previous_feedbacks': self._get_feedback_history(delivery_path.parent)
        }

    def _get_original_query(self, delivery_path: Path) -> str:
        """从交付目录获取原始查询"""
        try:
            # 从交付计划文件中获取原始查询
            plan_file = delivery_path / "delivery_plan.json"
            if not plan_file.exists():
                raise FileNotFoundError(f"交付计划文件不存在: {plan_file}")

            with open(plan_file, 'r', encoding='utf-8') as f:
                delivery_plan = json.load(f)
                return delivery_plan.get('metadata', {}).get('original_query', '')
            
        except Exception as e:
            logger.error(f"获取原始查询失败: {str(e)}")
            return ""

    def _get_feedback_history(self, parent_dir: Path) -> List[Dict]:
        """获取历史反馈记录"""
        feedback_history = []
        
        try:
            # 遍历所有迭代目录
            for iter_dir in parent_dir.glob("iter_*"):
                feedback_logs_dir = iter_dir / "feedback_logs"
                
                if feedback_logs_dir.exists():
                    # 按时间顺序处理日志文件
                    for log_file in sorted(feedback_logs_dir.glob("*.json")):
                        try:
                            with open(log_file, 'r', encoding='utf-8') as f:
                                log_data = json.load(f)
                                feedback_history.append({
                                    'iteration': int(iter_dir.name.split('_')[-1]),
                                    'timestamp': log_data['timestamp'],
                                    'feedback': log_data['user_feedback'],
                                    'new_query': log_data['new_query']
                                })
                        except Exception as e:
                            logger.warning(f"加载反馈日志失败 {log_file}: {str(e)}")
                            continue
                            
            # 按迭代次数排序
            feedback_history.sort(key=lambda x: x['iteration'])
            return feedback_history
            
        except Exception as e:
            logger.error(f"获取反馈历史失败: {str(e)}")
            return [] 