import os
import sys
import json
import asyncio
from pathlib import Path
import logging
import argparse

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from datamind import (
    setup_logging
)

from datamind.services.alchemy_service import DataMindAlchemy, AlchemyEventType, CancellationException
from datamind.services.alchemy_manager import AlchemyManager

# 事件处理函数
async def on_process_started(data, logger):
    """处理开始事件"""
    logger.info(f"=== 炼丹开始 [ID: {data['alchemy_id']}] ===")
    logger.info(f"当前迭代: {data['iteration']}")
    logger.info(f"处理查询: {data['query']}")

async def on_intent_parsed(data, logger):
    """意图解析事件"""
    logger.info("\n=== 意图解析完成 ===")
    logger.info("解析结果:\n%s", 
        json.dumps(data['parsed_intent'], indent=2, ensure_ascii=False))

async def on_plan_built(data, logger):
    """计划构建事件"""
    logger.info("\n=== 检索计划已构建 ===")
    logger.info("检索计划:\n%s", 
        json.dumps(data['search_plan'], indent=2, ensure_ascii=False))

async def on_search_executed(data, logger):
    """搜索执行事件"""
    logger.info("\n=== 搜索已执行 ===")
    stats = data.get('search_results', {}).get('stats', {})
    logger.info(f"搜索结果: 总计 {stats.get('total', 0)} 条记录")

async def on_artifact_generated(data, logger):
    """制品生成事件"""
    logger.info("\n=== 制品已生成 ===")
    logger.info(f"制品文件: {Path(data['artifact_path']).name}")

async def on_optimization_suggested(data, logger):
    """优化建议事件"""
    logger.info("\n=== 收到优化建议 ===")
    logger.info(f"原始查询: {data['original_query']}")
    logger.info(f"优化建议: {data['optimization_query']}")

async def on_process_completed(data, logger):
    """处理完成事件"""
    logger.info("\n=== 炼丹流程完成 [ID: {data['alchemy_id']}] ===")
    results = data.get('results', {})
    
    if results.get('status') == 'success':
        artifacts = results.get('results', {}).get('artifacts', [])
        if artifacts:
            logger.info("\n生成的制品文件:")
            for artifact_path in artifacts:
                logger.info(f"- {Path(artifact_path).name}")
                
        optimization_suggestions = results.get('results', {}).get('optimization_suggestions', [])
        if optimization_suggestions:
            logger.info("\n优化建议和结果:")
            for suggestion in optimization_suggestions:
                logger.info(f"- 优化建议: {suggestion['suggestion']}")
                logger.info(f"  来源: {suggestion['source']}")
                logger.info(f"  生成时间: {suggestion['timestamp']}")
                if suggestion.get('artifacts'):
                    logger.info("  生成的制品:")
                    for artifact in suggestion['artifacts']:
                        logger.info(f"    - {Path(artifact).name}")
                logger.info("---")

async def on_error_occurred(data, logger):
    """错误事件"""
    logger.error(f"\n=== 处理过程中发生错误 ===")
    logger.error(f"错误信息: {data['error']}")
    logger.error(f"查询内容: {data['query']}")

async def on_cancellation_requested(data, logger):
    """取消请求事件"""
    logger.info(f"\n=== 收到取消请求 [ID: {data['alchemy_id']}] ===")
    logger.info(f"时间: {data['timestamp']}")

async def on_process_cancelled(data, logger):
    """处理取消事件"""
    logger.info(f"\n=== 处理已取消 [ID: {data['alchemy_id']}] ===")
    logger.info(f"当前步骤: {data['current_step']}")
    logger.info(f"时间: {data['timestamp']}")

async def on_process_checkpoint(data, logger):
    """检查点事件"""
    logger.info(f"\n=== 已创建检查点 [ID: {data['alchemy_id']}] ===")
    logger.info(f"当前步骤: {data['current_step']}")
    logger.info(f"时间: {data['timestamp']}")

async def handle_keyboard_interrupt(alchemy, logger):
    """处理键盘中断(Ctrl+C)事件"""
    logger.info("\n=== 检测到键盘中断(Ctrl+C)，正在尝试优雅退出 ===")
    try:
        # 调用取消处理方法
        await alchemy.cancel_process()
        logger.info("已请求取消处理，等待当前操作完成...")
        return {
            'status': 'interrupted',
            'message': '用户通过Ctrl+C中断了处理',
            'checkpoint': {
                'alchemy_id': alchemy.alchemy_id,
            }
        }
    except Exception as e:
        logger.error(f"处理中断时发生错误: {str(e)}")
        return {
            'status': 'error',
            'message': f'中断处理失败: {str(e)}'
        }

