"""基础HTML模板"""
from typing import Dict, List
from html import escape
import json

class BaseTemplate:
    def get_style(self) -> str:
        return """
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 20px;
            line-height: 1.6;
        }
        .query-info {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .results-table {
            width: 100%;
            border-collapse: collapse;
            margin: 1em 0;
        }
        .results-table th, .results-table td {
            padding: 8px;
            border: 1px solid #ddd;
            text-align: left;
        }
        .results-table th {
            background-color: #f5f5f5;
            font-weight: bold;
        }
        .results-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .table-responsive {
            overflow-x: auto;
            margin: 1em 0;
        }
        .insight-section {
            background: #f5f5f5;
            padding: 20px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .chart-container {
            height: 300px;
            margin: 20px 0;
            padding: 20px;
            background: white;
            border: 1px solid #eee;
            border-radius: 4px;
        }
        """
    
    def get_scripts(self) -> str:
        return """
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            const ctx = document.getElementById('resultsChart');
            if (ctx) {
                new Chart(ctx, {
                    type: 'bar',
                    data: window.chartData,
                    options: {
                        responsive: true,
                        scales: {
                            y: {
                                beginAtZero: true
                            }
                        }
                    }
                });
            }
        });
        </script>
        """

class SearchResultTemplate(BaseTemplate):
    def render(self, context: Dict) -> str:
        chart_data = self._prepare_chart_data(context)
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{context.get('title', '搜索结果报告')}</title>
            <style>{self.get_style()}</style>
            <script>
            window.chartData = {json.dumps(chart_data)};
            </script>
            {self.get_scripts()}
        </head>
        <body>
            {self._render_header(context)}
            {self._render_stats(context)}
            {self._render_insights(context)}
            {self._render_results(context)}
        </body>
        </html>
        """
    
    def _render_header(self, context: Dict) -> str:
        metadata = context.get('metadata', {})
        return f"""
        <h1>搜索结果报告</h1>
        <div class="query-info">
            <h2>查询信息</h2>
            <p><strong>原始查询：</strong>{escape(context.get('original_query', ''))}</p>
            <p><strong>生成时间：</strong>{metadata.get('generated_at', '')}</p>
            <p><strong>执行时间：</strong>{metadata.get('execution_time', '')}</p>
        </div>
        """
    
    def _render_stats(self, context: Dict) -> str:
        return """
        <div class="chart-container">
            <canvas id="resultsChart"></canvas>
        </div>
        """
    
    def _render_insights(self, context: Dict) -> str:
        insights = context.get('insights', {})
        key_concepts = insights.get('key_concepts', [])
        relationships = insights.get('relationships', [])
        
        concepts_html = "<ul>" + "".join([
            f"<li>{escape(str(concept))}</li>" 
            for concept in key_concepts
        ]) + "</ul>"
        
        relationships_html = "<ul>" + "".join([
            f"<li>{escape(rel.get('type', ''))}: {escape(rel.get('doc1', ''))} - {escape(rel.get('doc2', ''))}</li>"
            for rel in relationships
        ]) + "</ul>"
        
        return f"""
        <div class="insight-section">
            <h2>关键发现</h2>
            {concepts_html}
            
            <h2>关系发现</h2>
            {relationships_html}
        </div>
        """
    
    def _render_results(self, context: Dict) -> str:
        def render_result_table(results: List[Dict], title: str) -> str:
            if not results:
                return f"<h3>{escape(title)}</h3><p>无结果</p>"
            
            # 获取所有列
            columns = set()
            for result in results:
                columns.update(result.keys())
            
            # 固定的元数据列放在前面
            meta_columns = ['file_path', 'file_type', 'similarity']
            other_columns = sorted(col for col in columns if col not in meta_columns)
            all_columns = meta_columns + other_columns
            
            # 生成表格
            table_html = [
                f"<h3>{escape(title)}</h3>",
                '<div class="table-responsive">',
                '<table class="results-table">',
                '<thead><tr>'
            ]
            
            # 表头
            table_html.extend(f"<th>{escape(col)}</th>" for col in all_columns)
            table_html.append("</tr></thead><tbody>")
            
            # 数据行
            for result in results:
                table_html.append("<tr>")
                for col in all_columns:
                    value = result.get(col, '')
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value, ensure_ascii=False)
                    table_html.append(f"<td>{escape(str(value))}</td>")
                table_html.append("</tr>")
            
            table_html.extend(['</tbody></table></div>'])
            return '\n'.join(table_html)
        
        structured_html = render_result_table(
            context.get('structured_results', []), 
            "结构化查询结果"
        )
        vector_html = render_result_table(
            context.get('vector_results', []), 
            "向量查询结果"
        )
        
        return f"""
        <div class="results-section">
            {structured_html}
            {vector_html}
        </div>
        """
    
    def _prepare_chart_data(self, context: Dict) -> Dict:
        stats = context.get('stats', {})
        return {
            'labels': ['结构化查询', '向量查询'],
            'datasets': [{
                'label': '结果数量',
                'data': [
                    stats.get('structured_count', 0),
                    stats.get('vector_count', 0)
                ],
                'backgroundColor': [
                    'rgba(54, 162, 235, 0.5)',
                    'rgba(75, 192, 192, 0.5)'
                ],
                'borderColor': [
                    'rgba(54, 162, 235, 1)',
                    'rgba(75, 192, 192, 1)'
                ],
                'borderWidth': 1
            }]
        } 