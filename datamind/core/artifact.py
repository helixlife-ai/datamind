import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import traceback
from .reasoningLLM import ReasoningLLMEngine
from ..llms.model_manager import ModelManager, ModelConfig
from ..config.settings import (
    parse_api_keys,
    DEFAULT_REASONING_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE
)
import re
from .context_preparation import prepare_context_files
from ..prompts import load_prompt, format_prompt
import os
from dotenv import load_dotenv
import asyncio
from playwright.async_api import async_playwright
load_dotenv(override=True)

LLMCORE_LLM_API_KEY = parse_api_keys(os.getenv("LLMCORE_API_KEY", ""))
LLMCORE_LLM_API_BASE = os.getenv("LLMCORE_BASE_URL") 
LLMCORE_GENERATOR_MODEL = os.getenv("LLMCORE_GENERATOR_MODEL") 
LLMCORE_REASONING_MODEL = os.getenv("LLMCORE_REASONING_MODEL") 

class ArtifactGenerator:
    """制品生成器，用于根据上下文文件生成HTML格式的制品"""
    
    def __init__(self, alchemy_dir: str = None, logger: Optional[logging.Logger] = None):
        """初始化制品生成器
        
        Args:
            alchemy_dir: 炼丹目录
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
        self.iterations_dir = self.alchemy_dir / "iterations"  # 存放迭代版本
        
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
        model_manager.register_model(ModelConfig(
            name=LLMCORE_REASONING_MODEL,
            model_type="api",
            api_base=LLMCORE_LLM_API_BASE,
            api_key=LLMCORE_LLM_API_KEY
        ))
        return ReasoningLLMEngine(model_manager, model_name=LLMCORE_REASONING_MODEL)
       
    def _generate_error_html(self, error_message: str, title: str) -> str:
        """生成错误提示页面
        
        Args:
            error_message: 错误信息
            title: 页面标题
            
        Returns:
            str: 错误页面HTML内容
        """
        # 加载错误HTML模板并替换占位符
        return format_prompt("artifact/error_html_template", 
                            error_message=error_message,
                            title=title)

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
        return max(existing_iterations, default=0)

    async def _collect_stream_response(self, 
                                 temperature=0.7, 
                                 max_tokens=30000,
                                 metadata=None, 
                                 process_path=None):
        """收集流式响应并显示
        
        Args:
            temperature: 温度参数
            max_tokens: 最大令牌数
            metadata: 元数据字典
            process_path: 可选，保存生成过程的文件路径
            
        Returns:
            str: 收集到的完整响应
        """
        full_response = ""
        
        async for chunk in self.reasoning_engine.get_stream_response(
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata or {}
        ):
            if chunk:
                full_response += chunk
                
                # 如果提供了文件路径，保存生成过程
                if process_path:
                    with process_path.open("a", encoding="utf-8") as f:
                        f.write(chunk)
                
                # 显示流式输出内容
                print(f"\r{chunk}", end='', flush=True)
                
        return full_response

    def _build_html_prompt(self, context_files: Dict[str, str], query: str) -> str:
        """构建HTML生成的提示词
        
        Args:
            context_files: 文件内容字典，key为文件名，value为文件内容
            query: 用户的查询内容
            
        Returns:
            str: 生成提示词
        """
        # 将文件内容格式化为字符串
        context_files_str = ""
        for filename, content in context_files.items():
            context_files_str += f"\n[file name]: {filename}\n[file content begin]\n{content}\n[file content end]\n"
        
        # 加载提示词模板并替换占位符
        return format_prompt("artifact/html_prompt",
                            context_files=context_files_str,
                            query=query)

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
                    "iterations": []
                }
                
                status_file.parent.mkdir(parents=True, exist_ok=True)
                with open(status_file, 'w', encoding='utf-8') as f:
                    json.dump(initial_status, f, ensure_ascii=False, indent=2)
                self.logger.info(f"status.json文件已创建，artifact_id: {self.alchemy_id}")

            # 确定生成目录
            iteration = self._get_next_iteration()
            
            # 生成HTML
            return await self._generate_html(search_results_files, output_name, query, iteration)
                
        except Exception as e:
            self.logger.error(f"生成HTML制品时发生错误: {str(e)}")
            
            # 错误处理和记录
            work_base = self.iterations_dir / f"iter{iteration}" / "artifact"
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
            
            # 尝试为错误页面生成截图
            try:
                await self._generate_screenshot(error_path, output_dir / f"{output_name}_error.png")
            except Exception as screenshot_error:
                self.logger.error(f"为错误页面生成截图时发生错误: {str(screenshot_error)}")
            
            return None

    async def _generate_html(self, 
                        search_results_files: List[str], 
                        output_name: str,
                        query: str,
                        iteration: int) -> Optional[Path]:
        """生成HTML
        
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
            work_base = self.iterations_dir / f"iter{iteration}" / "artifact"
            artifact_name = f"artifact_iter{iteration}"
            
            # 创建工作目录
            process_dir = work_base / "process"    # 生成过程
            output_dir = work_base / "output"      # 最终输出
            context_dir = work_base / "context"    # 上下文文件副本
            
            for dir_path in [work_base, process_dir, output_dir, context_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)

            # 将上下文文件复制到工作目录，并收集内容信息
            context_contents, context_files_info = prepare_context_files(search_results_files, context_dir, work_base, self.logger)
                
            if not context_contents:
                raise ValueError("未能成功读取任何上下文文件内容")

            # 获取优化建议查询
            optimization_suggestion = await self._get_optimization_query()

            # 更新元数据结构
            metadata_info = {
                "artifact_id": f"artifact_{self.alchemy_id}",
                "type": "html",
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "optimization_suggestion": optimization_suggestion,
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

            # 构建HTML提示词
            html_prompt = self._build_html_prompt(context_contents, query)
            with open(process_dir / "html_prompt.md", "w", encoding="utf-8") as f:
                f.write(html_prompt)

            # 在添加新消息前清除历史对话记录
            self.reasoning_engine.clear_history()
            
            # 添加用户消息
            self.reasoning_engine.add_message("user", html_prompt)
            
            # 收集生成的内容
            full_response = await self._collect_stream_response(
                temperature=0.7,
                metadata={'stage': 'html_generation'},
                process_path=process_dir / "generation_process.txt"
            )
            
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

            # 保存artifact.html
            artifact_path = self.artifacts_dir / "artifact.html"
            
            # 写入artifact.html
            artifact_path.write_text(html_content, encoding="utf-8")
            self.logger.info(f"已保存制品HTML: {artifact_path}")
            
            # 使用Playwright生成HTML文件的截图
            await self._generate_screenshot(output_path, output_dir / f"{artifact_name}.png")
            
            # 保存本轮生成的完整信息
            generation_info = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "input_query": query,
                "output_file": str(output_path.relative_to(self.alchemy_dir)),
                "output_screenshot": str((output_dir / f"{artifact_name}.png").relative_to(self.alchemy_dir)),
                "optimization_suggestion": optimization_suggestion,
                "generation_stats": {
                    "html_size": len(html_content)
                }
            }
            
            with open(output_dir / "generation_info.json", "w", encoding="utf-8") as f:
                json.dump(generation_info, f, ensure_ascii=False, indent=2)


            # 更新status.json
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
                    "artifact": {
                        "path": "artifact.html",
                        "timestamp": datetime.now().isoformat()
                    },
                    "iterations": []
                }
                       
            # 确保iterations字段存在
            if "iterations" not in status_info:
                status_info["iterations"] = []


            # 更新迭代信息
            iteration_info = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "path": str(work_base.relative_to(self.alchemy_dir)),
                "query": query,
                "type": "html",
                "output": str(output_path.relative_to(self.alchemy_dir)),
                "screenshot": str((output_dir / f"{artifact_name}.png").relative_to(self.alchemy_dir)),
                "optimization_suggestion": optimization_suggestion
            }

            status_info["iterations"].append(iteration_info)
            
            with open(status_path, "w", encoding="utf-8") as f:
                json.dump(status_info, f, ensure_ascii=False, indent=2)



            return output_path

        except Exception as e:
            self.logger.error(f"生成HTML时发生错误: {str(e)}")
            traceback.print_exc()
            return None 

    async def _get_optimization_query(self) -> Optional[str]:
        """根据原始查询，生成新的建议查询
                    
        Returns:
            Optional[str]: 新的建议查询语句
        """
        try:
            # 从status.json中读取原始查询
            original_query = ""
            status_path = self.artifacts_dir / "status.json"
            
            if status_path.exists():
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        status_info = json.load(f)
                    original_query = status_info.get("original_query", "")
                    self.logger.info(f"从status.json中读取到原始查询: {original_query}")
                except Exception as e:
                    self.logger.error(f"读取status.json时发生错误: {str(e)}")
                        
            if not original_query:
                self.logger.warning("无法获取原始查询，将使用空字符串")
            

            #获取前面迭代已经生成过的查询
            # 先检查status.json是否已存在，如果存在则读取现有内容
            status_path = self.artifacts_dir / "status.json"
            if status_path.exists():
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        status_info = json.load(f)
                        previous_queries = [
                            iteration_info.get("query", "")
                            for iteration_info in status_info.get("iterations", [])
                        ]
                        self.logger.info(f"前面迭代已经生成过的查询: {previous_queries}")
                except Exception as e:
                    self.logger.error(f"读取status.json时发生错误: {str(e)}")
            else:
                self.logger.warning("无法获取前面迭代已经生成过的查询，将使用空列表")
                previous_queries = []
                        
            #处理previous_queries
            previous_queries_str = "\n".join(previous_queries)
            self.logger.info(f"前面迭代已经生成过的查询: {previous_queries_str}")

            # 加载生成新的建议查询提示词模板
            prompt = format_prompt("artifact/optimization_query_prompt",
                                    original_query=original_query,
                                    previous_queries=previous_queries_str
            )
            
            # 在添加新消息前清除历史对话记录
            self.reasoning_engine.clear_history()
            
            # 添加用户消息
            self.reasoning_engine.add_message("user", prompt)
            
            # 使用流式输出收集响应
            full_response = await self._collect_stream_response(
                temperature=0.7,
                metadata={'stage': 'optimization_suggestion'},
                process_path=None
            )
            
            # 从full_response中提取<answer></answer>标签之间的内容
            if "<answer>" in full_response and "</answer>" in full_response:
                start_idx = full_response.find("<answer>") + len("<answer>")
                end_idx = full_response.find("</answer>")
                if start_idx < end_idx:
                    suggestion = full_response[start_idx:end_idx].strip()
                    self.logger.info(f"最终建议查询: {suggestion}")
                    return suggestion
            else:
                # 如果没有找到标签，保留原有逻辑
                suggestion = full_response.strip().strip('`').strip('"').strip()
                if suggestion:
                    self.logger.info(f"最终建议查询: {suggestion}")
                    return suggestion
                
            return None
            
        except Exception as e:
            self.logger.error(f"生成建议查询时发生错误: {str(e)}")
            return None

    async def _take_screenshot(self, url: str, output_path: Path) -> bool:
        """使用Playwright截图
        
        Args:
            url: 网页URL
            output_path: 输出截图文件路径
            
        Returns:
            bool: 是否成功截图
        """
        try:
            async def screenshot(playwright):
                browser = await playwright.chromium.launch()
                page = await browser.new_page()
                await page.goto(url)
                await page.screenshot(path=str(output_path))
                await browser.close()

            async with async_playwright() as playwright:
                await screenshot(playwright)
            return True
        except Exception as e:
            self.logger.error(f"截图失败: {str(e)}")
            return False

    async def _generate_html_with_screenshot(self, 
                        search_results_files: List[str], 
                        output_name: str,
                        query: str,
                        iteration: int) -> Optional[Path]:
        """生成HTML并截图
        
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
            work_base = self.iterations_dir / f"iter{iteration}" / "artifact"
            artifact_name = f"artifact_iter{iteration}"
            
            # 创建工作目录
            process_dir = work_base / "process"    # 生成过程
            output_dir = work_base / "output"      # 最终输出
            context_dir = work_base / "context"    # 上下文文件副本
            
            for dir_path in [work_base, process_dir, output_dir, context_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)

            # 将上下文文件复制到工作目录，并收集内容信息
            context_contents, context_files_info = prepare_context_files(search_results_files, context_dir, work_base, self.logger)
                
            if not context_contents:
                raise ValueError("未能成功读取任何上下文文件内容")

            # 获取优化建议查询
            optimization_suggestion = await self._get_optimization_query()

            # 更新元数据结构
            metadata_info = {
                "artifact_id": f"artifact_{self.alchemy_id}",
                "type": "html",
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "optimization_suggestion": optimization_suggestion,
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

            # 构建HTML提示词
            html_prompt = self._build_html_prompt(context_contents, query)
            with open(process_dir / "html_prompt.md", "w", encoding="utf-8") as f:
                f.write(html_prompt)

            # 在添加新消息前清除历史对话记录
            self.reasoning_engine.clear_history()
            
            # 添加用户消息
            self.reasoning_engine.add_message("user", html_prompt)
            
            # 收集生成的内容
            full_response = await self._collect_stream_response(
                temperature=0.7,
                metadata={'stage': 'html_generation'},
                process_path=process_dir / "generation_process.txt"
            )
            
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

            # 保存artifact.html
            artifact_path = self.artifacts_dir / "artifact.html"
            
            # 写入artifact.html
            artifact_path.write_text(html_content, encoding="utf-8")
            self.logger.info(f"已保存制品HTML: {artifact_path}")
            
            # 保存本轮生成的完整信息
            generation_info = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "input_query": query,
                "output_file": str(output_path.relative_to(self.alchemy_dir)),
                "optimization_suggestion": optimization_suggestion,
                "generation_stats": {
                    "html_size": len(html_content)
                }
            }
            
            with open(output_dir / "generation_info.json", "w", encoding="utf-8") as f:
                json.dump(generation_info, f, ensure_ascii=False, indent=2)


            # 更新status.json
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
                    "artifact": {
                        "path": "artifact.html",
                        "timestamp": datetime.now().isoformat()
                    },
                    "iterations": []
                }
                       
            # 确保iterations字段存在
            if "iterations" not in status_info:
                status_info["iterations"] = []


            # 更新迭代信息
            iteration_info = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "path": str(work_base.relative_to(self.alchemy_dir)),
                "query": query,
                "type": "html",
                "output": str(output_path.relative_to(self.alchemy_dir)),
                "optimization_suggestion": optimization_suggestion
            }

            status_info["iterations"].append(iteration_info)
            
            with open(status_path, "w", encoding="utf-8") as f:
                json.dump(status_info, f, ensure_ascii=False, indent=2)



            # 截图
            screenshot_path = output_dir / f"{artifact_name}_screenshot.png"
            if await self._take_screenshot(html_content, screenshot_path):
                self.logger.info(f"已保存截图: {screenshot_path}")
            else:
                self.logger.warning("截图失败，将跳过保存截图")


            return output_path

        except Exception as e:
            self.logger.error(f"生成HTML并截图时发生错误: {str(e)}")
            traceback.print_exc()
            return None 

    async def _generate_screenshot(self, html_path: Path, screenshot_path: Path) -> bool:
        """使用Playwright生成HTML文件的截图
        
        Args:
            html_path: HTML文件路径
            screenshot_path: 截图保存路径
            
        Returns:
            bool: 截图是否成功
        """
        try:
            self.logger.info(f"正在为HTML文件生成截图: {html_path}")
            
            # 将路径转换为文件URL
            file_url = f"file://{html_path.absolute()}"
            
            async with async_playwright() as p:
                # 启动浏览器
                browser = await p.chromium.launch()
                
                # 创建新页面 - 修改视口大小为600x400，与gallery.html中的卡片比例相匹配
                page = await browser.new_page(viewport={"width": 600, "height": 400})
                
                # 导航到HTML文件
                await page.goto(file_url, wait_until="networkidle")
                
                # 等待页面内容加载完成
                await page.wait_for_load_state("domcontentloaded")
                
                # 额外等待一段时间，确保所有内容都已渲染
                await asyncio.sleep(1)
                
                # 截图
                await page.screenshot(path=str(screenshot_path), full_page=False)
                
                # 关闭浏览器
                await browser.close()
                
            self.logger.info(f"截图已保存: {screenshot_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"生成截图时发生错误: {str(e)}")
            traceback.print_exc()
            return False 