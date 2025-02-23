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
    
    def __init__(self, work_dir: str = "work_dir", reasoning_engine: Optional[ReasoningEngine] = None, logger: Optional[logging.Logger] = None):
        """初始化制品生成器
        
        Args:
            work_dir: 工作目录
            reasoning_engine: 推理引擎实例，用于生成内容
            logger: 可选，日志记录器实例
        """
        self.work_dir = Path(work_dir)
        self.artifacts_dir = self.work_dir / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
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

    def _build_html_prompt(self, context_files: Dict[str, str], title: str) -> str:
        """构建HTML生成的提示词
        
        Args:
            context_files: 文件内容字典，key为文件名，value为文件内容
            title: HTML页面标题
            
        Returns:
            str: 生成提示词
        """
        prompt = f"""请根据文件内容生成一个HTML页面：

[页面标题]
{title}

[文件]
"""
        for filename, content in context_files.items():
            prompt += f"\n[{filename}]\n{content}\n"
        
        prompt += """
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

    async def generate_artifact(self, 
                              context_files: List[str], 
                              output_name: str,
                              title: str,
                              metadata: Optional[Dict] = None) -> Optional[Path]:
        """生成HTML制品
        
        Args:
            context_files: 上下文文件路径列表
            output_name: 输出文件名
            title: HTML页面标题
            metadata: 可选的元数据字典
            
        Returns:
            Optional[Path]: 生成的HTML文件路径，如果生成失败返回None
        """
        try:
            if not self.reasoning_engine:
                raise ValueError("未配置推理引擎，无法生成内容")

            # 创建更有意义的制品目录结构
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            artifact_name = f"{output_name}_{timestamp}"
            
            # 主目录结构
            artifact_dir = self.artifacts_dir / artifact_name
            artifact_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建子目录
            process_dir = artifact_dir / "process"  # 存放生成过程
            output_dir = artifact_dir / "output"    # 存放最终输出
            
            for dir_path in [process_dir, output_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)

            # 读取上下文文件并记录源文件信息
            context_contents = {}
            source_files_info = {}
            
            for file_path in context_files:
                src_path = Path(file_path)
                if src_path.exists():
                    content = self._read_file_content(file_path)
                    if content:
                        context_contents[src_path.name] = content
                        # 记录源文件信息
                        source_files_info[src_path.name] = {
                            "absolute_path": str(src_path.absolute()),
                            "size": src_path.stat().st_size,
                            "modified_time": datetime.fromtimestamp(src_path.stat().st_mtime).isoformat(),
                            "content_hash": hashlib.md5(content.encode()).hexdigest()
                        }

            if not context_contents:
                raise ValueError("未能成功读取任何上下文文件内容")

            # 保存完整的元数据信息
            metadata_info = {
                "artifact_id": artifact_name,
                "timestamp": timestamp,
                "title": title,
                "output_name": output_name,
                "source_files": source_files_info,
                "custom_metadata": metadata or {},
                "generation_config": {
                    "engine": self.reasoning_engine.__class__.__name__,
                    "model": getattr(self.reasoning_engine, 'model_name', 'unknown')
                }
            }

            with open(artifact_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata_info, f, ensure_ascii=False, indent=2)

            # 构建提示词并保存
            prompt = self._build_html_prompt(context_contents, title)
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
                    title
                )
            
            # 保存最终HTML文件到output目录
            output_path = output_dir / f"{output_name}.html"
            output_path.write_text(html_content, encoding="utf-8")

            # 记录生成结果
            generation_result = {
                "timestamp": datetime.now().isoformat(),
                "status": "success",
                "output_file": str(output_path.relative_to(self.artifacts_dir)),
                "file_size": output_path.stat().st_size,
                "generation_stats": {
                    "total_chunks": len(full_response),
                    "final_html_size": len(html_content)
                }
            }
            
            with open(output_dir / "generation_result.json", "w", encoding="utf-8") as f:
                json.dump(generation_result, f, ensure_ascii=False, indent=2)

            self.logger.info(f"已生成HTML制品: {output_path}")
            return output_path

        except Exception as e:
            self.logger.error(f"生成HTML制品时发生错误: {str(e)}")
            
            # 错误处理和记录
            if 'artifact_dir' in locals():
                error_info = {
                    "timestamp": datetime.now().isoformat(),
                    "status": "error",
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }
                
                with open(process_dir / "generation_error.json", "w", encoding="utf-8") as f:
                    json.dump(error_info, f, ensure_ascii=False, indent=2)
                
                error_html = self._generate_error_html(str(e), title)
                error_path = output_dir / f"{output_name}_error.html"
                error_path.write_text(error_html, encoding="utf-8")
            
            return None 