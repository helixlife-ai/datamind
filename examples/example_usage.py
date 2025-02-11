import os
import sys
import json
import asyncio
from pathlib import Path
import time

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from datamind import (
    SearchEngine,
    SearchPlanner, 
    SearchPlanExecutor, 
    DataProcessor, 
    IntentParser, 
    setup_logging
)
from datamind.core.delivery_planner import DeliveryPlanner
from datamind.core.executor import Executor

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
        db_path = Path(processor.db_path)
        if not db_path.exists():
            logger.info("首次运行，执行全量更新")
            # 确保数据库目录存在
            db_path.parent.mkdir(parents=True, exist_ok=True)
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

async def intelligent_search_test(
    intent_parser: IntentParser, 
    planner: SearchPlanner,
    executor: SearchPlanExecutor,
    work_dir: Path = None
) -> None:
    """智能检索测试"""
    logger = setup_logging()
    
    try:
        print("\n=== 智能检索测试 ===")
        
        # 确保work_dir存在
        if work_dir is None:
            script_dir = Path(__file__).parent
            if script_dir.name == 'examples':
                work_dir = script_dir.parent / "work_dir"
            else:
                work_dir = Path("work_dir")
        work_dir.mkdir(exist_ok=True)
        
        # 查询文件路径
        queries_file = work_dir / "test_queries.txt"
        
        # 如果查询文件不存在，创建示例查询
        if not queries_file.exists():
            default_queries = [
                "找出上海2025年与人工智能专利技术相似度高的研究报告，要求显示作者和发布日期",
                "最近一个月新增的机器学习相关文档"
            ]
            queries_file.write_text("\n".join(default_queries), encoding="utf-8")
            logger.info(f"已创建默认查询文件: {queries_file}")
        
        # 从文件加载查询
        queries = queries_file.read_text(encoding="utf-8").strip().split("\n")
        queries = [q.strip() for q in queries if q.strip()]
        
        output_dir = work_dir / "output/intelligent_search"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化交付计划生成器和执行器
        delivery_planner = DeliveryPlanner(work_dir=str(output_dir))
        main_executor = Executor(work_dir=str(work_dir))
        main_executor.set_search_engine(executor.engine)  # 设置搜索引擎
        
        for idx, query in enumerate(queries):
            print(f"\n原始查询: {query}")
            print("-" * 50)
            
            # 异步解析查询意图
            parsed_intent = await intent_parser.parse_query(query)
            print("解析结果:", json.dumps(parsed_intent, indent=2, ensure_ascii=False))

            # 构建搜索计划
            parsed_plan = planner.build_search_plan(parsed_intent)
            print("检索计划:", json.dumps(parsed_plan, indent=2, ensure_ascii=False))
            
            # 执行搜索计划
            results = executor.execute_plan(parsed_plan)
            print("检索结果:")
            print(executor.format_results(results))  
            
            # 生成交付计划
            if results['stats']['total'] > 0:
                try:
                    # 构建完整的原始计划
                    original_plan = {
                        'metadata': {
                            'original_query': query,
                            'generated_at': results.get('metadata', {}).get('execution_time', '')
                        },
                        'query_params': {  # 添加查询参数
                            'query': query,
                            'keywords': parsed_intent.get('structured_conditions', [{}])[0].get('keywords', []),
                            'reference_text': query,
                            'filters': {
                                'time_range': parsed_intent.get('structured_conditions', [{}])[0].get('time_range', {}),
                                'sections': ['摘要', '分析', '结论']
                            },
                            'weights': {
                                '相关性': 1.0,
                                '时效性': 0.8,
                                '权威性': 0.7
                            }
                        },
                        'delivery_config': {  # 添加交付配置
                            'formats': ['md', 'html'],
                            'sections': ['摘要', '主要发现', '详细分析', '结论建议'],
                            'style_preferences': {
                                'language': 'zh_CN',
                                'tone': 'professional',
                                'detail_level': 'comprehensive'
                            }
                        }
                    }
                    
                    delivery_plan = await delivery_planner.generate_plan(
                        original_plan=original_plan,
                        search_results=results
                    )
                    
                    if delivery_plan:
                        print("\n交付计划生成成功！")
                        print(f"相关文件保存在: {delivery_plan['_file_paths']['base_dir']}")
                        print("\n交付计划内容:")
                        print(json.dumps(delivery_plan, indent=2, ensure_ascii=False))
                        
                        # 生成交付文件
                        from datamind.core.delivery_generator import DeliveryGenerator
                        generator = DeliveryGenerator()
                        try:
                            generated_files = await generator.generate_deliverables(
                                delivery_plan['_file_paths']['base_dir'],  # plan_id：交付计划目录
                                results,                                # search_results：搜索结果
                                delivery_plan.get('delivery_config')    # delivery_config：交付配置（可选）
                            )
                            print("\n已生成以下交付文件:")
                            for file_path in generated_files:
                                print(f"- {file_path}")
                                
                            # 模拟用户反馈优化流程
                            print("\n=== 开始反馈优化流程测试 ===")
                            
                            # 等待原始交付文件生成完成
                            max_retries = 5
                            retry_interval = 1  # 秒
                            
                            for retry in range(max_retries):
                                plan_dir = Path(delivery_plan['_file_paths']['base_dir'])
                                required_files = [
                                    plan_dir / 'delivery_plan.json',
                                    plan_dir / 'search_results.json',
                                    plan_dir / 'reasoning_process.md'
                                ]
                                
                                if all(f.exists() for f in required_files):
                                    print("交付文件已就绪，开始反馈优化流程")
                                    break
                                    
                                if retry < max_retries - 1:
                                    print(f"等待交付文件生成完成，将在 {retry_interval} 秒后重试...")
                                    time.sleep(retry_interval)
                                else:
                                    print("等待交付文件超时，跳过反馈优化流程")
                                    continue
                            
                            # 示例反馈
                            test_feedbacks = [
                                "请在AI趋势分析中增加更多关于大模型发展的内容",
                                "建议删除过时的技术参考",
                                "希望在报告中补充更多实际应用案例"
                            ]
                            
                            # 获取计划ID
                            plan_id = Path(delivery_plan['_file_paths']['base_dir']).name
                            
                            # 执行多轮反馈优化
                            for i, feedback in enumerate(test_feedbacks, 1):
                                print(f"\n第{i}轮反馈优化:")
                                print(f"用户反馈: {feedback}")
                                
                                # 使用main_executor处理反馈
                                feedback_result = await main_executor.process_feedback(plan_id, feedback)
                                
                                if feedback_result['status'] == 'success':
                                    print(f"反馈处理成功！新计划ID: {feedback_result['plan_id']}")
                                    print("已生成优化后的交付物:")
                                    for deliverable in feedback_result['deliverables']:
                                        print(f"- {deliverable}")
                                    # 更新计划ID用于下一轮优化
                                    plan_id = feedback_result['plan_id']
                                else:
                                    print(f"反馈处理失败: {feedback_result.get('message', '未知错误')}")
                                    break
                                    
                            print("\n反馈优化流程测试完成")
                            
                        except Exception as e:
                            logger.error(f"生成交付文件失败: {str(e)}")
                            print(f"\n生成交付文件失败: {str(e)}")
                    else:
                        print("\n交付计划生成失败")
                        
                except Exception as e:
                    logger.error(f"生成交付计划时发生错误: {str(e)}")
                    print(f"\n生成交付计划失败: {str(e)}")
            else:
                print("\n未找到检索结果，跳过交付计划生成")
            
            # 保存不同格式的结果
            for format in ['json', 'html', 'csv', 'excel']:
                try:
                    filepath = executor.save_results(
                        results, 
                        format=format,
                        output_dir=str(output_dir / f"query_{idx + 1}")
                    )
                    print(f"结果已保存为{format}格式: {filepath}")
                except Exception as e:
                    logger.error(f"保存{format}格式失败: {str(e)}")
            
    except Exception as e:
        logger.error(f"智能检索测试失败: {str(e)}", exc_info=True)
        raise

