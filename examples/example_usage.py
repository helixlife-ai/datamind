import os
import sys
import json
import asyncio
from pathlib import Path
import logging
import argparse
from datetime import datetime

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from datamind import (
    setup_logging
)

from datamind.services.alchemy_service import DataMindAlchemy, AlchemyEventType
from datamind.services.alchemy_manager import AlchemyManager

# 事件处理函数
async def on_process_started(data, logger):
    """处理开始事件"""
    logger.info(f"=== 炼丹开始 [ID: {data['alchemy_id']}] ===")
    logger.info(f"当前迭代: {data['iteration']}")
    logger.info(f"处理查询: {data['query']}")
    
    # 添加输入目录信息
    if 'input_dirs' in data and data['input_dirs']:
        logger.info(f"使用输入目录: {', '.join(data['input_dirs'])}")

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
    """处理键盘中断事件"""
    logger.info("处理键盘中断，尝试保存检查点...")
    
    try:
        # 请求取消处理
        await alchemy.cancel_process()
        
        # 显示任务目录结构，帮助调试
        work_dir = Path(alchemy.work_dir)
        logger.info(f"工作目录: {work_dir}")
        
        # 使用正确的任务目录路径 - alchemy_dir在DataMindAlchemy中定义
        task_dir = alchemy.alchemy_dir
        logger.info(f"任务目录: {task_dir}")
        
        # 检查任务目录是否存在
        if task_dir.exists():
            logger.info(f"任务目录存在: {task_dir}")
            # 列出任务目录内容
            task_files = list(task_dir.glob("*"))
            logger.info(f"任务目录文件: {[str(f.name) for f in task_files]}")
            
            # 打印目录路径以确认正确结构
            logger.info(f"目录结构: {str(task_dir.relative_to(work_dir.parent))}")
            
            # 尝试从resume_info.json读取额外信息
            resume_info_path = task_dir / "resume_info.json"
            if resume_info_path.exists():
                with open(resume_info_path, 'r', encoding='utf-8') as f:
                    resume_info = json.load(f)
                    logger.info(f"恢复信息: {resume_info}")
        else:
            logger.warning(f"任务目录不存在: {task_dir}")
            
        logger.info("中断处理完成")
        return True
    except Exception as e:
        logger.error(f"处理中断时发生错误: {str(e)}")
        return False

