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
                    "structured_conditions": {
                        "time_range": {"start": "2023-01", "end": "2023-12"},
                        "file_types": ["json", "txt"],
                        "keywords": "搜索关键词",
                        "exclusions": ["排除词1", "排除词2"]
                    },
                    "vector_conditions": {
                        "reference_text": "相似内容",
                        "similarity_threshold": 0.7,
                        "top_k": 5
                    }
                }
                
        Returns:
            Dict: 检索计划
        """
        plan = {
            "steps": [],
            "structured_query": None,
            "vector_query": None,
            "expected_fields": intent.get("result_format", {}).get("required_fields", ["*"]),
            "metadata": {
                "generated_at": datetime.now().isoformat()
            }
        }
        
        # 构建结构化查询
        if "structured_conditions" in intent:
            structured_query = self._build_structured_query(intent["structured_conditions"])
            if structured_query:
                plan["steps"].append("结构化查询")
                plan["structured_query"] = structured_query
                
        # 构建向量查询
        if "vector_conditions" in intent:
            vector_query = self._build_vector_query(intent["vector_conditions"])
            if vector_query:
                plan["steps"].append("向量相似度查询")
                plan["vector_query"] = vector_query
                
        if not plan["steps"]:
            raise ValueError("未能生成有效的检索计划")
            
        return plan
        
    def _build_structured_query(self, conditions: Dict) -> Optional[Dict]:
        """构建结构化查询部分"""
        query_parts = []
        params = []
        
        try:
            # 处理时间范围
            if conditions.get("time_range"):
                time_range = conditions["time_range"]
                if time_range.get("start") and time_range.get("end"):
                    query_parts.append("_processed_at BETWEEN CAST(? AS TIMESTAMP) AND CAST(? AS TIMESTAMP)")
                    params.extend([
                        time_range["start"] + " 00:00:00",
                        time_range["end"] + " 23:59:59"
                    ])
                    
            # 处理文件类型
            if conditions.get("file_types"):
                file_types = conditions["file_types"]
                if file_types:
                    placeholders = ", ".join(["?" for _ in file_types])
                    query_parts.append(f"_file_type IN ({placeholders})")
                    params.extend(file_types)
                    
            # 处理关键词搜索
            if conditions.get("keywords"):
                keywords = conditions["keywords"].strip()
                if keywords:
                    keyword_list = keywords.split()
                    for keyword in keyword_list:
                        query_parts.append("LOWER(data::TEXT) LIKE LOWER(?)")
                        params.append(f"%{keyword}%")
                    
            # 处理排除条件
            if conditions.get("exclusions"):
                exclusions = [e.strip() for e in conditions["exclusions"] if e.strip()]
                for exclusion in exclusions:
                    query_parts.append("LOWER(data::TEXT) NOT LIKE LOWER(?)")
                    params.append(f"%{exclusion}%")
                    
            if not query_parts:
                return None
                    
            # 构建最终查询
            fields = [
                "_record_id",
                "_file_path",
                "_file_name",
                "_file_type",
                "_processed_at",
                "data"
            ]
            
            query = f"""
                SELECT {', '.join(fields)}
                FROM unified_data
                {f"WHERE {' AND '.join(query_parts)}" if query_parts else ""}
                ORDER BY _processed_at DESC
                LIMIT 100
            """
            
            return {
                "query": query,
                "params": params
            }
                
        except Exception as e:
            self.logger.error(f"构建结构化查询失败: {str(e)}", exc_info=True)
            return None
            
    def _build_vector_query(self, conditions: Dict) -> Optional[Dict]:
        """构建向量查询部分"""
        if not conditions.get("reference_text"):
            return None
            
        try:
            return {
                "reference_text": conditions["reference_text"],
                "similarity_threshold": conditions.get("similarity_threshold", 0.6),
                "top_k": conditions.get("top_k", 5)
            }
        except Exception as e:
            self.logger.error(f"向量查询构建失败: {str(e)}")
            return None 