async def datamind_alchemy_process(
    alchemy_id: str = None,
    query: str = None,
    input_dirs: list = None,
    work_dir: Path = None,
    logger: logging.Logger = None,
    auto_cancel: bool = False,
    should_resume: bool = False  # 是否尝试从中断点恢复
) -> None:
    """统一的数据炼丹处理函数 - 支持新建和继续/恢复"""
    logger = logger or logging.getLogger(__name__)
    
    try:
        # 创建任务管理器
        alchemy_manager = AlchemyManager(work_dir=work_dir.parent, logger=logger)
        
        # 创建DataMindAlchemy实例
        alchemy = DataMindAlchemy(
            work_dir=work_dir, 
            logger=logger,
            alchemy_id=alchemy_id,
            alchemy_manager=alchemy_manager  # 传入任务管理器
        )
        
        # 注册事件处理函数
        alchemy.subscribe(AlchemyEventType.PROCESS_STARTED, lambda data: on_process_started(data, logger))
        alchemy.subscribe(AlchemyEventType.INTENT_PARSED, lambda data: on_intent_parsed(data, logger))
        alchemy.subscribe(AlchemyEventType.PLAN_BUILT, lambda data: on_plan_built(data, logger))
        alchemy.subscribe(AlchemyEventType.SEARCH_EXECUTED, lambda data: on_search_executed(data, logger))
        alchemy.subscribe(AlchemyEventType.ARTIFACT_GENERATED, lambda data: on_artifact_generated(data, logger))
        alchemy.subscribe(AlchemyEventType.OPTIMIZATION_SUGGESTED, lambda data: on_optimization_suggested(data, logger))
        alchemy.subscribe(AlchemyEventType.PROCESS_COMPLETED, lambda data: on_process_completed(data, logger))
        alchemy.subscribe(AlchemyEventType.ERROR_OCCURRED, lambda data: on_error_occurred(data, logger))
        alchemy.subscribe(AlchemyEventType.CANCELLATION_REQUESTED, lambda data: on_cancellation_requested(data, logger))
        alchemy.subscribe(AlchemyEventType.PROCESS_CANCELLED, lambda data: on_process_cancelled(data, logger))
        alchemy.subscribe(AlchemyEventType.PROCESS_CHECKPOINT, lambda data: on_process_checkpoint(data, logger))
        
        # 开始处理任务
        if should_resume and alchemy_id:
            # 尝试从中断点恢复
            logger.info(f"尝试从中断点恢复处理 (alchemy_id: {alchemy_id})")
            process_task = asyncio.create_task(alchemy.resume_process(
                query=query,
                input_dirs=input_dirs
            ))
        else:
            # 正常处理（新建或继续）
            if alchemy_id:
                logger.info(f"继续已有炼丹流程的新迭代 (alchemy_id: {alchemy_id})")
            else:
                logger.info(f"开始新的炼丹流程")
                
            process_task = asyncio.create_task(alchemy.process(
                query=query,
                input_dirs=input_dirs
            ))
        
        # 如果启用了自动取消，等待一段时间后取消
        if auto_cancel:
            # 等待3秒后取消处理（仅用于测试）
            await asyncio.sleep(3)
            logger.info("执行自动取消测试")
            await alchemy.cancel_process()
        
        try:
            # 等待处理完成
            result = await process_task
        except asyncio.CancelledError:
            # 如果任务被取消（可能是由于KeyboardInterrupt导致的）
            logger.info("处理任务被取消")
            result = {
                'status': 'cancelled',
                'message': '处理任务被取消',
                'checkpoint': {
                    'alchemy_id': alchemy.alchemy_id
                }
            }
        
        # 如果处理被取消，记录alchemy_id以便后续恢复
        if result.get('status') == 'cancelled':
            logger.info(f"处理被取消，可以使用以下命令恢复: --mode=continue --id={result.get('checkpoint', {}).get('alchemy_id')} --resume")
            # 可以保存恢复信息到文件，方便命令行恢复
            resume_info = {
                "mode": "continue",
                "alchemy_id": result.get('checkpoint', {}).get('alchemy_id'),
                "query": query,
                "resume": True
            }
            resume_file = work_dir / "resume_info.json"
            with open(resume_file, "w", encoding="utf-8") as f:
                json.dump(resume_info, f, ensure_ascii=False, indent=2)
            logger.info(f"恢复信息已保存到: {resume_file}")
        
        return result
            
    except Exception as e:
        logger.error("数据炼丹处理失败: %s", str(e), exc_info=True)
        raise

