import logging
import pandas as pd
from typing import Dict

class SearchPlanExecutor:
    """搜索计划执行器"""
    
    def __init__(self, search_engine):
        self.engine = search_engine
        self.logger = logging.getLogger(__name__)
        
    def execute_plan(self, plan: Dict) -> Dict:
        """执行检索计划"""
        results = {
            "structured": [],
            "vector": [],
            "stats": {
                "structured_count": 0,
                "vector_count": 0,
                "total": 0
            }
        }
        
        # 执行结构化查询
        if plan.get("structured_query"):
            try:
                query = plan["structured_query"]
                df = self.engine.db.execute(query["query"], query["params"]).fetchdf()
                results["structured"] = df.to_dict('records')
                results["stats"]["structured_count"] = len(df)
            except Exception as e:
                self.logger.error(f"结构化查询执行失败: {str(e)}")
                
        # 执行向量查询
        if plan.get("vector_query"):
            try:
                vector_query = plan["vector_query"]
                vector_results = self.engine.execute_vector_search(
                    vector_query["reference_text"],
                    vector_query["top_k"]
                )
                
                # 过滤相似度阈值
                threshold = vector_query["similarity_threshold"]
                vector_results = [r for r in vector_results if r["similarity"] >= threshold]
                
                results["vector"] = vector_results
                results["stats"]["vector_count"] = len(vector_results)
            except Exception as e:
                self.logger.error(f"向量查询执行失败: {str(e)}")
                
        # 计算总数
        results["stats"]["total"] = (
            results["stats"]["structured_count"] + 
            results["stats"]["vector_count"]
        )
        
        return results 

    def format_results(self, results: Dict) -> str:
        """格式化搜索结果
        
        Args:
            results: 检索结果字典
            
        Returns:
            str: 格式化的结果文本
        """
        output = []
        
        # 添加统计信息
        output.append(f"找到 {results['stats']['total']} 条相关结果")
        output.append(f"其中结构化数据 {results['stats']['structured_count']} 条")
        output.append(f"向量相似度匹配 {results['stats']['vector_count']} 条")
        
        # 添加结构化搜索结果
        if results['structured']:
            output.append("\n结构化数据匹配:")
            for item in results['structured'][:3]:  # 只显示前3条
                output.append(f"- 文件: {item['_file_name']}")
                output.append(f"  类型: {item['_file_type']}")
                data_str = str(item['data'])[:200] + "..." if len(str(item['data'])) > 200 else str(item['data'])
                output.append(f"  内容: {data_str}")
        
        # 添加向量搜索结果
        if results['vector']:
            output.append("\n相似内容匹配:")
            for item in results['vector'][:3]:  # 只显示前3条
                output.append(f"- 相似度: {item['similarity']:.2f}")
                output.append(f"  文件: {item['file_name']}")
                output.append(f"  类型: {item['file_type']}")
                data_str = str(item['data'])[:200] + "..." if len(str(item['data'])) > 200 else str(item['data'])
                output.append(f"  内容: {data_str}")
        
        return "\n".join(output)