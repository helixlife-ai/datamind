import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime
import re
from ..config.settings import (
    DEFAULT_REASONING_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE
)
from ..models.model_manager import ModelManager, ModelConfig

class DeliveryGenerator:
    """交付文件生成器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.model_manager = ModelManager()
        
        # 注册推理模型配置
        self.model_manager.register_model(ModelConfig(
            name=DEFAULT_REASONING_MODEL,
            model_type="api",
            api_key=DEFAULT_LLM_API_KEY,
            api_base=DEFAULT_LLM_API_BASE
        ))
    
    def _load_context(self, plan_dir: Path) -> Dict:
        """加载上下文信息"""
        context = {}
        try:
            # 加载交付计划
            with (plan_dir / "delivery_plan.json").open('r', encoding='utf-8') as f:
                context['delivery_plan'] = json.load(f)
            
            # 加载检索结果
            with (plan_dir / "search_results.json").open('r', encoding='utf-8') as f:
                context['search_results'] = json.load(f)
            
            # 加载推理过程
            with (plan_dir / "reasoning_process.md").open('r', encoding='utf-8') as f:
                context['reasoning_process'] = f.read()
                
            return context
        except Exception as e:
            self.logger.error(f"加载上下文信息失败: {str(e)}")
            raise
    
    async def _generate_markdown_content(self, 
                                      file_config: Dict, 
                                      context: Dict) -> str:
        """生成Markdown格式的内容"""
        messages = [
            {
                "role": "system",
                "content": """你是一个专业的技术文档撰写专家。请根据提供的上下文信息，
                生成一份结构清晰、重点突出的Markdown格式文档。要求：
                1. 使用标准Markdown语法
                2. 合理使用标题层级
                3. 适当添加表格、列表等元素
                4. 突出重要内容
                5. 保持专业性和可读性"""
            },
            {
                "role": "user",
                "content": f"""
                请根据以下信息生成文档内容：
                
                文档主题：{file_config['topic']}
                文档用途：{file_config['description']}
                
                内容结构：
                {json.dumps(file_config['content_structure'], ensure_ascii=False, indent=2)}
                
                上下文数据：
                1. 检索结果统计：
                - 结构化数据：{len(context['search_results'].get('structured_results', []))}条
                - 向量数据：{len(context['search_results'].get('vector_results', []))}条
                
                2. 数据示例：
                {json.dumps([x.get('data', '') for x in context['search_results'].get('structured_results', [])[:3]], ensure_ascii=False, indent=2)}
                
                请生成完整的Markdown文档内容。
                """
            }
        ]
        
        response = await self.model_manager.generate_reasoned_response(messages=messages)
        if response and response.choices:
            return response.choices[0].message.content
        return ""
    
    async def _generate_html_content(self,
                                   file_config: Dict,
                                   context: Dict) -> str:
        """生成HTML格式的内容"""
        messages = [
            {
                "role": "system",
                "content": """你是一个专业的Web内容开发专家。请根据提供的上下文信息，
                生成一份美观、交互性好的HTML文档。要求：
                1. 使用现代HTML5语法
                2. 包含基础的CSS样式
                3. 适当添加图表和交互元素
                4. 确保响应式布局
                5. 保持专业性和可用性
                
                请使用markdown代码块包裹HTML代码，如：
                ```html
                <!DOCTYPE html>
                <html>
                ...
                </html>
                ```
                """
            },
            {
                "role": "user",
                "content": f"""
                请根据以下信息生成HTML内容：
                
                页面主题：{file_config['topic']}
                页面用途：{file_config['description']}
                
                内容结构：
                {json.dumps(file_config['content_structure'], ensure_ascii=False, indent=2)}
                
                上下文数据：
                1. 检索结果统计：
                - 结构化数据：{len(context['search_results'].get('structured_results', []))}条
                - 向量数据：{len(context['search_results'].get('vector_results', []))}条
                
                2. 数据示例：
                {json.dumps([x.get('data', '') for x in context['search_results'].get('structured_results', [])[:3]], ensure_ascii=False, indent=2)}
                
                请生成完整的HTML文档内容，包含必要的CSS样式。
                注意：请将HTML代码放在markdown代码块中。
                """
            }
        ]
        
        response = await self.model_manager.generate_reasoned_response(messages=messages)
        if response and response.choices:
            content = response.choices[0].message.content
            
            # 使用正则表达式提取HTML代码
            import re
            # 匹配```html和```之间的内容
            html_pattern = r'```html\n([\s\S]*?)\n```'
            html_match = re.search(html_pattern, content)
            
            if html_match:
                html_content = html_match.group(1).strip()
                # 验证HTML内容的基本结构
                if ('<!DOCTYPE html>' in html_content and 
                    '<html' in html_content and 
                    '</html>' in html_content):
                    return html_content
                else:
                    self.logger.warning("提取的HTML内容结构不完整")
                    return self._generate_error_html(
                        "生成的HTML内容结构不完整",
                        file_config['topic']
                    )
            else:
                # 尝试直接查找HTML标记
                if ('<!DOCTYPE html>' in content and 
                    '<html' in content and 
                    '</html>' in content):
                    # 提取完整的HTML文档
                    start_idx = content.find('<!DOCTYPE html>')
                    end_idx = content.find('</html>') + 7
                    return content[start_idx:end_idx]
                else:
                    self.logger.warning("未找到有效的HTML内容")
                    return self._generate_error_html(
                        "未能生成有效的HTML内容",
                        file_config['topic']
                    )
        return self._generate_error_html(
            "生成HTML内容失败",
            file_config['topic']
        )

    def _generate_error_html(self, error_message: str, title: str) -> str:
        """生成错误提示页面"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - 生成失败</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 40px auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .error-container {{
            background: white;
            border-left: 5px solid #dc3545;
            padding: 20px;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #dc3545;
            margin-top: 0;
        }}
    </style>