async def async_main():
    """异步主函数"""
    logger = setup_logging()
    logger.info("开始运行测试程序")
    
    try:        
        # 创建工作目录
        script_dir = Path(__file__).parent
        if script_dir.name == 'examples':
            work_dir = script_dir.parent / "work_dir"
            data_dir = script_dir.parent / "data"
        else:
            work_dir = Path("work_dir")
            data_dir = Path("data")
        work_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置数据库和缓存路径
        db_path = str(data_dir / "unified_storage.duckdb")
        cache_file = str(data_dir / "file_cache.pkl")
        
        # 初始化组件
        from datamind.core.processor import FileCache
        processor = DataProcessor(db_path=db_path)
        processor.file_cache = FileCache(cache_file=cache_file)  # 重新创建FileCache实例
        search_engine = SearchEngine(db_path=db_path)
        intent_parser = IntentParser()
        planner = SearchPlanner()
        executor = Executor(work_dir=str(work_dir), search_engine=search_engine)
        search_plan_executor = SearchPlanExecutor(search_engine)
        
        # 设置executor的输出目录
        executor.set_work_dir(str(work_dir / "output"))
        search_plan_executor.set_work_dir(str(work_dir / "output"))
        
        # 数据处理测试
        logger.info("开始数据处理测试")
        test_data_dir = work_dir / "test_data"
        input_dirs = [str(test_data_dir)]
        abs_input_dirs = [str(Path(d).resolve()) for d in input_dirs]
        process_data(processor, abs_input_dirs)
        logger.info("数据处理测试完成")

        # 搜索测试
        logger.info("开始基础搜索测试")
        search_test(search_engine, search_plan_executor)
        logger.info("基础搜索测试完成")
        
        # 异步执行智能检索测试
        logger.info("开始智能检索测试")
        await intelligent_search_test(intent_parser, planner, search_plan_executor, work_dir=work_dir)
        logger.info("智能检索测试完成")
        
        logger.info("测试程序运行完成")
        
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}", exc_info=True)
        raise

def main():
    """同步主函数入口"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main() 