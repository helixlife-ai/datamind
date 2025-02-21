"""
执行器模块，负责协调搜索和交付物生成
"""
import logging
import pandas as pd
from typing import Dict, List, Optional, Any
import os
from datetime import datetime, date
from collections import defaultdict
import numpy as np
from itertools import combinations
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import hashlib
import re
from ..utils.common import DateTimeEncoder

logger = logging.getLogger(__name__)


class ResultAnalyzer:
    """结果分析器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """初始化结果分析器
        
        Args:
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)

    def analyze(self, results: Dict) -> Dict:
        """分析搜索结果
        
        Args:
            results: 包含搜索结果的字典
            
        Returns:
            Dict: 更新后的结果字典，包含分析见解
        """
        try:
            self._extract_key_concepts(results)
            self._build_timeline(results)
            self._analyze_relationships(results)
            self._rank_importance(results)
            return results
        except Exception as e:
            self.logger.error(f"结果分析失败: {str(e)}")
            raise

    def _extract_key_concepts(self, results: Dict):
        """提取关键概念
        
        从结构化和向量搜索结果中提取关键概念和主题。
        使用词频统计和重要性评分来识别重要概念。
        """
        try:
            concepts = []
            concept_scores = defaultdict(float)
            
            # 处理结构化搜索结果
            for item in results.get("structured", []):
                if isinstance(item.get("data"), dict):
                    # 从字段值中提取概念
                    for value in item["data"].values():
                        if isinstance(value, str):
                            # 使用简单的分词和统计
                            words = value.split()
                            for word in words:
                                if len(word) > 1:  # 忽略单字符
                                    concept_scores[word] += 1
                                    
            # 处理向量搜索结果
            for item in results.get("vector", []):
                if isinstance(item.get("data"), str):
                    # 考虑相似度分数
                    similarity = item.get("similarity", 0.5)
                    words = item["data"].split()
                    for word in words:
                        if len(word) > 1:
                            concept_scores[word] += similarity

            # 选择得分最高的概念
            top_concepts = sorted(
                concept_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )[:20]  # 取前20个概念

            # 格式化概念列表
            results["insights"]["key_concepts"] = [
                {
                    "concept": concept,
                    "score": float(score),  # 确保score是Python float
                    "frequency": int(score)  # 添加频率信息
                }
                for concept, score in top_concepts
            ]

        except Exception as e:
            self.logger.error(f"提取关键概念失败: {str(e)}")
            results["insights"]["key_concepts"] = []

    def _build_timeline(self, results: Dict):
        """构建时间线
        
        从搜索结果中提取时间信息，构建事件时间线。
        支持多种时间格式，并按时间排序。
        """
        try:
            timeline_events = []
            
            # 时间格式正则表达式
            date_patterns = [
                r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
                r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
                r'\d{4}年\d{1,2}月\d{1,2}日'  # YYYY年MM月DD日
            ]
            
            def extract_date(text):
                """从文本中提取日期"""
                for pattern in date_patterns:
                    matches = re.findall(pattern, str(text))
                    if matches:
                        try:
                            # 统一日期格式
                            date_str = matches[0].replace('/', '-').replace('年', '-').replace('月', '-').replace('日', '')
                            return datetime.strptime(date_str, '%Y-%m-%d')
                        except ValueError:
                            continue
                return None

            # 从结构化结果中提取时间信息
            for item in results.get("structured", []):
                if isinstance(item.get("data"), dict):
                    # 查找日期字段
                    for key, value in item["data"].items():
                        date = extract_date(value)
                        if date:
                            timeline_events.append({
                                "date": date.isoformat(),
                                "content": str(value),
                                "source": "structured",
                                "importance": item.get("importance", 1.0)
                            })

            # 从向量结果中提取时间信息
            for item in results.get("vector", []):
                if isinstance(item.get("data"), str):
                    date = extract_date(item["data"])
                    if date:
                        timeline_events.append({
                            "date": date.isoformat(),
                            "content": item["data"][:200],  # 限制内容长度
                            "source": "vector",
                            "importance": item.get("similarity", 0.5)
                        })

            # 按时间排序
            timeline_events.sort(key=lambda x: x["date"])
            
            results["insights"]["timeline"] = timeline_events

        except Exception as e:
            self.logger.error(f"构建时间线失败: {str(e)}")
            results["insights"]["timeline"] = []

    def _analyze_relationships(self, results: Dict):
        """分析关系
        
        分析实体之间的关系，构建关系网络。
        包括共现分析和关联强度计算。
        """
        try:
            relationships = []
            entity_pairs = defaultdict(float)
            
            def extract_entities(text):
                """简单的实体提取"""
                # 这里使用简单的分词作为示例
                # 实际应用中可以使用更复杂的NER
                words = str(text).split()
                return [w for w in words if len(w) > 1]

            # 分析结构化结果
            for item in results.get("structured", []):
                if isinstance(item.get("data"), dict):
                    entities = []
                    for value in item["data"].values():
                        entities.extend(extract_entities(str(value)))
                    
                    # 分析实体对
                    for e1, e2 in combinations(set(entities), 2):
                        entity_pairs[(e1, e2)] += 1.0

            # 分析向量结果
            for item in results.get("vector", []):
                if isinstance(item.get("data"), str):
                    entities = extract_entities(item["data"])
                    similarity = item.get("similarity", 0.5)
                    
                    for e1, e2 in combinations(set(entities), 2):
                        entity_pairs[(e1, e2)] += similarity

            # 构建关系列表
            for (entity1, entity2), strength in entity_pairs.items():
                if strength > 0.5:  # 设置阈值
                    relationships.append({
                        "source": entity1,
                        "target": entity2,
                        "strength": float(strength),
                        "type": "co-occurrence"
                    })

            # 按关系强度排序
            relationships.sort(key=lambda x: x["strength"], reverse=True)
            
            results["insights"]["relationships"] = relationships[:50]  # 限制关系数量

        except Exception as e:
            self.logger.error(f"分析关系失败: {str(e)}")
            results["insights"]["relationships"] = []

    def _rank_importance(self, results: Dict):
        """重要性排序
        
        对搜索结果进行重要性排序。
        考虑多个因素：相似度、时间相关性、引用频率等。
        """
        try:
            importance_scores = []
            
            # 评分函数
            def calculate_score(item):
                score = 0.0
                
                # 基础分数
                if "similarity" in item:
                    score += item["similarity"] * 0.4  # 相似度权重
                
                # 时间相关性
                if "_processed_at" in item:
                    try:
                        processed_time = datetime.fromisoformat(item["_processed_at"])
                        time_diff = (datetime.now() - processed_time).days
                        time_score = 1.0 / (1.0 + time_diff/365)  # 随时间衰减
                        score += time_score * 0.3
                    except (ValueError, TypeError):
                        pass
                
                # 文档完整性
                if isinstance(item.get("data"), dict):
                    completeness = len(item["data"]) / 10  # 假设最多10个字段
                    score += min(completeness, 1.0) * 0.3
                
                return score

            # 处理结构化结果
            for item in results.get("structured", []):
                score = calculate_score(item)
                importance_scores.append({
                    "id": item.get("_id", ""),
                    "type": "structured",
                    "score": float(score),
                    "content": str(item.get("data", ""))[:100]  # 预览内容
                })

            # 处理向量结果
            for item in results.get("vector", []):
                score = calculate_score(item)
                importance_scores.append({
                    "id": item.get("_id", ""),
                    "type": "vector",
                    "score": float(score),
                    "content": str(item.get("data", ""))[:100]
                })

            # 按得分排序
            importance_scores.sort(key=lambda x: x["score"], reverse=True)
            
            results["insights"]["importance_ranking"] = importance_scores

        except Exception as e:
            self.logger.error(f"重要性排序失败: {str(e)}")
            results["insights"]["importance_ranking"] = [] 


