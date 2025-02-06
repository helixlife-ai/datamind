# 全局配置
DEFAULT_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'
DEFAULT_DB_PATH = "unified_storage.duckdb"
SEARCH_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.7
DEFAULT_TARGET_FIELD = "abstract_embedding"
DEEPSEEK_MODEL = "deepseek-chat"

# 查询模板
QUERY_TEMPLATE = {
    "data_subject": "识别主要查询对象类型",
    "structured_conditions": {
        "time_range": {"start": "", "end": ""},
        "filters": [],
        "exclusions": []
    },
    "vector_conditions": {
        "target_field": "需要向量搜索的字段",
        "similarity_threshold": DEFAULT_SIMILARITY_THRESHOLD,
        "reference_keywords": "生成参考向量的关键词"
    },
    "result_format": {
        "required_fields": [],
        "display_preferences": ""
    }
} 