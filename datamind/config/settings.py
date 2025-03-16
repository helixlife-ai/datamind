import os
from dotenv import load_dotenv
load_dotenv(override=True)

# 全局配置
DEFAULT_EMBEDDING_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'
DEFAULT_DB_PATH = "unified_storage.duckdb"
DEFAULT_TARGET_FIELD = "abstract_embedding"
SEARCH_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.6

def parse_api_keys(env_value: str) -> list:
    """解析环境变量中的API密钥列表"""
    try:
        if env_value.startswith('[') and env_value.endswith(']'):
            # 移除方括号并分割字符串
            keys = [k.strip(' "\'') for k in env_value[1:-1].split(',')]
            return [k for k in keys if k]  # 移除空值
        return [env_value]  # 如果不是列表格式，返回单个值的列表
    except:
        return []

# LLM模型配置
DEFAULT_LLM_API_KEY = parse_api_keys(os.getenv("DEFAULT_API_KEY", ""))
DEFAULT_LLM_API_BASE = os.getenv("DEFAULT_BASE_URL") 
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_GENERATOR_MODEL")   
DEFAULT_GENERATOR_MODEL = os.getenv("DEFAULT_GENERATOR_MODEL") 
DEFAULT_REASONING_MODEL = os.getenv("DEFAULT_REASONING_MODEL") 

# 支持的文件类型
SUPPORTED_FILE_TYPES = ["txt", "pdf", "doc", "docx", "md", "json", "csv", "xlsx"]