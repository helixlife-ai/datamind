import json
import logging
from typing import Dict, Optional
from pathlib import Path
from datetime import datetime
from ..core.reasoning import ReasoningEngine
import re
import asyncio
from ..utils.common import DateTimeEncoder
from ..utils.stream_logger import StreamLineHandler

class DeliveryPlanner:
    """交付计划生成器"""
    
    def __init__(self, work_dir: str = "output", reasoning_engine: Optional[ReasoningEngine] = None, logger: Optional[logging.Logger] = None):
        """初始化交付计划生成器
        
        Args:
            work_dir: 工作目录
            reasoning_engine: 推理引擎实例，用于生成交付计划
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.work_dir = work_dir
        self.reasoning_engine = reasoning_engine
        
        if not self.reasoning_engine:
            self.logger.warning("未配置推理引擎，无法生成交付计划")
        
    async def generate_plan(self, results: Dict) -> Optional[Dict]:
        """生成交付计划

        Args:
            results: 推理结果
                    
        Returns:
            Optional[Dict]: 交付计划
        """
        try:
            if not self.reasoning_engine:
                raise ValueError("未配置推理引擎，无法生成交付计划")
                            
            # 构建JSON模板
            json_template = {
                "delivery_files": {
                    "<file_purpose>": {    # 文件用途
                        "file_name": "",   # 文件名，必须以.html/.md/.csv结尾
                        "topic": "",       # 文件内容主题
                        "description": "", # 文件用途说明
                        "content_structure": {
                            "sections": [],    # 章节或数据组织方式
                            "focus_points": [] # 重点关注内容
                        }
                    }
                }
            }
                
            # 添加用户消息
            message = f"""
                [用户的意图 begin]
                {json.dumps(results['results']['parsed_intent'], ensure_ascii=False, indent=2)}
                [用户的意图 end]
                
                根据用户的意图，生成一份详细的交付计划。
                1. 交付计划是指你准备生成的交付文件的结构和内容
                2. 交付文件的结构和内容要符合用户的意图
                               
                请以JSON格式输出，包含以下字段：
                {json.dumps(json_template, ensure_ascii=False, indent=2)}
                
                注意事项：
                1. 所有JSON字段必须使用标准的键值对格式
                2. 不要在键名中使用冒号或其他特殊字符
                3. 所有字符串值使用双引号
                4. 数组值使用方括号
                5. 对象值使用花括号
                6. 确保JSON格式的严格正确性
                
                在生成delivery_files时，请注意：
                1. 根据要交付的内容特点选择合适的文件格式，下面是可以选择的格式：
                   - .md
                   - .html
                   - .csv
                2. 文件命名要清晰表达用途
            """
            
            self.reasoning_engine.add_message("user", message)
            
            # 生成输出目录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path(self.work_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建本次推理的目录
            plan_dir = output_dir
            
            # 保存提示词为markdown格式
            prompts_file = plan_dir / "prompts.md"
            with prompts_file.open('w', encoding='utf-8') as f:
                f.write("# 推理提示词配置\n\n")
                f.write(f"生成时间：{timestamp}\n")
                f.write(f"模型：{self.reasoning_engine.model_name}\n")
                f.write(f"温度：0.7\n")
                                
                f.write("## User Message\n\n")
                f.write("```\n")
                # 获取最后一条消息的内容
                last_message = self.reasoning_engine.messages[-1]
                f.write(last_message.content)  # ChatMessage对象直接访问content属性
                f.write("\n```\n\n")
                
                f.write("## 完整提示词(JSON格式)\n\n")
                f.write("```json\n")
                # 将消息历史转换为可序列化的格式
                serializable_messages = []
                for msg in self.reasoning_engine.messages:
                    serializable_messages.append({
                        'role': msg.role,
                        'content': msg.content,
                        'timestamp': msg.timestamp.isoformat(),
                        'metadata': msg.metadata
                    })
                
                f.write(json.dumps({
                    "timestamp": timestamp,
                    "messages": serializable_messages,
                    "model": self.reasoning_engine.model_name,
                    "temperature": 0.7,
                }, ensure_ascii=False, indent=2, cls=DateTimeEncoder))
                f.write("\n```\n")
            
            max_retries = 3
            retry_delay = 1  # 初始重试延迟1秒
            delivery_plan = None
            
            for attempt in range(max_retries):
                try:
                    # 使用流式输出收集完整响应
                    content = ""
                    async for chunk in self.reasoning_engine.get_stream_response(
                        temperature=0.7,
                        metadata={'stage': 'delivery_planning'}
                    ):
                        content += chunk
                        self.logger.info(f"\r生成交付计划: {content}")
                    
                    if not content:
                        self.logger.error(f"推理引擎未返回响应（尝试 {attempt+1}/{max_retries}）")
                        continue
                    
                    self.logger.info(f"响应内容: {content}")
                    
                    try:
                        # 使用正则表达式提取JSON内容
                        json_pattern = r'```json\n([\s\S]*?)\n```'
                        json_match = re.search(json_pattern, content)
                        
                        if json_match:
                            json_content = json_match.group(1).strip()
                            try:
                                delivery_plan = json.loads(json_content)
                                self.logger.debug(f"成功从markdown格式解析JSON")
                            except json.JSONDecodeError as je:
                                self.logger.warning(f"从markdown格式解析JSON失败: {str(je)}")
                                cleaned_content = json_content.replace('\r', '').replace('\t', '  ')
                                try:
                                    delivery_plan = json.loads(cleaned_content)
                                    self.logger.debug("清理特殊字符后成功解析JSON")
                                except json.JSONDecodeError as je2:
                                    self.logger.error(f"清理后仍然无法解析JSON: {str(je2)}")
                                    self.logger.debug(f"问题内容: {cleaned_content}")
                                    raise
                        else:
                            self.logger.warning("未找到markdown格式的JSON，尝试直接解析响应内容")
                            try:
                                delivery_plan = json.loads(content)
                                self.logger.info("成功直接解析响应内容为JSON")
                            except json.JSONDecodeError as je:
                                self.logger.error(f"直接解析响应内容失败: {str(je)}")
                                self.logger.info(f"响应内容: {content}")
                                raise
                            
                        if not isinstance(delivery_plan, dict):
                            raise ValueError("解析后的内容不是有效的字典格式")
                            
                        if delivery_plan:
                            break
                            
                    except json.JSONDecodeError as e:
                        self.logger.error(f"解析响应内容失败: {str(e)}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        return None
                        
                except Exception as e:
                    self.logger.error(f"处理响应时发生错误: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    raise
            
            if not delivery_plan:
                self.logger.error("所有重试尝试均失败")
                return None
            
            # 保存推理过程
            reasoning_file = plan_dir / "reasoning_process.md"
            with reasoning_file.open('w', encoding='utf-8') as f:
                f.write("# 交付计划推理过程\n\n")
                
                f.write("```json\n")
                f.write(json.dumps(delivery_plan, ensure_ascii=False, indent=2))
                f.write("\n```\n")

            
            # 保存交付计划
            plan_file = plan_dir / "delivery_plan.json"
            
            final_delivery_plan = {
                'metadata': {
                    'query': results['results']['query'],
                    'generated_at': datetime.now().isoformat()
                },
                **delivery_plan
            }
            
            with plan_file.open('w', encoding='utf-8') as f:
                json.dump(final_delivery_plan, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            
            # 生成README文件
            readme_file = plan_dir / "README.md"
            with readme_file.open('w', encoding='utf-8') as f:
                f.write("# 检索结果与交付计划\n\n")
                f.write(f"生成时间：{timestamp}\n\n")
                f.write("## 文件说明\n\n")
                f.write("- prompts.md: 推理提示词配置\n")
                f.write("- reasoning_process.md: 推理过程详情\n")
                f.write("- delivery_plan.json: 生成的交付计划\n")
            
            # 更新文件路径
            final_delivery_plan['_file_paths'] = {
                'base_dir': str(plan_dir),
                'reasoning_process': str(reasoning_file),
                'delivery_plan': str(plan_file),
                'readme': str(readme_file),
                'prompts': str(prompts_file)
            }
            
            return final_delivery_plan
            
        except Exception as e:
            self.logger.error(f"生成交付计划时发生错误: {str(e)}")
            return None 