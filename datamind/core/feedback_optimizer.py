"""
反馈优化工作流模块，用于处理用户反馈并生成优化后的交付物
"""
from typing import Dict, List, Optional, Any
import json
from pathlib import Path
import logging
import asyncio
from datetime import datetime

from .delivery_generator import DeliveryGenerator

logger = logging.getLogger(__name__)

class FeedbackOptimizer:
    """反馈优化工作流管理器"""
    
    def __init__(self, work_dir: str, search_engine=None):
        self.work_dir = Path(work_dir)
        self.search_engine = search_engine
        self.delivery_generator = DeliveryGenerator()
        self.max_retries = 5
        self.retry_interval = 1  # 秒
        
    def set_search_engine(self, search_engine):
        """设置搜索引擎实例"""
        self.search_engine = search_engine

    async def optimize_delivery(self, delivery_dir: str, feedback: str) -> Dict[str, Any]:
        """根据用户反馈优化交付内容
        
        Args:
            delivery_dir: 原始交付文件目录
            feedback: 用户反馈内容
            
        Returns:
            Dict[str, Any]: 包含优化结果的字典
            {
                'status': 'success' | 'error',
                'message': str,
                'new_delivery_dir': str,  # 新的交付文件目录
                'generated_files': List[str]  # 生成的文件列表
            }
        """
        try:
            if not self.search_engine:
                return {'status': 'error', 'message': 'Search engine not initialized'}

            delivery_path = Path(delivery_dir)
            if not delivery_path.exists():
                return {'status': 'error', 'message': f'Delivery directory not found: {delivery_dir}'}

            # 加载原始交付计划
            plan_file = delivery_path / 'delivery_plan.json'
            if not plan_file.exists():
                return {'status': 'error', 'message': 'Delivery plan not found'}

            with open(plan_file, 'r', encoding='utf-8') as f:
                original_plan = json.load(f)

            # 创建新的交付目录
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_delivery_dir = delivery_path.parent / f"{delivery_path.name}_optimized_{timestamp}"
            new_delivery_dir.mkdir(parents=True, exist_ok=True)

            # 复制并更新交付计划
            updated_plan = original_plan.copy()
            updated_plan['feedback'] = feedback
            updated_plan['original_delivery_dir'] = str(delivery_path)
            updated_plan['_file_paths']['base_dir'] = str(new_delivery_dir)

            # 保存更新后的计划
            with open(new_delivery_dir / 'delivery_plan.json', 'w', encoding='utf-8') as f:
                json.dump(updated_plan, f, ensure_ascii=False, indent=2)

            # 重新生成交付文件
            try:
                generated_files = await self.delivery_generator.generate_deliverables(
                    str(new_delivery_dir),
                    updated_plan['search_results'],
                    updated_plan.get('delivery_config')
                )

                return {
                    'status': 'success',
                    'message': 'Successfully optimized delivery files',
                    'new_delivery_dir': str(new_delivery_dir),
                    'generated_files': generated_files
                }

            except Exception as e:
                logger.error(f"生成优化后的交付文件失败: {str(e)}")
                return {
                    'status': 'error',
                    'message': f'Failed to generate optimized deliverables: {str(e)}'
                }

        except Exception as e:
            logger.error(f"优化交付内容失败: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e)
            } 