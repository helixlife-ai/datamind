from typing import Dict
from openai import AsyncOpenAI
import json
import logging
import asyncio
from .cache import QueryCache
from ..config.settings import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TARGET_FIELD,
    QUERY_TEMPLATE,
    SEARCH_TOP_K,
    KEYWORD_EXTRACT_PROMPT,
    REFERENCE_TEXT_EXTRACT_PROMPT,
    SUPPORTED_FILE_TYPES,
    DEFAULT_EMBEDDING_MODEL
)
from ..models.model_manager import ModelManager, ModelConfig

class IntentParser:
    """查询意图解析器，负责将自然语言转换为结构化查询条件"""
    
    def __init__(self, api_key: str = DEFAULT_LLM_API_KEY, base_url: str = DEFAULT_LLM_API_BASE):
        """初始化解析器
        
        Args:
            api_key: API密钥，默认使用配置中的DEFAULT_LLM_API_KEY
            base_url: API基础URL，默认使用配置中的DEFAULT_LLM_API_BASE
        """
        self.logger = logging.getLogger(__name__)
        self.model_manager = ModelManager()
        
        # 注册LLM模型配置
        self.model_manager.register_model(ModelConfig(
            name=DEFAULT_LLM_MODEL,
            model_type="api",
            api_key=api_key,
            api_base=base_url
        ))
        
        # 注册Embedding模型配置
        self.model_manager.register_model(ModelConfig(
            name=DEFAULT_EMBEDDING_MODEL,
            model_type="local"
        ))
        
        self.cache = QueryCache()
        self.output_template = QUERY_TEMPLATE
        
    async def parse_query(self, query: str) -> Dict:
        """异步解析自然语言查询"""
        try:
            # 检查缓存
            if cached_result := self.cache.get(query):
                self.logger.info("使用缓存的查询结果")
                return cached_result

            # 并行执行关键词和参考文本提取
            keywords_task = self._extract_keywords(query)
            reference_texts_task = self._extract_reference_texts(query)
            
            keywords, reference_texts = await asyncio.gather(
                keywords_task,
                reference_texts_task,
                return_exceptions=True
            )
            
            # 处理可能的异常
            if isinstance(keywords, Exception):
                self.logger.error(f"关键词提取失败: {str(keywords)}")
                keywords = {"keywords": []}
                
            if isinstance(reference_texts, Exception):
                self.logger.error(f"参考文本提取失败: {str(reference_texts)}")
                reference_texts = {"reference_texts": []}

            # 组装查询条件时传入原始查询
            result = self._build_query_conditions(keywords, reference_texts, query)
            
            # 存入缓存
            self.cache.store(query, result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"查询解析失败: {str(e)}")
            return self.output_template

    async def _extract_keywords(self, query: str, max_retries: int = 3) -> Dict:
        """异步提取结构化查询关键词"""
        for retry in range(max_retries):
            try:
                response = await self.model_manager.generate_llm_response(
                    messages=[
                        {"role": "system", "content": KEYWORD_EXTRACT_PROMPT},
                        {"role": "user", "content": query}
                    ],
                    #response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=256
                )
                
                content = response.choices[0].message.content
                result = json.loads(content)
                
                if not isinstance(result, dict) or "keywords" not in result:
                    raise ValueError("响应格式不正确")
                    
                return result
                
            except Exception as e:
                self.logger.warning(f"关键词提取失败 (尝试 {retry + 1}/{max_retries}): {str(e)}")
                if retry == max_retries - 1:
                    raise
                await asyncio.sleep(1)  # 重试前等待

    async def _extract_reference_texts(self, query: str, max_retries: int = 3) -> Dict:
        """异步提取向量查询参考文本"""
        for retry in range(max_retries):
            try:
                response = await self.model_manager.generate_llm_response(
                    messages=[
                        {"role": "system", "content": REFERENCE_TEXT_EXTRACT_PROMPT},
                        {"role": "user", "content": query}
                    ],
                    #response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=256
                )
                
                content = response.choices[0].message.content
                result = json.loads(content)
                
                if not isinstance(result, dict) or "reference_texts" not in result:
                    raise ValueError("响应格式不正确")
                    
                return result
                
            except Exception as e:
                self.logger.warning(f"参考文本提取失败 (尝试 {retry + 1}/{max_retries}): {str(e)}")
                if retry == max_retries - 1:
                    raise
                await asyncio.sleep(1)  # 重试前等待

    def _build_query_conditions(self, keywords_json: dict, reference_texts_json: dict, original_query: str) -> Dict:
        """组装最终的查询条件"""
        query_conditions = {
            "original_query": original_query,
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