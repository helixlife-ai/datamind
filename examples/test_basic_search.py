import sys
from pathlib import Path

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from datamind import SearchEngine, SearchPlanExecutor, setup_logging

def search_test(search_engine: SearchEngine, executor: SearchPlanExecutor) -> None:
    """基础搜索测试"""
    logger = setup_logging()
    
    try:
        print("\n=== 基础搜索测试 ===")
        queries = [
            "机器学习",
            "人工智能",
            "file:json",
            "modified:>2024-01-01"
        ]
        
        for query in queries:
            print(f"\n查询: {query}")
            print("-" * 50)
            
            # 1. 解析查询并生成搜索计划
            parsed_query = search_engine.parse_query(query)
            
            # 2. 执行搜索
            structured_results = search_engine.execute_structured_query(parsed_query)
            vector_results = search_engine.execute_vector_search(query)
            
            # 3. 整合结果
            results = {
                'structured': structured_results.to_dict('records') if not structured_results.empty else [],
                'vector': vector_results,
                'stats': {
                    'total': len(structured_results) + len(vector_results),
                    'structured_count': len(structured_results),
                    'vector_count': len(vector_results)
                }
            }
            
            # 4. 增强结果
            enhanced_results = search_engine.enhance_results(results)
            
            # 5. 格式化并显示结果
            formatted_results = search_engine.format_results(enhanced_results)
            if formatted_results:
                print(formatted_results)
            else:
                print("未找到相关结果")
            
    except Exception as e:
        logger.error(f"搜索测试失败: {str(e)}", exc_info=True)
        raise

def main():
    """主函数"""
    try:
        # 设置数据库路径
        data_dir = project_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(data_dir / "unified_storage.duckdb")
        
        # 初始化组件
        search_engine = SearchEngine(db_path=db_path)
        executor = SearchPlanExecutor(search_engine)
        
        # 设置输出目录
        work_dir = project_root / "work_dir"
        work_dir.mkdir(parents=True, exist_ok=True)
        executor.set_work_dir(str(work_dir / "output"))
        
        # 执行搜索测试
        search_test(search_engine, executor)
        
    except Exception as e:
        print(f"程序运行失败: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 