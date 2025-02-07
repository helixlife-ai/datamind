from typing import Dict
from openai import OpenAI
import json
import logging
from ..config.settings import (
    DEEPSEEK_MODEL, 
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TARGET_FIELD,
    QUERY_TEMPLATE,
    SEARCH_TOP_K,
    KEYWORD_EXTRACT_PROMPT,
    REFERENCE_TEXT_EXTRACT_PROMPT,
    SUPPORTED_FILE_TYPES
)

class IntentParser:
    """查询意图解析器，负责将自然语言转换为结构化查询条件"""
    
    def __init__(self, api_key: str, base_url: str):
        """初始化解析器
        
        Args:
            api_key: DeepSeek API密钥
        """
        self.logger = logging.getLogger(__name__)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
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
            # 步骤1: 提取结构化查询关键词
            keywords = self._extract_keywords(query)
            self.logger.info(f"提取的关键词: {keywords}")
            
            # 步骤2: 提取向量查询参考文本
            reference_texts = self._extract_reference_texts(query)
            self.logger.info(f"提取的参考文本: {reference_texts}")
            # 步骤3: 组装查询条件
            return self._build_query_conditions(keywords, reference_texts)
            
        except Exception as e:
            self.logger.error(f"查询解析失败: {str(e)}")
            return self.output_template

    def _extract_keywords(self, query: str, max_retries: int = 3) -> list:
        """提取结构化查询关键词
        
        Args:
            query: 用户查询文本
            max_retries: 最大重试次数
            
        Returns:
            list: 提取的关键词列表
        """
        retry_count = 0
        while retry_count < max_retries:
            try:
                response = self.client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": KEYWORD_EXTRACT_PROMPT},
                        {"role": "user", "content": query}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=256
                )
                
                # 验证响应格式
                content = response.choices[0].message.content
                result = json.loads(content)
                if not isinstance(result, dict) or "keywords" not in result:
                    raise ValueError("响应格式不正确")
                    
                return result
                
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.warning(f"关键词提取失败 (尝试 {retry_count + 1}/{max_retries}): {str(e)}")
                retry_count += 1
                if retry_count == max_retries:
                    self.logger.error("关键词提取最终失败")
                    return {"keywords": []}
                
            except Exception as e:
                self.logger.error(f"关键词提取发生未预期错误: {str(e)}")
                return {"keywords": []}

    def _extract_reference_texts(self, query: str, max_retries: int = 3) -> list:
        """提取向量查询参考文本
        
        Args:
            query: 用户查询文本
            max_retries: 最大重试次数
            
        Returns:
            list: 提取的参考文本列表
        """
        retry_count = 0
        while retry_count < max_retries:
            try:
                response = self.client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": REFERENCE_TEXT_EXTRACT_PROMPT},
                        {"role": "user", "content": query}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=256
                )
                
                # 验证响应格式
                content = response.choices[0].message.content
                result = json.loads(content)
                if not isinstance(result, dict) or "reference_texts" not in result:
                    raise ValueError("响应格式不正确")
                    
                return result
                
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.warning(f"参考文本提取失败 (尝试 {retry_count + 1}/{max_retries}): {str(e)}")
                retry_count += 1
                if retry_count == max_retries:
                    self.logger.error("参考文本提取最终失败")
                    return {"reference_texts": []}
                
            except Exception as e:
                self.logger.error(f"参考文本提取发生未预期错误: {str(e)}")
                return {"reference_texts": []}

    def _build_query_conditions(self, keywords_json: dict, reference_texts_json: dict) -> Dict:
        """组装最终的查询条件"""
        query_conditions = {
            "structured_conditions": [],
            "vector_conditions": [],
            "result_format": {
                "required_fields": ["_file_name", "data"],
                "display_preferences": ""
            }
        }
        
        # 处理结构化查询条件
        for keyword in keywords_json.get("keywords", []):
            condition = {
                "time_range": {"start": "", "end": ""},
                "file_types": SUPPORTED_FILE_TYPES,
                "keyword": keyword,
                "exclusions": []
            }
            query_conditions["structured_conditions"].append(condition)
        
        # 处理向量查询条件
        for text in reference_texts_json.get("reference_texts", []):
            condition = {
                "reference_text": text,
                "similarity_threshold": DEFAULT_SIMILARITY_THRESHOLD,
                "top_k": SEARCH_TOP_K
            }
            query_conditions["vector_conditions"].append(condition)
        
        return query_conditions

    def _build_system_prompt(self) -> str:
        """此方法可以删除，因为不再使用统一的系统提示词"""
        pass

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
                "structured_conditions": [],
                "vector_conditions": [],
                "result_format": {
                    "required_fields": list(filter(None, parsed.get("result_format", {})
                                                .get("required_fields", ["*"]))),
                    "display_preferences": str(parsed.get("result_format", {})
                                             .get("display_preferences", ""))
                }
            }
            
            # 处理结构化条件数组
            for condition in parsed.get("structured_conditions", [{}]):
                validated["structured_conditions"].append({
                    "time_range": {
                        "start": str(condition.get("time_range", {}).get("start", "")),
                        "end": str(condition.get("time_range", {}).get("end", ""))
                    },
                    "file_types": list(filter(None, condition.get("file_types", []))),
                    "keyword": str(condition.get("keyword", "")),
                    "exclusions": list(filter(None, condition.get("exclusions", [])))
                })
                
            # 处理向量条件数组
            for condition in parsed.get("vector_conditions", [{}]):
                validated["vector_conditions"].append({
                    "reference_text": str(condition.get("reference_text", "")),
                    "similarity_threshold": min(max(float(
                        condition.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)
                    ), 0.0), 1.0),
                    "top_k": int(condition.get("top_k", SEARCH_TOP_K))
                })
            
            self.logger.debug(f"验证后的查询条件: {json.dumps(validated, indent=2, ensure_ascii=False)}")
            return validated
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {str(e)}")
            return self.output_template
        except Exception as e:
            self.logger.error(f"验证过程出错: {str(e)}")
            return self.output_template 