</head>
<body>
    <div class="error-container">
        <h1>内容生成失败</h1>
        <p>{error_message}</p>
        <p>请检查生成日志获取详细信息。</p>
    </div>
</body>
</html>"""
    
    def _generate_csv_content(self,
                            file_config: Dict,
                            context: Dict) -> pd.DataFrame:
        """生成CSV格式的内容"""
        try:
            # 从检索结果中提取结构化数据
            structured_data = context['search_results'].get('structured_results', [])
            
            # 转换为DataFrame，确保正确解析JSON中的中文
            rows = []
            for item in structured_data:
                try:
                    if isinstance(item['data'], str):
                        # 确保字符串格式的JSON数据被正确解析
                        data = json.loads(item['data'])
                    else:
                        # 如果已经是字典格式，直接使用
                        data = item['data']
                    rows.append(data)
                except Exception as e:
                    self.logger.warning(f"解析数据行时出错: {str(e)}")
                    continue
            
            df = pd.DataFrame(rows)
            
            # 根据content_structure进行数据处理
            sections = file_config['content_structure']['sections']
            if sections:
                # 选择指定的列
                if 'columns' in sections[0]:
                    df = df[sections[0]['columns']]
                
                # 排序
                if 'sort_by' in sections[0]:
                    df = df.sort_values(by=sections[0]['sort_by'])
                    
                # 过滤
                if 'filters' in sections[0]:
                    for filter_rule in sections[0]['filters']:
                        if 'column' in filter_rule and 'condition' in filter_rule:
                            df = df[df[filter_rule['column']].apply(
                                lambda x: eval(f"x {filter_rule['condition']}")
                            )]
            
            return df
        except Exception as e:
            self.logger.error(f"生成CSV内容时发生错误: {str(e)}")
            return pd.DataFrame()
    
    async def generate_deliverables(self, 
                                  plan_id: str,
                                  search_results: Dict,
                                  delivery_config: Dict = None,
                                  output_dir: str = None) -> List[str]:
        """生成交付文件
        
        Args:
            plan_id: 交付计划ID
            search_results: 搜索结果
            delivery_config: 交付配置
            output_dir: 输出目录，如果为None则使用plan_id目录
            
        Returns:
            List[str]: 生成的文件路径列表
        """
        try:
            # 如果没有指定output_dir，则使用plan_id目录
            if output_dir is None:
                plan_path = Path(plan_id)
            else:
                plan_path = Path(output_dir) / plan_id
                
            if not plan_path.exists():
                raise ValueError(f"交付计划目录不存在: {plan_id}")
            
            # 加载上下文
            context = self._load_context(plan_path)
            
            # 如果提供了delivery_config，更新上下文中的配置
            if delivery_config:
                context['delivery_plan']['delivery_config'] = delivery_config
            
            # 创建输出目录
            output_dir = plan_path / "deliverables"
            output_dir.mkdir(exist_ok=True)
            
            generated_files = []
            
            # 获取交付文件配置
            delivery_files = context['delivery_plan'].get('delivery_files', {})
            
            # 生成每个交付文件
            for purpose, file_config in delivery_files.items():
                file_name = file_config['file_name']
                file_path = output_dir / file_name
                
                try:
                    if file_name.endswith('.md'):
                        content = await self._generate_markdown_content(file_config, context)
                        file_path.write_text(content, encoding='utf-8')
                        
                    elif file_name.endswith('.html'):
                        content = await self._generate_html_content(file_config, context)
                        file_path.write_text(content, encoding='utf-8')
                        
                    elif file_name.endswith('.csv'):
                        df = self._generate_csv_content(file_config, context)
                        df.to_csv(file_path, index=False, encoding='utf-8-sig')
                    
                    generated_files.append(str(file_path))
                    self.logger.info(f"已生成文件: {file_path}")
                    
                except Exception as e:
                    self.logger.error(f"生成文件 {file_name} 时发生错误: {str(e)}")
                    continue
            
            # 生成README文件
            readme_path = output_dir / "README.md"
            with readme_path.open('w', encoding='utf-8') as f:
                f.write("# 交付文件说明\n\n")
                f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("## 文件列表\n\n")
                for file_path in generated_files:
                    file_name = Path(file_path).name
                    purpose = next((k for k, v in delivery_files.items() 
                                 if v['file_name'] == file_name), "未知用途")
                    f.write(f"- {file_name}\n")
                    f.write(f"  - 用途：{purpose}\n")
                    f.write(f"  - 说明：{delivery_files[purpose]['description']}\n\n")
            
            generated_files.append(str(readme_path))
            
            return generated_files
            
        except Exception as e:
            self.logger.error(f"生成交付文件时发生错误: {str(e)}")
            raise 