import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import traceback
from ..utils.stream_logger import StreamLineHandler
from ..core.reasoningLLM import ReasoningLLMEngine
from ..llms.model_manager import ModelManager, ModelConfig
from ..config.settings import (
    DEFAULT_REASONING_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE
)
import shutil
import hashlib
import re
from bs4 import BeautifulSoup
import sys

class ArtifactGenerator:
    """制品生成器，用于根据上下文文件生成HTML格式的制品"""
    
    def __init__(self, alchemy_dir: str = None, logger: Optional[logging.Logger] = None):
        """初始化制品生成器
        
        Args:
            alchemy_dir: 炼丹目录
            model_manager: 模型管理器实例，用于创建推理引擎
            logger: 可选，日志记录器实例
        """
        if alchemy_dir is None:
            raise ValueError("炼丹目录不能为空")
        self.alchemy_dir = Path(alchemy_dir)
        
        # 从炼丹目录路径中提取炼丹ID
        try:
            self.alchemy_id = self.alchemy_dir.name.split('alchemy_')[-1]
        except Exception as e:
            raise ValueError("无法从炼丹目录路径中提取炼丹ID") from e
        
        # 修改目录结构，与alchemy_service.py保持一致
        self.artifacts_base = self.alchemy_dir / "artifacts"  # 基础制品目录
        
        # 每个制品的目录结构
        self.artifacts_dir = self.artifacts_base 
        self.iterations_dir = self.artifacts_dir / "iterations"  # 存放迭代版本
        
        # 创建所需目录
        for dir_path in [self.artifacts_base, self.artifacts_dir, self.iterations_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # 设置日志记录器
        self.logger = logger
        
        # 创建推理引擎实例
        self.reasoning_engine = self._setup_reasoning_engine()
        self.logger.info(f"已创建推理引擎实例，使用默认推理模型")    


    def _setup_reasoning_engine(self):
        """初始化推理引擎"""
        model_manager = ModelManager()
        model_manager.register_model(ModelConfig(
            name=DEFAULT_REASONING_MODEL,
            model_type="api",
            api_base=DEFAULT_LLM_API_BASE,
            api_key=DEFAULT_LLM_API_KEY
        ))
        return ReasoningLLMEngine(model_manager, model_name=DEFAULT_REASONING_MODEL)

    def print_stream(self,text):
        print(f"\r{text}", end='', flush=True)

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
            
            self.logger.info(f"成功读取文件: {file_path}")
            return content
        
        except Exception as e:
            self.logger.error(f"读取文件 {file_path} 时发生错误: {str(e)}")
            return None

    def _generate_error_html(self, error_message: str, title: str) -> str:
        """生成错误提示页面
        
        Args:
            error_message: 错误信息
            title: 页面标题
            
        Returns:
            str: 错误页面HTML内容
        """
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

    def _extract_html_content(self, full_response: str) -> Optional[str]:
        """从响应中提取HTML内容
        
        Args:
            full_response: 完整的响应文本
            
        Returns:
            Optional[str]: 提取的HTML内容，如果提取失败返回None
        """
        try:
            # 如果响应为空，直接返回None
            if not full_response or not full_response.strip():
                return None
                
            # 1. 如果响应本身就是完整的HTML
            if full_response.strip().startswith('<!DOCTYPE html>') or full_response.strip().startswith('<html'):
                return full_response.strip()
            
            # 2. 尝试提取html代码块
            html_markers = ["```html", "```HTML", "```"]
            start_marker = None
            
            for marker in html_markers:
                if marker in full_response:
                    start_marker = marker
                    break
            
            if start_marker:
                start_idx = full_response.find(start_marker) + len(start_marker)
                remaining_text = full_response[start_idx:]
                
                # 查找结束标记
                end_marker = "```"
                if end_marker in remaining_text:
                    end_idx = remaining_text.find(end_marker)
                    html_content = remaining_text[:end_idx].strip()
                    
                    # 移除开头的换行符
                    if html_content.startswith('\n'):
                        html_content = html_content[1:]
                        
                    if html_content and (html_content.startswith('<!DOCTYPE html>') or html_content.startswith('<html')):
                        return html_content
                    elif html_content:
                        # 如果内容不是以<!DOCTYPE html>或<html>开头，但包含有效的HTML标签
                        if re.search(r'<(?!!)([a-z]+)[^>]*>.*?</\1>', html_content, re.DOTALL):
                            # 不是完整的HTML文档，但包含有效标签，可能需要包装
                            if not html_content.startswith('<'):
                                # 移除开头的非HTML内容
                                first_tag_idx = re.search(r'<(?!!)([a-z]+)[^>]*>', html_content)
                                if first_tag_idx:
                                    html_content = html_content[first_tag_idx.start():]
                            return html_content
            
            # 3. 尝试从多个代码块中提取HTML
            code_blocks = re.findall(r'```(?:html|HTML)?\s*(.*?)```', full_response, re.DOTALL)
            for block in code_blocks:
                block = block.strip()
                if block.startswith('<!DOCTYPE html>') or block.startswith('<html'):
                    return block
                elif re.search(r'<(?!!)([a-z]+)[^>]*>.*?</\1>', block, re.DOTALL):
                    # 包含有效HTML标签的代码块
                    if not block.startswith('<'):
                        # 移除开头的非HTML内容
                        first_tag_idx = re.search(r'<(?!!)([a-z]+)[^>]*>', block)
                        if first_tag_idx:
                            block = block[first_tag_idx.start():]
                    return block
            
            # 4. 如果响应包含HTML基本结构但没有代码块标记
            if '<html' in full_response and '</html>' in full_response:
                start_idx = full_response.find('<html')
                end_idx = full_response.find('</html>') + 7
                return full_response[start_idx:end_idx].strip()
            
            # 5. 尝试从任意位置提取HTML文档片段
            if '<!DOCTYPE html>' in full_response:
                start_idx = full_response.find('<!DOCTYPE html>')
                # 查找最后一个</html>标签
                end_html_matches = list(re.finditer(r'</html>', full_response))
                if end_html_matches:
                    end_idx = end_html_matches[-1].end()
                    return full_response[start_idx:end_idx].strip()
            
            # 6. 尝试提取任何具有HTML结构的内容
            html_fragment_pattern = r'<(?!!)([a-z]+)[^>]*>.*?</\1>'
            html_fragments = re.findall(html_fragment_pattern, full_response, re.DOTALL)
            
            if html_fragments:
                # 找到最长的HTML片段
                longest_fragment = ''
                for match in re.finditer(html_fragment_pattern, full_response, re.DOTALL):
                    fragment = match.group(0)
                    if len(fragment) > len(longest_fragment):
                        longest_fragment = fragment
                
                if longest_fragment:
                    return longest_fragment
            
            # 7. 最后尝试从响应中提取任何包含尖括号的部分
            if '<' in full_response and '>' in full_response:
                # 找到第一个<标签
                start_idx = full_response.find('<')
                # 找到最后一个>标签
                last_close_bracket = full_response.rfind('>')
                
                if start_idx < last_close_bracket:
                    potential_html = full_response[start_idx:last_close_bracket+1].strip()
                    # 验证是否包含成对的标签
                    if re.search(r'<([a-z]+)[^>]*>.*?</\1>', potential_html, re.DOTALL):
                        return potential_html
            
            return None
        
        except Exception as e:
            self.logger.error(f"提取HTML内容时发生错误: {str(e)}")
            return None

    def _get_next_iteration(self) -> int:
        """获取下一个迭代版本号"""
        if not self.iterations_dir.exists():
            return 1
            
        existing_iterations = [int(v.name.split('iter')[-1]) 
                             for v in self.iterations_dir.glob("iter*") 
                             if v.name.startswith('iter')]
        return max(existing_iterations, default=0) + 1

    async def _get_optimization_query(self, html_content: str) -> Optional[str]:
        """分析当前HTML内容并生成优化建议查询
        
        Args:
            html_content: 当前生成的HTML内容
            
        Returns:
            Optional[str]: 优化建议查询
        """
        try:
            # 从status.json中读取原始查询和组件信息
            original_query = ""
            components = []
            status_path = self.artifacts_dir / "status.json"
            
            if status_path.exists():
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        status_info = json.load(f)
                    original_query = status_info.get("original_query", "")
                    components = status_info.get("components", [])
                    self.logger.info(f"从status.json中读取到原始查询: {original_query}")
                    self.logger.info(f"从status.json中读取到{len(components)}个组件信息")
                except Exception as e:
                    self.logger.error(f"读取status.json时发生错误: {str(e)}")
            
            # 如果无法从status.json获取原始查询，尝试从最早的迭代记录中获取
            if not original_query and status_path.exists():
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        status_info = json.load(f)
                    if status_info.get("iterations") and len(status_info["iterations"]) > 0:
                        # 获取第一次迭代的查询作为原始查询
                        original_query = status_info["iterations"][0].get("query", "")
                        self.logger.info(f"从第一次迭代记录中读取到原始查询: {original_query}")
                except Exception as e:
                    self.logger.error(f"从迭代记录中读取原始查询时发生错误: {str(e)}")
            
            if not original_query:
                self.logger.warning("无法获取原始查询，将使用空字符串")
            
            # 获取下一个组件编号
            try:
                next_component_number = self._get_next_component_id()
            except Exception as e:
                # 如果获取失败，使用组件列表长度+1作为下一个编号
                self.logger.warning(f"获取下一个组件编号失败: {str(e)}，将使用组件列表长度+1")
                next_component_number = len(components) + 1
            
            # 构建组件信息文本，确保组件是可序列化的基本类型
            components_text = ""
            for i, component in enumerate(components):
                # 确保使用的是基本类型，不是自定义对象
                if isinstance(component, dict):
                    title = component.get('title', '未知')
                    description = component.get('description', '无描述')
                    comp_id = component.get('id', '未知')
                    # 使用组件编号，如果没有则使用索引+1
                    comp_num = component.get('component_number', i+1)  
                    components_text += f"""
组件 {comp_num}:
- 标题: {title}
- 描述: {description}
- ID: {comp_id}
"""
            
            # 确定当前迭代次数
            iteration = self._get_next_iteration() - 1
            
            # 根据迭代次数调整提示词
            if iteration == 1:
                # 构建类似于原来的提示词，但保持简单并加入组件编号信息
                prompt = f"""请分析以下HTML框架和原始查询，提出一个进阶的查询语句，目的是生成在这个HTML框架中的第一个组件(组件1)。

原始查询：
{original_query}

HTML框架：
{html_content}

请思考：
1. 用户的原始查询中最重要的方面是什么？
2. 作为组件1，应该解决什么具体问题？
3. 该组件需要包含哪些关键信息或功能？

请直接输出进阶查询语句，不要包含其他解释内容。
"""
            else:
                # 后续迭代的提示词，加入下一个组件编号信息
                prompt = f"""请分析以下HTML框架、已有组件信息和原始查询，提出一个进阶的查询语句，目的是生成在这个HTML框架中的下一个组件(组件{next_component_number})。

原始查询：
{original_query}

已有组件信息：
{components_text}

HTML框架：
{html_content}

请思考：
1. 用户的原始需求中哪些方面尚未被现有组件满足？
2. 作为组件{next_component_number}，应该解决什么具体问题？
3. 该组件如何与现有组件形成互补？

请直接输出进阶查询语句，不要包含其他解释内容。
"""
            
            # 在添加新消息前清除历史对话记录
            self.reasoning_engine.clear_history()
            
            # 添加用户消息
            self.reasoning_engine.add_message("user", prompt)
            
            # 使用流式输出收集响应
            full_response = ""
            suggestion = ""
            
            async for chunk in self.reasoning_engine.get_stream_response(
                temperature=0.7,
                metadata={'stage': 'optimization_suggestion'}
            ):
                if chunk:
                    full_response += chunk
                    # 显示流式输出内容
                    #self.logger.info(f"生成优化建议: {full_response}")
                    self.print_stream(chunk)
            
            # 从full_response中提取<answer></answer>标签之间的内容
            if "<answer>" in full_response and "</answer>" in full_response:
                start_idx = full_response.find("<answer>") + len("<answer>")
                end_idx = full_response.find("</answer>")
                if start_idx < end_idx:
                    suggestion = full_response[start_idx:end_idx].strip()
                    self.logger.info(f"最终优化建议: {suggestion}")
                    return suggestion
            else:
                # 如果没有找到标签，保留原有逻辑
                suggestion = full_response.strip().strip('`').strip('"').strip()
                if suggestion:
                    self.logger.info(f"最终优化建议: {suggestion}")
                    return suggestion
                
            return None
            
        except Exception as e:
            self.logger.error(f"生成优化建议时发生错误: {str(e)}")
            return None

    async def generate_artifact(self, 
                              search_results_files: List[str], 
                              output_name: str,
                              query: str) -> Optional[Path]:
        """生成HTML制品
        
        Args:
            search_results_files: 搜索结果文件路径列表
            output_name: 输出文件名
            query: 用户的查询内容
            
        Returns:
            Optional[Path]: 生成的HTML文件路径，如果生成失败返回None
        """
        try:
            if not self.reasoning_engine:
                raise ValueError("未配置推理引擎，无法生成内容")

            # 确定生成目录
            iteration = self._get_next_iteration()
            
            # 根据迭代次数决定生成框架HTML还是组件HTML
            if iteration == 1:
                # 第一次迭代：生成框架HTML
                return await self._generate_scaffold_html(search_results_files, output_name, query, iteration)
            else:
                # 后续迭代：生成组件HTML并更新框架
                return await self._generate_component_html(search_results_files, output_name, query, iteration)
                
        except Exception as e:
            self.logger.error(f"生成HTML制品时发生错误: {str(e)}")
            
            # 错误处理和记录
            work_base = self.iterations_dir / f"iter{iteration}"
            process_dir = work_base / "process"
            output_dir = work_base / "output"
            
            # 确保目录存在
            for dir_path in [work_base, process_dir, output_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)
                
            error_info = {
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error": str(e),
                "query": query,
                "traceback": traceback.format_exc()
            }
            
            with open(process_dir / "generation_error.json", "w", encoding="utf-8") as f:
                json.dump(error_info, f, ensure_ascii=False, indent=2)
            
            error_html = self._generate_error_html(str(e), query)
            error_path = output_dir / f"{output_name}_error.html"
            error_path.write_text(error_html, encoding="utf-8")
            
            return None

    def _get_next_artifact_version(self) -> int:
        """获取artifact.html的下一个版本号"""
        artifact_versions_dir = self.artifacts_dir / "artifact_versions"
        artifact_versions_dir.mkdir(exist_ok=True)
        
        try:
            # 使用更健壮的版本号提取方法
            existing_versions = []
            for file_path in artifact_versions_dir.glob("artifact_v*.html"):
                try:
                    # 从文件名中提取版本号，格式应该是 artifact_v{number}.html
                    version_str = file_path.stem.split('v')[-1]  # 使用stem去掉.html后缀
                    if version_str.isdigit():
                        existing_versions.append(int(version_str))
                except (ValueError, IndexError):
                    self.logger.warning(f"跳过无效的版本文件名: {file_path.name}")
                    continue
            
            return max(existing_versions, default=0) + 1
            
        except Exception as e:
            self.logger.error(f"获取下一个版本号时发生错误: {str(e)}")
            return 1  # 发生错误时返回1作为安全的默认值

    def _get_next_component_id(self) -> int:
        """获取下一个组件编号（与迭代编号分离）
        
        Returns:
            int: 下一个组件编号，从1开始
        """
        components_dir = self.artifacts_dir / "components"
        if not components_dir.exists():
            components_dir.mkdir(exist_ok=True)
            return 1
            
        # 从文件名提取组件编号
        component_nums = []
        for comp_file in components_dir.glob("component_*.html"):
            try:
                # 从component_1.html, component_2.html等文件名中提取数字
                num_str = comp_file.stem.split('_')[-1]
                if num_str.isdigit():
                    component_nums.append(int(num_str))
            except (ValueError, IndexError):
                self.logger.warning(f"跳过无效的组件文件名: {comp_file.name}")
                continue
                
        # 从status.json中也提取组件编号
        status_path = self.artifacts_dir / "status.json"
        if status_path.exists():
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    status_info = json.load(f)
                for comp in status_info.get("components", []):
                    comp_id = comp.get("id", "")
                    if comp_id.startswith("component_"):
                        num_str = comp_id.split('_')[-1]
                        if num_str.isdigit():
                            component_nums.append(int(num_str))
            except Exception as e:
                self.logger.warning(f"从status.json提取组件编号时出错: {str(e)}")
                
        # 返回最大编号+1，如果没有现有组件则返回1
        return max(component_nums, default=0) + 1

    async def _generate_scaffold_html(self, 
                                search_results_files: List[str], 
                                output_name: str,
                                query: str,
                                iteration: int) -> Optional[Path]:
        """生成框架HTML（第一次迭代）
        
        Args:
            search_results_files: 搜索结果文件路径列表
            output_name: 输出文件名
            query: 用户的查询内容
            iteration: 迭代次数
            
        Returns:
            Optional[Path]: 生成的HTML文件路径，如果生成失败返回None
        """
        try:
            # 确定生成目录
            work_base = self.iterations_dir / f"iter{iteration}"
            artifact_name = f"artifact_iter{iteration}"
            
            # 创建工作目录
            process_dir = work_base / "process"    # 生成过程
            output_dir = work_base / "output"      # 最终输出
            context_dir = work_base / "context"    # 上下文文件副本
            
            for dir_path in [work_base, process_dir, output_dir, context_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)

            # 复制上下文文件并记录信息
            context_contents = {}
            context_files_info = {}
            
            for file_path in search_results_files:
                src_path = Path(file_path)
                if src_path.exists():
                    dst_path = context_dir / src_path.name
                    shutil.copy2(src_path, dst_path)
                    
                    content = self._read_file_content(file_path)
                    if content:
                        context_contents[src_path.name] = content
                        context_files_info[src_path.name] = {
                            "original_path": str(src_path.absolute()),
                            "copied_path": str(dst_path.relative_to(work_base)),
                            "size": src_path.stat().st_size,
                            "modified_time": datetime.fromtimestamp(src_path.stat().st_mtime).isoformat(),
                            "content_hash": hashlib.md5(content.encode()).hexdigest()
                        }

            if not context_contents:
                raise ValueError("未能成功读取任何上下文文件内容")

            # 更新元数据结构
            metadata_info = {
                "artifact_id": f"artifact_{self.alchemy_id}",
                "type": "scaffold",
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "output_name": output_name,
                "context_files": context_files_info,
                "generation_config": {
                    "engine": self.reasoning_engine.__class__.__name__,
                    "model": getattr(self.reasoning_engine, 'model_name', 'unknown')
                }
            }

            # 保存元数据
            with open(work_base / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata_info, f, ensure_ascii=False, indent=2)

            # 构建框架HTML提示词
            scaffold_prompt = self._build_scaffold_html_prompt(context_contents, query)
            with open(process_dir / "scaffold_prompt.md", "w", encoding="utf-8") as f:
                f.write(scaffold_prompt)

            # 在添加新消息前清除历史对话记录
            self.reasoning_engine.clear_history()
            
            # 添加用户消息
            self.reasoning_engine.add_message("user", scaffold_prompt)
            
            # 收集生成的内容
            full_response = ""
            process_path = process_dir / "generation_process.txt"
            temp_html_path = process_dir / "temp_content.html"
            current_html_content = []  # 使用列表存储HTML片段
            
            # 用于跟踪HTML内容的状态
            html_started = False
            in_html_block = False

            async for chunk in self.reasoning_engine.get_stream_response(
                temperature=0.7,
                metadata={'stage': 'scaffold_generation'}
            ):
                if chunk:
                    full_response += chunk
                    
                    # 保存生成过程
                    with process_path.open("a", encoding="utf-8") as f:
                        f.write(chunk)
                    
                    # 显示流式输出内容
                    #self.logger.info(f"\r生成框架内容: {full_response}")

                    self.print_stream(chunk)
                    
                    # 尝试实时提取和更新HTML内容
                    if not html_started:
                        if '<!DOCTYPE html>' in chunk:
                            html_started = True
                            start_idx = chunk.find('<!DOCTYPE html>')
                            current_html_content.append(chunk[start_idx:])
                        elif '```html' in chunk:
                            html_started = True
                            in_html_block = True
                            start_idx = chunk.find('```html') + 7
                            if start_idx < len(chunk):
                                current_html_content.append(chunk[start_idx:])
                    else:
                        if in_html_block and '```' in chunk:
                            # 结束代码块
                            end_idx = chunk.find('```')
                            if end_idx >= 0:
                                current_html_content.append(chunk[:end_idx])
                                in_html_block = False
                        else:
                            current_html_content.append(chunk)
                    
                    # 实时更新临时HTML文件
                    if current_html_content:
                        combined_content = ''.join(current_html_content)
                        temp_html_path.write_text(combined_content.strip(), encoding="utf-8")

            if not full_response:
                raise ValueError("生成内容为空")
            
            # 提取最终的HTML内容
            scaffold_html = self._extract_html_content(full_response)
            
            if not scaffold_html:
                self.logger.warning("无法从响应中提取有效的HTML内容，将生成错误页面")
                scaffold_html = self._generate_error_html(
                    "无法从AI响应中提取有效的HTML内容",
                    query
                )
            
            # 保存迭代版本HTML文件
            output_path = output_dir / f"{artifact_name}.html"
            output_path.write_text(scaffold_html, encoding="utf-8")

            # 创建组件目录
            components_dir = self.artifacts_dir / "components"
            components_dir.mkdir(exist_ok=True)

            # 保存框架HTML - 这是静态不变的框架，后续不会被修改
            scaffold_path = self.artifacts_dir / "scaffold.html"
            scaffold_path.write_text(scaffold_html, encoding="utf-8")
            self.logger.info(f"已保存框架HTML: {scaffold_path}")
            
            # 同时创建artifact.html作为初始版本（后续会随组件添加而更新）
            artifact_path = self.artifacts_dir / "artifact.html"
            
            # 如果artifact.html已存在，进行版本管理
            if artifact_path.exists():
                # 保存当前版本
                current_version = self._get_next_artifact_version()
                artifact_versions_dir = self.artifacts_dir / "artifact_versions"
                artifact_versions_dir.mkdir(exist_ok=True)
                version_path = artifact_versions_dir / f"artifact_v{current_version}.html"
                
                # 备份当前版本
                shutil.copy2(artifact_path, version_path)
                
                # 更新版本记录
                versions_info_path = artifact_versions_dir / "versions_info.json"
                versions_info = {
                    "latest_version": current_version,
                    "versions": []
                }
                
                if versions_info_path.exists():
                    with open(versions_info_path, "r", encoding="utf-8") as f:
                        versions_info = json.load(f)
                
                version_info = {
                    "version": current_version,
                    "timestamp": datetime.now().isoformat(),
                    "query": query,
                    "path": str(version_path.relative_to(self.artifacts_base))
                }
                
                versions_info["versions"].append(version_info)
                versions_info["latest_version"] = current_version
                
                with open(versions_info_path, "w", encoding="utf-8") as f:
                    json.dump(versions_info, f, ensure_ascii=False, indent=2)
            
            # 写入新的artifact.html（初始时与scaffold.html相同）
            artifact_path.write_text(scaffold_html, encoding="utf-8")
            self.logger.info(f"已初始化制品HTML: {artifact_path}")
            
            # 先获取优化建议
            optimization_query = await self._get_optimization_query(scaffold_html)

            # 然后更新迭代信息
            iteration_info = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "path": str(work_base.relative_to(self.artifacts_base)),
                "query": query,
                "type": "scaffold",
                "output": str(output_path.relative_to(self.artifacts_base)),
                "optimization_suggestion": optimization_query
            }
            
            # 先检查status.json是否已存在，如果存在则读取现有内容
            status_path = self.artifacts_dir / "status.json"
            if status_path.exists():
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        status_info = json.load(f)
                    # 更新必要字段，保留其他现有信息
                    status_info.update({
                        "updated_at": datetime.now().isoformat(),
                        "latest_iteration": iteration,
                    })
                    # 确保原始查询存在
                    if "original_query" not in status_info:
                        status_info["original_query"] = query
                except Exception as e:
                    self.logger.warning(f"读取现有status.json失败: {str(e)}，将创建新文件")
                    status_info = None
            
            # 如果status.json不存在或读取失败，则创建新的status_info
            if not status_path.exists() or status_info is None:
                status_info = {
                    "artifact_id": f"artifact_{self.alchemy_id}",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "latest_iteration": iteration,
                    "original_query": query,
                    # 添加artifact字段，与旧版本兼容
                    "artifact": {
                        "path": "artifact.html",
                        "timestamp": datetime.now().isoformat()
                    },
                    "scaffold": {
                        "path": "scaffold.html",
                        "timestamp": datetime.now().isoformat(),
                        "is_static": True  # 明确标记scaffold是静态的
                    },
                    "components": [],
                    "iterations": []
                }
            
            # 确保iterations字段存在
            if "iterations" not in status_info:
                status_info["iterations"] = []
            
            status_info["iterations"].append(iteration_info)
            
            with open(status_path, "w", encoding="utf-8") as f:
                json.dump(status_info, f, ensure_ascii=False, indent=2)

            # 保存本轮生成的完整信息
            generation_info = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "input_query": query,
                "output_file": str(output_path.relative_to(self.artifacts_base)),
                "optimization_suggestion": optimization_query,
                "generation_stats": {
                    "html_size": len(scaffold_html)
                }
            }
            
            with open(output_dir / "generation_info.json", "w", encoding="utf-8") as f:
                json.dump(generation_info, f, ensure_ascii=False, indent=2)

            return output_path

        except Exception as e:
            self.logger.error(f"生成框架HTML时发生错误: {str(e)}")
            traceback.print_exc()
            return None 

    def _build_scaffold_html_prompt(self, context_files: Dict[str, str], query: str) -> str:
        """构建框架HTML生成的提示词
        
        Args:
            context_files: 文件内容字典，key为文件名，value为文件内容
            query: 用户的查询内容
            
        Returns:
            str: 生成提示词
        """
        prompt = f"""[文件]
"""
        for filename, content in context_files.items():
            prompt += f"\n[file name]: {filename}\n[file content begin]\n{content}\n[file content end]\n"
        
        prompt += f"""目的是满足用户查询背后的意图。从上述文件中提炼相关信息，生成一个合适的框架型HTML页面。因为后续的迭代会不断添加组件，所以框架必须能够支持无限扩展组件的结构框架。

[用户的查询]
{query}

要求：
1. 生成一个高度可扩展的框架型HTML页面，包含以下元素：
   a. 页面标题和基本信息
   b. 动态导航区域，能随组件增加自动扩展
   c. 弹性主内容区域，能容纳无限组件（使用id标识的div容器）
   d. 组件目录或索引区域
   e. 页脚信息

2. 框架页面应该包含：
   a. 响应式布局，适应不同设备和任意数量的组件
   b. 清晰的视觉层次结构
   c. 统一的样式主题和组件样式继承系统
   d. 使用锚点链接实现简单导航功能
   e. 静态展示组件的区域划分

3. 无限扩展的组件系统：
   a. 预设多个组件容器的HTML结构
   b. 组件容器应有统一的样式类和结构
   c. 组件区域应有明确的视觉边界和一致的样式

4. CSS框架选择：
   a. 请使用知名的CSS框架如Tailwind CSS、Bootstrap或Bulma
   b. 直接通过CDN引入CSS框架
   c. 利用框架提供的组件和样式类设计界面
   d. 添加必要的自定义CSS以满足特定需求

5. 确保代码质量：
   a. 使用语义化HTML5标签
   b. 模块化CSS样式设计
   c. 代码应有详细注释
   d. 结构清晰，便于后续扩展

请生成完整的HTML代码，包括所有必要的CSS。不需要包含任何JavaScript代码。这个框架必须设计为可以无限扩展组件的系统，确保即使添加大量组件也能保持良好的性能和用户体验。
"""
        return prompt 

    async def _generate_component_html(self, 
                                 search_results_files: List[str], 
                                 output_name: str,
                                 query: str,
                                 iteration: int) -> Optional[Path]:
        """生成组件HTML（后续迭代）
        
        Args:
            search_results_files: 搜索结果文件路径列表
            output_name: 输出文件名
            query: 用户的查询内容
            iteration: 迭代次数
            
        Returns:
            Optional[Path]: 生成的HTML文件路径，如果生成失败返回None
        """
        try:
            # 确定生成目录
            work_base = self.iterations_dir / f"iter{iteration}"
            artifact_name = f"artifact_iter{iteration}"
            
            # 创建工作目录
            process_dir = work_base / "process"    # 生成过程
            output_dir = work_base / "output"      # 最终输出
            context_dir = work_base / "context"    # 上下文文件副本
            
            for dir_path in [work_base, process_dir, output_dir, context_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)

            # 复制上下文文件并记录信息
            context_contents = {}
            context_files_info = {}
            
            for file_path in search_results_files:
                src_path = Path(file_path)
                if src_path.exists():
                    dst_path = context_dir / src_path.name
                    shutil.copy2(src_path, dst_path)
                    
                    content = self._read_file_content(file_path)
                    if content:
                        context_contents[src_path.name] = content
                        context_files_info[src_path.name] = {
                            "original_path": str(src_path.absolute()),
                            "copied_path": str(dst_path.relative_to(work_base)),
                            "size": src_path.stat().st_size,
                            "modified_time": datetime.fromtimestamp(src_path.stat().st_mtime).isoformat(),
                            "content_hash": hashlib.md5(content.encode()).hexdigest()
                        }

            if not context_contents:
                raise ValueError("未能成功读取任何上下文文件内容")

            # 检查框架HTML是否存在
            scaffold_path = self.artifacts_dir / "scaffold.html"
            if not scaffold_path.exists():
                raise ValueError("框架HTML不存在，无法生成组件")
            
            # 读取框架HTML内容 (仅用于提供给组件生成提示词，不会修改)
            scaffold_html = scaffold_path.read_text(encoding="utf-8")
            
            # 读取当前artifact内容 (这个会被更新)
            artifact_path = self.artifacts_dir / "artifact.html"
            if not artifact_path.exists():
                # 如果artifact.html不存在，则以scaffold为模板创建它
                artifact_html = scaffold_html
            else:
                artifact_html = artifact_path.read_text(encoding="utf-8")
            
            # 读取状态信息，获取已有组件信息
            status_path = self.artifacts_dir / "status.json"
            if not status_path.exists():
                raise ValueError("状态信息文件不存在，无法获取组件信息")
            
            with open(status_path, "r", encoding="utf-8") as f:
                status_info = json.load(f)
            
            # 确保original_query字段存在
            if "original_query" not in status_info or not status_info["original_query"]:
                # 如果不存在或为空，使用当前查询替代
                status_info["original_query"] = query
                self.logger.info(f"在status.json中添加缺失的original_query字段: {query}")
            
            # 获取下一个组件编号（与迭代编号分离）
            try:
                component_number = self._get_next_component_id()
            except Exception as e:
                # 如果方法调用失败，使用迭代号作为备选
                self.logger.warning(f"获取组件编号失败: {str(e)}，将使用迭代号")
                component_number = iteration
                
            # 生成组件ID
            component_id = f"component_{component_number}"
            
            # 验证组件ID是否有冲突
            existing_component_ids = [comp.get("id", "") for comp in status_info.get("components", [])]
            if component_id in existing_component_ids:
                self.logger.warning(f"组件ID {component_id} 已存在，自动递增编号")
                # 确保找到一个未使用的ID
                while component_id in existing_component_ids:
                    component_number += 1
                    component_id = f"component_{component_number}"
            
            # 更新元数据结构
            metadata_info = {
                "artifact_id": f"artifact_{self.alchemy_id}",
                "type": f"component_{component_number}",
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "output_name": output_name,
                "context_files": context_files_info,
                "generation_config": {
                    "engine": self.reasoning_engine.__class__.__name__,
                    "model": getattr(self.reasoning_engine, 'model_name', 'unknown')
                }
            }

            # 保存元数据
            with open(work_base / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata_info, f, ensure_ascii=False, indent=2)

            # 构建组件HTML提示词
            component_prompt = self._build_component_html_prompt(
                context_contents, 
                query, 
                scaffold_html,
                status_info.get("components", []),
                component_id
            )
            
            with open(process_dir / "component_prompt.md", "w", encoding="utf-8") as f:
                f.write(component_prompt)

            # 在添加新消息前清除历史对话记录
            self.reasoning_engine.clear_history()
            
            # 添加用户消息
            self.reasoning_engine.add_message("user", component_prompt)
            
            # 收集生成的内容
            full_response = ""
            process_path = process_dir / "generation_process.txt"
            temp_html_path = process_dir / "temp_content.html"
            current_html_content = []  # 使用列表存储HTML片段
            
            # 用于跟踪HTML内容的状态
            html_started = False
            in_html_block = False
            
            async for chunk in self.reasoning_engine.get_stream_response(
                temperature=0.7,
                metadata={'stage': 'component_generation'}
            ):
                if chunk:
                    full_response += chunk
                    
                    # 保存生成过程
                    with process_path.open("a", encoding="utf-8") as f:
                        f.write(chunk)
                    
                    # 显示流式输出内容
                    #self.logger.info(f"\r生成组件内容: {full_response}")
                    self.print_stream(chunk)
                    
                    # 尝试实时提取和更新HTML内容
                    if not html_started:
                        if '<!DOCTYPE html>' in chunk:
                            html_started = True
                            start_idx = chunk.find('<!DOCTYPE html>')
                            current_html_content.append(chunk[start_idx:])
                        elif '```html' in chunk:
                            html_started = True
                            in_html_block = True
                            start_idx = chunk.find('```html') + 7
                            if start_idx < len(chunk):
                                current_html_content.append(chunk[start_idx:])
                    else:
                        if in_html_block and '```' in chunk:
                            # 结束代码块
                            end_idx = chunk.find('```')
                            if end_idx >= 0:
                                current_html_content.append(chunk[:end_idx])
                                in_html_block = False
                        else:
                            current_html_content.append(chunk)
                    
                    # 实时更新临时HTML文件
                    if current_html_content:
                        combined_content = ''.join(current_html_content)
                        temp_html_path.write_text(combined_content.strip(), encoding="utf-8")
                                
            if not full_response:
                raise ValueError("生成内容为空")
            
            # 提取最终的HTML内容和组件信息
            component_result = self._extract_component_info(full_response)
            
            if not component_result or not component_result.get("html"):
                self.logger.warning("无法从响应中提取有效的组件HTML内容，将生成错误页面")
                component_html = self._generate_error_html(
                    "无法从AI响应中提取有效的组件HTML内容",
                    query
                )
                component_info = {
                    "id": component_id,
                    "title": f"组件 {component_number}",
                    "description": "生成失败",
                    "mount_point": f"component_{component_number}"
                }
            else:
                component_html = component_result["html"]
                component_info = {
                    "id": component_id,
                    "title": component_result.get("title", f"组件 {component_number}"),
                    "description": component_result.get("description", ""),
                    "mount_point": component_result.get("mount_point", f"component_{component_number}")
                }
            
            # 保存组件HTML文件
            components_dir = self.artifacts_dir / "components"
            components_dir.mkdir(exist_ok=True)
            
            component_path = components_dir / f"{component_id}.html"
            
            # 检查组件是否已存在（如果存在，保存为新版本）
            if component_path.exists():
                # 保存组件版本历史
                self._save_component_version(component_id, component_html, query)
                self.logger.info(f"组件 {component_id} 已存在，保存为新版本")
            
            # 保存/更新组件文件
            component_path.write_text(component_html, encoding="utf-8")
            
            # 保存迭代版本HTML文件
            output_path = output_dir / f"{artifact_name}.html"
            output_path.write_text(component_html, encoding="utf-8")
            
            # 更新artifact HTML，添加新组件的链接
            # 注意：我们不再更新scaffold.html，只更新artifact.html
            updated_artifact = self._update_artifact_with_component(
                artifact_html,
                str(component_path.relative_to(self.artifacts_dir)),
                component_info
            )
            
            # 更新artifact.html（作为最新版本的完整制品）
            # 如果artifact.html已存在，进行版本管理
            if artifact_path.exists():
                # 保存当前版本
                current_version = self._get_next_artifact_version()
                artifact_versions_dir = self.artifacts_dir / "artifact_versions"
                artifact_versions_dir.mkdir(exist_ok=True)
                version_path = artifact_versions_dir / f"artifact_v{current_version}.html"
                
                # 备份当前版本
                shutil.copy2(artifact_path, version_path)
                
                # 更新版本记录
                versions_info_path = artifact_versions_dir / "versions_info.json"
                versions_info = {
                    "latest_version": current_version,
                    "versions": []
                }
                
                if versions_info_path.exists():
                    with open(versions_info_path, "r", encoding="utf-8") as f:
                        versions_info = json.load(f)
                
                version_info = {
                    "version": current_version,
                    "timestamp": datetime.now().isoformat(),
                    "query": query,
                    "path": str(version_path.relative_to(self.artifacts_base))
                }
                
                versions_info["versions"].append(version_info)
                versions_info["latest_version"] = current_version
                
                with open(versions_info_path, "w", encoding="utf-8") as f:
                    json.dump(versions_info, f, ensure_ascii=False, indent=2)
            
            # 写入新的artifact.html
            artifact_path.write_text(updated_artifact, encoding="utf-8")
            self.logger.info(f"已更新主制品: {artifact_path}")
            
            # 更新状态信息
            component_info["path"] = f"components/{component_id}.html"
            component_info["created_at"] = datetime.now().isoformat()
            component_info["query"] = query
            
            # 确保使用正确的组件编号（从组件ID中提取）
            try:
                component_number_str = component_id.split('_')[-1]
                if component_number_str.isdigit():
                    component_info["component_number"] = int(component_number_str)
                else:
                    component_info["component_number"] = iteration
            except Exception:
                # 如果提取失败，回退到使用迭代号
                component_info["component_number"] = iteration
                
            component_info["iteration"] = iteration  # 添加关联的迭代编号
            
            # 检查组件是否已存在于status.json中
            existing_component_index = None
            for i, comp in enumerate(status_info.get("components", [])):
                if comp.get("id") == component_id:
                    existing_component_index = i
                    break
            
            if existing_component_index is not None:
                # 更新现有组件信息
                component_info["updated_at"] = datetime.now().isoformat()
                try:
                    component_info["version"] = self._get_component_version(component_id) - 1  # 当前版本
                except Exception as e:
                    self.logger.warning(f"获取组件版本失败: {str(e)}，将设置为1")
                    component_info["version"] = 1
                status_info["components"][existing_component_index] = component_info
                self.logger.info(f"更新组件信息: {component_id}")
            else:
                # 添加新组件信息
                component_info["version"] = 1  # 首次创建，版本为1
                status_info["components"].append(component_info)
                self.logger.info(f"添加新组件信息: {component_id}")
            
            status_info["updated_at"] = datetime.now().isoformat()
            status_info["latest_iteration"] = iteration
            
            # 先获取优化建议，用于指导下一个组件的生成
            optimization_query = await self._get_optimization_query(updated_artifact)
            
            # 然后更新迭代信息
            iteration_info = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "path": str(work_base.relative_to(self.artifacts_base)),
                "query": query,
                "type": "component",
                "component_id": component_id,
                "output": str(output_path.relative_to(self.artifacts_base)),
                "optimization_suggestion": optimization_query
            }
            
            status_info["iterations"].append(iteration_info)
            
            with open(status_path, "w", encoding="utf-8") as f:
                json.dump(status_info, f, ensure_ascii=False, indent=2)

            # 保存本轮生成的完整信息
            generation_info = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "input_query": query,
                "output_file": str(output_path.relative_to(self.artifacts_base)),
                "component_id": component_id,
                "component_info": component_info,
                "optimization_suggestion": optimization_query,
                "generation_stats": {
                    "html_size": len(component_html)
                }
            }
            
            with open(output_dir / "generation_info.json", "w", encoding="utf-8") as f:
                json.dump(generation_info, f, ensure_ascii=False, indent=2)

            return output_path

        except Exception as e:
            self.logger.error(f"生成组件HTML时发生错误: {str(e)}")
            traceback.print_exc()
            return None 

    def _build_component_html_prompt(self, 
                                context_files: Dict[str, str], 
                                query: str, 
                                scaffold_html: str,
                                existing_components: List[Dict],
                                component_id: str) -> str:
        """构建组件HTML生成的提示词
        
        Args:
            context_files: 文件内容字典，key为文件名，value为文件内容
            query: 用户的查询内容
            scaffold_html: 框架HTML内容
            existing_components: 已有组件信息列表
            component_id: 当前组件ID
            
        Returns:
            str: 生成提示词
        """
        prompt = f"""[文件]
"""
        for filename, content in context_files.items():
            prompt += f"\n[file name]: {filename}\n[file content begin]\n{content}\n[file content end]\n"
        
        prompt += f"""[框架HTML]
{scaffold_html}

[已有组件]
"""
        
        # 获取组件编号，用于显示给模型
        component_number = component_id.split('_')[-1] if '_' in component_id else ""
        
        for component in existing_components:
            prompt += f"""
组件ID: {component.get('id')}
标题: {component.get('title')}
描述: {component.get('description')}
挂载点: {component.get('mount_point')}
"""
        
        # 提取可用的挂载点信息
        try:
            soup = BeautifulSoup(scaffold_html, 'html.parser')
            mount_points = []
            for element in soup.find_all(id=True):
                mount_points.append({
                    "id": element.get("id"),
                    "type": element.name,
                    "classes": " ".join(element.get("class", []))
                })
            
            # 将挂载点信息转换为易读格式
            mount_points_text = ""
            for i, mp in enumerate(mount_points):
                mount_points_text += f"""
挂载点 {i+1}:
- ID: {mp['id']}
- 元素类型: {mp['type']}
- CSS类: {mp['classes']}
"""
            
            prompt += f"""
[可用挂载点]
{mount_points_text}
"""
        except Exception as e:
            self.logger.warning(f"提取挂载点信息时发生错误: {str(e)}")
        
        prompt += f"""请根据用户的问题和上述信息，生成一个HTML组件，该组件将被挂载到框架HTML中。

[用户的问题]
{query}

[当前组件ID]
{component_id}

[组件编号]
{component_number}

要求：
1. 生成一个独立的HTML组件，专注于解决用户问题的一个特定方面
2. 组件应该是一个完整的HTML页面，包含所有必要的样式和脚本
3. 组件应该与框架HTML的样式保持一致
4. 组件应该提供以下信息（使用JSON格式包装在HTML注释中）：
   a. 组件标题（title）：简短描述组件的主要内容
   b. 组件描述（description）：详细说明组件的功能和内容
   c. 挂载点（mount_point）：建议在框架HTML中的哪个位置挂载该组件，必须使用上述可用挂载点中的ID

JSON格式示例：
<!--COMPONENT_INFO
{{
  "title": "组件标题",
  "description": "组件详细描述",
  "mount_point": "建议的挂载点ID"
}}
COMPONENT_INFO-->

5. 确保组件内容：
   a. 专注于解决用户问题的一个特定方面
   b. 与已有组件不重复
   c. 内容丰富、结构清晰
   d. 如有必要，可以包含交互元素

请生成完整的HTML组件代码，包括所有必要的CSS和JavaScript。特别注意：挂载点必须从上述提供的可用挂载点列表中选择，这一点非常重要。
"""
        return prompt 

    def _extract_component_info(self, full_response: str) -> Optional[Dict]:
        """从响应中提取组件HTML内容和组件信息
        
        Args:
            full_response: 完整的响应文本
            
        Returns:
            Optional[Dict]: 包含HTML内容和组件信息的字典，如果提取失败返回None
        """
        try:
            # 提取HTML内容
            html_content = self._extract_html_content(full_response)
            if not html_content:
                return None
            
            # 提取组件信息
            component_info = {}
            
            # 查找组件信息注释
            info_pattern = r'<!--COMPONENT_INFO\s*(.*?)\s*COMPONENT_INFO-->'
            info_match = re.search(info_pattern, html_content, re.DOTALL)
            
            if info_match:
                try:
                    # 尝试解析JSON
                    info_json = info_match.group(1).strip()
                    component_info = json.loads(info_json)
                except Exception as e:
                    self.logger.warning(f"解析组件信息JSON时发生错误: {str(e)}")
            
            # 如果没有找到组件信息或解析失败，尝试从HTML中提取基本信息
            if not component_info:
                # 尝试从title标签提取标题
                title_match = re.search(r'<title>(.*?)</title>', html_content)
                if title_match:
                    component_info["title"] = title_match.group(1).strip()
                
                # 尝试从meta description提取描述
                desc_match = re.search(r'<meta\s+name="description"\s+content="(.*?)"', html_content)
                if desc_match:
                    component_info["description"] = desc_match.group(1).strip()
                
                # 尝试从h1标签提取标题（如果title标签没有提供）
                if not component_info.get("title"):
                    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_content, re.DOTALL)
                    if h1_match:
                        component_info["title"] = h1_match.group(1).strip()
            
            # 如果HTML提取方法都失败，尝试从响应文本中直接寻找关键信息
            if not component_info.get("title"):
                # 尝试找出可能的标题 - 查找"标题"、"title"等关键词后的内容
                title_patterns = [
                    r'(?:标题|title)[：:]\s*"([^"]+)"',
                    r'(?:标题|title)[：:]\s*([^\n]+)'
                ]
                for pattern in title_patterns:
                    match = re.search(pattern, full_response, re.IGNORECASE)
                    if match:
                        component_info["title"] = match.group(1).strip()
                        break
            
            if not component_info.get("description"):
                # 尝试找出可能的描述 - 查找"描述"、"description"等关键词后的内容
                desc_patterns = [
                    r'(?:描述|description)[：:]\s*"([^"]+)"',
                    r'(?:描述|description)[：:]\s*([^\n]+)'
                ]
                for pattern in desc_patterns:
                    match = re.search(pattern, full_response, re.IGNORECASE)
                    if match:
                        component_info["description"] = match.group(1).strip()
                        break
            
            if not component_info.get("mount_point"):
                # 尝试找出可能的挂载点 - 查找"挂载点"、"mount_point"等关键词后的内容
                mount_patterns = [
                    r'(?:挂载点|mount_point|mount point)[：:]\s*"([^"]+)"',
                    r'(?:挂载点|mount_point|mount point)[：:]\s*([^\n]+)'
                ]
                for pattern in mount_patterns:
                    match = re.search(pattern, full_response, re.IGNORECASE)
                    if match:
                        component_info["mount_point"] = match.group(1).strip()
                        break
            
            return {
                "html": html_content,
                "title": component_info.get("title", ""),
                "description": component_info.get("description", ""),
                "mount_point": component_info.get("mount_point", "")
            }
            
        except Exception as e:
            self.logger.error(f"提取组件信息时发生错误: {str(e)}")
            return None 

    def _update_artifact_with_component(self, 
                              artifact_html: str, 
                              component_path: str, 
                              component_info: Dict) -> str:
        """更新制品HTML，添加新组件的链接。与_update_scaffold_with_component相同，
        但名称更加明确，表示这是针对artifact的更新而非scaffold
        
        Args:
            artifact_html: 制品HTML内容
            component_path: 组件HTML文件的相对路径
            component_info: 组件信息
            
        Returns:
            str: 更新后的制品HTML内容
        """
        try:
            # 解析HTML
            soup = BeautifulSoup(artifact_html, 'html.parser')
            
            # 1. 更新导航区域
            nav_updated = False
            
            # 尝试找到导航区域 - 扩展查找范围
            nav_elements = soup.find_all(['nav', 'ul', 'div'], 
                                      class_=['nav', 'navigation', 'menu', 'sidebar', 'navbar', 
                                             'navbar-nav', 'nav-menu', 'navigation-menu'])
            
            for nav in nav_elements:
                # 创建新的导航项
                new_nav_item = soup.new_tag('li')
                new_nav_link = soup.new_tag('a', href=f'#{component_info["id"]}')
                new_nav_link.string = component_info["title"]
                new_nav_item.append(new_nav_link)
                
                # 尝试找到合适的位置添加
                ul = nav.find('ul')
                if ul:
                    ul.append(new_nav_item)
                    nav_updated = True
                    break
                # 如果没有ul元素但当前元素本身是ul
                elif nav.name == 'ul':
                    nav.append(new_nav_item)
                    nav_updated = True
                    break
            
            # 如果没有找到合适的导航区域，尝试创建一个
            if not nav_updated:
                # 查找可能的挂载点
                potential_nav_containers = soup.find_all(['header', 'div'], 
                                                      class_=['header', 'top', 'navbar', 'navigation-container'])
                
                if potential_nav_containers:
                    container = potential_nav_containers[0]
                    new_nav = soup.new_tag('nav', class_='navigation')
                    new_ul = soup.new_tag('ul')
                    new_nav_item = soup.new_tag('li')
                    new_nav_link = soup.new_tag('a', href=f'#{component_info["id"]}')
                    new_nav_link.string = component_info["title"]
                    
                    new_nav_item.append(new_nav_link)
                    new_ul.append(new_nav_item)
                    new_nav.append(new_ul)
                    container.append(new_nav)
                    nav_updated = True
            
            # 2. 更新组件区域
            component_updated = False
            
            # 尝试找到指定的挂载点 - 使用多种选择器
            if component_info.get("mount_point"):
                # 尝试通过多种选择器查找挂载点
                mount_point = None
                selectors = [
                    f"#{component_info['mount_point']}",  # ID选择器
                    f"[data-mount='{component_info['mount_point']}']",  # 数据属性选择器
                    f".{component_info['mount_point']}"  # 类选择器
                ]
                
                for selector in selectors:
                    try:
                        elements = soup.select(selector)
                        if elements:
                            mount_point = elements[0]
                            break
                    except Exception as e:
                        self.logger.warning(f"尝试选择器 {selector} 时出错: {str(e)}")
                
                # 如果直接选择器未找到，尝试更宽松的查找方式
                if not mount_point:
                    for element in soup.find_all(True):  # 查找所有元素
                        # 检查ID是否包含目标挂载点
                        if element.get('id') and component_info['mount_point'] in element.get('id'):
                            mount_point = element
                            break
                        # 检查class是否包含目标挂载点
                        elif element.get('class') and component_info['mount_point'] in ' '.join(element.get('class', [])):
                            mount_point = element
                            break
                
                if mount_point:
                    # 创建组件链接
                    component_link = soup.new_tag('a', href=component_path, class_='component-link')
                    component_link.string = f'查看 {component_info["title"]}'
                    
                    # 创建iframe（可选）
                    component_iframe = soup.new_tag('iframe', 
                                                  src=component_path, 
                                                  class_='component-frame',
                                                  frameborder="0",
                                                  width="100%",
                                                  height="500px")
                    
                    # 清空挂载点内容并添加新内容
                    mount_point.clear()
                    
                    # 添加标题和描述
                    component_title = soup.new_tag('h3')
                    component_title.string = component_info["title"]
                    mount_point.append(component_title)
                    
                    if component_info.get("description"):
                        component_desc = soup.new_tag('p')
                        component_desc.string = component_info["description"]
                        mount_point.append(component_desc)
                    
                    # 添加iframe和链接
                    mount_point.append(component_iframe)
                    mount_point.append(component_link)
                    
                    component_updated = True
            
            # 如果没有找到指定的挂载点，尝试找到主内容区域
            if not component_updated:
                # 扩展主内容区域的查找范围
                main_content = None
                
                # 按优先级尝试不同的选择器
                main_selectors = [
                    "main",
                    ".main",
                    "#main",
                    ".content",
                    "#content",
                    ".container",
                    "#container",
                    "article",
                    ".article",
                    "section",
                    ".components-container",
                    "[data-role='content']",
                    ".main-content"
                ]
                
                for selector in main_selectors:
                    elements = soup.select(selector)
                    if elements:
                        main_content = elements[0]
                        break
                
                if main_content:
                    # 创建新的组件容器
                    component_container = soup.new_tag('div', id=component_info["id"], class_='component-container')
                    
                    # 添加标题和描述
                    component_title = soup.new_tag('h3')
                    component_title.string = component_info["title"]
                    component_container.append(component_title)
                    
                    if component_info.get("description"):
                        component_desc = soup.new_tag('p')
                        component_desc.string = component_info["description"]
                        component_container.append(component_desc)
                    
                    # 创建iframe
                    component_iframe = soup.new_tag('iframe', 
                                                  src=component_path, 
                                                  class_='component-frame',
                                                  frameborder="0",
                                                  width="100%",
                                                  height="500px")
                    component_container.append(component_iframe)
                    
                    # 创建组件链接
                    component_link = soup.new_tag('a', href=component_path, class_='component-link')
                    component_link.string = f'在新窗口中查看 {component_info["title"]}'
                    component_container.append(component_link)
                    
                    # 添加到主内容区域
                    main_content.append(component_container)
                    component_updated = True
                else:
                    # 找不到主内容区域时，添加到body
                    body = soup.find('body')
                    if body:
                        # 创建一个主内容区域
                        main_content = soup.new_tag('div', class_='main-content')
                        
                        # 创建新的组件容器
                        component_container = soup.new_tag('div', id=component_info["id"], class_='component-container')
                        
                        # 添加标题和描述
                        component_title = soup.new_tag('h3')
                        component_title.string = component_info["title"]
                        component_container.append(component_title)
                        
                        if component_info.get("description"):
                            component_desc = soup.new_tag('p')
                            component_desc.string = component_info["description"]
                            component_container.append(component_desc)
                        
                        # 创建iframe
                        component_iframe = soup.new_tag('iframe', 
                                                      src=component_path, 
                                                      class_='component-frame',
                                                      frameborder="0",
                                                      width="100%",
                                                      height="500px")
                        component_container.append(component_iframe)
                        
                        # 创建组件链接
                        component_link = soup.new_tag('a', href=component_path, class_='component-link')
                        component_link.string = f'在新窗口中查看 {component_info["title"]}'
                        component_container.append(component_link)
                        
                        # 添加到主内容区域和body
                        main_content.append(component_container)
                        body.append(main_content)
                        component_updated = True
            
            # 3. 更新组件索引/目录区域
            index_updated = False
            
            # 尝试找到组件索引区域
            index_area = soup.find(['div', 'section'], class_=['component-index', 'index', 'directory', 'toc', 'table-of-contents'])
            
            if index_area:
                # 创建新的索引项
                index_item = soup.new_tag('div', class_='index-item')
                
                index_title = soup.new_tag('h4')
                index_link = soup.new_tag('a', href=f'#{component_info["id"]}')
                index_link.string = component_info["title"]
                index_title.append(index_link)
                index_item.append(index_title)
                
                if component_info.get("description"):
                    index_desc = soup.new_tag('p')
                    index_desc.string = component_info["description"]
                    index_item.append(index_desc)
                
                # 添加到索引区域
                index_area.append(index_item)
                index_updated = True
            
            # 如果没有找到索引区域，尝试在侧边栏或页脚创建一个
            if not index_updated:
                sidebar = soup.find(['aside', 'div'], class_=['sidebar', 'aside', 'toc-container'])
                
                if sidebar:
                    # 创建索引区域
                    index_area = soup.new_tag('div', class_='component-index')
                    
                    index_header = soup.new_tag('h3')
                    index_header.string = '组件索引'
                    index_area.append(index_header)
                    
                    # 创建新的索引项
                    index_item = soup.new_tag('div', class_='index-item')
                    
                    index_title = soup.new_tag('h4')
                    index_link = soup.new_tag('a', href=f'#{component_info["id"]}')
                    index_link.string = component_info["title"]
                    index_title.append(index_link)
                    index_item.append(index_title)
                    
                    if component_info.get("description"):
                        index_desc = soup.new_tag('p')
                        index_desc.string = component_info["description"]
                        index_item.append(index_desc)
                    
                    # 添加到索引区域
                    index_area.append(index_item)
                    
                    # 添加到侧边栏
                    sidebar.append(index_area)
                    index_updated = True
            
            # 返回更新后的HTML
            return str(soup)
            
        except Exception as e:
            self.logger.error(f"更新制品HTML时发生错误: {str(e)}")
            # 如果更新失败，返回原始HTML
            return artifact_html

    def _get_component_version(self, component_id: str) -> int:
        """获取组件的下一个版本号
        
        Args:
            component_id: 组件ID
            
        Returns:
            int: 组件的下一个版本号，从1开始
        """
        component_versions_dir = self.artifacts_dir / "component_versions"
        component_versions_dir.mkdir(exist_ok=True)
        
        # 查找该组件的所有版本
        version_pattern = f"{component_id}_v*.html"
        existing_versions = []
        
        for version_file in component_versions_dir.glob(version_pattern):
            try:
                # 从文件名中提取版本号，例如 component_1_v2.html -> 2
                version_str = version_file.stem.split('_v')[-1]
                if version_str.isdigit():
                    existing_versions.append(int(version_str))
            except (ValueError, IndexError):
                self.logger.warning(f"跳过无效的组件版本文件名: {version_file.name}")
                continue
                
        return max(existing_versions, default=0) + 1
        
    def _save_component_version(self, component_id: str, component_html: str, query: str) -> dict:
        """保存组件的版本历史
        
        Args:
            component_id: 组件ID
            component_html: 组件HTML内容
            query: 生成该版本的查询
            
        Returns:
            dict: 版本信息
        """
        component_versions_dir = self.artifacts_dir / "component_versions"
        component_versions_dir.mkdir(exist_ok=True)
        
        # 获取下一个版本号
        next_version = self._get_component_version(component_id)
        
        # 保存组件版本
        version_file = f"{component_id}_v{next_version}.html"
        version_path = component_versions_dir / version_file
        version_path.write_text(component_html, encoding="utf-8")
        
        # 创建版本信息
        version_info = {
            "component_id": component_id,
            "version": next_version,
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "path": str(version_path.relative_to(self.artifacts_base))
        }
        
        # 更新组件版本记录
        versions_info_path = component_versions_dir / f"{component_id}_versions.json"
        versions_info = {
            "component_id": component_id,
            "latest_version": next_version,
            "versions": []
        }
        
        if versions_info_path.exists():
            try:
                with open(versions_info_path, "r", encoding="utf-8") as f:
                    versions_info = json.load(f)
            except Exception as e:
                self.logger.warning(f"读取组件版本记录时出错: {str(e)}，将创建新记录")
        
        # 添加新版本记录
        versions_info["versions"].append(version_info)
        versions_info["latest_version"] = next_version
        
        # 保存版本记录
        with open(versions_info_path, "w", encoding="utf-8") as f:
            json.dump(versions_info, f, ensure_ascii=False, indent=2)
            
        return version_info