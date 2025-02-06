# %% [markdown]
"""
# 智能查询意图解析器
此模块实现了一个基于DeepSeek的自然语言查询意图解析器。
将自然语言查询转换为结构化的查询条件，支持时间、地域、相似度等多维度解析。

主要功能：
- 自然语言解析
- 结构化条件生成
- 向量搜索参数配置
- 输出格式定制
"""

# %% [1. 环境准备]
import os
import json
from typing import Dict
from openai import OpenAI
from dotenv import load_dotenv

# %% [2. 常量定义]
DEFAULT_SIMILARITY_THRESHOLD = 0.7
DEFAULT_TARGET_FIELD = "abstract_embedding"
DEFAULT_MODEL = "deepseek-chat"

# %% [3. 输出模板定义]
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

# %% [4. 意图解析器核心类]
class DeepSeekIntentParser:
    """独立的DeepSeek语义解析器"""
    
    def __init__(self, api_key: str):
        """初始化解析器
        
        Args:
            api_key: DeepSeek API密钥
        """
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        self.output_template = QUERY_TEMPLATE

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
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

    def parse_query(self, query: str) -> Dict:
        """解析自然语言查询
        
        Args:
            query: 用户输入的自然语言查询
            
        Returns:
            Dict: 结构化查询条件
        """
        try:
            response = self.client.chat.completions.create(
                model=DEFAULT_MODEL,
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
            print(f"API调用失败: {str(e)}")
            return self.output_template

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
            return {
                "data_subject": str(parsed.get("data_subject", "")),
                "structured_conditions": {
                    "time_range": {
                        "start": str(parsed.get("structured_conditions", {}).get("time_range", {}).get("start", "")),
                        "end": str(parsed.get("structured_conditions", {}).get("time_range", {}).get("end", ""))
                    },
                    "filters": list(filter(None, parsed.get("structured_conditions", {}).get("filters", []))),
                    "exclusions": list(filter(None, parsed.get("structured_conditions", {}).get("exclusions", [])))
                },
                "vector_conditions": {
                    "target_field": str(parsed.get("vector_conditions", {}).get("target_field", DEFAULT_TARGET_FIELD)),
                    "similarity_threshold": min(max(float(
                        parsed.get("vector_conditions", {}).get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)
                    ), 0.0), 1.0),
                    "reference_keywords": str(parsed.get("vector_conditions", {}).get("reference_keywords", ""))
                },
                "result_format": {
                    "required_fields": list(filter(None, parsed.get("result_format", {}).get("required_fields", []))),
                    "display_preferences": str(parsed.get("result_format", {}).get("display_preferences", ""))
                }
            }
        except json.JSONDecodeError:
            print("JSON解析失败，返回默认模板")
            return self.output_template

# %% [5. 使用示例]
def test_parser():
    """测试意图解析器功能"""
    try:
        # 确保加载环境变量
        load_dotenv()
        
        # 获取API key并验证
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("未找到DEEPSEEK_API_KEY环境变量，请确保.env文件中包含该配置")
            
        # 初始化解析器
        parser = DeepSeekIntentParser(api_key=api_key)
        
        # 测试查询
        test_queries = [
            "找出上海2024年与人工智能专利技术相似度高的研究报告，要求显示作者和发布日期",
            "查找去年发表的关于机器学习的文章",
            "搜索长三角地区最近一个月的技术报告"
        ]
        
        for query in test_queries:
            print(f"\n测试查询: {query}")
            print("-" * 50)
            parsed_intent = parser.parse_query(query)
            print(json.dumps(parsed_intent, indent=2, ensure_ascii=False))
            print("-" * 50)
            
    except Exception as e:
        print(f"测试过程中发生错误: {str(e)}")

# %% [6. 主程序]
if __name__ == "__main__":
    test_parser()