async def async_main():
    """异步主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='数据炼丹测试工具')
    parser.add_argument('--query', type=str, help='查询文本')
    parser.add_argument('--config', type=str, help='配置文件路径', default='work_dir/config.json')
    parser.add_argument('--mode', type=str, choices=['new', 'continue', 'cancel_test'], 
                     help='运行模式: new(新建), continue(继续/恢复), cancel_test(取消测试)')
    parser.add_argument('--id', type=str, help='要继续的alchemy_id（仅在continue模式下有效）')
    parser.add_argument('--resume', action='store_true', help='是否尝试从中断点恢复（仅在continue模式下有效）')
    args = parser.parse_args()
    
    logger = setup_logging()
    logger.info("开始运行数据炼丹程序")
    
    try:        
        # 创建工作目录
        script_dir = Path(__file__).parent
        work_dir = script_dir.parent / "work_dir"
        test_data_dir = work_dir / "test_data"

        # 初始化默认参数
        query = args.query or "请生成一份关于AI发展的报告"
        input_dirs = [str(test_data_dir)]
        mode = args.mode or "new"  # 默认为新建模式
        alchemy_id = args.id
        should_resume = args.resume
        
        # 首先尝试从配置文件读取
        config_path = Path(args.config)
        if config_path.exists():
            logger.info(f"从配置文件加载: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                query = config.get('query', query)
                if config.get('input_dirs'):
                    input_dirs = config.get('input_dirs')
                    logger.info(f"从配置中读取input_dirs: {input_dirs}")
                # 读取运行模式
                mode = config.get('mode', mode)
                # 在continue模式下读取alchemy_id和resume标志
                if mode == "continue":
                    alchemy_id = config.get('alchemy_id', alchemy_id)
                    should_resume = config.get('resume', should_resume)
        
        # 如果mode是continue但没有提供alchemy_id，尝试从resume_info.json加载
        if mode == "continue" and not alchemy_id:
            resume_file = work_dir / "resume_info.json"
            if resume_file.exists():
                with open(resume_file, 'r', encoding='utf-8') as f:
                    resume_info = json.load(f)
                    alchemy_id = resume_info.get('alchemy_id')
                    if resume_info.get('query'):
                        query = resume_info.get('query')
                    if 'resume' in resume_info:
                        should_resume = resume_info.get('resume')
                        
            # 仍然没有alchemy_id时报错
            if not alchemy_id:
                logger.error("错误: 在continue模式下必须提供alchemy_id！使用--id参数或在配置文件中指定")
                return
        
        # 根据模式执行不同的处理
        if mode == "continue":
            logger.info(f"运行模式: 继续炼丹流程 (alchemy_id: {alchemy_id}, resume: {should_resume})")
            await datamind_alchemy_process(
                alchemy_id=alchemy_id,
                query=query,
                input_dirs=input_dirs,
                work_dir=work_dir / "data_alchemy",  
                logger=logger,
                should_resume=should_resume
            )
            logger.info("继续炼丹流程完成")
        elif mode == "cancel_test":
            # 取消测试模式：启动处理然后自动取消
            logger.info("运行模式: 取消测试")
            logger.info(f"开始数据炼丹测试，查询: {query}，将在3秒后自动取消")
            await datamind_alchemy_process(
                query=query,
                input_dirs=input_dirs,
                work_dir=work_dir / "data_alchemy",  
                logger=logger,
                auto_cancel=True  # 启用自动取消
            )
            logger.info("取消测试完成")
        else:
            # 新建模式：执行标准数据炼丹流程
            logger.info("运行模式: 新建炼丹流程")
            logger.info(f"开始数据炼丹测试，查询: {query}")
            await datamind_alchemy_process(
                query=query,
                input_dirs=input_dirs,
                work_dir=work_dir / "data_alchemy",  
                logger=logger
            )
            logger.info("数据炼丹测试完成")
        
        logger.info("程序运行完成")
        
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}", exc_info=True)
        raise

def main():
    """同步主函数入口"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n程序被用户中断(Ctrl+C)，尝试优雅退出...")
        
        # 创建新的事件循环来处理中断
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        logger = logging.getLogger(__name__)
        
        # 加载配置，尝试获取当前运行的alchemy_id
        try:
            # 首先尝试从全局resume_info.json中获取alchemy_id
            work_dir = Path(__file__).parent.parent / "work_dir"
            global_resume_file = work_dir / "resume_info.json"
            alchemy_id = None
            
            if global_resume_file.exists():
                with open(global_resume_file, 'r', encoding='utf-8') as f:
                    resume_info = json.load(f)
                    alchemy_id = resume_info.get('alchemy_id')
            
            if alchemy_id:
                # 创建任务管理器
                alchemy_manager = AlchemyManager(work_dir=work_dir, logger=logger)
                
                # 创建alchemy实例用于保存检查点
                alchemy = DataMindAlchemy(
                    work_dir=work_dir / "data_alchemy",
                    logger=logger,
                    alchemy_id=alchemy_id,
                    alchemy_manager=alchemy_manager
                )
                
                # 处理中断
                loop.run_until_complete(handle_keyboard_interrupt(alchemy, logger))
                
                # 更新恢复指令，现在包含多个可恢复任务的提示
                print(f"已保存检查点，可以使用以下命令恢复当前任务:")
                print(f"python examples/example_usage.py --mode=continue --id={alchemy_id} --resume")
                print("\n或者查看所有可恢复的任务:")
                print(f"python examples/alchemy_manager_cli.py resumable")
            else:
                print("无法找到当前运行的任务ID，无法保存检查点")
                print("您可以通过以下命令查看所有可恢复的任务:")
                print(f"python examples/alchemy_manager_cli.py resumable")
        except Exception as e:
            print(f"处理中断时发生错误: {str(e)}")
        finally:
            loop.close()
            
        print("程序已退出")
        sys.exit(1)

if __name__ == "__main__":
    main() 