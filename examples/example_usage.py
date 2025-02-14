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
    setup_logging,
    FileCache
)
from datamind.core.delivery_planner import DeliveryPlanner
from datamind.core.delivery_generator import DeliveryGenerator
from datamind.core.feedback_optimizer import FeedbackOptimizer


async def run_test_optimization(
    feedback_optimizer: FeedbackOptimizer, 
    alchemy_dir: str,
) -> None:
    """运行反馈优化测试流程
    
    Args:
        feedback_optimizer: 反馈优化器实例
        alchemy_dir: 炼丹工作流运行目录
    """
    print("\n=== 开始反馈优化流程测试 ===")
    
    # 获取当前交付目录
    delivery_dir = Path(alchemy_dir) / "delivery"
    
    # 示例反馈
    test_feedbacks = [
        "请在AI趋势分析中增加更多关于大模型发展的内容",
        "建议删除过时的技术参考",
        "希望在报告中补充更多实际应用案例"
    ]
    
    # 执行多轮反馈优化
    for i, feedback in enumerate(test_feedbacks, 1):
        print(f"\n第{i}轮反馈优化:")
        print(f"用户反馈: {feedback}")
        
        # 将反馈写入feedback.txt
        feedback_file = Path(alchemy_dir).parent / "feedback.txt"
        with open(feedback_file, "w", encoding="utf-8") as f:
            f.write(feedback)
        
        # 生成反馈上下文
        context_result = await feedback_optimizer.feedback_to_context(alchemy_dir)
        
        if context_result['status'] == 'success':
            print(f"反馈上下文生成成功！")
            
            # 使用新查询重新执行 datamind_alchemy 工作流
            alchemy_result = await datamind_alchemy(
                query=context_result['context']['current_query'],  # 使用当前查询
                work_dir=Path(alchemy_dir).parent / "iteration",  
                input_dirs=None,  # 使用已有数据
                context=context_result['context']  # 传入完整上下文
            )
            
            if alchemy_result['status'] == 'success':
                print("基于反馈的新一轮处理成功！")
                if alchemy_result['results']['delivery_plan']:
                    # 更新当前目录为新的运行目录
                    alchemy_dir = Path(alchemy_result['results']['delivery_plan']['_file_paths']['base_dir']).parent
                    print(f"新的交付文件保存在: {alchemy_dir}/delivery")
            else:
                print(f"新一轮处理失败: {alchemy_result['message']}")
                break
        else:
            print(f"反馈上下文生成失败: {context_result['message']}")
            break
            
    print("\n反馈优化流程测试完成")

