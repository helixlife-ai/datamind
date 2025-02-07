# 全局配置
DEFAULT_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'
DEFAULT_DB_PATH = "unified_storage.duckdb"
SEARCH_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.6
DEFAULT_TARGET_FIELD = "abstract_embedding"
DEEPSEEK_MODEL = "deepseek-chat"
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
你是一个专业的语义查询分析器。请从用户的自然语言查询中，提取出用于向量相似度查询的参考文本列表。

输出要求：
1. 必须是JSON数组格式
2. 每个元素包含完整的语义描述文本
3. 提取的文本应该保留完整的语义信息
4. 最多输出3个参考文本

示例输出:
{
    "reference_texts": [
        "基于transformer架构的大规模语言模型在自然语言理解任务中的应用",
        "深度学习模型在医疗影像诊断中的准确性分析"
    ]
}
""" 