class ResultFormatter:
    """统一的结果格式化器"""
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def format(self, results: Dict, format_type: str = 'json') -> Any:
        """根据指定格式类型格式化结果
        
        Args:
            results: 要格式化的结果
            format_type: 格式类型 ('json' 或 'csv')
            
        Returns:
            格式化后的结果
        """
        if format_type == 'json':
            return self._format_json(results)
        elif format_type == 'csv':
            return self._format_csv(results)
        else:
            raise ValueError(f"不支持的格式类型: {format_type}")

    def _format_json(self, results: Dict) -> Dict:
        """格式化为JSON结构"""
        return {
            "metadata": {
                "original_query": results.get("metadata", {}).get("original_query", ""),
                "generated_at": datetime.now().isoformat(),
                "version": "1.0",
                "summary": {
                    "total_results": results["stats"]["total"],
                    "structured_count": results["stats"]["structured_count"],
                    "vector_count": results["stats"]["vector_count"]
                }
            },
            "results": {
                "structured": results.get("structured", []),
                "vector": results.get("vector", []),
                "insights": results.get("insights", {})
            }
        }

    def _format_csv(self, results: Dict) -> List[Dict]:
        """格式化为CSV友好的结构"""
        formatted_results = []
        
        for item in results.get('structured', []):
            formatted_results.append(self._format_item(item, '结构化搜索'))
            
        for item in results.get('vector', []):
            formatted_results.append(self._format_item(item, '向量搜索'))
            
        return formatted_results
    
    def _format_item(self, item: Dict, search_type: str) -> Dict:
        formatted = {
            'search_type': search_type,
            'similarity': item.get('similarity', 'N/A'),
            'file_path': item.get('_file_path', '') or item.get('file_path', ''),
            'file_name': item.get('_file_name', '') or item.get('file_name', ''),
            'file_type': item.get('_file_type', '') or item.get('file_type', ''),
            'processed_at': item.get('_processed_at', '') or item.get('processed_at', '')
        }
        
        if isinstance(item.get('data'), str):
            try:
                data_dict = json.loads(item['data'])
                formatted.update(data_dict)
            except json.JSONDecodeError:
                formatted['raw_content'] = item.get('data', '')
        elif isinstance(item.get('data'), dict):
            formatted.update(item['data'])
            
        return formatted

