import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
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
import re
from bs4 import BeautifulSoup
from ..core.context_preparation import prepare_context_files, read_file_content

class ComponentManager:
    """组件管理器类，负责处理所有与组件相关的操作"""
    
    def __init__(self, artifacts_dir: Path, logger: Optional[logging.Logger] = None):
        """初始化组件管理器
        
        Args:
            artifacts_dir: 工件目录路径
            logger: 日志记录器
        """
        self.artifacts_dir = artifacts_dir
        self.logger = logger or logging.getLogger(__name__)
        
        # 确保组件目录存在
        self.components_dir = self.artifacts_dir / "components"
        self.components_dir.mkdir(exist_ok=True)
        
        # 状态文件路径
        self.status_path = self.artifacts_dir / "status.json"
        
    def get_next_component_id(self) -> int:
        """获取下一个组件编号
        
        Returns:
            int: 下一个组件编号，从1开始
        """
        if not self.status_path.exists():
            return 1
            
        try:
            with open(self.status_path, "r", encoding="utf-8") as f:
                status_info = json.load(f)
                
            components = status_info.get("components", [])
            component_nums = []
            
            for component in components:
                try:
                    # 从组件ID中提取数字
                    comp_id = component.get("id", "")
                    if comp_id.startswith("component_"):
                        num_str = comp_id.split('_')[-1]
                        if num_str.isdigit():
                            component_nums.append(int(num_str))
                except (ValueError, IndexError):
                    self.logger.warning(f"跳过无效的组件ID: {component.get('id', '')}")
                    
            return max(component_nums, default=0) + 1
        except Exception as e:
            self.logger.error(f"从status.json获取组件编号失败: {str(e)}")
            return 1
    
    def get_component_metadata(self, component_id: str) -> Optional[Dict]:
        """获取组件的元数据
        
        Args:
            component_id: 组件ID
            
        Returns:
            Optional[Dict]: 组件元数据，如果不存在则返回None
        """
        if not self.status_path.exists():
            return None
            
        try:
            with open(self.status_path, "r", encoding="utf-8") as f:
                status_info = json.load(f)
                
            components = status_info.get("components", [])
            
            # 查找匹配的组件
            for component in components:
                if component.get("id") == component_id:
                    return component
                    
            return None
        except Exception as e:
            self.logger.error(f"从status.json获取组件元数据失败: {str(e)}")
            return None
    
    def get_all_components_metadata(self) -> List[Dict]:
        """获取所有组件的元数据
        
        Returns:
            List[Dict]: 所有组件的元数据列表
        """
        if not self.status_path.exists():
            return []
            
        try:
            with open(self.status_path, "r", encoding="utf-8") as f:
                status_info = json.load(f)
                
            return status_info.get("components", [])
        except Exception as e:
            self.logger.error(f"从status.json获取所有组件元数据失败: {str(e)}")
            return []
    
    def load_component_for_integration(self, component_id: str) -> Dict:
        """加载组件用于集成
        
        Args:
            component_id: 组件ID
            
        Returns:
            Dict: 包含组件信息的字典
        """
        metadata = self.get_component_metadata(component_id)
        if not metadata:
            raise ValueError(f"组件不存在: {component_id}")
            
        latest_path = self.components_dir / f"{component_id}.html"
        if not latest_path.exists():
            raise ValueError(f"组件文件不存在: {latest_path}")
            
        try:
            with open(latest_path, "r", encoding="utf-8") as f:
                html_content = f.read()
                
            # 提取组件信息
            component_info = {
                "id": component_id,
                "html": html_content,
                "metadata": metadata
            }
            
            return component_info
        except Exception as e:
            self.logger.error(f"加载组件失败: {component_id}, 错误: {str(e)}")
            raise
    
    def extract_component_info(self, full_response: str) -> Optional[Dict]:
        """从完整响应中提取组件信息
        
        Args:
            full_response: 完整的响应文本
            
        Returns:
            Optional[Dict]: 组件信息，如果提取失败则返回None
        """
        # 提取组件信息部分
        component_info_match = re.search(r'<component_info>(.*?)</component_info>', 
                                        full_response, re.DOTALL)
        if not component_info_match:
            self.logger.warning("未找到组件信息标记")
            return None
            
        component_info_text = component_info_match.group(1).strip()
        
        # 尝试解析JSON
        try:
            component_info = json.loads(component_info_text)
            return component_info
        except json.JSONDecodeError as e:
            self.logger.error(f"解析组件信息JSON失败: {str(e)}")
            return None
    
    def update_artifact_with_component(self, 
                          artifact_html: str, 
                          component_path: str, 
                          component_info: Dict) -> str:
        """使用组件更新工件HTML
        
        Args:
            artifact_html: 工件HTML内容
            component_path: 组件路径
            component_info: 组件信息
            
        Returns:
            str: 更新后的工件HTML
        """
        # 获取组件的相对URL
        component_url = component_path
        
        # 创建组件引用代码
        component_id = component_info.get("id", "unknown")
        component_ref = f'<div class="component-container" data-component-id="{component_id}">\n'
        component_ref += f'  <iframe src="{component_url}" frameborder="0" width="100%" '
        component_ref += f'height="{component_info.get("height", 300)}" '
        component_ref += f'title="{component_info.get("title", "组件")}">'
        component_ref += f'</iframe>\n</div>\n'
        
        # 查找组件占位符
        placeholder_pattern = r'<!-- COMPONENT_PLACEHOLDER -->'
        if re.search(placeholder_pattern, artifact_html):
            # 替换第一个占位符
            updated_html = re.sub(placeholder_pattern, component_ref, artifact_html, count=1)
        else:
            # 如果没有占位符，添加到内容区域
            content_pattern = r'(<div[^>]*class="[^"]*content[^"]*"[^>]*>)'
            match = re.search(content_pattern, artifact_html)
            if match:
                # 在内容区域开始标签后添加组件
                pos = match.end()
                updated_html = artifact_html[:pos] + '\n' + component_ref + artifact_html[pos:]
            else:
                # 如果找不到内容区域，添加到body
                body_pattern = r'(<body[^>]*>)'
                match = re.search(body_pattern, artifact_html)
                if match:
                    pos = match.end()
                    updated_html = artifact_html[:pos] + '\n' + component_ref + artifact_html[pos:]
                else:
                    # 最后的选择：添加到HTML末尾
                    updated_html = artifact_html + '\n' + component_ref
        
        return updated_html

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
        
        # 初始化组件管理器
        self.component_manager = ComponentManager(self.artifacts_dir, self.logger)


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
            encoding: 编码方式，默认utf-8
            
        Returns:
            Optional[str]: 文件内容，如果读取失败则返回None
        """
        # 使用封装后的函数
        return read_file_content(file_path, encoding, self.logger)

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
            
            # 2. 尝试提取html代码块 - 改进提取逻辑，确保只获取代码部分
            html_markers = ["```html", "```HTML", "```"]
            start_marker = None
            
            for marker in html_markers:
                if marker in full_response:
                    start_marker = marker
                    break
            
            if start_marker:
                # 查找代码块的边界
                parts = full_response.split(start_marker, 1)
                if len(parts) > 1:
                    remaining_text = parts[1].lstrip()
                    
                    # 查找结束标记
                    end_marker = "```"
                    if end_marker in remaining_text:
                        code_part = remaining_text.split(end_marker, 1)[0].strip()
                        
                        # 如果代码块的第一行是语言标识符，去掉它
                        if code_part.startswith('html') or code_part.startswith('HTML'):
                            code_part = code_part[4:].lstrip()
                        
                        if code_part and (code_part.startswith('<!DOCTYPE html>') or code_part.startswith('<html')):
                            return code_part
                        elif code_part:
                            # 检查是否包含有效的HTML标签
                            if re.search(r'<(?!!)([a-z]+)[^>]*>.*?</\1>', code_part, re.DOTALL):
                                # 移除可能的前导注释或非HTML内容
                                first_tag_match = re.search(r'<(?!!)([a-z]+)[^>]*>', code_part)
                                if first_tag_match:
                                    code_part = code_part[first_tag_match.start():]
                                return code_part
            
            # 3. 尝试从多个代码块中提取最符合条件的HTML
            code_blocks = re.findall(r'```(?:html|HTML)?\s*(.*?)```', full_response, re.DOTALL)
            valid_html_blocks = []
            
            for block in code_blocks:
                block = block.strip()
                # 如果第一行是语言标识符，去掉它
                if block.startswith('html') or block.startswith('HTML'):
                    block = block[4:].lstrip()
                    
                if block.startswith('<!DOCTYPE html>') or block.startswith('<html'):
                    valid_html_blocks.append((block, 3))  # 优先级3：完整HTML文档
                elif re.search(r'<(?!!)([a-z]+)[^>]*>.*?</\1>', block, re.DOTALL):
                    # 确保提取的是HTML片段，而不是其他内容
                    first_tag_match = re.search(r'<(?!!)([a-z]+)[^>]*>', block)
                    if first_tag_match:
                        # 从第一个HTML标签开始
                        clean_block = block[first_tag_match.start():]
                        valid_html_blocks.append((clean_block, 2))  # 优先级2：有效HTML片段
            
            # 返回优先级最高的HTML块
            if valid_html_blocks:
                valid_html_blocks.sort(key=lambda x: x[1], reverse=True)
                return valid_html_blocks[0][0]
            
            # 4. 如果响应包含HTML基本结构但没有代码块标记
            if '<html' in full_response and '</html>' in full_response:
                html_start = full_response.find('<html')
                html_end = full_response.rfind('</html>') + 7
                if html_start < html_end:
                    return full_response[html_start:html_end].strip()
            
            # 5. 尝试从响应中提取DOCTYPE到结束的完整HTML
            if '<!DOCTYPE html>' in full_response:
                doctype_start = full_response.find('<!DOCTYPE html>')
                # 查找最后一个</html>标签
                end_html_matches = list(re.finditer(r'</html>', full_response))
                if end_html_matches:
                    end_idx = end_html_matches[-1].end()
                    return full_response[doctype_start:end_idx].strip()
            
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
                
            # 检查status.json文件是否存在，不存在则创建
            status_file = self.artifacts_dir / "status.json"
            if not status_file.exists():
                self.logger.info("status.json文件不存在，正在创建初始文件...")
                
                # 使用self.alchemy_id作为artifact_id
                current_time = datetime.now()
                iso_timestamp = current_time.isoformat()
                
                initial_status = {
                    "artifact_id": self.alchemy_id,
                    "created_at": iso_timestamp,
                    "updated_at": iso_timestamp,
                    "latest_iteration": 0,
                    "original_query": query,
                    "artifact": {
                        "path": "artifact.html",
                        "timestamp": iso_timestamp
                    },
                    "scaffold": {
                        "path": "scaffold.html",
                        "timestamp": iso_timestamp,
                        "is_static": True
                    },
                    "components": [],
                    "iterations": []
                }
                
                status_file.parent.mkdir(parents=True, exist_ok=True)
                with open(status_file, 'w', encoding='utf-8') as f:
                    json.dump(initial_status, f, ensure_ascii=False, indent=2)
                self.logger.info(f"status.json文件已创建，artifact_id: {self.alchemy_id}")

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
        return self.component_manager.get_next_component_id()

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

            # 将上下文文件复制到工作目录，并收集内容信息
            context_contents, context_files_info = self._prepare_context_files(
                search_results_files, context_dir, work_base)
                
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

            # 将上下文文件复制到组件工作目录，并收集内容信息
            context_contents, context_files_info = self._prepare_context_files(
                search_results_files, context_dir, work_base)

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
            component_result = self.component_manager.extract_component_info(full_response)
            
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
            
            # 保存/更新组件文件
            component_path.write_text(component_html, encoding="utf-8")
            
            # 准备组件元数据
            component_metadata = {
                "id": component_id,
                "title": component_info.get("title", f"组件 {component_number}"),
                "description": component_info.get("description", ""),
                "mount_point": component_info.get("mount_point", f"component_{component_number}"),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "iteration": iteration,
                "query": query,
                "html_path": f"components/{component_id}.html",
                "component_url": f"components/{component_id}.html",  # 明确设置用于iframe的URL
                "status": "active",
                "component_number": component_number,
                "version": 1,
                "dependencies": [],
                "tags": []
            }
            
            # 额外检查并修正mount_point，确保它是ID而不是路径
            if "/" in component_metadata["mount_point"] or "." in component_metadata["mount_point"]:
                self.logger.warning(f"挂载点 {component_metadata['mount_point']} 格式异常，尝试修正")
                # 提取ID部分
                mount_id = component_metadata["mount_point"].split("/")[-1].replace(".html", "")
                component_metadata["mount_point"] = mount_id
                self.logger.info(f"修正后的挂载点: {mount_id}")
            
            # 读取或创建组件元数据文件
            metadata_file = components_dir / "component_metadata.json"
            all_components_metadata = {}
            
            if metadata_file.exists():
                try:
                    with open(metadata_file, "r", encoding="utf-8") as f:
                        all_components_metadata = json.load(f)
                except json.JSONDecodeError:
                    self.logger.warning(f"无法解析组件元数据文件，将创建新文件")
                    all_components_metadata = {}
            
            # 更新元数据字典
            all_components_metadata[component_id] = component_metadata
            
            # 保存更新后的元数据文件
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(all_components_metadata, f, ensure_ascii=False, indent=2)
                
            self.logger.info(f"已更新组件元数据文件: {metadata_file}")
            
            # 保存迭代版本HTML文件
            output_path = output_dir / f"{artifact_name}.html"
            output_path.write_text(component_html, encoding="utf-8")
            
            # 更新artifact HTML，添加新组件的链接
            # 注意：我们不再更新scaffold.html，只更新artifact.html
            updated_artifact = self.component_manager.update_artifact_with_component(
                artifact_html,
                self.artifacts_dir / f"components/{component_id}.html",  # 使用相对路径，方便在HTML中引用
                component_metadata  # 使用完整元数据替代简单的component_info
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
<component_info>
{{
  "title": "组件标题",
  "description": "组件详细描述",
  "mount_point": "建议的挂载点ID"
}}
</component_info>

5. 确保组件内容：
   a. 专注于解决用户问题的一个特定方面
   b. 与已有组件不重复
   c. 内容丰富、结构清晰
   d. 如有必要，可以包含交互元素

重要说明：请将HTML代码放在单独的代码块中，不要在代码块内添加任何解释或说明文本。
例如：

```html
<!DOCTYPE html>
<html>
...您的代码...
</html>
```

请分两部分回复：
1. 首先是对组件的说明
2. 然后单独放置HTML代码块，确保代码块内只有纯HTML代码，不含任何额外说明
"""
        return prompt 


    def _prepare_context_files(self, search_results_files: List[str], context_dir: Path, work_base: Path) -> Tuple[Dict[str, str], Dict[str, Dict]]:
        """准备上下文文件，复制文件并收集内容与元数据
        
        Args:
            search_results_files: 搜索结果文件路径列表
            context_dir: 上下文文件目标目录
            work_base: 工作目录基础路径
            
        Returns:
            Tuple[Dict[str, str], Dict[str, Dict]]: (context_contents, context_files_info)
        """
        # 调用封装后的函数
        return prepare_context_files(search_results_files, context_dir, work_base, self.logger)