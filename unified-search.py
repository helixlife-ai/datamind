# %% [markdown]
"""
# 智能搜索引擎
此模块实现了一个混合搜索引擎，支持结构化查询和向量相似度搜索。
适配预处理后的统一数据格式，提供精确和模糊搜索功能。

主要功能：
- 结构化数据查询
- 向量相似度搜索
- 混合搜索结果排序
- 智能结果增强
"""

# %% [1. 环境准备]
import os
import re
import json
from typing import Dict, List, Union, Tuple
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import duckdb
import faiss
from sentence_transformers import SentenceTransformer

# 设置环境变量
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

# %% [2. 常量定义]
DEFAULT_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'
DEFAULT_DB_PATH = "unified_storage.duckdb"
SEARCH_TOP_K = 5

# %% [3. 数据库初始化]
def setup_database(db_path: str = DEFAULT_DB_PATH):
    """初始化数据库表结构"""
    db = duckdb.connect(db_path)
    
    # 创建统一数据表
    db.execute("""
        CREATE TABLE IF NOT EXISTS unified_data (
            _record_id VARCHAR PRIMARY KEY,  
            _file_path VARCHAR,             
            _file_name VARCHAR,             
            _file_type VARCHAR,             
            _processed_at TIMESTAMP,        
            _sub_id INTEGER,                
            data JSON,                      
            vector DOUBLE[]                 
        )
    """)
    
    db.close()

# %% [4. 搜索引擎核心类]
class SearchEngine:
    """智能搜索引擎核心类"""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """初始化搜索引擎
        Args:
            db_path: DuckDB数据库路径
        """
        self.db = duckdb.connect(db_path)
        
        # 获取当前工作目录作为根目录
        root_dir = Path.cwd()
        model_cache_dir = root_dir / 'model_cache'
        
        # 确保缓存目录存在
        model_cache_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 优先尝试从本地缓存加载模型
            print("尝试从本地缓存加载模型...")
            self.text_model = SentenceTransformer(
                model_name_or_path=DEFAULT_MODEL,
                cache_folder=str(model_cache_dir)
            )
            print("模型加载成功")
        except Exception as e:
            print(f"模型加载失败: {str(e)}")
            print("尝试下载模型...")
            try:
                # 下载并保存模型到缓存目录
                self.text_model = SentenceTransformer(
                    model_name_or_path=DEFAULT_MODEL,
                    cache_folder=str(model_cache_dir)
                )
                print(f"模型已成功下载到: {model_cache_dir}")
            except Exception as e:
                print(f"模型下载失败: {str(e)}")
                print("向量搜索功能将不可用")
                self.text_model = None
        
        self.faiss_index = None
        self.vectors_map = {}  # 存储向量ID到源数据的映射
        self.load_vectors()

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
                print(f"找到 {len(vector_data)} 条向量记录")
                
                # 构建向量数据
                vectors = []
                for idx, record in enumerate(vector_data):
                    try:
                        # 直接使用向量数据，因为DuckDB已经将其转换为Python列表
                        vector = record[4]
                        vectors.append(np.array(vector))
                        
                        # 保存映射关系
                        self.vectors_map[len(vectors)-1] = {
                            'record_id': record[0],
                            'file_path': record[1],
                            'file_name': record[2],
                            'file_type': record[3],
                            'data': record[5]  # 直接使用data字段，不需要JSON解析
                        }
                    except Exception as e:
                        print(f"处理记录 {record[0]} 时出错: {str(e)}")
                        continue
                
                if vectors:
                    vectors = np.stack(vectors)
                    dimension = vectors.shape[1]
                    
                    # 初始化FAISS索引
                    self.faiss_index = faiss.IndexFlatL2(dimension)
                    self.faiss_index.add(vectors.astype('float32'))
                    
                    print(f"成功加载 {len(vectors)} 个向量")
                else:
                    print("未找到有效的向量数据")
            else:
                print("未在数据库中找到向量数据")
                
        except Exception as e:
            print(f"加载向量数据时出错: {str(e)}")
            print("将继续运行，但向量搜索功能可能不可用")

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
            print(f"结构化查询失败: {str(e)}")
            return pd.DataFrame()
        
        return pd.DataFrame()

    def execute_vector_search(self, query: str, top_k: int = SEARCH_TOP_K) -> List[Dict]:
        """执行向量相似度搜索"""
        if not self.faiss_index or not self.text_model:
            print("向量搜索功能未就绪")
            return []
        
        try:
            # 将查询转换为向量
            query_vector = self.text_model.encode([query])[0]
            
            # 执行相似度搜索
            D, I = self.faiss_index.search(np.array([query_vector], dtype='float32'), top_k)
            
            results = []
            for idx, distance in zip(I[0], D[0]):
                if idx in self.vectors_map:
                    vector_data = self.vectors_map[idx]
                    # 修改相似度计算方式：使用余弦相似度转换
                    similarity = 1 / (1 + distance) *10  # 将L2距离转换为[0,1]范围的相似度
                    results.append({
                        'record_id': vector_data['record_id'],
                        'file_name': vector_data['file_name'],
                        'file_type': vector_data['file_type'],
                        'data': vector_data['data'],
                        'similarity': similarity
                    })
            
            return results
            
        except Exception as e:
            print(f"向量搜索失败: {str(e)}")
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
                # 直接使用data字段，不需要额外的JSON解析
                data_str = str(item['data'])[:200] + "..." if len(str(item['data'])) > 200 else str(item['data'])
                output.append(f"  内容: {data_str}")
        
        # 添加向量搜索结果
        if results['vector']:
            output.append("\n相似内容匹配:")
            for item in results['vector'][:3]:  # 只显示前3条
                output.append(f"- 相似度: {item['similarity']:.2f}")
                output.append(f"  文件: {item['file_name']}")
                output.append(f"  类型: {item['file_type']}")
                # 直接使用data字段，不需要额外的JSON解析
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
            return f"搜索过程中发生错误: {str(e)}"

