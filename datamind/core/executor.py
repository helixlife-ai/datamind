import logging
import pandas as pd
from typing import Dict, List
import os
from datetime import datetime, date
from collections import defaultdict
import numpy as np
from itertools import combinations
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import hashlib

class SearchPlanExecutor:
    """搜索计划执行器"""
    
    def __init__(self, search_engine):
        self.engine = search_engine
        self.logger = logging.getLogger(__name__)
        self.work_dir = "output"  # 默认输出目录
        self.nlp_processor = None  # 用于文本分析，后续初始化
        self.knowledge_graph = None  # 用于关系分析，后续初始化
        self.supported_formats = ['csv', 'json', 'xml', 'html', 'md', 'xlsx']
        
    def execute_plan(self, plan: Dict) -> Dict:
        """执行检索计划并进行深度分析"""
        # 基础搜索结果
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
            }
        }
        
        # 执行基础搜索
        self._execute_basic_search(plan, results)
        
        # 深度分析结果
        self._analyze_results(results)
        
        # 生成洞察
        self._generate_insights(results)
        
        return results

    def _execute_basic_search(self, plan: Dict, results: Dict):
        """执行基础搜索逻辑"""
        # 用于存储已见过的内容指纹
        seen_fingerprints = set()
        
        # 执行结构化查询
        if plan.get("structured_queries"):
            try:
                for query in plan["structured_queries"]:
                    df = self.engine.execute_structured_query(query)
                    records = df.to_dict('records')
                    # 对结构化查询结果进行排重
                    for record in records:
                        fingerprint = self._generate_content_fingerprint(record.get('data', ''))
                        if fingerprint not in seen_fingerprints:
                            seen_fingerprints.add(fingerprint)
                            results["structured"].append(record)
                            
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
                    
                    # 过滤相似度阈值并排重
                    threshold = vector_query["similarity_threshold"]
                    for result in vector_results:
                        if result["similarity"] >= threshold:
                            fingerprint = self._generate_content_fingerprint(result.get('data', ''))
                            if fingerprint not in seen_fingerprints:
                                seen_fingerprints.add(fingerprint)
                                results["vector"].append(result)
                                
                results["stats"]["vector_count"] = len(results["vector"])
                self.logger.info(f"向量查询结果: {results['vector']}")
            except Exception as e:
                self.logger.error(f"向量查询执行失败: {str(e)}")
                
        # 计算总数
        results["stats"]["total"] = (
            results["stats"]["structured_count"] + 
            results["stats"]["vector_count"]
        )

    def _analyze_results(self, results: Dict):
        """深度分析搜索结果"""
        try:
            # 1. 提取关键概念
            all_content = self._get_all_content(results)
            results["insights"]["key_concepts"] = self._extract_key_concepts(all_content)
            
            # 2. 建立时间线
            results["insights"]["timeline"] = self._build_timeline(results)
            
            # 3. 分析文档关系
            results["insights"]["relationships"] = self._analyze_relationships(results)
            
            # 4. 重要性排序
            results["insights"]["importance_ranking"] = self._rank_importance(results)
            
        except Exception as e:
            self.logger.error(f"结果分析失败: {str(e)}")

    def _get_all_content(self, results: Dict) -> List[str]:
        """获取所有搜索结果的内容"""
        content = []
        for item in results["structured"]:
            content.append(str(item.get("data", "")))
        for item in results["vector"]:
            content.append(str(item.get("data", "")))
        return content

    def _extract_key_concepts(self, content: List[str]) -> List[Dict]:
        """提取关键概念及其重要性"""
        concepts = []
        # 实现关键概念提取逻辑
        # TODO: 使用NLP工具实现
        return concepts

    def _build_timeline(self, results: Dict) -> List[Dict]:
        """构建结果时间线"""
        timeline = []
        for item in results["structured"] + results["vector"]:
            if timestamp := self._extract_timestamp(item):
                timeline.append({
                    "date": timestamp,
                    "event": self._summarize_content(item.get("data", "")),
                    "source": item.get("_file_name", "")
                })
        return sorted(timeline, key=lambda x: x["date"])

    def _analyze_relationships(self, results: Dict) -> List[Dict]:
        """分析文档间关系"""
        relationships = []
        documents = results["structured"] + results["vector"]
        
        # 构建文档相似度矩阵
        for doc1, doc2 in combinations(documents, 2):
            similarity = self._calculate_similarity(doc1, doc2)
            if similarity > 0.5:  # 相似度阈值
                relationships.append({
                    "type": "similar_content",
                    "doc1": doc1.get("_file_name"),
                    "doc2": doc2.get("_file_name"),
                    "similarity": similarity
                })
        
        return relationships

    def _rank_importance(self, results: Dict) -> List[Dict]:
        """对结果进行重要性排序"""
        ranked_items = []
        for item in results["structured"] + results["vector"]:
            score = self._calculate_importance_score(item)
            ranked_items.append({
                "item": item,
                "score": score
            })
        return sorted(ranked_items, key=lambda x: x["score"], reverse=True)

    def _generate_insights(self, results: Dict):
        """生成洞察"""
        # 实现洞察生成逻辑
        # TODO: 根据分析结果生成洞察
        pass

    def format_results(self, results: Dict) -> str:
        """增强的结果格式化"""
        output = []
        
        # 1. 执行摘要
        output.append(self._generate_executive_summary(results))
        
        # 2. 关键发现
        output.append("\n主要发现:")
        for idx, concept in enumerate(results["insights"]["key_concepts"][:5], 1):
            output.append(f"{idx}. {concept}")
            
        # 3. 时间线视图
        if results["insights"]["timeline"]:
            output.append("\n时间发展:")
            for event in results["insights"]["timeline"]:
                output.append(f"- {event['date']}: {event['event']}")
                
        # 4. 相关性聚类
        if results["insights"]["relationships"]:
            output.append("\n相关内容聚类:")
            for relation in results["insights"]["relationships"]:
                output.append(f"- {relation['type']}: {relation['doc1']} 与 {relation['doc2']}")
                
        # 5. 重要性排序
        output.append("\n重要内容排序:")
        for idx, item in enumerate(results["insights"]["importance_ranking"][:5], 1):
            output.append(f"{idx}. {self._summarize_content(item['item'].get('data', ''))}")
        
        return "\n".join(output)

    def _generate_executive_summary(self, results: Dict) -> str:
        """生成执行摘要"""
        return f"""搜索结果摘要:
- 总计找到 {results['stats']['total']} 条相关结果
- 识别出 {len(results['insights']['key_concepts'])} 个关键概念
- 发现 {len(results['insights']['relationships'])} 个内容关联
- 时间跨度: {self._get_time_span(results['insights']['timeline'])}"""

    def save_results(self, results: Dict, format: str = 'json', output_dir: str = None) -> str:
        """多格式结果保存
        
        Args:
            results: 搜索结果
            format: 输出格式 (json/csv/xml/html/md/xlsx)
            output_dir: 输出目录
            
        Returns:
            str: 保存的文件路径
        """
        if format not in self.supported_formats:
            raise ValueError(f"不支持的格式: {format}")
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = output_dir or self.work_dir
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"search_results_{timestamp}"
        
        if format == 'json':
            return self._save_as_json(results, filename, output_dir)
        elif format == 'xml':
            return self._save_as_xml(results, filename, output_dir)
        elif format == 'html':
            return self._save_as_html(results, filename, output_dir)
        elif format == 'md':
            return self._save_as_markdown(results, filename, output_dir)
        elif format == 'xlsx':
            return self._save_as_excel(results, filename, output_dir)
        elif format == 'csv':
            return self._save_as_csv(results, filename, output_dir)
        
    def _save_as_csv(self, results: Dict, filename: str, output_dir: str) -> str:
        """保存为CSV格式，支持JSON字段展开
        
        Args:
            results: 搜索结果
            filename: 文件名
            output_dir: 输出目录
            
        Returns:
            str: 保存的文件路径
        """
        filepath = os.path.join(output_dir, f"{filename}.csv")
        
        try:
            # 准备数据
            rows = []
            
            # 处理结构化搜索结果
            for item in results.get('structured', []):
                row = {
                    'search_type': '结构化搜索',
                    'similarity': 'N/A',
                    'file_path': item.get('_file_path', ''),                    
                    'file_name': item.get('_file_name', ''),
                    'file_type': item.get('_file_type', ''),                   
                    'processed_at': item.get('_processed_at', '')
                }
                
                # 解析data字段的JSON内容
                if isinstance(item.get('data'), str):
                    try:
                        data_dict = json.loads(item['data'])
                        row.update(data_dict)
                    except json.JSONDecodeError:
                        row['raw_content'] = item.get('data', '')
                elif isinstance(item.get('data'), dict):
                    row.update(item['data'])
                
                rows.append(row)
            
            # 处理向量搜索结果
            for item in results.get('vector', []):
                row = {
                    'search_type': '向量搜索',
                    'similarity': f"{item.get('similarity', 0):.4f}",
                    'file_path': item.get('file_path', ''),                    
                    'file_name': item.get('file_name', ''),
                    'file_type': item.get('file_type', ''),
                    'processed_at': item.get('processed_at', '')
                }
                
                # 解析data字段的JSON内容
                if isinstance(item.get('data'), str):
                    try:
                        data_dict = json.loads(item['data'])
                        row.update(data_dict)
                    except json.JSONDecodeError:
                        row['raw_content'] = item.get('data', '')
                elif isinstance(item.get('data'), dict):
                    row.update(item['data'])
                
                rows.append(row)
            
            # 创建DataFrame并保存为CSV
            if rows:
                df = pd.DataFrame(rows)
                
                # 对列进行排序：元数据列在前，其他列按字母顺序排序
                meta_columns = ['search_type', 'similarity', 'file_path', 'file_name', 'file_type', 'processed_at']
                other_columns = sorted([col for col in df.columns if col not in meta_columns])
                ordered_columns = meta_columns + other_columns
                
                df = df.reindex(columns=ordered_columns)
                df.to_csv(filepath, index=False, encoding='utf-8-sig')
                self.logger.info(f"搜索结果已保存到: {filepath}")
                return filepath
            else:
                self.logger.warning("没有搜索结果可保存")
                return ""
            
        except Exception as e:
            self.logger.error(f"保存CSV格式结果时出错: {str(e)}")
            raise

    def _json_serializer(self, obj):
        """自定义JSON序列化处理"""
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

    def _save_as_json(self, results: Dict, filename: str, output_dir: str) -> str:
        """保存为JSON格式，保持完整的数据结构"""
        filepath = os.path.join(output_dir, f"{filename}.json")
        
        # 添加元数据
        output = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "version": "1.0",
                "summary": {
                    "total_results": results["stats"]["total"],
                    "query_types": list(results.keys())
                }
            },
            "results": results
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=self._json_serializer)
            
        return filepath

    def _save_as_html(self, results: Dict, filename: str, output_dir: str) -> str:
        """生成交互式HTML报告"""
        filepath = os.path.join(output_dir, f"{filename}.html")
        
        try:
            # 1. 安全地获取统计数据
            stats = results.get("stats", {})
            structured_count = stats.get("structured_count", 0)
            vector_count = stats.get("vector_count", 0)
            
            # 2. 生成HTML内容部分
            insights_section = self._generate_html_insights(results)
            results_section = self._generate_html_results(results)
            
            # 3. HTML模板 - 使用更安全的格式化方式
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>搜索结果报告</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 20px;
            line-height: 1.6;
        }}
        .results-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1em 0;
        }}
        .results-table th, .results-table td {{
            padding: 8px;
            border: 1px solid #ddd;
            text-align: left;
        }}
        .results-table th {{
            background-color: #f5f5f5;
            font-weight: bold;
        }}
        .results-table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        .table-responsive {{
            overflow-x: auto;
            margin: 1em 0;
        }}
        .insight-section {{
            background: #f5f5f5;
            padding: 20px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .chart-container {{
            height: 300px;
            margin: 20px 0;
            padding: 20px;
            background: white;
            border: 1px solid #eee;
            border-radius: 4px;
        }}
        h1, h2, h3, h4 {{
            color: #333;
            margin-top: 20px;
        }}
        .error {{
            color: #721c24;
            background-color: #f8d7da;
            padding: 1em;
            margin: 1em 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <h1>搜索结果报告</h1>

    <div class="chart-container">
        <canvas id="resultsChart"></canvas>
    </div>

    {insights_section}

    {results_section}

    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        const ctx = document.getElementById('resultsChart');
        new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: ['结构化查询', '向量查询'],
                datasets: [{{
                    label: '结果数量',
                    data: [{structured_count}, {vector_count}],
                    backgroundColor: [
                        'rgba(54, 162, 235, 0.5)',
                        'rgba(75, 192, 192, 0.5)'
                    ],
                    borderColor: [
                        'rgba(54, 162, 235, 1)',
                        'rgba(75, 192, 192, 1)'
                    ],
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }}
            }}
        }});
    }});
    </script>
