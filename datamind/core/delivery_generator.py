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
from io import StringIO

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
                "content": """
                <rule>
                1. 文章内容要符合用户的需求
                2. 文章内容要基于检索结果里的内容
                3. 说人话
                </rule>
                """
            },
            {
                "role": "user",
                "content": f"""
                请根据以下信息写一篇文章：
                
                主题：{file_config['topic']}
                用途：{file_config['description']}
                
                结构：
                {json.dumps(file_config['content_structure'], ensure_ascii=False, indent=2)}
                
                上下文：
                1. 检索结果统计：
                - 结构化数据：{len(context['search_results'].get('structured_results', []))}条
                - 向量数据：{len(context['search_results'].get('vector_results', []))}条
                
                2. 数据：
                {json.dumps([x.get('data', '') for x in context['search_results'].get('structured_results', [])[:3]], ensure_ascii=False, indent=2)}
                
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
                "content": """根据提供的上下文信息，
                生成一份美观、交互性好的HTML。要求：
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
                
                上下文：
                1. 检索结果统计：
                - 结构化数据：{len(context['search_results'].get('structured_results', []))}条
                - 向量数据：{len(context['search_results'].get('vector_results', []))}条
                
                2. 数据：
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
    
    async def _generate_csv_content(self,
                                  file_config: Dict,
                                  context: Dict) -> pd.DataFrame:
        """生成CSV格式的内容（通过模型生成）"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": """请根据上下文生成结构化CSV数据，要求：
1. 生成真实有效的数据，符合行业标准
2. 包含至少5列有意义的中文列名
3. 数据量在20-50行之间
4. 确保数据类型合理（数值、日期、分类等）
5. 包含必要的空值模拟真实数据
6. 输出时使用CSV格式并用```csv代码块包裹
"""
                },
                {
                    "role": "user",
                    "content": f"""
生成CSV数据要求：
主题：{file_config['topic']}
用途：{file_config['description']}

数据结构要求：
{json.dumps(file_config['content_structure'], ensure_ascii=False, indent=2)}

上下文数据：
{json.dumps([x.get('data', '') for x in context['search_results'].get('structured_results', [])[:3]], ensure_ascii=False, indent=2)}
"""
                }
            ]
            
            response = await self.model_manager.generate_reasoned_response(messages=messages)
            if response and response.choices:
                content = response.choices[0].message.content
                
                # 提取CSV内容
                csv_pattern = r'```csv\n([\s\S]*?)\n```'
                csv_match = re.search(csv_pattern, content)
                if csv_match:
                    csv_data = csv_match.group(1).strip()
                    return pd.read_csv(StringIO(csv_data))
                
                # 直接尝试解析为CSV
                if any([',' in line for line in content.split('\n')[:3]]):
                    return pd.read_csv(StringIO(content))
                
                self.logger.warning("未找到有效的CSV内容")
                return pd.DataFrame()

            return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"生成CSV内容时发生错误: {str(e)}")
            return pd.DataFrame()
    
    async def _generate_docx_content(self,
                                   file_config: Dict,
                                   context: Dict) -> bytes:
        """生成DOCX格式的内容（基于Markdown内容转换）"""
        try:
            # 先获取Markdown内容
            md_content = await self._generate_markdown_content(file_config, context)
            
            # 创建Word文档
            from docx import Document
            from docx.shared import Pt, Inches
            from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
            
            doc = Document()
            
            # 设置基本样式
            doc.styles['Normal'].font.name = '微软雅黑'
            doc.styles['Normal'].font.size = Pt(11)
            
            # 添加标题
            title = doc.add_heading(file_config['topic'], level=0)
            title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            
            # 添加分隔线
            doc.add_paragraph().add_run('').add_break()
            
            # 解析Markdown内容
            current_list = []
            in_code_block = False
            
            for line in md_content.split('\n'):
                line = line.strip()
                
                # 跳过空行
                if not line:
                    doc.add_paragraph()
                    continue
                    
                # 处理代码块
                if line.startswith('```'):
                    in_code_block = not in_code_block
                    if in_code_block:
                        p = doc.add_paragraph()
                        p.style = 'Normal'
                        continue
                    else:
                        doc.add_paragraph()
                        continue
                
                if in_code_block:
                    p = doc.add_paragraph(line)
                    p.style = 'Normal'
                    continue
                
                # 处理标题
                if line.startswith('#'):
                    level = len(line.split()[0])  # 计算#的数量
                    text = line.lstrip('#').strip()
                    doc.add_heading(text, level=min(level, 9))
                    continue
                
                # 处理列表
                if line.startswith('- ') or line.startswith('* '):
                    text = line[2:].strip()
                    p = doc.add_paragraph(text)
                    p.style = 'List Bullet'
                    continue
                
                if line.startswith('1. ') or re.match(r'^\d+\. ', line):
                    text = line.split('. ', 1)[1].strip()
                    p = doc.add_paragraph(text)
                    p.style = 'List Number'
                    continue
                
                # 处理加粗文本
                if '**' in line:
                    p = doc.add_paragraph()
                    parts = line.split('**')
                    for i, part in enumerate(parts):
                        run = p.add_run(part)
                        if i % 2 == 1:  # 奇数索引表示加粗部分
                            run.bold = True
                    continue
                
                # 处理普通段落
                p = doc.add_paragraph(line)
                p.style = 'Normal'
            
            # 保存到字节流
            from io import BytesIO
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            return buffer.read()
            
        except Exception as e:
            self.logger.error(f"生成DOCX内容时发生错误: {str(e)}")
            return b''
    
    async def generate_deliverables(self, 
                                  plan_id: str,
                                  delivery_config: Dict = None,
                                  output_dir: str = None,
                                  test_mode: bool = False) -> List[str]:
        """生成交付文件
        
        Args:
            plan_id: 交付计划ID
            delivery_config: 交付配置
            output_dir: 输出目录，如果为None则使用plan_id目录
            test_mode: 测试模式（生成占位文件）
            
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
            output_dir = plan_path / "delivery_results"
            output_dir.mkdir(exist_ok=True)
            
            generated_files = []
            
            # 获取交付文件配置
            delivery_files = context['delivery_plan'].get('delivery_files', {})
            
            # 生成每个交付文件
            for purpose, file_config in delivery_files.items():
                file_name = file_config['file_name']
                file_path = output_dir / file_name
                
                try:
                    if test_mode:  # 测试模式生成占位文件
                        if file_name.endswith('.md'):
                            file_path.write_text("# 测试文件\n这是测试模式生成的占位文件", encoding='utf-8')
                        elif file_name.endswith('.html'):
                            file_path.write_text("<html><body><h1>测试文件</h1></body></html>", encoding='utf-8')
                        elif file_name.endswith('.csv'):
                            pd.DataFrame({'测试列': [1,2,3]}).to_csv(file_path, index=False)
                        elif file_name.endswith('.docx'):
                            from docx import Document
                            doc = Document()
                            doc.add_heading('测试文档', 0)
                            doc.save(file_path)
                        generated_files.append(str(file_path))
                        continue
                    
                    if file_name.endswith('.md'):
                        content = await self._generate_markdown_content(file_config, context)
                        file_path.write_text(content, encoding='utf-8')
                        generated_files.append(str(file_path))
                        
                        # 同时生成对应的docx文件
                        docx_file_name = file_name.replace('.md', '.docx')
                        docx_file_path = output_dir / docx_file_name
                        docx_content = await self._generate_docx_content(file_config, context)
                        docx_file_path.write_bytes(docx_content)
                        generated_files.append(str(docx_file_path))
                        self.logger.info(f"已生成Markdown对应的Word文件: {docx_file_path}")
                        
                    elif file_name.endswith('.html'):
                        content = await self._generate_html_content(file_config, context)
                        file_path.write_text(content, encoding='utf-8')
                        
                    elif file_name.endswith('.csv'):
                        df = await self._generate_csv_content(file_config, context)
                        df.to_csv(file_path, index=False, encoding='utf-8-sig')
                    
                    elif file_name.endswith('.docx'):
                        content = await self._generate_docx_content(file_config, context)
                        file_path.write_bytes(content)
                    
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
                    # 查找文件用途，如果找不到则使用默认描述
                    purpose = next((k for k, v in delivery_files.items() 
                                 if v['file_name'] == file_name), None)
                    f.write(f"- {file_name}\n")
                    if purpose and purpose in delivery_files:
                        f.write(f"  - 用途：{purpose}\n")
                        f.write(f"  - 说明：{delivery_files[purpose]['description']}\n\n")
                    else:
                        f.write("  - 用途：自动生成的补充文件\n")
                        f.write("  - 说明：根据主文件自动生成的配套文件\n\n")
            
            generated_files.append(str(readme_path))
            
            return generated_files
            
        except Exception as e:
            self.logger.error(f"生成交付文件时发生错误: {str(e)}")
            raise 