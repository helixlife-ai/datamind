import json
import logging
from typing import Dict, Optional
from pathlib import Path
from datetime import datetime
from ..config.settings import (
    DEFAULT_REASONING_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE
)
from ..llms.model_manager import ModelManager, ModelConfig
import re
import numpy as np
import asyncio

class DateTimeEncoder(json.JSONEncoder):
    """增强版JSON编码器，处理datetime和numpy类型"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

class DeliveryPlanner:
    """交付计划生成器"""
    
    def __init__(self, work_dir: str = "output"):
        self.logger = logging.getLogger(__name__)
        self.work_dir = work_dir
        self.model_manager = ModelManager()
        
        # 注册推理模型配置
        self.model_manager.register_model(ModelConfig(
            name=DEFAULT_REASONING_MODEL,
            model_type="api",
            api_key=DEFAULT_LLM_API_KEY,
            api_base=DEFAULT_LLM_API_BASE
        ))
        
    async def generate_plan(self, 
                          search_plan: Dict,
                          search_results: Dict) -> Optional[Dict]:
        """生成交付计划
        
        Args:
            search_plan: 原始检索计划
            search_results: 检索结果
            
        Returns:
            Optional[Dict]: 交付计划
        """
        try:
            # 构建提示信息
            messages = [
                {
                    "role": "system",
                    "content": """
                    <rule>
                    1. 交付计划是指你准备生成的交付文件的结构和内容
                    2. 交付文件的结构和内容要符合用户的需求
                    3. 交付文件的结构和内容要基于检索结果里的内容
                    4. 说人话
                    </rule>
                    """
                },
                {
                    "role": "user",
                    "content": f"""
                    原始检索需求：{search_plan.get('metadata', {}).get('original_query', '')}
                    
                    检索结果统计：
                    - 结构化数据：{search_results['stats']['structured_count']}条
                    - 向量数据：{search_results['stats']['vector_count']}条
                    - 总计：{search_results['stats']['total']}条
                    
                    数据：
                    1. 结构化数据前3条：
                    {json.dumps([x.get('data', '') for x in search_results['structured'][:3]], ensure_ascii=False, indent=2)}
                    
                    2. 向量数据前3条：
                    {json.dumps([x.get('data', '') for x in search_results['vector'][:3]], ensure_ascii=False, indent=2)}                    
                    """+
                    """
                    根据用户的检索需求和检索结果，生成一份详细的交付计划。                  
                    请以JSON格式输出，包含以下字段：
                    {
                        "delivery_files": {
                            "<file_purpose>": {    // 文件用途
                                "file_name": "",   // 文件名，必须以.html/.md/.csv结尾
                                "topic": "",       // 文件内容主题
                                "description": "", // 文件用途说明
                                "content_structure": {
                                    "sections": [],    // 章节或数据组织方式
                                    "focus_points": [] // 重点关注内容
                                }
                            }
                        }
                    }
                    
                    注意事项：
                    1. 所有JSON字段必须使用标准的键值对格式
                    2. 不要在键名中使用冒号或其他特殊字符
                    3. 所有字符串值使用双引号
                    4. 数组值使用方括号
                    5. 对象值使用花括号
                    6. 确保JSON格式的严格正确性
                    
                    在生成delivery_files时，请注意：
                    1. 根据要交付的内容特点选择合适的文件格式：
                       - .md: 适用于报告、分析说明等富文本内容
                       - .html: 适用于交互式展示、可视化等
                       - .csv: 适用于结构化数据、统计结果等
                    2. 文件命名要清晰表达用途
                    3. 内容结构要符合内容特点和用户需求
                    4. 文件内容要符合用户需求，不要包含无关内容
                    """
                }
            ]
            
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
                f.write(f"模型：{DEFAULT_REASONING_MODEL}\n")
                f.write(f"温度：0.7\n")
                
                f.write("## System Message\n\n")
                f.write("```\n")
                f.write(messages[0]['content'].strip())
                f.write("\n```\n\n")
                
                f.write("## User Message\n\n")
                f.write("```\n")
                f.write(messages[1]['content'].strip())
                f.write("\n```\n\n")
                
                f.write("## 完整提示词(JSON格式)\n\n")
                f.write("```json\n")
                f.write(json.dumps({
                    "timestamp": timestamp,
                    "messages": messages,
                    "model": DEFAULT_REASONING_MODEL,
                    "temperature": 0.7,
                }, ensure_ascii=False, indent=2))
                f.write("\n```\n")
            
            max_retries = 3
            retry_delay = 1  # 初始重试延迟1秒
            delivery_plan = None
            
            for attempt in range(max_retries):
                try:
                    # 调用推理模型
                    response = await self.model_manager.generate_reasoned_response(
                        messages=messages
                    )
                    
                    if not response:
                        self.logger.error(f"模型未返回响应（尝试 {attempt+1}/{max_retries}）")
                        continue
                    
                    # 解析响应内容
                    reasoning_content = response.choices[0].message.reasoning_content
                    content = response.choices[0].message.content
                    self.logger.info(f"推理内容: {reasoning_content}")
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
                                self.logger.debug("成功直接解析响应内容为JSON")
                            except json.JSONDecodeError as je:
                                self.logger.error(f"直接解析响应内容失败: {str(je)}")
                                self.logger.debug(f"响应内容: {content}")
                                raise
                            
                        if not isinstance(delivery_plan, dict):
                            raise ValueError("解析后的内容不是有效的字典格式")
                            
                    except json.JSONDecodeError as e:
                        self.logger.error(f"解析响应内容失败: {str(e)}")
                        return None
                    except ValueError as e:
                        self.logger.error(str(e))
                        return None
                    except Exception as e:
                        self.logger.error(f"处理响应内容时发生未预期的错误: {str(e)}")
                        return None
                    
                    if delivery_plan:
                        break
                    
                except (json.JSONDecodeError, ConnectionError, TimeoutError) as e:
                    self.logger.warning(f"尝试 {attempt+1}/{max_retries} 失败: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                        continue
                    else:
                        self.logger.error("达到最大重试次数")
                        return None
                    
            if not delivery_plan:
                self.logger.error("所有重试尝试均失败")
                return None
            
            # 保存推理过程
            reasoning_file = plan_dir / "reasoning_process.md"
            with reasoning_file.open('w', encoding='utf-8') as f:
                f.write("# 交付计划推理过程\n\n")
                f.write("## 输入信息\n")
                f.write(f"- 原始检索需求：{search_plan.get('metadata', {}).get('original_query', '')}\n")
                f.write(f"- 结构化数据数量：{search_results['stats']['structured_count']}\n")
                f.write(f"- 向量数据数量：{search_results['stats']['vector_count']}\n")
                
                f.write("\n## 数据分析\n")
                if search_results["structured"]:
                    f.write("\n### 结构化数据\n")
                    for i, item in enumerate(search_results["structured"][:3], 1):
                        content = json.loads(item.get('data', '{}')).get('content', '')
                        f.write(f"\n{i}. {content[:200]}...\n")
                
                if search_results["vector"]:
                    f.write("\n### 向量数据\n")
                    for i, item in enumerate(search_results["vector"][:3], 1):
                        content = json.loads(item.get('data', '{}')).get('content', '')
                        f.write(f"\n{i}. {content[:200]}...\n")
                
                f.write("\n## 推理过程\n")
                if reasoning_content:
                    f.write(reasoning_content)
                else:
                    f.write("(推理过程未提供)\n")
                
                f.write("\n## 模型响应\n")
                f.write("```json\n")
                f.write(json.dumps(delivery_plan, ensure_ascii=False, indent=2))
                f.write("\n```\n")
            
            # 保存检索结果
            search_results_file = plan_dir / "search_results.json"
            results_to_save = {
                "structured_results": search_results["structured"][:10],
                "vector_results": search_results["vector"][:10],
                "stats": search_results["stats"],
                "insights": search_results["insights"],
                "context": search_results["context"]
            }

            # 新增：保存原始检索计划
            search_plan_file = plan_dir / "search_plan.json"
            with search_plan_file.open('w', encoding='utf-8') as f:
                json.dump(search_plan, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)

            # 使用自定义编码器保存JSON
            with search_results_file.open('w', encoding='utf-8') as f:
                json.dump(results_to_save, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            
            # 保存交付计划
            plan_file = plan_dir / "delivery_plan.json"
            
            final_delivery_plan = {
                'metadata': {
                    'original_query': search_plan.get('metadata', {}).get('original_query', ''),
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
                f.write(f"原始检索需求：{search_plan.get('metadata', {}).get('original_query', '')}\n\n")
                f.write("## 文件说明\n\n")
                f.write("- prompts.md: 推理提示词配置\n")
                f.write("- search_plan.json: 原始检索计划\n")
                f.write("- search_results.json: 检索结果数据\n")
                f.write("- reasoning_process.md: 推理过程详情\n")
                f.write("- delivery_plan.json: 生成的交付计划\n")
            
            # 更新文件路径
            final_delivery_plan['_file_paths'] = {
                'base_dir': str(plan_dir),
                'reasoning_process': str(reasoning_file),
                'delivery_plan': str(plan_file),
                'search_results': str(search_results_file),
                'search_plan': str(search_plan_file),
                'readme': str(readme_file),
                'prompts': str(prompts_file)
            }
            
            return final_delivery_plan
            
        except Exception as e:
            self.logger.error(f"生成交付计划时发生错误: {str(e)}")
            return None 