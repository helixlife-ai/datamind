import logging
from datetime import datetime
from typing import Dict, Optional

class SearchPlanner:
    """搜索计划生成器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def build_search_plan(self, intent: Dict) -> Dict:
        """根据查询意图构建检索计划
        
        Args:
            intent: 查询意图字典
                {
                    "original_query": "原始查询文本",
                    "structured_conditions": [{
                        "time_range": {"start": "2023-01", "end": "2023-12"},
                        "file_types": ["json", "txt"],
                        "keywords": "搜索关键词",
                        "exclusions": ["排除词1", "排除词2"]
                    }],
                    "vector_conditions": [{
                        "reference_text": "相似内容",
                        "similarity_threshold": 0.7,
                        "top_k": 5
                    }]
                }
                
        Returns:
            Dict: 检索计划
        """
        plan = {
            "steps": [],
            "structured_queries": [],
            "vector_queries": [],
            "expected_fields": intent.get("result_format", {}).get("required_fields", ["*"]),
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "original_query": intent.get("original_query", "")
            }
        }
        
        # 构建结构化查询
        if "structured_conditions" in intent:
            for condition in intent["structured_conditions"]:
                structured_query = self._build_structured_query(condition)
                if structured_query:
                    if "结构化查询" not in plan["steps"]:
                        plan["steps"].append("结构化查询")
                    plan["structured_queries"].append(structured_query)
            
        # 构建向量查询
        if "vector_conditions" in intent:
            for condition in intent["vector_conditions"]:
                vector_query = self._build_vector_query(condition)
                if vector_query:
                    if "向量相似度查询" not in plan["steps"]:
                        plan["steps"].append("向量相似度查询")
                    plan["vector_queries"].append(vector_query)
            
        if not plan["steps"]:
            raise ValueError("未能生成有效的检索计划")
            
        return plan
        
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

    def build_delivery_plan(self, query: str, intent: Dict, results: Dict, config: Dict) -> Dict:
        """构建交付计划
        
        Args:
            query: 原始查询
            intent: 解析后的查询意图
            results: 搜索结果
            config: 交付配置
            
        Returns:
            Dict: 交付计划
        """
        # 从意图中提取时间范围和关键词
        structured_conditions = intent.get('structured_conditions', [{}])[0]
        
        return {
            'metadata': {
                'original_query': query,
                'generated_at': results.get('metadata', {}).get('execution_time', '')
            },
            'query_params': {
                'query': query,
                'keywords': structured_conditions.get('keywords', []),
                'reference_text': query,
                'filters': {
                    'time_range': structured_conditions.get('time_range', {}),
                    'sections': ['摘要', '分析', '结论']
                },
                'weights': {
                    '相关性': 1.0,
                    '时效性': 0.8,
                    '权威性': 0.7
                }
            },
            'delivery_config': config
        } 