import json
import logging
from typing import Dict, Optional
from pathlib import Path
from datetime import datetime
from ..core.reasoning import ReasoningEngine
import re
import asyncio
from ..utils.common import DateTimeEncoder
import time

class DeliveryPlanner:
    """交付计划生成器"""
    
    def __init__(self, work_dir: str = "output", reasoning_engine: Optional[ReasoningEngine] = None, logger: Optional[logging.Logger] = None):
        """初始化交付计划生成器
        
        Args:
            work_dir: 工作目录
            reasoning_engine: 推理引擎实例，用于生成交付计划
            logger: 可选，日志记录器实例
        """
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger(__name__)
        self.reasoning_engine = reasoning_engine
        
        if not self.reasoning_engine:
            self.logger.warning("未配置推理引擎，无法生成交付计划")
        
    async def generate_plan(self, results: Dict) -> Optional[Dict]:
        """生成交付计划"""
        try:
            # 创建计划目录
            plan_dir = self.work_dir / "delivery_plans" 
            plan_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存输入结果
            input_dir = plan_dir / "inputs"
            input_dir.mkdir(exist_ok=True)
            
            with open(input_dir / "search_results.json", "w", encoding="utf-8") as f:
                json.dump(results['results'], f, ensure_ascii=False, indent=2)
            
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
            
            # 保存模板
            with open(plan_dir / "template.json", "w", encoding="utf-8") as f:
                json.dump(json_template, f, ensure_ascii=False, indent=2)
                
            # 添加用户消息
            message = f"""[用户的意图 begin]
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
            
            # 保存提示词
            prompts_dir = plan_dir / "prompts"
            prompts_dir.mkdir(exist_ok=True)
            
            with open(prompts_dir / "delivery_plan_prompt.md", "w", encoding="utf-8") as f:
                f.write("# 交付计划生成提示词\n\n")
                f.write("## 提示词内容\n\n")
                f.write("```\n")
                f.write(message)
                f.write("\n```\n")
            
            # 保存推理历史
            with open(prompts_dir / "reasoning_history.json", "w", encoding="utf-8") as f:
                history = [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp.isoformat(),
                        "metadata": msg.metadata
                    }
                    for msg in self.reasoning_engine.messages
                ]
                json.dump(history, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            
            max_retries = 3
            retry_delay = 1
            delivery_plan = None
            
            # 保存生成过程
            generation_dir = plan_dir / "generation"
            generation_dir.mkdir(exist_ok=True)
            
            for attempt in range(max_retries):
                try:
                    content = ""
                    async for chunk in self.reasoning_engine.get_stream_response(
                        temperature=0.7,
                        metadata={'stage': 'delivery_planning'}
                    ):
                        content += chunk
                        self.logger.info(f"\r生成交付计划: {content}")
                    
                    # 保存原始响应
                    with open(generation_dir / f"attempt_{attempt+1}_response.txt", "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    if not content:
                        self.logger.error(f"推理引擎未返回响应（尝试 {attempt+1}/{max_retries}）")
                        continue
                    
                    try:
                        # 解析JSON内容
                        delivery_plan = self._parse_json_response(content)
                        if delivery_plan:
                            # 保存成功的解析结果
                            with open(generation_dir / f"attempt_{attempt+1}_parsed.json", "w", encoding="utf-8") as f:
                                json.dump(delivery_plan, f, ensure_ascii=False, indent=2)
                            break
                            
                    except Exception as e:
                        self.logger.error(f"解析响应内容失败 (尝试 {attempt+1}): {str(e)}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        raise
                        
                except Exception as e:
                    self.logger.error(f"生成响应时发生错误 (尝试 {attempt+1}): {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    raise
            
            if not delivery_plan:
                self.logger.error("所有重试尝试均失败")
                return None
            
            # 保存最终计划
            final_plan = {
                'metadata': {
                    'query': results['results']['query'],
                    'generated_at': datetime.now().isoformat(),
                    'model': self.reasoning_engine.model_name,
                    'temperature': 0.7
                },
                **delivery_plan
            }
            
            with open(plan_dir / "final_plan.json", "w", encoding="utf-8") as f:
                json.dump(final_plan, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            
            # 生成README
            with open(plan_dir / "README.md", "w", encoding="utf-8") as f:
                f.write("# 交付计划生成记录\n\n")
                f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("## 目录结构\n\n")
                f.write("- inputs/: 输入数据\n")
                f.write("- prompts/: 提示词和推理历史\n")
                f.write("- generation/: 生成过程记录\n")
                f.write("- template.json: 计划模板\n")
                f.write("- final_plan.json: 最终交付计划\n")
            
            # 更新文件路径
            final_plan['_file_paths'] = {
                'base_dir': str(plan_dir),
                'inputs': str(input_dir),
                'prompts': str(prompts_dir),
                'generation': str(generation_dir),
                'template': str(plan_dir / "template.json"),
                'final_plan': str(plan_dir / "final_plan.json"),
                'readme': str(plan_dir / "README.md")
            }
            
            return final_plan
            
        except Exception as e:
            self.logger.error(f"生成交付计划时发生错误: {str(e)}")
            return None
            
    def _parse_json_response(self, content: str) -> Optional[Dict]:
        """解析JSON响应"""
        try:
            # 使用正则表达式提取JSON内容
            json_pattern = r'```json\n([\s\S]*?)\n```'
            json_match = re.search(json_pattern, content)
            
            if json_match:
                json_content = json_match.group(1).strip()
                try:
                    delivery_plan = json.loads(json_content)
                    self.logger.debug("成功从markdown格式解析JSON")
                    return delivery_plan
                except json.JSONDecodeError as je:
                    self.logger.warning(f"从markdown格式解析JSON失败: {str(je)}")
                    cleaned_content = json_content.replace('\r', '').replace('\t', '  ')
                    delivery_plan = json.loads(cleaned_content)
                    self.logger.debug("清理特殊字符后成功解析JSON")
                    return delivery_plan
            else:
                self.logger.warning("未找到markdown格式的JSON，尝试直接解析响应内容")
                delivery_plan = json.loads(content)
                self.logger.info("成功直接解析响应内容为JSON")
                return delivery_plan
                
        except Exception as e:
            self.logger.error(f"解析JSON响应失败: {str(e)}")
            return None 