import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import traceback
from .reasoning import ReasoningEngine
import shutil
import hashlib

class ArtifactGenerator:
    """制品生成器，用于根据上下文文件生成HTML格式的制品"""
    
    def __init__(self, alchemy_dir: str = None, reasoning_engine: Optional[ReasoningEngine] = None, logger: Optional[logging.Logger] = None):
        """初始化制品生成器
        
        Args:
            alchemy_dir: 炼丹目录
            reasoning_engine: 推理引擎实例，用于生成内容
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
        
        # 修改目录结构
        self.artifacts_base = self.alchemy_dir / "artifacts"  # 基础制品目录
        
        # 每个制品的目录结构
        self.artifacts_dir = self.artifacts_base 
        self.iterations_dir = self.artifacts_dir / "iterations"  # 存放迭代版本
        
        # 创建所需目录
        for dir_path in [self.artifacts_base, self.artifacts_dir, self.iterations_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        self.logger = logger or logging.getLogger(__name__)
        self.reasoning_engine = reasoning_engine
        
        if not self.reasoning_engine:
            self.logger.warning("未提供推理引擎实例，将无法生成内容")
    
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

    def _build_html_prompt(self, context_files: Dict[str, str], query: str) -> str:
        """构建HTML生成的提示词
        
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
        
        prompt += f"""请根据用户的问题，从以下文件中提炼出相关信息，生成一个HTML页面来解决用户的问题：

[用户的问题]
{query}
要求：
1. 生成一个结构良好的HTML页面
2. 使用适当的CSS样式美化页面
3. 合理组织和展示文件中的信息
4. 确保页面具有良好的可读性和导航性
5. 可以添加适当的交互元素增强用户体验
"""
        return prompt

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
            # 1. 如果响应本身就是完整的HTML
            if full_response.strip().startswith('<!DOCTYPE html>'):
                return full_response.strip()
            
            # 2. 尝试提取html代码块
            start_marker = "```html"
            end_marker = "```"
            
            if start_marker in full_response:
                start_idx = full_response.find(start_marker) + len(start_marker)
                remaining_text = full_response[start_idx:]
                if end_marker in remaining_text:
                    end_idx = remaining_text.find(end_marker)
                    html_content = remaining_text[:end_idx].strip()
                    if html_content.startswith('\n'):
                        html_content = html_content[1:]
                    if html_content:
                        return html_content
            
            # 3. 尝试提取任意代码块中的HTML内容
            if "```" in full_response:
                start_idx = full_response.find("```") + 3
                # 跳过语言标识符所在行
                start_idx = full_response.find("\n", start_idx) + 1
                remaining_text = full_response[start_idx:]
                if "```" in remaining_text:
                    end_idx = remaining_text.find("```")
                    html_content = remaining_text[:end_idx].strip()
                    if html_content.startswith('<!DOCTYPE html>'):
                        return html_content
            
            # 4. 如果响应包含HTML基本结构但没有代码块标记
            if '<html' in full_response and '</html>' in full_response:
                start_idx = full_response.find('<html')
                end_idx = full_response.find('</html>') + 7
                return full_response[start_idx:end_idx].strip()
            
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

    async def _get_optimization_query(self, html_content: str, previous_query: str) -> Optional[str]:
        """分析当前HTML内容并生成优化建议查询
        
        Args:
            html_content: 当前生成的HTML内容
            previous_query: 上一轮的查询内容
            
        Returns:
            Optional[str]: 优化建议查询
        """
        try:
            prompt = f"""请分析以下HTML内容和原始查询，提出一个具体的优化建议问题。这个问题将用于生成下一个优化版本。

原始查询：
{previous_query}

当前HTML内容：
{html_content}

请提出一个明确的优化问题，格式要求：
1. 只输出问题本身，不要其他内容
2. 问题应该具体且可操作
3. 问题应该针对内容、结构或用户体验的改进
4. 使用疑问句式
"""
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
                    self.logger.info(f"\r生成优化建议: {full_response}")
                    
                    # 如果发现完整的句子，更新建议
                    if any(chunk.strip().endswith(end) for end in ['。', '？', '!']):
                        suggestion = full_response.strip().strip('`').strip('"').strip()
            
            if suggestion:
                self.logger.info(f"最终优化建议: {suggestion}")
                return suggestion
                
            return None
            
        except Exception as e:
            self.logger.error(f"生成优化建议时发生错误: {str(e)}")
            return None

    async def generate_artifact(self, 
                              context_files: List[str], 
                              output_name: str,
                              query: str,
                              is_main: bool = True,
                              metadata: Optional[Dict] = None) -> Optional[Path]:
        """生成HTML制品
        
        Args:
            context_files: 上下文文件路径列表
            output_name: 输出文件名
            query: 用户的查询内容
            is_main: 是否为主制品，默认为True
            metadata: 可选的元数据字典
            
        Returns:
            Optional[Path]: 生成的HTML文件路径，如果生成失败返回None
        """
        try:
            if not self.reasoning_engine:
                raise ValueError("未配置推理引擎，无法生成内容")

            # 确定生成目录
            iteration = self._get_next_iteration()
            work_base = self.iterations_dir / f"iter{iteration}"
            artifact_name = f"artifact_iter{iteration}"
            
            # 创建工作目录
            process_dir = work_base / "process"    # 生成过程
            output_dir = work_base / "output"      # 最终输出
            source_dir = work_base / "source"      # 源文件副本
            
            for dir_path in [work_base, process_dir, output_dir, source_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)

            # 复制源文件并记录信息
            context_contents = {}
            source_files_info = {}
            
            for file_path in context_files:
                src_path = Path(file_path)
                if src_path.exists():
                    dst_path = source_dir / src_path.name
                    shutil.copy2(src_path, dst_path)
                    
                    content = self._read_file_content(file_path)
                    if content:
                        context_contents[src_path.name] = content
                        source_files_info[src_path.name] = {
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
                "type": "main" if is_main else f"iteration_{iteration}",
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "output_name": output_name,
                "source_files": source_files_info,
                "custom_metadata": metadata or {},
                "generation_config": {
                    "engine": self.reasoning_engine.__class__.__name__,
                    "model": getattr(self.reasoning_engine, 'model_name', 'unknown')
                }
            }

            # 保存元数据
            with open(work_base / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata_info, f, ensure_ascii=False, indent=2)

            # 构建提示词并保存
            prompt = self._build_html_prompt(context_contents, query)
            with open(process_dir / "generation_prompt.md", "w", encoding="utf-8") as f:
                f.write(prompt)

            # 添加用户消息
            self.reasoning_engine.add_message("user", prompt)
            
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
                metadata={'stage': 'html_generation'}
            ):
                if chunk:
                    full_response += chunk
                    
                    # 保存生成过程
                    with process_path.open("a", encoding="utf-8") as f:
                        f.write(chunk)
                    
                    # 显示流式输出内容
                    self.logger.info(f"\r生成内容: {full_response}")
                    
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
            html_content = self._extract_html_content(full_response)
            
            if not html_content:
                self.logger.warning("无法从响应中提取有效的HTML内容，将生成错误页面")
                html_content = self._generate_error_html(
                    "无法从AI响应中提取有效的HTML内容",
                    query
                )
            
            # 保存迭代版本HTML文件
            output_path = output_dir / f"{artifact_name}.html"
            output_path.write_text(html_content, encoding="utf-8")

            # 获取优化建议
            optimization_query = await self._get_optimization_query(html_content, query)

            # 更新main.html（作为最新版本的快照）
            main_path = self.artifacts_dir / "main.html"
            
            # 如果main.html已存在，进行版本管理和内容合并
            if main_path.exists():
                # 保存当前版本
                current_version = self._get_next_main_version()
                main_versions_dir = self.artifacts_dir / "main_versions"
                version_path = main_versions_dir / f"main_v{current_version}.html"
                
                # 备份当前版本
                shutil.copy2(main_path, version_path)
                
                # 读取当前main.html内容
                current_main_content = main_path.read_text(encoding="utf-8")
                
                # 合并内容
                merged_content = await self._merge_html_contents(current_main_content, html_content, query)
                if merged_content:
                    html_content = merged_content
                else:
                    self.logger.warning("内容合并失败，将使用新生成的内容")
                
                # 更新版本记录
                versions_info_path = main_versions_dir / "versions_info.json"
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
            
            # 写入新的main.html
            main_path.write_text(html_content, encoding="utf-8")
            self.logger.info(f"已更新主制品: {main_path}")

            # 更新状态信息
            status_info = {
                "artifact_id": f"artifact_{self.alchemy_id}",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "latest_iteration": iteration,
                "main_artifact": {
                    "path": str(main_path.relative_to(self.artifacts_base)),
                    "timestamp": datetime.now().isoformat()
                },
                "iterations": []
            }
            
            status_path = self.artifacts_dir / "status.json"
            if status_path.exists():
                with open(status_path, "r", encoding="utf-8") as f:
                    status_info = json.load(f)
            
            # 更新迭代信息，包含优化建议
            iteration_info = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "path": str(work_base.relative_to(self.artifacts_base)),
                "query": query,
                "optimization_suggestion": optimization_query
            }
            
            status_info["iterations"].append(iteration_info)
            status_info["latest_iteration"] = iteration
            status_info["updated_at"] = datetime.now().isoformat()
            
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
                    "html_size": len(html_content)
                }
            }
            
            with open(output_dir / "generation_info.json", "w", encoding="utf-8") as f:
                json.dump(generation_info, f, ensure_ascii=False, indent=2)

            return output_path

        except Exception as e:
            self.logger.error(f"生成HTML制品时发生错误: {str(e)}")
            
            # 错误处理和记录
            if 'work_base' in locals():
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

    def _get_next_main_version(self) -> int:
        """获取main.html的下一个版本号"""
        main_versions_dir = self.artifacts_dir / "main_versions"
        main_versions_dir.mkdir(exist_ok=True)
        
        try:
            # 使用更健壮的版本号提取方法
            existing_versions = []
            for file_path in main_versions_dir.glob("main_v*.html"):
                try:
                    # 从文件名中提取版本号，格式应该是 main_v{number}.html
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

    async def _merge_html_contents(self, current_main: str, new_content: str, query: str) -> Optional[str]:
        """合并当前main.html和新生成的HTML内容
        
        Args:
            current_main: 当前main.html的内容
            new_content: 新生成的HTML内容
            query: 用户的查询内容
            
        Returns:
            Optional[str]: 合并后的HTML内容
        """
        try:
            if not self.reasoning_engine:
                raise ValueError("未配置推理引擎，无法合并内容")

            prompt = f"""请分析并合并以下两个HTML内容，生成一个新的综合版本。

当前main.html内容：
{current_main}

新生成的HTML内容：
{new_content}

用户的查询内容：
{query}

要求：
1. 保留两个版本中的重要信息
2. 确保合并后的内容结构合理、样式统一
3. 新内容应该自然地融入现有结构
4. 保持页面的整体一致性和美观性
5. 只输出合并后的HTML内容，不要其他说明

请生成合并后的HTML内容："""

            # 添加用户消息
            self.reasoning_engine.add_message("user", prompt)
            
            # 收集合并后的内容
            merged_content = []
            async for chunk in self.reasoning_engine.get_stream_response(
                temperature=0.7,
                metadata={'stage': 'html_merge'}
            ):
                if chunk:
                    merged_content.append(chunk)
                    self.logger.info(f"\r合并内容: {''.join(merged_content)}")

            final_content = ''.join(merged_content)
            html_content = self._extract_html_content(final_content)
            
            if not html_content:
                raise ValueError("无法从合并响应中提取有效的HTML内容")
                
            return html_content

        except Exception as e:
            self.logger.error(f"合并HTML内容时发生错误: {str(e)}")
            return None 