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
from ..models.model_manager import ModelManager, ModelConfig

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
                          original_plan: Dict,
                          search_results: Dict) -> Optional[Dict]:
        """生成交付计划
        
        Args:
            original_plan: 原始检索计划
            search_results: 检索结果
            
        Returns:
            Optional[Dict]: 交付计划，包含建议的数据组织和展示方式
        """
        try:
            # 构建提示信息
            messages = [
                {
                    "role": "system",
                    "content": """你是一个专业的数据分析和内容组织专家。请根据用户的检索需求和获得的结果，
                    生成一个详细的交付计划。计划应包含：
                    1. 数据组织方式：如何对结构化数据和向量检索结果进行分类、聚合和关联
                    2. 内容提取建议：重点内容、关键观点、核心论述等
                    3. 可视化建议：合适的图表类型、展示重点、布局建议等
                    4. 交付格式建议：文档结构、展示顺序、重点突出方式等
                    5. 补充建议：额外的分析维度、关联信息等
                    
                    请以JSON格式输出，包含以下字段：
                    {
                        "data_organization": {
                            "structured_data": [],  // 结构化数据组织方式
                            "vector_data": [],     // 向量数据组织方式
                            "data_relations": []   // 数据关联建议
                        },
                        "key_insights": {
                            "main_points": [],     // 主要观点
                            "quotes": [],          // 关键引用
                            "trends": []           // 趋势和规律
                        },
                        "visualization": {
                            "charts": [],          // 建议的图表
                            "layout": {},          // 布局建议
                            "highlights": []       // 重点突出建议
                        },
                        "delivery_format": {
                            "structure": [],       // 文档结构
                            "sections": [],        // 章节安排
                            "emphasis": []         // 重点标注建议
                        },
                        "additional_suggestions": []  // 补充建议
                    }"""
                },
                {
                    "role": "user",
                    "content": f"""
                    原始检索需求：{original_plan.get('metadata', {}).get('original_query', '')}
                    
                    检索结果统计：
                    - 结构化数据：{search_results['stats']['structured_count']}条
                    - 向量数据：{search_results['stats']['vector_count']}条
                    - 总计：{search_results['stats']['total']}条
                    
                    数据示例：
                    1. 结构化数据前3条：
                    {json.dumps([x.get('data', '') for x in search_results['structured'][:3]], ensure_ascii=False, indent=2)}
                    
                    2. 向量数据前3条：
                    {json.dumps([x.get('data', '') for x in search_results['vector'][:3]], ensure_ascii=False, indent=2)}
                    
                    请基于以上信息生成详细的交付计划。重点关注：
                    1. 如何有效组织和展示这些数据
                    2. 如何突出重要观点和见解
                    3. 如何让最终交付物更有价值
                    """
                }
            ]
            
            # 生成输出目录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path(self.work_dir) / "delivery_plans"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建本次推理的目录
            plan_dir = output_dir / f"plan_{timestamp}"
            plan_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存提示词为markdown格式
            prompts_file = plan_dir / "prompts.md"
            with prompts_file.open('w', encoding='utf-8') as f:
                f.write("# 推理提示词配置\n\n")
                f.write(f"生成时间：{timestamp}\n")
                f.write(f"模型：{DEFAULT_REASONING_MODEL}\n")
                f.write(f"温度：0.7\n")
                f.write(f"最大tokens：2000\n\n")
                
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
                    "max_tokens": 2000
                }, ensure_ascii=False, indent=2))
                f.write("\n```\n")
            
            # 调用推理模型
            response = await self.model_manager.generate_reasoned_response(
                messages=messages
            )
            
            if response:
                try:
                    
                    # 解析响应内容 - 更新字段访问方式
                    reasoning_content = response.choices[0].message.reasoning_content
                    content = response.choices[0].message.content
                    self.logger.info(f"推理内容: {reasoning_content}")
                    self.logger.info(f"响应内容: {content}")
                    
                    try:
                        # 使用正则表达式提取JSON内容
                        import re
                        # 匹配```json后的换行符到下一个```之间的内容
                        json_pattern = r'```json\n([\s\S]*?)\n```'
                        json_match = re.search(json_pattern, content)
                        
                        if json_match:
                            json_content = json_match.group(1).strip()  # 获取第一个捕获组并去除首尾空白
                            try:
                                delivery_plan = json.loads(json_content)
                                self.logger.debug(f"成功从markdown格式解析JSON")
                            except json.JSONDecodeError as je:
                                self.logger.warning(f"从markdown格式解析JSON失败: {str(je)}")
                                # 尝试清理内容中的特殊字符
                                cleaned_content = json_content.replace('\r', '').replace('\t', '  ')
                                try:
                                    delivery_plan = json.loads(cleaned_content)
                                    self.logger.debug("清理特殊字符后成功解析JSON")
                                except json.JSONDecodeError as je2:
                                    self.logger.error(f"清理后仍然无法解析JSON: {str(je2)}")
                                    self.logger.debug(f"问题内容: {cleaned_content}")
                                    raise
                        else:
                            # 如果没有找到markdown格式的JSON，尝试直接解析整个响应
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
                    
                    if not delivery_plan:
                        self.logger.error("响应内容为空或格式错误")
                        return None
                        
                    # 保存推理过程 - 使用reasoning_content
                    reasoning_file = plan_dir / "reasoning_process.md"
                    with reasoning_file.open('w', encoding='utf-8') as f:
                        f.write("# 交付计划推理过程\n\n")
                        f.write("## 输入信息\n")
                        f.write(f"- 原始检索需求：{original_plan.get('metadata', {}).get('original_query', '')}\n")
                        f.write(f"- 结构化数据数量：{search_results['stats']['structured_count']}\n")
                        f.write(f"- 向量数据数量：{search_results['stats']['vector_count']}\n")
                        
                        f.write("\n## 数据分析\n")
                        if search_results["structured"]:
                            f.write("\n### 结构化数据示例\n")
                            for i, item in enumerate(search_results["structured"][:3], 1):
                                content = json.loads(item.get('data', '{}')).get('content', '')
                                f.write(f"\n{i}. {content[:200]}...\n")
                        
                        if search_results["vector"]:
                            f.write("\n### 向量数据示例\n")
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

                    # 添加JSON序列化器来处理datetime、Timestamp和numpy数值类型
                    class DateTimeEncoder(json.JSONEncoder):
                        def default(self, obj):
                            import numpy as np
                            if hasattr(obj, 'isoformat'):
                                return obj.isoformat()
                            elif hasattr(obj, 'timestamp'):
                                return obj.timestamp()
                            # 处理numpy数值类型
                            elif isinstance(obj, (np.int8, np.int16, np.int32, np.int64,
                                               np.uint8, np.uint16, np.uint32, np.uint64)):
                                return int(obj)
                            elif isinstance(obj, (np.float16, np.float32, np.float64)):
                                return float(obj)
                            elif isinstance(obj, np.ndarray):
                                return obj.tolist()
                            elif isinstance(obj, np.bool_):
                                return bool(obj)
                            # 处理其他numpy标量类型
                            elif np.isscalar(obj):
                                return obj.item()
                            return super().default(obj)

                    # 使用自定义编码器保存JSON
                    with search_results_file.open('w', encoding='utf-8') as f:
                        json.dump(results_to_save, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
                    
                    # 保存交付计划
                    plan_file = plan_dir / "delivery_plan.json"
                    with plan_file.open('w', encoding='utf-8') as f:
                        json.dump(delivery_plan, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
                    
                    # 生成README文件
                    readme_file = plan_dir / "README.md"
                    with readme_file.open('w', encoding='utf-8') as f:
                        f.write("# 检索结果与交付计划\n\n")
                        f.write(f"生成时间：{timestamp}\n\n")
                        f.write(f"原始检索需求：{original_plan.get('metadata', {}).get('original_query', '')}\n\n")
                        f.write("## 文件说明\n\n")
                        f.write("- prompts.md: 推理提示词配置（便于复制使用）\n")
                        f.write("- search_results.json: 检索结果数据\n")
                        f.write("- reasoning_process.md: 推理过程详情\n")
                        f.write("- delivery_plan.json: 生成的交付计划\n")
                    
                    # 更新文件路径
                    delivery_plan['_file_paths'] = {
                        'base_dir': str(plan_dir),
                        'reasoning_process': str(reasoning_file),
                        'delivery_plan': str(plan_file),
                        'search_results': str(search_results_file),
                        'readme': str(readme_file),
                        'prompts': str(prompts_file)
                    }
                    
                    return delivery_plan
                    
                except Exception as e:
                    self.logger.error(f"处理模型响应时发生错误: {str(e)}")
                    return None
            else:
                self.logger.error("模型未返回响应")
                return None
                
        except Exception as e:
            self.logger.error(f"生成交付计划时发生错误: {str(e)}")
            return None 