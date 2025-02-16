import duckdb
import faiss
import numpy as np
import pandas as pd
import re
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer
from typing import Dict, List, Union, Optional, Tuple
import logging
from ..config.settings import DEFAULT_EMBEDDING_MODEL, DEFAULT_DB_PATH, SEARCH_TOP_K
from ..utils.common import download_model
from .planner import SearchPlanner
from ..llms.model_manager import ModelManager, ModelConfig

class SearchEngine:
    """统一搜索引擎，支持结构化查询和向量相似度搜索"""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH, logger: Optional[logging.Logger] = None):
        """初始化搜索引擎
        
        Args:
            db_path: DuckDB数据库路径
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.db_path = db_path
        self.db = duckdb.connect(db_path)
        self.model_manager = ModelManager(
            logger=self.logger
        )
        # 注册Embedding模型配置
        self.model_manager.register_model(ModelConfig(
            name=DEFAULT_EMBEDDING_MODEL,
            model_type="local"
        ))
        
        self.text_model = self.model_manager.get_embedding_model()
        self.faiss_index = None
        self.vectors_map = {}
        self._vector_id_to_record_id = {}  # 添加向量ID到记录ID的映射
        self._record_id_to_vector_id = {}  # 添加记录ID到向量ID的映射
        self.load_vectors()
        self.planner = SearchPlanner(
            logger=self.logger
        )

    def load_vectors(self):
        """加载并处理向量数据"""
        try:
            # 从unified_data表获取数据
            vector_data = self.db.execute("""
                SELECT _record_id, _file_path, _file_name, _file_type, vector, data
                FROM unified_data
                WHERE vector IS NOT NULL
            """).fetchall()
            
            if vector_data:
                self.logger.info(f"找到 {len(vector_data)} 条向量记录")
                
                # 构建向量数据
                vectors = []
                for record in vector_data:
                    try:
                        vector = record[4]
                        vectors.append(np.array(vector))
                        
                        vector_id = len(vectors) - 1
                        record_id = record[0]
                        
                        # 保存映射关系
                        self.vectors_map[vector_id] = {
                            'record_id': record_id,
                            'file_path': record[1],
                            'file_name': record[2],
                            'file_type': record[3],
                            'data': record[5]
                        }
                        
                        # 保存ID映射关系
                        self._vector_id_to_record_id[vector_id] = record_id
                        self._record_id_to_vector_id[record_id] = vector_id
                        
                    except Exception as e:
                        self.logger.error(f"处理记录 {record[0]} 时出错: {str(e)}")
                        continue
                
                if vectors:
                    vectors = np.stack(vectors)
                    dimension = vectors.shape[1]
                    
                    # 初始化FAISS索引
                    self.faiss_index = faiss.IndexFlatL2(dimension)
                    self.faiss_index.add(vectors.astype('float32'))
                    
                    self.logger.info(f"成功加载 {len(vectors)} 个向量")
                else:
                    self.logger.warning("未找到有效的向量数据")
            else:
                self.logger.warning("未在数据库中找到向量数据")
                
        except Exception as e:
            self.logger.error(f"加载向量数据时出错: {str(e)}")
            self.logger.info("将继续运行，但向量搜索功能可能不可用")

    def remove_records(self, record_ids: List[str]):
        """删除指定记录ID的向量数据
        
        Args:
            record_ids: 要删除的记录ID列表
        """
        if not self.faiss_index:
            return
            
        try:
            # 找出需要删除的向量ID
            vector_ids_to_remove = []
            for record_id in record_ids:
                if record_id in self._record_id_to_vector_id:
                    vector_id = self._record_id_to_vector_id[record_id]
                    vector_ids_to_remove.append(vector_id)
                    
                    # 清理映射关系
                    del self._record_id_to_vector_id[record_id]
                    del self._vector_id_to_record_id[vector_id]
                    del self.vectors_map[vector_id]
            
            if vector_ids_to_remove:
                # 创建新的FAISS索引
                vectors = []
                new_vector_map = {}
                new_vector_id_to_record_id = {}
                new_record_id_to_vector_id = {}
                
                # 重建向量数据，跳过要删除的向量
                for old_vector_id, data in self.vectors_map.items():
                    if old_vector_id not in vector_ids_to_remove:
                        # 获取原始向量
                        vector = self.faiss_index.reconstruct(old_vector_id)
                        vectors.append(vector)
                        
                        # 更新映射关系
                        new_vector_id = len(vectors) - 1
                        record_id = data['record_id']
                        
                        new_vector_map[new_vector_id] = data
                        new_vector_id_to_record_id[new_vector_id] = record_id
                        new_record_id_to_vector_id[record_id] = new_vector_id
                
                if vectors:
                    vectors = np.stack(vectors)
                    dimension = vectors.shape[1]
                    
                    # 创建并填充新索引
                    new_index = faiss.IndexFlatL2(dimension)
                    new_index.add(vectors.astype('float32'))
                    
                    # 更新实例变量
                    self.faiss_index = new_index
                    self.vectors_map = new_vector_map
                    self._vector_id_to_record_id = new_vector_id_to_record_id
                    self._record_id_to_vector_id = new_record_id_to_vector_id
                    
                    self.logger.info(f"成功删除 {len(vector_ids_to_remove)} 个向量")
                else:
                    # 如果没有剩余向量，清空所有数据
                    self.faiss_index = None
                    self.vectors_map = {}
                    self._vector_id_to_record_id = {}
                    self._record_id_to_vector_id = {}
                    
        except Exception as e:
            self.logger.error(f"删除向量数据时出错: {str(e)}")

    def parse_query(self, query: str) -> Dict:
        """解析查询字符串
        
        支持的查询格式:
        - 普通查询: "关键词"
        - 文件类型: "file:txt"
        - 日期范围: "date:2023-01-01 to 2023-12-31"
        
        Args:
            query: 用户输入的查询字符串
            
        Returns:
            Dict: 包含查询类型和内容的字典
        """
        patterns = {
            'text': r'^(?!file:|date:).*',
            'file': r'file:(\w+)',
            'date': r'date:(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})'
        }
        
        for query_type, pattern in patterns.items():
            if match := re.match(pattern, query):
                return {
                    'type': query_type,
                    'content': match.groups()[0] if match.groups() else query
                }
        
        return {'type': 'text', 'content': query}

    def execute_structured_query(self, parsed_query: Dict) -> pd.DataFrame:
        """执行结构化数据查询"""
        query_type = parsed_query['type']
        content = parsed_query['content']
        
        try:
            if query_type == 'text':
                return self.db.execute(f"""
                    SELECT _record_id, _file_path, _file_name, _file_type, 
                           _processed_at, data
                    FROM unified_data
                    WHERE data::TEXT ILIKE '%{content}%'
                    ORDER BY _processed_at DESC
                    LIMIT 10
                """).fetchdf()
                
            elif query_type == 'file':
                return self.db.execute(f"""
                    SELECT _record_id, _file_path, _file_name, _file_type, 
                           _processed_at, data
                    FROM unified_data
                    WHERE _file_type = '{content}'
                    ORDER BY _processed_at DESC
                    LIMIT 10
                """).fetchdf()
                
            elif query_type == 'date':
                start_date, end_date = content
                return self.db.execute(f"""
                    SELECT _record_id, _file_path, _file_name, _file_type, 
                           _processed_at, data
                    FROM unified_data
                    WHERE _processed_at BETWEEN '{start_date}' AND '{end_date}'
                    ORDER BY _processed_at DESC
                """).fetchdf()
                
        except Exception as e:
            self.logger.error(f"结构化查询失败: {str(e)}")
            return pd.DataFrame()
        
        return pd.DataFrame()

    def execute_vector_search(self, query: str, top_k: int = SEARCH_TOP_K) -> List[Dict]:
        """执行向量相似度搜索"""
        if not self.faiss_index or not self.text_model:
            self.logger.warning("向量搜索功能未就绪")
            return []
        
        try:
            # 将查询转换为向量
            query_vector = self.text_model.encode([query])[0]
            
            # 执行相似度搜索
            D, I = self.faiss_index.search(
                np.array([query_vector], dtype='float32'), 
                top_k
            )
            
            results = []
            for idx, distance in zip(I[0], D[0]):
                if idx in self.vectors_map:
                    vector_data = self.vectors_map[idx]
                    # 修改相似度计算方式：使用余弦相似度转换
                    similarity = 1 / (1 + distance) * 10
                    results.append({
                        'record_id': vector_data['record_id'],
                        'file_name': vector_data['file_name'],
                        'file_path': vector_data['file_path'],
                        'file_type': vector_data['file_type'],
                        'data': vector_data['data'],
                        'similarity': similarity
                    })
            
            return results
            
        except Exception as e:
            self.logger.error(f"向量搜索失败: {str(e)}")
            return []

    def enhance_results(self, results: Dict) -> Dict:
        """增强搜索结果"""
        enhanced = results.copy()
        
        # 添加统计信息
        total = results['stats']['total']
        enhanced['summary'] = {
            'total_results': total,
            'structured_ratio': results['stats']['structured_count'] / total if total > 0 else 0,
            'vector_ratio': results['stats']['vector_count'] / total if total > 0 else 0
        }
        
        # 分析文件类型分布
        if results['structured']:
            df = pd.DataFrame(results['structured'])
            if '_file_type' in df.columns:
                enhanced['summary']['file_types'] = df['_file_type'].value_counts().to_dict()
        
        # 添加时间维度分析
        if results['structured']:
            df = pd.DataFrame(results['structured'])
            if '_processed_at' in df.columns:
                enhanced['summary']['time_range'] = {
                    'earliest': df['_processed_at'].min().isoformat(),
                    'latest': df['_processed_at'].max().isoformat()
                }
        
        return enhanced

    def format_results(self, results: Dict) -> str:
        """格式化搜索结果为可读文本"""
        output = []
        
        # 添加总览信息
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
        
        # 添加统计信息
        if 'summary' in results:
            output.append("\n统计信息:")
            if 'file_types' in results['summary']:
                output.append("文件类型分布:")
                for ftype, count in results['summary']['file_types'].items():
                    output.append(f"- {ftype}: {count}")
            
            if 'time_range' in results['summary']:
                output.append(f"\n时间范围:")
                output.append(f"从 {results['summary']['time_range']['earliest']}")
                output.append(f"至 {results['summary']['time_range']['latest']}")
        
        return "\n".join(output)

    def search(self, query: str) -> str:
        """执行搜索并返回格式化结果"""
        try:
            # 1. 解析查询
            parsed_query = self.parse_query(query)
            
            # 2. 执行搜索
            structured_results = self.execute_structured_query(parsed_query)
            vector_results = self.execute_vector_search(query)
            
            # 3. 整合结果
            results = {
                'structured': structured_results.to_dict('records'),
                'vector': vector_results,
                'stats': {
                    'total': len(structured_results) + len(vector_results),
                    'structured_count': len(structured_results),
                    'vector_count': len(vector_results)
                }
            }
            
            # 4. 增强结果
            enhanced_results = self.enhance_results(results)
            
            # 5. 格式化输出
            return self.format_results(enhanced_results)
            
        except Exception as e:
            self.logger.error(f"搜索过程中发生错误: {str(e)}", exc_info=True)
            return f"搜索过程中发生错误: {str(e)}" 