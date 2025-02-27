"""
反馈优化工作流模块，用于处理用户反馈并生成新的查询
"""
from typing import Optional
import json
from pathlib import Path
import logging

from ..core.reasoning import ReasoningEngine

logger = logging.getLogger(__name__)

class FeedbackOptimizer:
    """反馈优化工作流管理器"""
    
    def __init__(self, work_dir: str = "work_dir", reasoning_engine: Optional[ReasoningEngine] = None, logger: Optional[logging.Logger] = None):
        """初始化反馈优化工作流管理器
        
        Args:
            work_dir: 工作目录，现在是迭代目录 (alchemy_runs/alchemy_{id}/iterations/iterX)
            reasoning_engine: 推理引擎实例
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.work_dir = Path(work_dir)
        self.reasoning_engine = reasoning_engine
        
        # 从迭代目录计算各个重要路径，与alchemy_service.py保持一致
        self.iter_dir = self.work_dir  # 当前迭代目录
        self.iterations_dir = self.iter_dir.parent  # iterations目录
        self.alchemy_dir = self.iterations_dir.parent  # alchemy_{id}目录
        
        # 获取当前迭代信息
        self.current_iteration = int(self.iter_dir.name.replace('iter', ''))
        self.alchemy_id = self.alchemy_dir.name.split('alchemy_')[-1]
        
        # 设置制品目录
        self.artifacts_dir = self.alchemy_dir / "artifacts"
        
        if not self.reasoning_engine:
            self.logger.warning("未提供推理引擎实例，部分功能可能受限")

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