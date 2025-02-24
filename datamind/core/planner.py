import logging
from datetime import datetime
from typing import Dict, Optional
import json
from pathlib import Path

class SearchPlanner:
    """搜索计划生成器"""
    
    def __init__(self, work_dir: str = "work_dir", logger: Optional[logging.Logger] = None):
        """初始化搜索计划生成器
        
        Args:
            work_dir: 工作目录路径
            logger: 可选，日志记录器实例
        """
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger(__name__)
    
    def build_search_plan(self, intent: Dict) -> Dict:
        """根据查询意图构建检索计划"""
        try:
            # 创建计划保存目录
            plan_dir = self.work_dir / "search_plans" 
            plan_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存输入的意图
            with open(plan_dir / "input_intent.json", "w", encoding="utf-8") as f:
                json.dump(intent, f, ensure_ascii=False, indent=2)
            
            # 构建基础计划
            plan = {
                "steps": [],
                "structured_queries": [],
                "vector_queries": [],
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "original_query": intent.get("original_query", "")
                }
            }
            
            # 构建结构化查询
            if "structured_conditions" in intent:
                structured_queries = []
                for condition in intent["structured_conditions"]:
                    query = self._build_structured_query(condition)
                    if query:
                        if "结构化查询" not in plan["steps"]:
                            plan["steps"].append("结构化查询")
                        plan["structured_queries"].append(query)
                        structured_queries.append(query)
                
                # 保存结构化查询
                if structured_queries:
                    with open(plan_dir / "structured_queries.json", "w", encoding="utf-8") as f:
                        json.dump(structured_queries, f, ensure_ascii=False, indent=2)
            
            # 构建向量查询
            if "vector_conditions" in intent:
                vector_queries = []
                for condition in intent["vector_conditions"]:
                    query = self._build_vector_query(condition)
                    if query:
                        if "向量相似度查询" not in plan["steps"]:
                            plan["steps"].append("向量相似度查询")
                        plan["vector_queries"].append(query)
                        vector_queries.append(query)
                
                # 保存向量查询
                if vector_queries:
                    with open(plan_dir / "vector_queries.json", "w", encoding="utf-8") as f:
                        json.dump(vector_queries, f, ensure_ascii=False, indent=2)
            
            if not plan["steps"]:
                raise ValueError("未能生成有效的检索计划")
            
            # 保存完整的检索计划
            with open(plan_dir / "final_plan.json", "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
            
            return plan
            
        except Exception as e:
            self.logger.error(f"构建检索计划失败: {str(e)}", exc_info=True)
            raise
        
    def _build_structured_query(self, conditions: Dict) -> Optional[Dict]:
        """构建结构化查询部分
        
        Returns:
            Dict: 包含查询类型和内容的字典，格式为:
            {
                'type': 'text'|'file'|'date',
                'content': str|tuple
            }
        """
        try:
            # 处理关键词搜索
            if conditions.get("keyword"):
                return {
                    'type': 'text',
                    'content': conditions["keyword"].strip(),
                    'exclusions': conditions.get("exclusions", [])
                }
            
            # 处理文件类型
            if conditions.get("file_types") and len(conditions["file_types"]) == 1:
                return {
                    'type': 'file',
                    'content': conditions["file_types"][0]
                }
            
            # 处理时间范围
            if conditions.get("time_range"):
                time_range = conditions["time_range"]
                if time_range.get("start") and time_range.get("end"):
                    return {
                        'type': 'date',
                        'content': (time_range["start"], time_range["end"])
                    }
                
            return None
                
        except Exception as e:
            self.logger.error(f"构建结构化查询失败: {str(e)}", exc_info=True)
            return None
            
    def _build_vector_query(self, conditions: Dict) -> Optional[Dict]:
        """构建向量查询部分
        
        Returns:
            Dict: 向量查询参数，格式为:
            {
                'reference_text': str,
                'top_k': int,
                'similarity_threshold': float
            }
        """
        if not conditions.get("reference_text"):
            return None
        
        try:
            return {
                "reference_text": conditions["reference_text"],
                "top_k": conditions.get("top_k", 5),
                "similarity_threshold": conditions.get("similarity_threshold", 0.6)
            }
        except Exception as e:
            self.logger.error(f"构建向量查询失败: {str(e)}")
            return None 