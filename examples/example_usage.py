import os
import sys
import json
import asyncio
from pathlib import Path
import time
from typing import Dict
import logging

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
from datamind.core.delivery_generator import DeliveryGenerator
from datamind.core.feedback_optimizer import FeedbackOptimizer

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

async def run_test_optimization(
    feedback_optimizer: FeedbackOptimizer, 
    delivery_dir: str,
    # 添加必要的组件参数
    intent_parser: IntentParser,
    planner: SearchPlanner,
    executor: SearchPlanExecutor,
    delivery_planner: DeliveryPlanner,
    delivery_generator: DeliveryGenerator
) -> None:
    """运行反馈优化测试流程
    
    Args:
        feedback_optimizer: 反馈优化器实例
        delivery_dir: 交付文件目录
        intent_parser: 意图解析器
        planner: 搜索计划生成器
        executor: 搜索执行器
        delivery_planner: 交付计划生成器
        delivery_generator: 交付文件生成器
    """
    print("\n=== 开始反馈优化流程测试 ===")
    
    # 示例反馈
    test_feedbacks = [
        "请在AI趋势分析中增加更多关于大模型发展的内容",
        "建议删除过时的技术参考",
        "希望在报告中补充更多实际应用案例"
    ]
    
    current_dir = delivery_dir
    
    # 执行多轮反馈优化
    for i, feedback in enumerate(test_feedbacks, 1):
        print(f"\n第{i}轮反馈优化:")
        print(f"用户反馈: {feedback}")
        
        # 将反馈转换为新查询
        result = await feedback_optimizer.feedback_to_query(current_dir, feedback)
        
        if result['status'] == 'success':
            print(f"反馈处理成功！")
            print(f"生成的新查询: {result['query']}")
            
            # 使用新查询重新执行 datamind_alchemy 工作流
            alchemy_result = await datamind_alchemy(
                intent_parser=intent_parser,
                planner=planner,
                executor=executor,
                delivery_planner=delivery_planner,
                delivery_generator=delivery_generator,
                query=result['query'],
                work_dir=Path(current_dir).parent  # 使用父目录作为工作目录
            )
            
            if alchemy_result['status'] == 'success':
                print("基于反馈的新一轮处理成功！")
                if alchemy_result['results']['delivery_plan']:
                    # 更新当前目录为新生成的交付目录
                    current_dir = alchemy_result['results']['delivery_plan']['_file_paths']['base_dir']
                    print(f"新的交付文件保存在: {current_dir}")
            else:
                print(f"新一轮处理失败: {alchemy_result['message']}")
                break
        else:
            print(f"反馈处理失败: {result['message']}")
            break
            
    print("\n反馈优化流程测试完成")