# %% [5. 环境验证]
def validate_environment():
    """验证运行环境"""
    try:
        import sentence_transformers
        
        required_packages = {
            'duckdb': duckdb.__version__,
            'faiss': faiss.__version__,
            'pandas': pd.__version__,
            'numpy': np.__version__,
            'sentence_transformers': sentence_transformers.__version__
        }
        
        print("环境检查:")
        for package, version in required_packages.items():
            print(f"- {package}: {version}")
        
        if not os.path.exists(DEFAULT_DB_PATH):
            print("\n初始化数据库...")
            setup_database()
            print(f"数据库已创建: {DEFAULT_DB_PATH}")
            
    except Exception as e:
        print(f"环境检查失败: {str(e)}")
        print("请确保已安装所有必要的包:")
        print("pip install faiss-cpu duckdb pandas numpy sentence-transformers")

# %% [6. 检索计划生成器]
class SearchPlanner:
    """检索计划生成器,专注于生成混合检索计划"""
    
    def build_search_plan(self, intent: Dict) -> Dict:
        """根据查询意图生成检索计划
        
        Args:
            intent: {
                "structured_conditions": {
                    "time_range": {
                        "start": "2023-01-01",
                        "end": "2023-12-31"
                    },
                    "file_types": ["json", "txt"],
                    "keywords": "搜索关键词",
                    "exclusions": []
                },
                "vector_conditions": {
                    "reference_text": "相似文本",
                    "similarity_threshold": 0.6,
                    "top_k": 5
                },
                "result_format": {
                    "required_fields": ["_file_name", "data"]
                }
            }
            
        Returns:
            Dict: 检索计划
        """
        # 验证输入
        if not isinstance(intent, dict):
            raise ValueError("查询意图必须是字典类型")
            
        # 初始化计划
        plan = {
            "steps": [],
            "structured_query": None,
            "vector_query": None,
            "expected_fields": intent.get("result_format", {}).get("required_fields", ["*"]),
            # 添加元数据以便于调试和跟踪
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
        
        # 确保整个计划对象都使用正确的中文编码
        return json.loads(json.dumps(plan, ensure_ascii=False))
        
    def _build_structured_query(self, conditions: Dict) -> Dict:
        """构建结构化查询部分
        
        Args:
            conditions: 包含查询条件的字典
                {
                    "time_range": {
                        "start": "2023-01-01",
                        "end": "2023-12-31"
                    },
                    "file_types": ["json", "txt"],
                    "keywords": "搜索关键词",
                    "exclusions": ["排除词1", "排除词2"]
                }
                
        Returns:
            Dict: 包含SQL查询和参数的字典，或在失败时返回None
        """
        query_parts = []
        params = []
        
        try:
            # 处理时间范围
            if conditions.get("time_range"):
                time_range = conditions["time_range"]
                if time_range.get("start") and time_range.get("end"):
                    # 使用明确的TIMESTAMP类型转换
                    query_parts.append("_processed_at BETWEEN CAST(? AS TIMESTAMP) AND CAST(? AS TIMESTAMP)")
                    params.extend([
                        time_range["start"] + " 00:00:00",  # 添加时间部分
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
                    # 支持多个关键词的AND搜索
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
            
            # 打印调试信息
            print("Generated SQL:", query)
            print("Parameters:", params)
            
            return {
                "query": query,
                "params": params
            }
                
        except Exception as e:
            print(f"构建结构化查询失败: {str(e)}")
            import traceback
            print(traceback.format_exc())  # 打印详细错误栈
            return None
            
    def _build_vector_query(self, conditions: Dict) -> Dict:
        """构建向量查询部分"""
        if not conditions.get("reference_text"):
            return None
            
        try:
            return {
                "reference_text": conditions["reference_text"],
                "similarity_threshold": conditions.get("similarity_threshold", 0.6),  # 调整默认阈值
                "top_k": conditions.get("top_k", 5)
            }
        except Exception as e:
            print(f"向量查询构建失败: {str(e)}")
            return None

class SearchPlanExecutor:
    """搜索计划执行器,负责执行由SearchPlanner生成的搜索计划"""
    
    def __init__(self, search_engine: SearchEngine):
        """初始化搜索计划执行器
        
        Args:
            search_engine: SearchEngine实例
        """
        self.engine = search_engine
        
    def execute_plan(self, plan: Dict) -> Dict:
        """执行检索计划
        
        Args:
            plan: 由SearchPlanner生成的检索计划
            
        Returns:
            Dict: 检索结果
        """
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
                print(f"结构化查询执行失败: {str(e)}")
                
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
                print(f"向量查询执行失败: {str(e)}")
                
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

# %% [7. 集成测试]
def test_intelligent_search():
    """测试智能检索功能"""
    try:
        # 初始化搜索引擎
        engine = SearchEngine()
        
        # 初始化计划生成器和执行器
        planner = SearchPlanner()
        executor = SearchPlanExecutor(engine)
        
        # 创建查询意图
        intent = {
            "structured_conditions": {
                "time_range": {
                    "start": "2025-01-01",
                    "end": "2025-12-31"
                },
                "file_types": ["xml", "md", "json", "txt"],
                "keywords": "人工智能",
                "exclusions": [""]
            },
            "vector_conditions": {
                "reference_text": "人工智能",
                "similarity_threshold": 0.4,
                "top_k": 5
            },
            "result_format": {
                "required_fields": ["_file_name", "data"]
            }
        }
        
        # 生成检索计划
        search_plan = planner.build_search_plan(intent)
        print("生成的检索计划:", json.dumps(search_plan, indent=2, ensure_ascii=False))
        
        # 执行检索
        results = executor.execute_plan(search_plan)
        
        # 格式化输出
        formatted_results = executor.format_results(results)
        print(formatted_results)
        
    except Exception as e:
        print(f"搜索过程出错: {str(e)}")

# %% [8. 主程序]
if __name__ == "__main__":
    # 环境检查
    validate_environment()

     # 基础搜索测试
    print("\n=== 基础搜索测试 ===")
    engine = SearchEngine()
    for query in ["机器学习","人工智能","file:json"]:
        print(f"\n查询: {query}")
        print("-" * 50)
        result = engine.search(query)
        print(result)

    # 智能检索测试
    print("\n=== 智能检索测试 ===")
    test_intelligent_search()