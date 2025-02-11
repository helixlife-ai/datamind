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
        
        # 注册推理模型配置
        self.model_manager.register_model(ModelConfig(
            name=DEFAULT_REASONING_MODEL,
            model_type="api",
            api_key=DEFAULT_LLM_API_KEY,
            api_base=DEFAULT_LLM_API_BASE
        ))
        
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
            delivery_path = Path(delivery_dir)
            if not delivery_path.exists():
                return {
                    'status': 'error',
                    'message': f'Delivery directory not found: {delivery_dir}'
                }

            # 加载原始交付计划
            plan_file = delivery_path / 'delivery_plan.json'
            if not plan_file.exists():
                return {
                    'status': 'error',
                    'message': 'Delivery plan not found'
                }

            with open(plan_file, 'r', encoding='utf-8') as f:
                original_plan = json.load(f)

            # 构建提示信息
            messages = [
                {
                    "role": "system",
                    "content": """你是一个专业的查询优化专家。请基于用户的反馈和原始查询上下文，
                    生成一个新的查询文本。新查询应该：
                    1. 保留原始查询的核心意图
                    2. 融入用户反馈中的新需求
                    3. 使用清晰、结构化的语言
                    4. 确保查询的完整性和可执行性
                    
                    请直接输出优化后的查询文本，不需要其他解释。"""
                },
                {
                    "role": "user",
                    "content": f"""
                    原始查询：{original_plan.get('metadata', {}).get('original_query', '')}
                    
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
                log_dir = delivery_path / "feedback_logs"
                log_dir.mkdir(exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_file = log_dir / f"feedback_optimization_{timestamp}.json"
                
                log_data = {
                    "timestamp": timestamp,
                    "original_query": original_plan.get('metadata', {}).get('original_query', ''),
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