async def datamind_alchemy(
    intent_parser: IntentParser, 
    planner: SearchPlanner,
    executor: SearchPlanExecutor,
    delivery_planner: DeliveryPlanner,
    delivery_generator: DeliveryGenerator,
    query: str,
    work_dir: Path = None
) -> Dict:
    """数据炼丹工作流
    
    通过意图解析、计划生成、执行和反馈优化等步骤,
    将原始数据"炼制"成高价值的知识交付物。
    
    Args:
        intent_parser: 意图解析器
        planner: 搜索计划生成器
        executor: 搜索执行器
        delivery_planner: 交付计划生成器
        delivery_generator: 交付文件生成器
        query: 查询文本
        work_dir: 工作目录
        
    Returns:
        Dict: 包含处理结果的字典
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 初始化工作目录
        if work_dir is None:
            work_dir = Path("work_dir")
        work_dir.mkdir(exist_ok=True)
        
        results = {
            'status': 'success',
            'message': '',
            'results': {
                'parsed_intent': None,
                'search_plan': None,
                'search_results': None,
                'delivery_plan': None,
                'generated_files': []
            }
        }
        
        try:
            # 解析查询意图
            parsed_intent = await intent_parser.parse_query(query)
            results['results']['parsed_intent'] = parsed_intent

            # 构建搜索计划
            parsed_plan = planner.build_search_plan(parsed_intent)
            results['results']['search_plan'] = parsed_plan
            
            # 执行搜索计划
            search_results = await executor.execute_plan(parsed_plan)
            results['results']['search_results'] = search_results
            
            # 如果有检索结果，生成交付计划
            if search_results['stats']['total'] > 0:
                delivery_plan = await delivery_planner.generate_plan(
                    search_plan=parsed_plan,
                    search_results=search_results
                )
                
                if delivery_plan:
                    results['results']['delivery_plan'] = delivery_plan
                    delivery_dir = delivery_plan['_file_paths']['base_dir']
                    
                    # 生成交付文件
                    generated_files = await delivery_generator.generate_deliverables(
                        delivery_dir,
                        search_results,
                        delivery_plan.get('delivery_config')
                    )
                    results['results']['generated_files'] = generated_files
                    
                else:
                    results['status'] = 'error'
                    results['message'] = '交付计划生成失败'
                    
            else:
                results['status'] = 'error'
                results['message'] = '未找到检索结果'
                
            return results
                
        except Exception as e:
            logger.error(f"处理查询失败: {str(e)}", exc_info=True)
            results['status'] = 'error'
            results['message'] = str(e)
            return results
            
    except Exception as e:
        logger.error(f"数据炼丹工作流失败: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'message': str(e),
            'results': None
        }

async def datamind_alchemy_test(
    intent_parser: IntentParser, 
    planner: SearchPlanner,
    executor: SearchPlanExecutor,
    delivery_planner: DeliveryPlanner,
    delivery_generator: DeliveryGenerator,
    feedback_optimizer: FeedbackOptimizer,
    work_dir: Path = None
) -> None:
    """数据炼丹测试"""
    logger = logging.getLogger(__name__)
    
    try:
        print("\n=== 数据炼丹测试 ===")
        
        # 初始化工作目录
        if work_dir is None:
            script_dir = Path(__file__).parent
            if script_dir.name == 'examples':
                work_dir = script_dir.parent / "work_dir"
            else:
                work_dir = Path("work_dir")
        work_dir.mkdir(exist_ok=True)
        
        # 加载测试查询
        queries_file = work_dir / "test_queries.txt"
        if not queries_file.exists():
            default_queries = [
                "找出上海2025年与人工智能专利技术相似度高的研究报告，要求显示作者和发布日期",
                "最近一个月新增的机器学习相关文档"
            ]
            queries_file.write_text("\n".join(default_queries), encoding="utf-8")
            logger.info(f"已创建默认查询文件: {queries_file}")
        
        queries = queries_file.read_text(encoding="utf-8").strip().split("\n")
        queries = [q.strip() for q in queries if q.strip()]
        
        # 处理每个查询
        for idx, query in enumerate(queries):
            print(f"\n原始查询: {query}")
            print("-" * 50)
            
            # 调用数据炼丹工作流
            result = await datamind_alchemy(
                intent_parser=intent_parser,
                planner=planner,
                executor=executor,
                delivery_planner=delivery_planner,
                delivery_generator=delivery_generator,
                query=query,
                work_dir=work_dir
            )
            
            # 输出结果
            if result['status'] == 'success':
                print("解析结果:", json.dumps(result['results']['parsed_intent'], indent=2, ensure_ascii=False))
                print("检索计划:", json.dumps(result['results']['search_plan'], indent=2, ensure_ascii=False))
                print("检索结果:")
                print(executor.format_results(result['results']['search_results']))
                
                if result['results']['delivery_plan']:
                    print("\n交付计划生成成功！")
                    delivery_dir = result['results']['delivery_plan']['_file_paths']['base_dir']
                    print(f"相关文件保存在: {delivery_dir}")
                    
                    if result['results']['generated_files']:
                        print("\n已生成以下交付文件:")
                        for file_path in result['results']['generated_files']:
                            print(f"- {file_path}")
                            
                        # 运行反馈优化测试
                        await run_test_optimization(
                            feedback_optimizer=feedback_optimizer, 
                            delivery_dir=delivery_dir,
                            intent_parser=intent_parser,
                            planner=planner,
                            executor=executor,
                            delivery_planner=delivery_planner,
                            delivery_generator=delivery_generator
                        )
            else:
                print(f"\n处理失败: {result['message']}")
            
    except Exception as e:
        logger.error(f"数据炼丹测试失败: {str(e)}", exc_info=True)
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
        executor = SearchPlanExecutor(
            search_engine=search_engine,
            work_dir=str(work_dir / "output")  # 保持目录结构一致
        )
        
        # 数据处理测试
        logger.info("开始数据处理测试")
        test_data_dir = work_dir / "test_data"
        input_dirs = [str(test_data_dir)]
        abs_input_dirs = [str(Path(d).resolve()) for d in input_dirs]
        process_data(processor, abs_input_dirs)
        logger.info("数据处理测试完成")
        
        # 执行数据炼丹测试
        logger.info("开始数据炼丹测试")
        await datamind_alchemy_test(
            intent_parser=intent_parser,
            planner=planner,
            executor=executor,
            delivery_planner=DeliveryPlanner(work_dir=str(work_dir / "output")),
            delivery_generator=DeliveryGenerator(),
            feedback_optimizer=FeedbackOptimizer(work_dir=str(work_dir)),
            work_dir=work_dir
        )
        logger.info("数据炼丹测试完成")
        
        logger.info("测试程序运行完成")
        
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}", exc_info=True)
        raise

def main():
    """同步主函数入口"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main() 