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
DEFAULT_LLM_API_KEY = parse_api_keys(os.getenv("SILICONFLOW_API_KEY", ""))
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

# DeepSeek官方提示词模板
FILE_TEMPLATE = """[file name]: {file_name}
[file content begin]
{file_content}
[file content end]
{question}"""

SEARCH_ANSWER_ZH_TEMPLATE = '''# 以下内容是基于用户发送的消息的搜索结果:
{search_results}
在我给你的搜索结果中，每个结果都是[webpage X begin]...[webpage X end]格式的，X代表每篇文章的数字索引。请在适当的情况下在句子末尾引用上下文。请按照引用编号[citation:X]的格式在答案中对应部分引用上下文。如果一句话源自多个上下文，请列出所有相关的引用编号，例如[citation:3][citation:5]，切记不要将引用集中在最后返回引用编号，而是在答案对应部分列出。
在回答时，请注意以下几点：
- 今天是{cur_date}。
- 并非搜索结果的所有内容都与用户的问题密切相关，你需要结合问题，对搜索结果进行甄别、筛选。
- 对于列举类的问题（如列举所有航班信息），尽量将答案控制在10个要点以内，并告诉用户可以查看搜索来源、获得完整信息。优先提供信息完整、最相关的列举项；如非必要，不要主动告诉用户搜索结果未提供的内容。
- 对于创作类的问题（如写论文），请务必在正文的段落中引用对应的参考编号，例如[citation:3][citation:5]，不能只在文章末尾引用。你需要解读并概括用户的题目要求，选择合适的格式，充分利用搜索结果并抽取重要信息，生成符合用户要求、极具思想深度、富有创造力与专业性的答案。你的创作篇幅需要尽可能延长，对于每一个要点的论述要推测用户的意图，给出尽可能多角度的回答要点，且务必信息量大、论述详尽。
- 如果回答很长，请尽量结构化、分段落总结。如果需要分点作答，尽量控制在5个点以内，并合并相关的内容。
- 对于客观类的问答，如果问题的答案非常简短，可以适当补充一到两句相关信息，以丰富内容。
- 你需要根据用户要求和回答内容选择合适、美观的回答格式，确保可读性强。
- 你的回答应该综合多个相关网页来回答，不能重复引用一个网页。
- 除非用户要求，否则你回答的语言需要和用户提问的语言保持一致。

# 用户消息为：
{question}'''

SEARCH_ANSWER_EN_TEMPLATE = '''# The following contents are the search results related to the user's message:
{search_results}
In the search results I provide to you, each result is formatted as [webpage X begin]...[webpage X end], where X represents the numerical index of each article. Please cite the context at the end of the relevant sentence when appropriate. Use the citation format [citation:X] in the corresponding part of your answer. If a sentence is derived from multiple contexts, list all relevant citation numbers, such as [citation:3][citation:5]. Be sure not to cluster all citations at the end; instead, include them in the corresponding parts of the answer.
When responding, please keep the following points in mind:
- Today is {cur_date}.
- Not all content in the search results is closely related to the user's question. You need to evaluate and filter the search results based on the question.
- For listing-type questions (e.g., listing all flight information), try to limit the answer to 10 key points and inform the user that they can refer to the search sources for complete information. Prioritize providing the most complete and relevant items in the list. Avoid mentioning content not provided in the search results unless necessary.
- For creative tasks (e.g., writing an essay), ensure that references are cited within the body of the text, such as [citation:3][citation:5], rather than only at the end of the text. You need to interpret and summarize the user's requirements, choose an appropriate format, fully utilize the search results, extract key information, and generate an answer that is insightful, creative, and professional. Extend the length of your response as much as possible, addressing each point in detail and from multiple perspectives, ensuring the content is rich and thorough.
- If the response is lengthy, structure it well and summarize it in paragraphs. If a point-by-point format is needed, try to limit it to 5 points and merge related content.
- For objective Q&A, if the answer is very brief, you may add one or two related sentences to enrich the content.
- Choose an appropriate and visually appealing format for your response based on the user's requirements and the content of the answer, ensuring strong readability.
- Your answer should synthesize information from multiple relevant webpages and avoid repeatedly citing the same webpage.
- Unless the user requests otherwise, your response should be in the same language as the user's question.

# The user's message is:
{question}''' 