async def datamind_alchemy_process(
    alchemy_id: str = None,
    query: str = None,
    input_dirs: list = None,
    work_dir: Path = None,
    logger: logging.Logger = None,
    should_resume: bool = False,  # 是否尝试从中断点恢复
    alchemy_manager = None  # 添加任务管理器参数
) -> None:
    """统一的数据炼丹处理函数 - 支持新建和继续/恢复"""
    logger = logger or logging.getLogger(__name__)
    
    try:
        # 如果没有传入任务管理器，创建一个新的
        if alchemy_manager is None:
            alchemy_manager = AlchemyManager(work_dir=work_dir.parent, logger=logger)
        
        # 创建DataMindAlchemy实例
        alchemy = DataMindAlchemy(
            work_dir=work_dir, 
            logger=logger,
            alchemy_id=alchemy_id,
            alchemy_manager=alchemy_manager  # 传入任务管理器
        )
        
        # 注册事件处理函数
        alchemy.subscribe(AlchemyEventType.PROCESS_STARTED, lambda data: asyncio.create_task(on_process_started(data, logger)))
        alchemy.subscribe(AlchemyEventType.INTENT_PARSED, lambda data: asyncio.create_task(on_intent_parsed(data, logger)))
        alchemy.subscribe(AlchemyEventType.PLAN_BUILT, lambda data: asyncio.create_task(on_plan_built(data, logger)))
        alchemy.subscribe(AlchemyEventType.SEARCH_EXECUTED, lambda data: asyncio.create_task(on_search_executed(data, logger)))
        alchemy.subscribe(AlchemyEventType.ARTIFACT_GENERATED, lambda data: asyncio.create_task(on_artifact_generated(data, logger)))
        alchemy.subscribe(AlchemyEventType.OPTIMIZATION_SUGGESTED, lambda data: asyncio.create_task(on_optimization_suggested(data, logger)))
        alchemy.subscribe(AlchemyEventType.PROCESS_COMPLETED, lambda data: asyncio.create_task(on_process_completed(data, logger)))
        alchemy.subscribe(AlchemyEventType.ERROR_OCCURRED, lambda data: asyncio.create_task(on_error_occurred(data, logger)))
        alchemy.subscribe(AlchemyEventType.CANCELLATION_REQUESTED, lambda data: asyncio.create_task(on_cancellation_requested(data, logger)))
        alchemy.subscribe(AlchemyEventType.PROCESS_CANCELLED, lambda data: asyncio.create_task(on_process_cancelled(data, logger)))
        alchemy.subscribe(AlchemyEventType.PROCESS_CHECKPOINT, lambda data: asyncio.create_task(on_process_checkpoint(data, logger)))
        
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
                "resume": True,
                "input_dirs": input_dirs  # 确保保存输入目录信息
            }
            
            # 使用alchemy.alchemy_dir作为恢复信息保存位置
            # alchemy_dir已经是正确的目录：work_dir/data_alchemy/alchemy_runs/alchemy_{alchemy_id}
            resume_file = alchemy.alchemy_dir / "resume_info.json"
            
            # 记录路径信息，帮助诊断
            logger.debug(f"保存恢复信息 - 任务ID: {alchemy.alchemy_id}")
            logger.debug(f"保存恢复信息 - 任务目录: {alchemy.alchemy_dir}")
            logger.debug(f"保存恢复信息 - 恢复文件: {resume_file}")
            
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
    parser.add_argument('--mode', type=str, choices=['new', 'continue'], 
                     help='运行模式: new(新建), continue(继续/恢复)')
    parser.add_argument('--id', type=str, help='要继续的alchemy_id（仅在continue模式下有效）')
    parser.add_argument('--resume', action='store_true', help='是否尝试从中断点恢复（仅在continue模式下有效）')
    parser.add_argument('--cancel', action='store_true', help='取消指定ID的任务')
    parser.add_argument('--input-dirs', type=str, help='输入目录列表（JSON格式字符串）')
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
        input_dirs = [str(test_data_dir)]  # 默认使用test_data目录
        mode = args.mode or "new"  # 默认为新建模式
        alchemy_id = args.id
        should_resume = args.resume
        should_cancel = args.cancel  # 新增：是否需要取消任务
        
        # 处理输入目录参数
        if args.input_dirs:
            try:
                # 解析JSON格式的输入目录列表
                custom_input_dirs = json.loads(args.input_dirs)
                if isinstance(custom_input_dirs, list) and custom_input_dirs:
                    input_dirs = custom_input_dirs
                    logger.info(f"从命令行参数读取输入目录: {input_dirs}")
            except json.JSONDecodeError as e:
                logger.error(f"解析输入目录参数失败: {e}")
        
        # 首先尝试从配置文件读取
        config_path = Path(args.config)
        if config_path.exists():
            logger.info(f"从配置文件加载: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 修改：只有当命令行参数未提供时，才使用配置文件中的值
                if args.query is None:
                    query = config.get('query', query)
                if not args.mode and config.get('mode'):
                    mode = config.get('mode')
                # 只有当命令行没有指定输入目录时，才使用配置文件中的值
                if not args.input_dirs and config.get('input_dirs'):
                    input_dirs = config.get('input_dirs')
                    logger.info(f"从配置中读取input_dirs: {input_dirs}")
                # 在continue模式下读取alchemy_id和resume标志
                if mode == "continue":
                    if args.id is None and config.get('alchemy_id'):
                        alchemy_id = config.get('alchemy_id')
                    if not args.resume and config.get('resume'):
                        should_resume = config.get('resume')
        
        # 创建任务管理器
        alchemy_manager = AlchemyManager(work_dir=work_dir, logger=logger)
        
        # 如果指定了取消参数，则取消指定的任务
        if should_cancel and alchemy_id:
            logger.info(f"准备取消任务 (alchemy_id: {alchemy_id})")
            # 创建DataMindAlchemy实例
            alchemy = DataMindAlchemy(
                work_dir=work_dir / "data_alchemy", 
                logger=logger,
                alchemy_id=alchemy_id,
                alchemy_manager=alchemy_manager
            )
            
            # 发送取消请求
            await alchemy.cancel_process()
            logger.info(f"已发送取消请求 (alchemy_id: {alchemy_id})")
            return
        
        # 如果是恢复模式且没有指定alchemy_id
        if should_resume and not alchemy_id:
            # 如果没有找到alchemy_id，尝试从任务管理器获取可恢复任务
            if not alchemy_id:
                # 获取所有可恢复的任务
                resumable_tasks = alchemy_manager.get_resumable_tasks()
                
                if resumable_tasks:
                    logger.info(f"找到 {len(resumable_tasks)} 个可恢复的任务:")
                    for idx, task in enumerate(resumable_tasks):
                        task_id = task.get('id')
                        task_query = task.get('resume_info', {}).get('query', '未知查询')
                        task_time = task.get('resume_info', {}).get('timestamp', '未知时间')
                        logger.info(f"  {idx+1}. ID: {task_id} | 查询: {task_query} | 时间: {task_time}")
                    
                    # 使用最近的可恢复任务
                    latest_task = resumable_tasks[0]
                    alchemy_id = latest_task.get('id')
                    
                    # 使用恢复信息中的查询和输入目录(如果有)
                    resume_info = latest_task.get('resume_info', {})
                    if not query and "query" in resume_info:
                        query = resume_info["query"]
                    if not args.input_dirs and "input_dirs" in resume_info:
                        input_dirs = resume_info["input_dirs"]
                        
                    logger.info(f"已选择最近的可恢复任务: ID={alchemy_id}, 查询={query}")
                else:
                    logger.warning("未找到可恢复的任务")
        
        # 根据模式执行不同的处理
        if mode == "continue":
            logger.info(f"运行模式: 继续炼丹流程 (alchemy_id: {alchemy_id}, resume: {should_resume})")
            logger.info(f"使用输入目录: {input_dirs}")
            await datamind_alchemy_process(
                alchemy_id=alchemy_id,
                query=query,
                input_dirs=input_dirs,
                work_dir=work_dir / "data_alchemy",  
                logger=logger,
                should_resume=should_resume,
                alchemy_manager=alchemy_manager  # 添加任务管理器
            )
            logger.info("继续炼丹流程完成")
        else:
            # 新建模式：执行标准数据炼丹流程
            logger.info("运行模式: 新建炼丹流程")
            logger.info(f"开始数据炼丹测试，查询: {query}")
            logger.info(f"使用输入目录: {input_dirs}")
            await datamind_alchemy_process(
                query=query,
                input_dirs=input_dirs,
                work_dir=work_dir / "data_alchemy",  
                logger=logger,
                alchemy_manager=alchemy_manager  # 添加任务管理器
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
        print("\n程序被用户中断(Ctrl+C)，尝试保存检查点...")
        
        # 创建新的事件循环来处理中断
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        logger = logging.getLogger(__name__)
        
        # 加载配置，尝试获取当前运行的alchemy_id
        try:
            # 不再从latest_task.json获取alchemy_id
            work_dir = Path(__file__).parent.parent / "work_dir"
            alchemy_id = None
            query = None
            input_dirs = None
            
            # 尝试从配置文件获取
            config_file = work_dir / "config.json"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    alchemy_id = config.get('alchemy_id')
                    query = config.get('query')
                    input_dirs = config.get('input_dirs')
            
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
                
                # 主动保存当前查询和输入目录信息
                if query or input_dirs:
                    # 确保恢复信息被保存到正确的位置
                    alchemy._save_resume_info(query, input_dirs)
                
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