from typing import Dict
from openai import OpenAI
import json
import logging
from ..config.settings import (
    DEEPSEEK_MODEL, 
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TARGET_FIELD,
    QUERY_TEMPLATE
)

class IntentParser:
    """查询意图解析器，负责将自然语言转换为结构化查询条件"""
    
    def __init__(self, api_key: str):
        """初始化解析器
        
        Args:
            api_key: DeepSeek API密钥
        """
        self.logger = logging.getLogger(__name__)
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        self.output_template = QUERY_TEMPLATE
        
    def parse_query(self, query: str) -> Dict:
        """解析自然语言查询
        
        Args:
            query: 用户输入的自然语言查询
            
        Returns:
            Dict: 结构化查询条件
        """
        try:
            response = self.client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": self._build_system_prompt()},
                    {"role": "user", "content": query}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=512
            )
            
            raw_output = response.choices[0].message.content
            return self._validate_output(raw_output)
            
        except Exception as e:
            self.logger.error(f"API调用失败: {str(e)}")
            return self.output_template
        
    def _build_system_prompt(self) -> str:
        """构建系统提示词
        
        Returns:
            str: 系统提示词
        """
        return f"""
你是一个专业的查询解析器，负责将自然语言转换为结构化查询条件。请严格按照以下规则处理：

1. 输出格式：必须为合规的JSON，符合模板：
{json.dumps(self.output_template, indent=2, ensure_ascii=False)}

2. 时间解析规则：
   - "去年" → 当前年份-1
   - "上个月" → 当前月份-1
   - "Q2" → 4月1日至6月30日

3. 地域标准化：
   - "上海" → region IN ('上海')
   - "长三角" → region IN ('上海','江苏','浙江','安徽')

4. 相似度逻辑：
   - "相似度高" → similarity_threshold:0.8
   - "相关" → similarity_threshold:0.6

5. 字段映射：
   - "作者" → author
   - "发布日期" → publish_date
   - "标题" → title

请确保输出内容安全，过滤掉任何可能引发SQL注入的特殊字符。
        """
        
    def _validate_output(self, raw_json: str) -> Dict:
        """验证并修复模型输出
        
        Args:
            raw_json: 模型原始输出
            
        Returns:
            Dict: 验证后的结构化查询条件
        """
        try:
            parsed = json.loads(raw_json)
            
            # 强制类型校验和默认值处理
            validated = {
                "data_subject": str(parsed.get("data_subject", "")),
                "structured_conditions": {
                    "time_range": {
                        "start": str(parsed.get("structured_conditions", {})
                                     .get("time_range", {})
                                     .get("start", "")),
                        "end": str(parsed.get("structured_conditions", {})
                                   .get("time_range", {})
                                   .get("end", ""))
                    },
                    "filters": list(filter(None, parsed.get("structured_conditions", {})
                                        .get("filters", []))),
                    "exclusions": list(filter(None, parsed.get("structured_conditions", {})
                                           .get("exclusions", [])))
                },
                "vector_conditions": {
                    "target_field": str(parsed.get("vector_conditions", {})
                                      .get("target_field", DEFAULT_TARGET_FIELD)),
                    "similarity_threshold": min(max(float(
                        parsed.get("vector_conditions", {})
                              .get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)
                    ), 0.0), 1.0),
                    "reference_keywords": str(parsed.get("vector_conditions", {})
                                            .get("reference_keywords", ""))
                },
                "result_format": {
                    "required_fields": list(filter(None, parsed.get("result_format", {})
                                                .get("required_fields", []))),
                    "display_preferences": str(parsed.get("result_format", {})
                                             .get("display_preferences", ""))
                }
            }
            
            self.logger.debug(f"验证后的查询条件: {json.dumps(validated, indent=2, ensure_ascii=False)}")
            return validated
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {str(e)}")
            return self.output_template
        except Exception as e:
            self.logger.error(f"验证过程出错: {str(e)}")
            return self.output_template 