import logging
import pandas as pd
from typing import Dict
import os
from datetime import datetime

class SearchPlanExecutor:
    """搜索计划执行器"""
    
    def __init__(self, search_engine):
        self.engine = search_engine
        self.logger = logging.getLogger(__name__)
        self.work_dir = "output"  # 默认输出目录
        
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
        if plan.get("structured_queries"):
            try:
                for query in plan["structured_queries"]:
                    df = self.engine.execute_structured_query(query)
                    results["structured"].extend(df.to_dict('records'))
                results["stats"]["structured_count"] = len(results["structured"])
                self.logger.info(f"结构化查询结果: {results['structured']}")
            except Exception as e:
                self.logger.error(f"结构化查询执行失败: {str(e)}")
                
        # 执行向量查询
        if plan.get("vector_queries"):
            try:
                for vector_query in plan["vector_queries"]:
                    vector_results = self.engine.execute_vector_search(
                        vector_query["reference_text"],
                        vector_query["top_k"]
                    )
                    
                    # 过滤相似度阈值
                    threshold = vector_query["similarity_threshold"]
                    filtered_results = [r for r in vector_results if r["similarity"] >= threshold]
                    
                    results["vector"].extend(filtered_results)
                results["stats"]["vector_count"] = len(results["vector"])
                self.logger.info(f"向量查询结果: {results['vector']}")
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
        if results['stats']['structured_count'] > 0:
            output.append(f"其中结构化数据 {results['stats']['structured_count']} 条")
        if results['stats']['vector_count'] > 0:
            output.append(f"向量相似度匹配 {results['stats']['vector_count']} 条")
        
        # 添加结构化搜索结果
        if results['structured']:
            output.append("\n结构化数据匹配:")
            for idx, item in enumerate(results['structured'][:5]):  # 显示前5条
                output.append(f"\n结果 {idx + 1}:")
                output.append(f"- 文件: {item['_file_name']}")
                output.append(f"  类型: {item['_file_type']}")
                data_str = str(item['data'])[:200] + "..." if len(str(item['data'])) > 200 else str(item['data'])
                output.append(f"  内容: {data_str}")
        
        # 添加向量搜索结果
        if results['vector']:
            output.append("\n相似内容匹配:")
            for idx, item in enumerate(results['vector'][:5]):  # 显示前5条
                output.append(f"\n结果 {idx + 1}:")
                output.append(f"- 相似度: {item['similarity']:.2f}")
                output.append(f"  文件: {item['file_name']}")
                output.append(f"  类型: {item['file_type']}")
                data_str = str(item['data'])[:200] + "..." if len(str(item['data'])) > 200 else str(item['data'])
                output.append(f"  内容: {data_str}")
        
        return "\n".join(output)

    def save_results_to_csv(self, results: Dict, filename: str = None) -> str:
        """将搜索结果保存为CSV文件
        
        Args:
            results: 检索结果字典
            filename: CSV文件名(可选)。如果未提供，将使用时间戳生成文件名
            
        Returns:
            str: 保存的CSV文件路径
        """
        # 生成文件名
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"search_results_{timestamp}.csv"
            
        # 确保输出目录存在
        os.makedirs(self.work_dir, exist_ok=True)
            
        filepath = os.path.join(self.work_dir, filename)
        
        # 准备数据
        rows = []
        
        # 处理结构化搜索结果
        for item in results.get('structured', []):
            rows.append({
                'search_type': '结构化搜索',
                'similarity': 'N/A',
                'file_name': item.get('_file_name', ''),
                'file_type': item.get('_file_type', ''),
                'content': str(item.get('data', ''))
            })
            
        # 处理向量搜索结果
        for item in results.get('vector', []):
            rows.append({
                'search_type': '向量搜索',
                'similarity': f"{item.get('similarity', 0):.4f}",
                'file_name': item.get('file_name', ''),
                'file_type': item.get('file_type', ''),
                'content': str(item.get('data', ''))
            })
            
        # 创建DataFrame并保存为CSV
        if rows:
            df = pd.DataFrame(rows)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            self.logger.info(f"搜索结果已保存到: {filepath}")
            return filepath
        else:
            self.logger.warning("没有搜索结果可保存")
            return ""