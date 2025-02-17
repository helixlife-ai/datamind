import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime
import re
from ..core.reasoning import ReasoningEngine
import asyncio
from io import StringIO

class DeliveryGenerator:
    """交付文件生成器"""
    
    def __init__(self, reasoning_engine: Optional[ReasoningEngine] = None, logger: Optional[logging.Logger] = None):
        """初始化交付文件生成器
        
        Args:
            reasoning_engine: 推理引擎实例，用于生成内容
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.reasoning_engine = reasoning_engine
        
        if not self.reasoning_engine:
            self.logger.warning("未提供推理引擎实例，部分功能可能受限")
        
    
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

            return context
        except Exception as e:
            self.logger.error(f"加载上下文信息失败: {str(e)}")
            raise
    
    def _read_file_content(self, file_path: str, encoding: str = 'utf-8') -> Optional[str]:
        """读取文件内容
        
        Args:
            file_path: 文件路径
            encoding: 文件编码，默认utf-8
            
        Returns:
            Optional[str]: 文件内容，如果读取失败返回None
        """
        try:
            path = Path(file_path)
            if not path.exists():
                self.logger.warning(f"文件不存在: {file_path}")
                return None
            
            with path.open('r', encoding=encoding) as f:
                content = f.read()
            
            self.logger.debug(f"成功读取文件: {file_path}")
            return content
        
        except Exception as e:
            self.logger.error(f"读取文件 {file_path} 时发生错误: {str(e)}")
            return None
    
    async def _generate_markdown_content(self, 
                                      file_config: Dict, 
                                      context: Dict) -> str:
        """生成Markdown格式的内容"""
        if not self.reasoning_engine:
            raise ValueError("未配置推理引擎，无法生成内容")
            
        # 添加用户消息
        self.reasoning_engine.add_message("user", f"""
            请根据上下文和以下信息写一篇文章。
            - 主题：{file_config['topic']}
            - 用途：{file_config['description']}            
            - 结构：
            {json.dumps(file_config['content_structure'], ensure_ascii=False, indent=2)}
            - 要求：
            1. 要符合上下文里的信息，不要编造内容
            2. 要符合主题和用途
            3. 要符合结构
            4. 说人话
        """)
        
        response = await self.reasoning_engine.get_response(
            temperature=0.7,
            metadata={'stage': 'markdown_generation'}
        )
        return response if response else ""
    
    async def _generate_html_content(self,
                                   file_config: Dict,
                                   context: Dict) -> str:
        """生成HTML格式的内容"""
        if not self.reasoning_engine:
            raise ValueError("未配置推理引擎，无法生成内容")
            
        # 添加用户消息
        self.reasoning_engine.add_message("user", f"""
            请根据上下文和以下信息生成HTML内容：            
            - 页面主题：{file_config['topic']}
            - 页面用途：{file_config['description']}            
            - 内容结构：
            {json.dumps(file_config['content_structure'], ensure_ascii=False, indent=2)}             
            - 要求：
            1. 请生成完整的HTML文档内容，包含必要的CSS样式。
            2. 注意：请将HTML代码放在markdown代码块中。
        """)
        
        response = await self.reasoning_engine.get_response(
            temperature=0.7,
            metadata={'stage': 'html_generation'}
        )
        
        if response:
            # 使用正则表达式提取HTML代码
            html_pattern = r'```html\n([\s\S]*?)\n```'
            html_match = re.search(html_pattern, response)
            
            if html_match:
                html_content = html_match.group(1).strip()
                if ('<!DOCTYPE html>' in html_content and 
                    '<html' in html_content and 
                    '</html>' in html_content):
                    return html_content
                
            # 尝试直接查找HTML标记
            if ('<!DOCTYPE html>' in response and 
                '<html' in response and 
                '</html>' in response):
                start_idx = response.find('<!DOCTYPE html>')
                end_idx = response.find('</html>') + 7
                return response[start_idx:end_idx]
                
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
        """生成CSV格式的内容"""
        if not self.reasoning_engine:
            raise ValueError("未配置推理引擎，无法生成内容")
            
        try:
            # 添加用户消息
            self.reasoning_engine.add_message("user", f"""
                根据上下文和以下信息生成CSV数据：
                - 主题：{file_config['topic']}
                - 用途：{file_config['description']}
                - 数据结构要求：
                {json.dumps(file_config['content_structure'], ensure_ascii=False, indent=2)}
                
                - 要求：
                1. 请生成CSV格式的数据，并用```csv代码块包裹。
                2. 请确保数据结构符合要求。
                3. 请确保数据内容符合主题和用途。
            """)
            
            response = await self.reasoning_engine.get_response(
                temperature=0.7,
                metadata={'stage': 'csv_generation'}
            )
            
            if response:
                # 提取CSV内容
                csv_pattern = r'```csv\n([\s\S]*?)\n```'
                csv_match = re.search(csv_pattern, response)
                if csv_match:
                    csv_data = csv_match.group(1).strip()
                    return pd.read_csv(StringIO(csv_data))
                
                # 直接尝试解析为CSV
                if any([',' in line for line in response.split('\n')[:3]]):
                    return pd.read_csv(StringIO(response))
            
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

            # 加载源文件总结
            context['source_files_summaries'] = await self._summarize_source_files(context['search_results'])

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

    def _extract_file_paths(self, search_results: Dict) -> List[str]:
        """从搜索结果中提取所有不重复的文件路径
        
        Args:
            search_results: 搜索结果字典
            
        Returns:
            List[str]: 不重复的文件路径列表
        """
        try:
            file_paths = set()
            
            # 从结构化结果中提取
            structured_results = search_results.get('structured_results', [])
            for result in structured_results:
                if '_file_path' in result:
                    file_paths.add(result['_file_path'])
                    
            # 从向量结果中提取
            vector_results = search_results.get('vector_results', [])
            for result in vector_results:
                if 'file_path' in result:  # 注意向量结果中是file_path而不是_file_path
                    file_paths.add(result['file_path'])
            
            self.logger.debug(f"从搜索结果中提取了 {len(file_paths)} 个不重复文件路径")
            return list(file_paths)
            
        except Exception as e:
            self.logger.error(f"提取文件路径时发生错误: {str(e)}")
            return [] 

    async def _summarize_source_files(self, search_results: Dict) -> Optional[Dict[str, str]]:
        """读取并总结所有源文件的内容，每个文件单独总结
        
        Args:
            search_results: 搜索结果字典
            
        Returns:
            Optional[Dict[str, str]]: 文件名到总结内容的映射，如果处理失败返回None
        """
        try:
            if not self.reasoning_engine:
                self.logger.warning("未配置推理引擎，无法生成内容总结")
                return None
            
            # 获取所有文件路径
            file_paths = self._extract_file_paths(search_results)
            if not file_paths:
                self.logger.warning("未找到需要处理的源文件")
                return None
            
            # 存储每个文件的总结
            summaries = {}
            
            # 对每个文件单独处理
            for file_path in file_paths:
                content = self._read_file_content(file_path)
                if not content:
                    continue
                    
                file_name = Path(file_path).name
                
                # 构建针对单个文件的提示信息
                self.reasoning_engine.add_message("user", f"""
                    [file name]: {file_name}
                    [file content begin]
                    {content}
                    [file content end]
                    请对文件内容进行分析和总结：                    
                    请提供：
                    1. 文件的主要内容和目的
                    2. 核心概念和关键信息
                    3. 重要发现和结论
                    4. 与其他文件可能的关联点
                """)
                
                # 获取单个文件的总结响应
                summary = await self.reasoning_engine.get_response(
                    temperature=0.7,
                    metadata={'stage': 'single_file_summarization'}
                )
                
                if summary:
                    summaries[file_name] = summary
                    self.logger.info(f"成功生成文件 {file_name} 的内容总结")
                else:
                    self.logger.warning(f"生成文件 {file_name} 的总结失败")
            
            if not summaries:
                self.logger.warning("未能成功生成任何文件的总结")
                return None
            
            # 生成文件关联性分析
            if len(summaries) > 1:
                self.reasoning_engine.add_message("user", f"""
                    请分析以下文件总结之间的关联性：
                    
                    {json.dumps({
                        file_name: summary[:500] + "..." if len(summary) > 500 else summary
                        for file_name, summary in summaries.items()
                    }, ensure_ascii=False, indent=2)}
                    
                    请提供：
                    1. 文件之间的关联性和互补性
                    2. 信息的一致性和差异性
                    3. 综合见解和建议
                """)
                
                correlation = await self.reasoning_engine.get_response(
                    temperature=0.7,
                    metadata={'stage': 'correlation_analysis'}
                )
                
                if correlation:
                    summaries['_correlation_analysis'] = correlation
                    self.logger.info("成功生成文件关联性分析")
            
            return summaries
            
        except Exception as e:
            self.logger.error(f"总结文件内容时发生错误: {str(e)}")
            return None 