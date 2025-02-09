import os
from typing import Optional
from dotenv import load_dotenv
load_dotenv(override=True)

# 全局配置
DEFAULT_EMBEDDING_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'
DEFAULT_DB_PATH = "unified_storage.duckdb"
SEARCH_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.6

DEFAULT_TARGET_FIELD = "abstract_embedding"

# LLM模型配置
#硅基流动的充值版本
DEFAULT_LLM_MODEL = "Pro/deepseek-ai/DeepSeek-V3"    
DEFAULT_LLM_API_KEY = os.getenv("SILICONFLOW_API_KEY")  
DEFAULT_LLM_API_BASE = os.getenv("SILICONFLOW_BASE_URL") 
DEFAULT_CHAT_MODEL = "Pro/deepseek-ai/DeepSeek-V3" 
DEFAULT_REASONING_MODEL = "Pro/deepseek-ai/DeepSeek-R1" 

#硅基流动的免费版本
#DEFAULT_LLM_MODEL = "deepseek-ai/DeepSeek-V3"    
#DEFAULT_LLM_API_KEY = os.getenv("SILICONFLOW_API_KEY")  # 硅基流动的API KEY
#DEFAULT_LLM_API_BASE = os.getenv("SILICONFLOW_BASE_URL") #硅基流动的API BASE
#DEFAULT_CHAT_MODEL = "deepseek-ai/DeepSeek-V3" 
#DEFAULT_REASONING_MODEL = "deepseek-ai/DeepSeek-R1" 

#DeepSeek的免费版本
#DEFAULT_LLM_MODEL = "deepseek-chat"    
#DEFAULT_LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY")  
#DEFAULT_LLM_API_BASE = os.getenv("DEEPSEEK_BASE_URL") 
#DEFAULT_CHAT_MODEL = "deepseek-chat" 
#DEFAULT_REASONING_MODEL = "deepseek-reasoner" 

# 支持的文件类型
SUPPORTED_FILE_TYPES = ["txt", "pdf", "doc", "docx", "md", "json", "csv", "xlsx"]


# 查询模板
QUERY_TEMPLATE = {
    "structured_conditions": [{
        "time_range": {"start": "", "end": ""},
        "file_types": SUPPORTED_FILE_TYPES,
        "keyword": "",
        "exclusions": []
    }],
    "vector_conditions": [{
        "reference_text": "",
        "similarity_threshold": DEFAULT_SIMILARITY_THRESHOLD,
        "top_k": SEARCH_TOP_K
    }],
    "result_format": {
        "required_fields": ["_file_name", "data"],
        "display_preferences": ""
    }
}

# 意图解析提示词模板
KEYWORD_EXTRACT_PROMPT = """
你是一个专业的关键词提取器。请从用户的自然语言查询中，提取出用于结构化查询的关键词列表。

输出要求：
1. 必须是JSON数组格式
2. 每个元素是一个独立的搜索关键词
3. 关键词应该简洁明确，不包含语气词和修饰词
4. 最多输出3个关键词

示例输出:
{
    "keywords": [
        "transformer",
        "注意力机制",
        "BERT"
    ]
}
"""

REFERENCE_TEXT_EXTRACT_PROMPT = """
你是一个专业的语义查询优化器。请基于用户的自然语言查询，生成更有助于向量相似度搜索的相关查询句子。

要求：
1. 输出必须是JSON数组格式
2. 生成的句子应该：
   - 保留原始查询的核心语义
   - 使用更规范和专业的表达
   - 添加相关的同义词或相近概念
   - 去除无关的修饰词
3. 每个句子应该完整且独立
4. 最多生成3个查询句子

示例：
用户查询：
"找一下去年发布的关于AI绘画的论文"

输出：
{
    "reference_texts": [
        "人工智能技术在数字艺术创作和图像生成领域的应用研究",
        "基于深度学习的AI绘画系统技术分析与发展趋势",
        "计算机视觉与生成对抗网络在数字艺术创作中的创新应用"
    ]
}

用户查询：
"找找关于电动汽车电池技术的最新进展"

输出：
{
    "reference_texts": [
        "新能源汽车动力电池系统的技术创新与发展现状分析",
        "锂离子电池在电动汽车领域的最新研究进展与应用",
        "电动汽车储能技术的优化与效率提升研究"
    ]
}
""" 