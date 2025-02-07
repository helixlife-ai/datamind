from datamind import UnifiedSearchEngine, SearchPlanner, SearchPlanExecutor, DataProcessor, IntentParser, setup_logging
import os
import json
from pathlib import Path
from dotenv import load_dotenv

def process_data(processor: DataProcessor, input_dirs: list) -> None:
    """处理数据目录
    
    Args:
        processor: 数据处理器实例
        input_dirs: 输入目录列表
    """
    logger = setup_logging()
    
    try:
        # 转换路径
        dirs = [Path(d.strip()) for d in input_dirs]
        
        # 首次运行使用全量更新
        if not Path(processor.db_path).exists():
            logger.info("首次运行，执行全量更新")
            stats = processor.process_directory(dirs, incremental=False)
        else:
            # 后续运行使用增量更新
            logger.info("检测到已有数据，执行增量更新")
            stats = processor.process_directory(dirs, incremental=True)
            
        # 输出处理统计
        logger.info("\n=== 处理统计 ===")
        logger.info(f"更新模式: {stats.get('update_mode', 'unknown')}")
        logger.info(f"总文件数: {stats.get('total_files', 0)}")
        logger.info(f"成功处理: {stats.get('successful_files', 0)}")
        logger.info(f"处理失败: {stats.get('failed_files', 0)}")
        logger.info(f"总记录数: {stats.get('total_records', 0)}")
        if 'removed_files' in stats:
            logger.info(f"删除记录: {stats['removed_files']}")
        logger.info(f"总耗时: {stats.get('total_time', 0):.2f}秒")
        
        # 如果有错误，输出错误信息
        if stats.get('errors'):
            logger.warning("\n处理过程中的错误:")
            for error in stats['errors']:
                logger.warning(f"- {error}")
                
    except Exception as e:
        logger.error(f"数据处理失败: {str(e)}", exc_info=True)
        raise

def search_test(search_engine: UnifiedSearchEngine) -> None:
    """基础搜索测试"""
    logger = setup_logging()
    
    try:
        print("\n=== 基础搜索测试 ===")
        queries = [
            "机器学习",
            "人工智能",
            "file:json",
            "modified:>2024-01-01"  # 测试时间过滤
        ]
        
        for query in queries:
            print(f"\n查询: {query}")
            print("-" * 50)
            result = search_engine.search(query)   
            print(result)
            
    except Exception as e:
        logger.error(f"搜索测试失败: {str(e)}", exc_info=True)
        raise

def intelligent_search_test(
    intent_parser: IntentParser, 
    planner: SearchPlanner,
    executor: SearchPlanExecutor
) -> None:
    """智能检索测试"""
    logger = setup_logging()
    
    try:
        print("\n=== 智能检索测试 ===")
        
        # 测试查询
        queries = [
            "找出上海2025年与人工智能专利技术相似度高的研究报告，要求显示作者和发布日期",
            "最近一个月新增的机器学习相关文档"  # 测试增量数据查询
        ]
        
        for idx, query in enumerate(queries):
            print(f"\n原始查询: {query}")
            print("-" * 50)
            
            # 解析查询意图
            parsed_intent = intent_parser.parse_query(query)
            print("解析结果:", json.dumps(parsed_intent, indent=2, ensure_ascii=False))

            # 构建搜索计划
            parsed_plan = planner.build_search_plan(parsed_intent)
            print("检索计划:", json.dumps(parsed_plan, indent=2, ensure_ascii=False))
            
            # 执行搜索计划
            results = executor.execute_plan(parsed_plan)
            print("检索结果:")
            print(executor.format_results(results))
            
            # 保存结果到CSV文件
            filename = f"query_{idx + 1}_results.csv"
            csv_path = executor.save_results_to_csv(results, filename)
            if csv_path:
                print(f"结果已保存到: {csv_path}")
            
    except Exception as e:
        logger.error(f"智能检索测试失败: {str(e)}", exc_info=True)
        raise

def main():
    """主函数"""
    # 设置日志
    logger = setup_logging()
    logger.info("开始运行测试程序")
    
    try:
        # 加载环境变量
        load_dotenv()
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL")
        if not api_key:
            raise ValueError("未找到 DEEPSEEK_API_KEY 环境变量")
        
        # 初始化组件
        processor = DataProcessor()
        search_engine = UnifiedSearchEngine()
        intent_parser = IntentParser(api_key=api_key, base_url=base_url)
        planner = SearchPlanner()
        executor = SearchPlanExecutor(search_engine)
        
        # 创建工作目录
        work_dir = Path("work_dir")
        work_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置executor的输出目录为work_dir下的output目录
        executor.work_dir = str(work_dir / "output")
        
        # 数据处理测试 - 使用相对路径
        input_dirs = ["source/test_data"]  # 改为使用相对路径
        # 将相对路径转换为绝对路径
        abs_input_dirs = [str(Path(d).resolve()) for d in input_dirs]
        process_data(processor, abs_input_dirs)

        # 搜索测试
        search_test(search_engine)
        
        # 智能检索测试
        intelligent_search_test(intent_parser, planner, executor)
        
        logger.info("测试程序运行完成")
        
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main() 