class ResultSaver:
    """统一的结果保存器"""
    def __init__(self, work_dir: str = "output", logger: Optional[logging.Logger] = None):
        self.work_dir = work_dir
        self.logger = logger or logging.getLogger(__name__)
        self.formatter = ResultFormatter(logger=self.logger)

    def save(self, results: Dict, filename: str, format_type: str = 'json') -> str:
        """保存结果
        
        Args:
            results: 要保存的结果
            filename: 文件名
            format_type: 保存格式类型
            
        Returns:
            str: 保存文件的路径
        """
        self._ensure_dir()
        filepath = self._get_filepath(filename, format_type)
        
        try:
            formatted_data = self.formatter.format(results, format_type)
            
            if format_type == 'json':
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(formatted_data, f, ensure_ascii=False, indent=2, default=self._json_serializer)
            elif format_type == 'csv':
                df = pd.DataFrame(formatted_data)
                df.to_csv(filepath, index=False, encoding='utf-8')
            
            self.logger.info(f"文件已保存: {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"保存文件失败: {str(e)}")
            return None
            
    def _ensure_dir(self):
        """确保输出目录存在"""
        os.makedirs(self.work_dir, exist_ok=True)
        
    def _get_filepath(self, filename: str, extension: str) -> str:
        """获取完整的文件路径"""
        return os.path.join(self.work_dir, f"{filename}.{extension}")
        
    def _json_serializer(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if pd.isna(obj):
            return None
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

class SearchPlanExecutor:
    """搜索计划执行器"""
    
    def __init__(self, search_engine, work_dir="output", logger: Optional[logging.Logger] = None):
        """初始化搜索计划执行器
        
        Args:
            search_engine: 搜索引擎实例
            work_dir: 工作目录
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.engine = search_engine
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.nlp_processor = None  # 用于文本分析，后续初始化
        self.knowledge_graph = None  # 用于关系分析，后续初始化
        
        # 初始化分析器，传递logger
        self.analyzer = ResultAnalyzer(logger=self.logger)
        
        # 使用新的内部格式化器和保存器
        self.result_saver = ResultSaver(work_dir=str(self.work_dir), logger=self.logger)

    def set_work_dir(self, work_dir: str):
        """设置工作目录"""
        self.work_dir = work_dir
        # 更新所有保存器的工作目录
        self.result_saver.work_dir = work_dir
            
    async def execute_plan(self, plan: Dict) -> Dict:
        """执行检索计划"""
        try:
            # 创建执行结果目录
            execution_dir = self.work_dir / "search_results" 
            execution_dir.mkdir(parents=True, exist_ok=True)
            
            # 初始化文件路径跟踪
            saved_files = {
                "plan": str(execution_dir / "input_plan.json"),
                "final_results": str(execution_dir / "final_results.json"),
                "execution_stats": str(execution_dir / "execution_stats.json"),
                "analysis": {},
                "search_results": {
                    "structured": [],
                    "vector": []
                }
            }
            
            # 保存输入的计划
            with open(saved_files["plan"], "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
            
            # 初始化结果结构
            results = self._initialize_results(plan)
            
            # 执行基础搜索
            search_results = await self._execute_basic_search(plan, results, execution_dir)
            if search_results:
                results = search_results
            
            # 分析结果
            if results['stats']['total'] > 0:
                self.analyzer.analyze(results)
                
                # 保存分析结果
                analysis_dir = execution_dir / "analysis"
                analysis_dir.mkdir(exist_ok=True)
                
                # 保存关键概念
                if results['insights']['key_concepts']:
                    key_concepts_path = analysis_dir / "key_concepts.json"
                    with open(key_concepts_path, "w", encoding="utf-8") as f:
                        json.dump(results['insights']['key_concepts'], f, ensure_ascii=False, indent=2)
                    saved_files["analysis"]["key_concepts"] = str(key_concepts_path)
                
                # 保存关系分析
                if results['insights']['relationships']:
                    relationships_path = analysis_dir / "relationships.json"
                    with open(relationships_path, "w", encoding="utf-8") as f:
                        json.dump(results['insights']['relationships'], f, ensure_ascii=False, indent=2)
                    saved_files["analysis"]["relationships"] = str(relationships_path)
                
                # 保存时间线
                if results['insights']['timeline']:
                    timeline_path = analysis_dir / "timeline.json"
                    with open(timeline_path, "w", encoding="utf-8") as f:
                        json.dump(results['insights']['timeline'], f, ensure_ascii=False, indent=2)
                    saved_files["analysis"]["timeline"] = str(timeline_path)
                
                # 保存重要性排名
                if results['insights']['importance_ranking']:
                    ranking_path = analysis_dir / "importance_ranking.json"
                    with open(ranking_path, "w", encoding="utf-8") as f:
                        json.dump(results['insights']['importance_ranking'], f, ensure_ascii=False, indent=2)
                    saved_files["analysis"]["importance_ranking"] = str(ranking_path)
            
            # 保存最终结果
            with open(saved_files["final_results"], "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            
            # 保存执行统计信息
            stats = {
                "execution_time": datetime.now().isoformat(),
                "query": plan.get("metadata", {}).get("original_query", ""),
                "total_results": results["stats"]["total"],
                "structured_results": results["stats"]["structured_count"],
                "vector_results": results["stats"]["vector_count"]
            }
            with open(saved_files["execution_stats"], "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            
            # 将文件路径信息添加到结果中
            results["saved_files"] = saved_files
            
            return results
            
        except Exception as e:
            self.logger.error(f"执行检索计划失败: {str(e)}", exc_info=True)
            raise

    def _initialize_results(self, plan: Dict) -> Dict:
        """初始化结果结构"""
        results = {
            "structured": [],
            "vector": [],
            "stats": {
                "structured_count": 0,
                "vector_count": 0,
                "total": 0
            },
            "insights": {
                "key_concepts": [],
                "relationships": [],
                "timeline": [],
                "importance_ranking": []
            },
            "context": {
                "historical": [],
                "related": [],
                "dependencies": []
            },
            "metadata": {
                "original_query": plan.get("metadata", {}).get("original_query", ""),
                "generated_at": plan.get("metadata", {}).get("generated_at", ""),
                "execution_time": datetime.now().isoformat()
            },
            "saved_files": {
                "plan": "",
                "final_results": "",
                "execution_stats": "",
                "analysis": {},
                "search_results": {
                    "structured": [],
                    "vector": []
                }
            }
        }
        return results

    async def _execute_basic_search(self, plan: Dict, results: Dict, execution_dir: Path):
        """执行基础搜索"""
        try:
            seen_fingerprints = set()
            search_results_dir = execution_dir / "search_results"
            search_results_dir.mkdir(exist_ok=True)
            
            # 执行结构化查询
            if plan.get("structured_queries"):
                structured_dir = search_results_dir / "structured"
                structured_dir.mkdir(exist_ok=True)
                
                for i, query in enumerate(plan["structured_queries"]):
                    try:
                        df = self.engine.execute_structured_query(query)
                        if df is not None and not df.empty:
                            # 将DataFrame转换为记录之前处理Timestamp
                            for col in df.select_dtypes(include=['datetime64[ns]']).columns:
                                df[col] = df[col].astype(str)
                                
                            records = df.to_dict('records')
                            filtered_records = []
                            for record in records:
                                fingerprint = self._generate_content_fingerprint(record.get('data', ''))
                                if fingerprint not in seen_fingerprints:
                                    seen_fingerprints.add(fingerprint)
                                    filtered_records.append(record)
                                    results["structured"].append(record)
                            
                            # 保存结果并记录文件路径
                            result_path = structured_dir / f"query_{i+1}_results.json"
                            with open(result_path, "w", encoding="utf-8") as f:
                                json.dump(filtered_records, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
                            results["saved_files"]["search_results"]["structured"].append(str(result_path))
                    except Exception as e:
                        self.logger.error(f"结构化查询执行失败: {str(e)}", exc_info=True)
                        continue
            
            # 执行向量查询
            if plan.get("vector_queries"):
                vector_dir = search_results_dir / "vector"
                vector_dir.mkdir(exist_ok=True)
                
                for i, vector_query in enumerate(plan["vector_queries"]):
                    try:
                        vector_results = self.engine.execute_vector_search(
                            vector_query["reference_text"],
                            vector_query["top_k"]
                        )
                        
                        if vector_results:
                            filtered_results = []
                            threshold = vector_query["similarity_threshold"]
                            for result in vector_results:
                                if result["similarity"] >= threshold:
                                    if isinstance(result["similarity"], np.float32):
                                        result["similarity"] = float(result["similarity"])
                                    
                                    fingerprint = self._generate_content_fingerprint(result.get('data', ''))
                                    if fingerprint not in seen_fingerprints:
                                        seen_fingerprints.add(fingerprint)
                                        filtered_results.append(result)
                                        results["vector"].append(result)
                            
                            # 保存结果并记录文件路径
                            result_path = vector_dir / f"query_{i+1}_results.json"
                            with open(result_path, "w", encoding="utf-8") as f:
                                json.dump(filtered_results, f, ensure_ascii=False, indent=2)
                            results["saved_files"]["search_results"]["vector"].append(str(result_path))
                    except Exception as e:
                        self.logger.error(f"向量查询执行失败: {str(e)}", exc_info=True)
                        continue
            
            # 更新统计信息
            results["stats"]["structured_count"] = len(results["structured"])
            results["stats"]["vector_count"] = len(results["vector"])
            results["stats"]["total"] = (
                results["stats"]["structured_count"] + 
                results["stats"]["vector_count"]
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"基础搜索执行失败: {str(e)}", exc_info=True)
            raise

    def _generate_content_fingerprint(self, content: str) -> str:
        """生成内容指纹
        
        Args:
            content: 需要生成指纹的内容
            
        Returns:
            str: 内容的唯一指纹
        """
        # 预处理内容
        processed_content = str(content).lower()  # 转小写
        processed_content = ' '.join(processed_content.split())  # 规范化空白字符
        
        # 生成MD5指纹
        return hashlib.md5(processed_content.encode('utf-8')).hexdigest()

    def set_search_engine(self, search_engine):
        """设置搜索引擎"""
        self.engine = search_engine
