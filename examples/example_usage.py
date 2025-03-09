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

from datamind.services.alchemy_service import DataMindAlchemy, AlchemyEventHandler
from datamind.services.alchemy_manager import AlchemyManager


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
        
        # 在继续模式下，尝试获取原任务的查询文本和输入目录
        if alchemy_id and (should_resume or query is None):
            # 获取任务恢复信息
            resume_info = alchemy_manager.get_task_resume_info(alchemy_id)
            if resume_info:
                logger.info(f"找到任务 {alchemy_id} 的恢复信息")
                
                # 在继续模式下，始终使用原任务的查询文本
                if resume_info.get("query"):
                    if query and query != resume_info["query"]:
                        logger.warning(f"继续任务模式下忽略新提供的查询文本，将使用原任务的查询文本")
                    query = resume_info["query"]
                    logger.info(f"使用原任务的查询文本: {query}")
                
                # 在继续模式下，始终使用原任务的输入目录
                if resume_info.get("input_dirs"):
                    if input_dirs and input_dirs != resume_info["input_dirs"]:
                        logger.warning(f"继续任务模式下忽略新提供的输入目录，将使用原任务的输入目录")
                    input_dirs = resume_info["input_dirs"]
                    logger.info(f"使用原任务的输入目录: {input_dirs}")
        
        # 创建DataMindAlchemy实例
        alchemy = DataMindAlchemy(
            work_dir=work_dir, 
            logger=logger,
            alchemy_id=alchemy_id,
            alchemy_manager=alchemy_manager  # 传入任务管理器
        )
        
        # 创建事件处理器并注册事件
        event_handler = AlchemyEventHandler(logger)
        event_handler.register_events(alchemy)
        
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
        
        # 处理输入目录参数 - 仅在新建模式下处理
        if args.input_dirs and mode != "continue":
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
                # 修改：只有在新建模式下，才使用配置文件中的查询和输入目录
                if mode == "new":
                    if args.query is None:
                        query = config.get('query', query)
                    # 只有当命令行没有指定输入目录时，才使用配置文件中的值
                    if not args.input_dirs and config.get('input_dirs'):
                        input_dirs = config.get('input_dirs')
                        logger.info(f"从配置中读取input_dirs: {input_dirs}")
                
                # 在continue模式下只读取alchemy_id和resume标志
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
                    
                    # 在继续模式下，不再从这里设置查询和输入目录，而是在datamind_alchemy_process中获取
                    logger.info(f"已选择最近的可恢复任务: ID={alchemy_id}")
                else:
                    logger.warning("未找到可恢复的任务")
        
        # 根据模式执行不同的处理
        if mode == "continue":
            logger.info(f"运行模式: 继续炼丹流程 (alchemy_id: {alchemy_id}, resume: {should_resume})")
            
            # 在继续模式下，不显示输入目录信息，因为将使用原任务的输入目录
            logger.info(f"将使用原任务的查询文本和输入目录")
            
            await datamind_alchemy_process(
                alchemy_id=alchemy_id,
                query=None,  # 传入None，表示使用原任务的查询文本
                input_dirs=None,  # 传入None，表示使用原任务的输入目录
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
                
                # 创建事件处理器
                event_handler = AlchemyEventHandler(logger)
                
                # 主动保存当前查询和输入目录信息
                if query or input_dirs:
                    # 确保恢复信息被保存到正确的位置
                    alchemy._save_resume_info(query, input_dirs)
                
                # 处理中断，使用事件处理器
                loop.run_until_complete(event_handler.handle_keyboard_interrupt(alchemy))
                
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