async def datamind_alchemy(
    query: str,
    work_dir: Path = None,
    input_dirs: list = None,
    context: Dict = None
) -> Dict:
    """数据炼丹工作流
    
    Args:
        query: 查询文本
        work_dir: 工作目录
        input_dirs: 输入目录列表
        context: 上下文数据，如果提供则保存为context.json并复制上级source_data
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 初始化工作目录
        script_dir = Path(__file__).parent
        if work_dir is None:
            if script_dir.name == 'examples':
                work_dir = script_dir.parent / "work_dir" / "output" / "alchemy_runs"
            else:
                work_dir = Path("output") / "alchemy_runs"
        work_dir.mkdir(exist_ok=True, parents=True)
        
        # 初始化运行目录
        run_id = time.strftime("%Y%m%d_%H%M%S")
        run_dir = work_dir / f"run_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # 如果提供了上下文，保存为context.json
        if context:
            context_file = run_dir / "context.json"
            with open(context_file, 'w', encoding='utf-8') as f:
                json.dump(context, f, ensure_ascii=False, indent=2)
        
        # 创建并准备source_data目录
        source_data = run_dir / "source_data"
        source_data.mkdir(exist_ok=True)
        
        # 如果有上下文，复制上级目录的source_data内容
        if context:
            parent_source = work_dir.parent / "source_data"
            if parent_source.exists() and parent_source.is_dir():
                logger.info("开始复制上级source_data")
                try:
                    import shutil
                    # 清空当前source_data目录
                    if any(source_data.iterdir()):
                        shutil.rmtree(source_data)
                        source_data.mkdir()
                    
                    # 复制所有内容
                    for item in parent_source.iterdir():
                        if item.is_dir():
                            shutil.copytree(item, source_data / item.name, dirs_exist_ok=True)
                        else:
                            shutil.copy2(item, source_data / item.name)
                    logger.info(f"上级source_data已复制到: {source_data}")
                except Exception as e:
                    logger.error(f"复制上级source_data失败: {str(e)}", exc_info=True)
                    raise
        
        # 如果有输入目录，复制到source_data（保持原有逻辑）
        if input_dirs:
            logger.info("开始复制源数据")
            try:
                import shutil
                for input_dir in input_dirs:
                    input_path = Path(input_dir)
                    if input_path.exists():
                        if input_path.is_dir():
                            # 复制目录内容
                            for item in input_path.iterdir():
                                if item.is_dir():
                                    shutil.copytree(item, source_data / item.name, dirs_exist_ok=True)
                                else:
                                    shutil.copy2(item, source_data / item.name)
                        else:
                            # 复制单个文件
                            shutil.copy2(input_path, source_data / input_path.name)
                logger.info(f"源数据已复制到: {source_data}")
            except Exception as e:
                logger.error(f"复制源数据失败: {str(e)}", exc_info=True)
                raise
        
        # 数据目录路径修正
        data_dir = run_dir / "data"
        data_dir.mkdir(exist_ok=True)
        db_path = data_dir / "unified_storage.duckdb"
        cache_file = str(data_dir / "file_cache.pkl")
        
        # 初始化数据处理器
        processor = DataProcessor(db_path=str(db_path))
        processor.file_cache = FileCache(cache_file=cache_file)

        # 处理source_data目录中的数据
        if source_data.exists() and any(source_data.iterdir()):
            logger.info("开始处理源数据")
            try:
                # 根据数据库存在情况选择更新模式
                if not db_path.exists():
                    logger.info("首次运行，执行全量更新")
                    db_path.parent.mkdir(parents=True, exist_ok=True)
                    stats = processor.process_directory([source_data], incremental=False)
                else:
                    logger.info("检测到已有数据，执行增量更新")
                    stats = processor.process_directory([source_data], incremental=True)
                    
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
                
                if stats.get('errors'):
                    logger.warning("\n处理过程中的错误:")
                    for error in stats['errors']:
                        logger.warning(f"- {error}")
                        
            except Exception as e:
                logger.error(f"数据处理失败: {str(e)}", exc_info=True)
                raise
                
            logger.info("源数据处理完成")

        # 初始化其他组件（必须在数据处理之后）
        search_engine = SearchEngine(db_path=db_path)
        intent_parser = IntentParser()
        planner = SearchPlanner()
        
        # 先创建执行器实例
        executor = SearchPlanExecutor(
            search_engine=search_engine,
            work_dir=str(run_dir / "search_results")
        )
        
        # 创建交付计划器实例
        delivery_planner = DeliveryPlanner(
            work_dir=str(run_dir / "delivery")
        )
        
        delivery_generator = DeliveryGenerator()
        feedback_optimizer = FeedbackOptimizer(
            work_dir=str(run_dir / "feedback")
        )

        results = {
            'status': 'success',
            'message': '',
            'results': {
                'parsed_intent': None,
                'search_plan': None,
                'search_results': None,
                'delivery_plan': None,
                'generated_files': []
            },
            'components': {
                'intent_parser': intent_parser,
                'planner': planner,
                'executor': executor,
                'delivery_planner': delivery_planner,
                'delivery_generator': delivery_generator,
                'feedback_optimizer': feedback_optimizer
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
                    
                    # 生成交付文件（路径已自动包含运行目录）
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
    input_dirs: list = None,
    work_dir: Path = None
) -> None:
    """数据炼丹测试"""
    logger = logging.getLogger(__name__)  # 添加logger初始化
    
    try:
        print("\n=== 数据炼丹测试 ===")
        
        # 定义测试查询（修复未定义query的问题）
        query = "请生成关于人工智能最新发展的分析报告"
        
        # 调用数据炼丹工作流
        result = await datamind_alchemy(
            query=query,  # 使用本地定义的query变量
            work_dir=work_dir,
            input_dirs=input_dirs
        )
        
        # 输出结果
        if result['status'] == 'success':
            print("解析结果:", json.dumps(result['results']['parsed_intent'], indent=2, ensure_ascii=False))
            print("检索计划:", json.dumps(result['results']['search_plan'], indent=2, ensure_ascii=False))
            
            # 修复结果格式化问题
            print("\n检索结果摘要:")
            if 'formatted' in result['results']['search_results']:
                print(result['results']['search_results']['formatted'])
            else:
                print("总记录数:", result['results']['search_results'].get('stats', {}).get('total', 0))
            
            if result['results']['delivery_plan']:
                print("\n交付计划生成成功！")
                delivery_dir = result['results']['delivery_plan']['_file_paths']['base_dir']
                print(f"相关文件保存在: {delivery_dir}")
                
                if result['results']['generated_files']:
                    print("\n已生成以下交付文件:")
                    for file_path in result['results']['generated_files']:
                        print(f"- {Path(file_path).name}")  # 显示文件名简化路径
                    
                    # 修改调用方式
                    await run_test_optimization(
                        feedback_optimizer=result['components']['feedback_optimizer'],
                        alchemy_dir=delivery_dir
                    )
        else:
            print(f"\n处理失败: {result.get('message', '未知错误')}")
            
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
        test_data_dir = script_dir.parent / "work_dir" / "test_data"
        
        # 执行数据炼丹测试
        logger.info("开始数据炼丹测试")
        await datamind_alchemy_test(
            input_dirs=[str(test_data_dir)],
            work_dir=script_dir.parent / "work_dir" / "output" / "alchemy_runs"  # 路径调整
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