</body>
</html>"""

            # 4. 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)
            
            # 5. 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            self.logger.info(f"HTML报告已生成: {filepath}")
            return filepath
            
        except Exception as e:
            error_msg = f"生成HTML报告时出错: {str(e)}"
            self.logger.error(error_msg)
            
            # 生成错误报告
            error_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>搜索结果报告 - 错误</title>
    <style>
        .error {{
            color: #721c24;
            background-color: #f8d7da;
            padding: 1em;
            margin: 1em 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <h1>搜索结果报告生成失败</h1>
    <div class="error">
        <h2>错误信息:</h2>
        <pre>{error_msg}</pre>
    </div>
</body>
</html>"""

            # 写入错误报告
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(error_html)
            
            raise

    def _save_as_markdown(self, results: Dict, filename: str, output_dir: str) -> str:
        """生成Markdown格式报告"""
        filepath = os.path.join(output_dir, f"{filename}.md")
        
        content = [
            "# 搜索结果报告",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            
            "## 统计摘要",
            f"- 总结果数: {results['stats']['total']}",
            f"- 结构化结果: {results['stats']['structured_count']}",
            f"- 向量结果: {results['stats']['vector_count']}",
            
            "## 关键发现",
            *[f"- {concept}" for concept in results["insights"]["key_concepts"]],
            
            "## 时间线",
            *[f"- {event['date']}: {event['event']}" for event in results["insights"]["timeline"]],
            
            "## 详细结果",
            "### 结构化查询结果",
            *self._format_results_as_md(results["structured"]),
            
            "### 向量查询结果",
            *self._format_results_as_md(results["vector"])
        ]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(content))
            
        return filepath

    def _save_as_excel(self, results: Dict, filename: str, output_dir: str) -> str:
        """保存为Excel格式，支持多sheet和JSON字段展开
        
        Args:
            results: 搜索结果
            filename: 文件名
            output_dir: 输出目录
            
        Returns:
            str: 保存的文件路径
        """
        filepath = os.path.join(output_dir, f"{filename}.xlsx")
        
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # 概述sheet
            summary_data = {
                "指标": ["总结果数", "结构化结果数", "向量结果数"],
                "数值": [
                    results["stats"]["total"],
                    results["stats"]["structured_count"],
                    results["stats"]["vector_count"]
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name="概述", index=False)
            
            # 处理搜索结果
            def process_results(items, sheet_name):
                if not items:
                    return
                
                rows = []
                for item in items:
                    row = {
                        'file_name': item.get('_file_name', ''),
                        'file_path': item.get('_file_path', ''),
                        'file_type': item.get('_file_type', ''),
                        'processed_at': item.get('_processed_at', ''),
                        'similarity': item.get('similarity', 'N/A')
                    }
                    
                    # 解析data字段
                    if isinstance(item.get('data'), str):
                        try:
                            data_dict = json.loads(item['data'])
                            row.update(data_dict)
                        except json.JSONDecodeError:
                            row['raw_content'] = item.get('data', '')
                    elif isinstance(item.get('data'), dict):
                        row.update(item['data'])
                    
                    rows.append(row)
                
                if rows:
                    df = pd.DataFrame(rows)
                    # 对列进行排序：元数据列在前，其他列按字母顺序排序
                    meta_columns = ['file_name', 'file_path', 'file_type', 'processed_at', 'similarity']
                    other_columns = sorted([col for col in df.columns if col not in meta_columns])
                    df = df.reindex(columns=meta_columns + other_columns)
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # 保存结构化结果
            process_results(results.get("structured", []), "结构化搜索结果")
            
            # 保存向量结果
            process_results(results.get("vector", []), "向量搜索结果")
            
            # 保存洞察结果
            insights_data = []
            for concept in results.get("insights", {}).get("key_concepts", []):
                insights_data.append({
                    "类型": "关键概念",
                    "内容": concept
                })
            
            for relation in results.get("insights", {}).get("relationships", []):
                insights_data.append({
                    "类型": "关系发现",
                    "内容": f"{relation['type']}: {relation['doc1']} - {relation['doc2']}"
                })
            
            if insights_data:
                pd.DataFrame(insights_data).to_excel(writer, sheet_name="分析洞察", index=False)
        
        return filepath

    # 辅助方法
    def _calculate_similarity(self, doc1: Dict, doc2: Dict) -> float:
        """计算文档相似度"""
        # TODO: 实现文档相似度计算
        return 0.0

    def _calculate_importance_score(self, item: Dict) -> float:
        """计算内容重要性分数"""
        # TODO: 实现重要性评分
        return 0.0

    def _summarize_content(self, content: str) -> str:
        """生成内容摘要"""
        # TODO: 实现内容摘要
        return content[:100] + "..." if len(content) > 100 else content

    def _extract_timestamp(self, item: Dict) -> str:
        """提取时间戳"""
        # TODO: 实现时间提取
        return ""

    def _get_time_span(self, timeline: List[Dict]) -> str:
        """获取时间跨度"""
        if not timeline:
            return "无时间信息"
        dates = [event["date"] for event in timeline]
        return f"{min(dates)} 至 {max(dates)}"

    def _generate_html_insights(self, results: Dict) -> str:
        """生成HTML格式的洞察部分，包含错误处理"""
        try:
            insights = results.get("insights", {})
            key_concepts = insights.get("key_concepts", [])
            timeline = insights.get("timeline", [])
            
            # 使用HTML转义处理内容
            from html import escape
            
            concepts_html = "<ul>" + "".join([
                f"<li>{escape(str(concept))}</li>" 
                for concept in key_concepts
            ]) + "</ul>"
            
            timeline_html = "<div class='timeline'>" + "".join([
                f"<div class='timeline-item'><strong>{escape(str(event.get('date', '')))}</strong>: {escape(str(event.get('event', '')))}</div>"
                for event in timeline
            ]) + "</div>"
            
            return f"""
            <div class="insight-section">
                <h2>关键发现</h2>
                {concepts_html}
                
                <h2>时间线</h2>
                {timeline_html}
            </div>
            """
        except Exception as e:
            self.logger.error(f"生成洞察HTML时出错: {str(e)}")
            return "<div class='error'>生成洞察内容时出错</div>"

    def _generate_html_results(self, results: Dict) -> str:
        """生成HTML格式的结果部分，包含错误处理"""
        try:
            from html import escape
            
            def process_result_items(items, title, search_type):
                if not items:
                    return f"<div class='results-group'><h3>{escape(title)}</h3><p>无结果</p></div>"
                
                # 定义固定的元数据列，与CSV保持一致
                meta_columns = ['file_path', 'file_type']
                
                # 处理数据
                data_dicts = []
                for item in items:
                    row = {
                        'file_path': item.get('file_path', '') or item.get('_file_path', ''),
                        'file_type': item.get('file_type', '') or item.get('_file_type', ''),
                    }
                    
                    # 解析data字段
                    if isinstance(item.get('data'), str):
                        try:
                            data_dict = json.loads(item['data'])
                            row.update(data_dict)
                        except json.JSONDecodeError:
                            row['raw_content'] = item.get('data', '')
                    elif isinstance(item.get('data'), dict):
                        row.update(item['data'])
                    
                    data_dicts.append(row)
                
                if not data_dicts:
                    return f"<div class='results-group'><h3>{escape(title)}</h3><p>无结果</p></div>"
                
                # 收集所有列
                all_columns = set()
                for data in data_dicts:
                    all_columns.update(data.keys())
                
                # 对非元数据列进行排序
                other_columns = sorted([col for col in all_columns if col not in meta_columns])
                display_columns = meta_columns + other_columns
                
                # 生成表格HTML
                table_html = [
                    f"<div class='results-group'>",
                    f"<h3>{escape(title)}</h3>",
                    "<div class='table-responsive'>",
                    "<table class='results-table'>",
                    "<thead><tr>"
                ]
                
                # 表头
                table_html.extend(f"<th>{escape(col)}</th>" for col in display_columns)
                table_html.append("</tr></thead>")
                
                # 表格内容
                table_html.append("<tbody>")
                for data in data_dicts:
                    table_html.append("<tr>")
                    for col in display_columns:
                        value = data.get(col, '')
                        if isinstance(value, (dict, list)):
                            value = json.dumps(value, ensure_ascii=False)
                        table_html.append(f"<td>{escape(str(value))}</td>")
                    table_html.append("</tr>")
                
                table_html.extend([
                    "</tbody>",
                    "</table>",
                    "</div>",
                    "</div>"
                ])
                
                return "\n".join(table_html)
            
            # 处理结构化和向量搜索结果
            structured_html = process_result_items(results.get("structured", []), "结构化查询结果", "结构化搜索")
            vector_html = process_result_items(results.get("vector", []), "向量查询结果", "向量搜索")
            
            return f"""
            <div class="results-section">
                {structured_html}
                {vector_html}
            </div>
            """
            
        except Exception as e:
            self.logger.error(f"生成结果HTML时出错: {str(e)}")
            return "<div class='error'>生成结果内容时出错</div>"

    def _format_results_as_md(self, results: List[Dict]) -> List[str]:
        """格式化结果为Markdown格式"""
        formatted = []
        for item in results:
            formatted.extend([
                f"#### {item.get('_file_name', '')}",
                f"```",
                self._summarize_content(str(item.get('data', ''))),
                f"```",
                ""
            ])
        return formatted

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