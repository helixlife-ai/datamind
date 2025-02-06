from datamind import UnifiedSearchEngine, SearchPlanner, SearchPlanExecutor, DataProcessor, IntentParser, setup_logging
import os
import json
from pathlib import Path
from dotenv import load_dotenv

def main():
    # 设置日志
    logger = setup_logging()
    
    # 加载环境变量
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    
    # 初始化组件
    processor = DataProcessor()
    search_engine = UnifiedSearchEngine()
    intent_parser = IntentParser(api_key=api_key)
    planner = SearchPlanner()
    executor = SearchPlanExecutor(search_engine)
    

    # 处理数据
    input_dirs = [r"D:\github\Helixlife\datamind\source\test_data"]
    input_dirs = [Path(d.strip()) for d in input_dirs]
    #processor.process_directory(input_dirs)
    
    # 基础搜索测试
    print("\n=== 基础搜索测试 ===")
    for query in ["机器学习","人工智能","file:json"]:
        print(f"\n查询: {query}")
        print("-" * 50)
        result = search_engine.search(query)   
        print(result)

    # 智能检索测试
    print("\n=== 智能检索测试 ===")
    # 解析查询意图
    #query = "机器学习"  
    #parsed_intent = intent_parser.parse_query(query)
    #print(parsed_intent)

    parsed_intent = {
        "structured_conditions": {
            "time_range": {
                "start": "2025-01-01",
                "end": "2025-12-31"
            },
            "file_types": ["xml", "md", "json", "txt"],
            "keywords": "人工智能",
            "exclusions": [""]
        },
        "vector_conditions": {
            "reference_text": "人工智能",
            "similarity_threshold": 0.6,
            "top_k": 5
        },
        "result_format": {
            "required_fields": ["_file_name", "data"]
        }
    }

    # 构建搜索计划
    parsed_plan = planner.build_search_plan(parsed_intent)
    print("生成的检索计划:", json.dumps(parsed_plan, indent=2, ensure_ascii=False))
    
    # 执行搜索计划
    results = executor.execute_plan(parsed_plan)

    # 格式化输出
    print(executor.format_results(results))

if __name__ == "__main__":
    main() 