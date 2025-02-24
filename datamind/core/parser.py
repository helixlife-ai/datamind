from typing import Dict, Optional
import json
import logging
import asyncio
from pathlib import Path
import time
from ..core.reasoning import ReasoningEngine
from ..config.settings import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_API_BASE,
    DEFAULT_SIMILARITY_THRESHOLD,
    QUERY_TEMPLATE,
    SEARCH_TOP_K,
    KEYWORD_EXTRACT_PROMPT,
    REFERENCE_TEXT_EXTRACT_PROMPT,
    SUPPORTED_FILE_TYPES,
    DEFAULT_EMBEDDING_MODEL
)
from ..llms.model_manager import ModelManager, ModelConfig
from dataclasses import dataclass

@dataclass
class CacheEntry:
    result: Dict
    timestamp: float
    
class QueryCache:
    """查询结果缓存"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.ttl = ttl  # 缓存生存时间(秒)
        
    def get(self, query: str) -> Optional[Dict]:
        """获取缓存的查询结果"""
        if query not in self.cache:
            return None
            
        entry = self.cache[query]
        if time.time() - entry.timestamp > self.ttl:
            del self.cache[query]
            return None
            
        return entry.result
        
    def store(self, query: str, result: Dict):
        """存储查询结果"""
        if len(self.cache) >= self.max_size:
            # 删除最旧的条目
            oldest = min(self.cache.items(), key=lambda x: x[1].timestamp)
            del self.cache[oldest[0]]
            
        self.cache[query] = CacheEntry(
            result=result,
            timestamp=time.time()
        ) 


class IntentParser:
    """查询意图解析器，负责将自然语言转换为结构化查询条件"""
    
    def __init__(self, work_dir: str = "work_dir", reasoning_engine: Optional[ReasoningEngine] = None, api_key: str = DEFAULT_LLM_API_KEY, base_url: str = DEFAULT_LLM_API_BASE, logger: Optional[logging.Logger] = None):
        """初始化解析器
        
        Args:
            work_dir: 工作目录
            reasoning_engine: 推理引擎实例
            api_key: API密钥，默认使用配置中的DEFAULT_LLM_API_KEY
            base_url: API基础URL，默认使用配置中的DEFAULT_LLM_API_BASE
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.reasoning_engine = reasoning_engine
        
        if not self.reasoning_engine:
            self.logger.warning("未配置推理引擎")

        self.model_manager = ModelManager(logger=self.logger)
        
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
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
    async def parse_query(self, query: str) -> Dict:
        """异步解析自然语言查询"""
        try:
            # 为每次查询创建唯一标识符
            query_id = str(int(time.time()))
            query_dir = self.work_dir / "intent_results" 
            query_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存原始查询
            with open(query_dir / "original_query.txt", "w", encoding="utf-8") as f:
                f.write(query)
            
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
            
            # 保存关键词提取结果
            if not isinstance(keywords, Exception):
                with open(query_dir / "keywords.json", "w", encoding="utf-8") as f:
                    json.dump(keywords, f, ensure_ascii=False, indent=2)
            
            # 保存参考文本提取结果
            if not isinstance(reference_texts, Exception):
                with open(query_dir / "reference_texts.json", "w", encoding="utf-8") as f:
                    json.dump(reference_texts, f, ensure_ascii=False, indent=2)
            
            # 组装查询条件时传入原始查询和推理历史
            result = self._build_query_conditions(
                keywords, 
                reference_texts, 
                query
            )
            
            # 保存最终的查询条件
            with open(query_dir / "query_conditions.json", "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
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

    def _build_query_conditions(self, keywords_json: dict, reference_texts_json: dict, 
                              original_query: str) -> Dict:
        """组装最终的查询条件"""
        query_conditions = {
            "original_query": original_query,
            "structured_conditions": [],
            "vector_conditions": []
        }
        
        # 处理结构化查询条件
        for keyword in keywords_json.get("keywords", []):
            condition = {
                "time_range": {"start": "", "end": ""},
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
                "vector_conditions": []
            }
            
            # 处理结构化条件数组
            for condition in parsed.get("structured_conditions", [{}]):
                validated["structured_conditions"].append({
                    "time_range": {
                        "start": str(condition.get("time_range", {}).get("start", "")),
                        "end": str(condition.get("time_range", {}).get("end", ""))
                    },
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