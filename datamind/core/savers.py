import os
import json
import pandas as pd
from datetime import datetime, date
from typing import Dict, List
import logging
from pathlib import Path
import numpy as np
from html import escape

class ResultSaver:
    """结果保存器基类"""
    def __init__(self, work_dir: str = "output"):
        self.work_dir = work_dir
        self.logger = logging.getLogger(__name__)

    def save(self, results: Dict, filename: str) -> str:
        """保存结果的抽象方法"""
        raise NotImplementedError
        
    def _ensure_dir(self):
        """确保输出目录存在"""
        os.makedirs(self.work_dir, exist_ok=True)
        
    def _get_filepath(self, filename: str, extension: str) -> str:
        """获取完整的文件路径"""
        self._ensure_dir()
        return os.path.join(self.work_dir, f"{filename}.{extension}")

class JSONSaver(ResultSaver):
    """JSON保存器"""
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为JSON格式"""
        filepath = self._get_filepath(filename, "json")
        
        # 添加元数据
        output = {
            "metadata": {
                "original_query": results.get("metadata", {}).get("original_query", ""),
                "generated_at": datetime.now().isoformat(),
                "version": "1.0",
                "summary": {
                    "total_results": results["stats"]["total"],
                    "query_types": list(results.keys())
                }
            },
            "results": results
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2, default=self._json_serializer)
            self.logger.info(f"JSON文件已保存: {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"保存JSON文件失败: {str(e)}")
            return None
            
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

class CSVSaver(ResultSaver):
    """CSV保存器"""
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为CSV格式"""
        filepath = self._get_filepath(filename, "csv")
        
        try:
            # 准备数据
            rows = []
            original_query = results.get("metadata", {}).get("original_query", "")
            
            # 处理结构化搜索结果
            for item in results.get('structured', []):
                row = {
                    'original_query': original_query,
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
                    'original_query': original_query,
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
                meta_columns = ['original_query', 'search_type', 'similarity', 'file_path', 
                              'file_name', 'file_type', 'processed_at']
                other_columns = sorted([col for col in df.columns if col not in meta_columns])
                ordered_columns = meta_columns + other_columns
                
                df = df.reindex(columns=ordered_columns)
                df.to_csv(filepath, index=False, encoding='utf-8-sig')
                self.logger.info(f"CSV文件已保存: {filepath}")
                return filepath
            else:
                self.logger.warning("没有搜索结果可保存")
                return None
                
        except Exception as e:
            self.logger.error(f"保存CSV文件失败: {str(e)}")
            return None

class ExcelSaver(ResultSaver):
    """Excel保存器"""
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为Excel格式"""
        filepath = self._get_filepath(filename, "xlsx")
        
        try:
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
            
            self.logger.info(f"Excel文件已保存: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"保存Excel文件失败: {str(e)}")
            return None

class HTMLSaver(ResultSaver):
    """HTML保存器"""
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为HTML格式"""
        filepath = self._get_filepath(filename, "html")
        
        try:
            # 获取统计数据和元数据
            stats = results.get("stats", {})
            metadata = results.get("metadata", {})
            structured_count = stats.get("structured_count", 0)
            vector_count = stats.get("vector_count", 0)
            original_query = metadata.get("original_query", "")
            
            # 生成HTML内容
            html_content = self._generate_html_content(
                results=results,
                stats=stats,
                metadata=metadata,
                structured_count=structured_count,
                vector_count=vector_count,
                original_query=escape(original_query)
            )
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            self.logger.info(f"HTML文件已保存: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"保存HTML文件失败: {str(e)}")
            return None
            
    def _generate_html_content(self, **kwargs) -> str:
        """生成HTML内容"""
        results = kwargs['results']
        stats = kwargs['stats']
        metadata = kwargs['metadata']
        structured_count = kwargs['structured_count']
        vector_count = kwargs['vector_count']
        original_query = kwargs['original_query']
        
        insights_section = self._generate_insights_section(results)
        results_section = self._generate_results_section(results)
        
        return f"""<!DOCTYPE html>
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
        .query-info {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
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
    </style>
</head>
<body>
    <h1>搜索结果报告</h1>

    <div class="query-info">
        <h2>查询信息</h2>
        <p><strong>原始查询：</strong>{original_query}</p>
        <p><strong>生成时间：</strong>{metadata.get("generated_at", "")}</p>
        <p><strong>执行时间：</strong>{metadata.get("execution_time", "")}</p>
    </div>

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

    def _generate_insights_section(self, results: Dict) -> str:
        """生成洞察部分HTML"""
        insights = results.get("insights", {})
        key_concepts = insights.get("key_concepts", [])
        timeline = insights.get("timeline", [])
        
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

    def _generate_results_section(self, results: Dict) -> str:
        """生成结果部分HTML"""
        def process_result_items(items, title):
            if not items:
                return f"<div class='results-group'><h3>{escape(title)}</h3><p>无结果</p></div>"
            
            # 定义固定的元数据列
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
        structured_html = process_result_items(results.get("structured", []), "结构化查询结果")
        vector_html = process_result_items(results.get("vector", []), "向量查询结果")
        
        return f"""
        <div class="results-section">
            {structured_html}
            {vector_html}
        </div>
        """

# 其他保存器类... 