import os
import sys
import json
import asyncio
from pathlib import Path
import logging
import argparse
from typing import Dict, List, Optional, Any, Tuple
import time

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from datamind import (
    setup_logging
)
from datamind.services import DataMindAlchemy, AlchemyEventHandler, AlchemyManager


class ConfigManager:
    """配置管理类"""
    
    def __init__(self, config_path: Path, logger: logging.Logger = None):
        self.config_path = config_path
        self.config = {}
        self.logger = logger or logging.getLogger(__name__)
        self._load_config()
    
    def _load_config(self) -> None:
        """加载配置文件"""
        if self.config_path.exists():
            self.logger.info(f"从配置文件加载: {self.config_path}")
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except json.JSONDecodeError as e:
                self.logger.error(f"配置文件JSON格式错误: {e}")
                # 使用空配置继续
                self.config = {}
            except Exception as e:
                self.logger.error(f"加载配置文件失败: {e}")
                # 使用空配置继续
                self.config = {}
        else:
            self.logger.warning(f"配置文件不存在: {self.config_path}，将使用默认配置")
            # 创建默认配置
            self.config = {
                "query": "请生成一份关于AI发展的报告",
                "input_dirs": [],
                "resume": False
            }
            # 尝试创建配置文件目录
            try:
                self.config_path.parent.mkdir(exist_ok=True, parents=True)
                # 保存默认配置
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, ensure_ascii=False, indent=2)
                self.logger.info(f"已创建默认配置文件: {self.config_path}")
            except Exception as e:
                self.logger.error(f"创建默认配置文件失败: {e}")
    
    def get(self, key: str, default=None) -> Any:
        """获取配置项"""
        value = self.config.get(key, default)
        if value is None and default is not None:
            self.logger.debug(f"配置项 '{key}' 不存在，使用默认值: {default}")
            return default
        return value
    
    def get_new_mode_config(self, cmd_query: Optional[str], cmd_input_dirs: Optional[List[str]]) -> Tuple[str, List[str]]:
        """获取新建模式的配置"""
        # 优先使用命令行参数
        query = cmd_query
        if query is None:
            # 如果命令行没有指定，使用配置文件
            query = self.get('query', "请生成一份关于AI发展的报告")
            self.logger.info(f"使用配置文件中的查询: {query}")
        
        # 只有当命令行没有指定输入目录时，才使用配置文件中的值
        input_dirs = None
        if cmd_input_dirs:
            input_dirs = cmd_input_dirs
            self.logger.info(f"使用命令行指定的输入目录: {input_dirs}")
        elif self.get('input_dirs'):
            input_dirs = self.get('input_dirs')
            self.logger.info(f"使用配置文件中的输入目录: {input_dirs}")
        else:
            self.logger.info("未指定输入目录，将使用默认目录")
            
        return query, input_dirs
    
    def get_continue_mode_config(self, cmd_id: Optional[str], cmd_resume: bool) -> Tuple[Optional[str], bool]:
        """获取继续模式的配置"""
        # 优先使用命令行参数
        alchemy_id = cmd_id
        if alchemy_id is None:
            # 如果命令行没有指定，使用配置文件
            alchemy_id = self.get('alchemy_id')
            if alchemy_id:
                self.logger.info(f"使用配置文件中的alchemy_id: {alchemy_id}")
            else:
                self.logger.warning("未指定alchemy_id，将尝试查找最近的任务")
        
        # 优先使用命令行参数
        should_resume = cmd_resume
        if not should_resume:
            # 如果命令行没有指定，使用配置文件
            should_resume = self.get('resume', False)
            if should_resume:
                self.logger.info("使用配置文件中的resume设置: True")
        
        return alchemy_id, should_resume


class ArgParser:
    """命令行参数解析类"""
    
    def __init__(self):
        self.parser = self._create_parser()
        
    def _create_parser(self) -> argparse.ArgumentParser:
        """创建命令行参数解析器"""
        parser = argparse.ArgumentParser(description='数据炼丹测试工具')
        parser.add_argument('--query', type=str, help='查询文本')
        parser.add_argument('--config', type=str, help='配置文件路径', default='work_dir/config.json')
        parser.add_argument('--mode', type=str, choices=['new', 'continue'], 
                         help='运行模式: new(新建), continue(继续/恢复)')
        parser.add_argument('--id', type=str, help='要继续的alchemy_id（仅在continue模式下有效）')
        parser.add_argument('--resume', action='store_true', help='是否尝试从中断点恢复（仅在continue模式下有效）')
        parser.add_argument('--cancel', action='store_true', help='取消指定ID的任务')
        parser.add_argument('--input-dirs', type=str, help='输入目录列表（JSON格式字符串）')
        return parser
    
    def parse_args(self) -> argparse.Namespace:
        """解析命令行参数"""
        return self.parser.parse_args()
    
    def parse_input_dirs(self, input_dirs_str: str) -> Optional[List[str]]:
        """解析输入目录参数"""
        if not input_dirs_str:
            return None
            
        try:
            # 解析JSON格式的输入目录列表
            custom_input_dirs = json.loads(input_dirs_str)
            if isinstance(custom_input_dirs, list) and custom_input_dirs:
                print(f"从命令行参数读取输入目录: {custom_input_dirs}")
                return custom_input_dirs
        except json.JSONDecodeError as e:
            print(f"解析输入目录参数失败: {e}")
        
        return None


class AlchemyClient:
    """炼丹客户端类"""
    
    def __init__(self, work_dir: Path, logger: logging.Logger):
        self.work_dir = work_dir
        self.logger = logger
        self.alchemy_work_dir = work_dir / "data_alchemy"
        self.test_data_dir = work_dir / "test_data"
        self.alchemy_manager = AlchemyManager(work_dir=work_dir, logger=logger)
        self.model_manager = None  # 初始化model_manager为None
        
        # 尝试导入并初始化ModelManager
        try:
            from datamind.llms.model_manager import ModelManager
            self.model_manager = ModelManager(logger=logger)  # 使用相同的logger
            self.logger.info("已初始化ModelManager")
        except ImportError:
            self.logger.warning("无法导入ModelManager，将使用默认模型管理器")
    
    async def process_task(self, 
                           mode: str, 
                           alchemy_id: Optional[str], 
                           query: Optional[str], 
                           input_dirs: Optional[List[str]], 
                           should_resume: bool) -> None:
        """处理炼丹任务"""
        if mode == "continue":
            self.logger.info(f"运行模式: 继续炼丹流程 (alchemy_id: {alchemy_id}, resume: {should_resume})")
            self.logger.info(f"将使用原任务的查询文本和输入目录")
            
            await self._run_alchemy_process(
                alchemy_id=alchemy_id,
                query=None,  # 传入None，表示使用原任务的查询文本
                input_dirs=None,  # 传入None，表示使用原任务的输入目录
                should_resume=should_resume
            )
            self.logger.info("继续炼丹流程完成")
        else:
            # 新建模式：执行标准数据炼丹流程
            self.logger.info("运行模式: 新建炼丹流程")
            self.logger.info(f"开始数据炼丹测试，查询: {query}")
            self.logger.info(f"使用输入目录: {input_dirs}")
            
            # 如果没有提供输入目录，使用默认测试目录
            if not input_dirs:
                input_dirs = [str(self.test_data_dir)]
                self.logger.info(f"使用默认测试数据目录: {input_dirs}")
                
            await self._run_alchemy_process(
                query=query,
                input_dirs=input_dirs,
                alchemy_id=None,
                should_resume=False
            )
            self.logger.info("数据炼丹测试完成")
    
    async def _run_alchemy_process(self, 
                                  alchemy_id: Optional[str] = None,
                                  query: Optional[str] = None,
                                  input_dirs: Optional[List[str]] = None,
                                  should_resume: bool = False) -> Dict:
        """运行炼丹处理函数"""
        return await datamind_alchemy_process(
            alchemy_id=alchemy_id,
            query=query,
            input_dirs=input_dirs,
            work_dir=self.alchemy_work_dir,  
            logger=self.logger,
            should_resume=should_resume,
            alchemy_manager=self.alchemy_manager,
            model_manager=self.model_manager if hasattr(self, 'model_manager') else None  # 添加model_manager参数
        )
    
    async def cancel_task(self, alchemy_id: str) -> None:
        """取消炼丹任务"""
        self.logger.info(f"准备取消任务 (alchemy_id: {alchemy_id})")
        
        # 创建DataMindAlchemy实例
        alchemy = DataMindAlchemy(
            work_dir=self.alchemy_work_dir, 
            logger=self.logger,
            alchemy_id=alchemy_id,
            alchemy_manager=self.alchemy_manager
        )
        
        # 发送取消请求
        await alchemy.cancel_process()
        self.logger.info(f"已发送取消请求 (alchemy_id: {alchemy_id})")
    
    def find_resumable_task(self) -> Optional[str]:
        """查找可恢复的任务ID"""
        # 获取所有可恢复的任务
        resumable_tasks = self.alchemy_manager.get_resumable_tasks()
        
        if resumable_tasks:
            self.logger.info(f"找到 {len(resumable_tasks)} 个可恢复的任务:")
            for idx, task in enumerate(resumable_tasks):
                task_id = task.get('id')
                task_query = task.get('resume_info', {}).get('query', '未知查询')
                task_time = task.get('resume_info', {}).get('timestamp', '未知时间')
                self.logger.info(f"  {idx+1}. ID: {task_id} | 查询: {task_query} | 时间: {task_time}")
            
            # 使用最近的可恢复任务
            latest_task = resumable_tasks[0]
            alchemy_id = latest_task.get('id')
            self.logger.info(f"已选择最近的可恢复任务: ID={alchemy_id}")
            return alchemy_id
        else:
            self.logger.warning("未找到可恢复的任务")
            return None
    
    async def handle_interrupt(self, alchemy_id: Optional[str], query: Optional[str], input_dirs: Optional[List[str]]) -> None:
        """处理键盘中断"""
        if not alchemy_id:
            self.logger.warning("无法找到当前运行的任务ID，尝试查找最近的任务")
            # 尝试查找最近的任务
            alchemy_id = self.find_resumable_task()
            if not alchemy_id:
                self.logger.error("无法找到可恢复的任务，无法保存检查点")
                print("无法找到当前运行的任务ID，无法保存检查点")
                print("您可以通过以下命令查看所有可恢复的任务:")
                print(f"python scripts/alchemy_manager_cli.py resumable")
                return
        
        try:
            # 创建alchemy实例用于保存检查点
            alchemy = DataMindAlchemy(
                work_dir=self.alchemy_work_dir,
                logger=self.logger,
                alchemy_id=alchemy_id,
                alchemy_manager=self.alchemy_manager
            )
            
            # 创建事件处理器
            event_handler = AlchemyEventHandler(self.logger)
            
            # 主动保存当前查询和输入目录信息
            if query or input_dirs:
                # 确保恢复信息被保存到正确的位置
                alchemy._save_resume_info(query, input_dirs)
                self.logger.info(f"已保存查询和输入目录信息")
            
            # 处理中断，使用事件处理器
            await event_handler.handle_keyboard_interrupt(alchemy)
            
            # 更新恢复指令，现在包含多个可恢复任务的提示
            self.logger.info(f"已保存检查点，可以使用以下命令恢复当前任务:")
            print(f"已保存检查点，可以使用以下命令恢复当前任务:")
            print(f"python examples/example_usage.py --mode=continue --id={alchemy_id} --resume")
            print("\n或者查看所有可恢复的任务:")
            print(f"python scripts/alchemy_manager_cli.py resumable")
        except Exception as e:
            self.logger.error(f"处理中断时发生错误: {str(e)}", exc_info=True)
            print(f"处理中断时发生错误: {str(e)}")


async def datamind_alchemy_process(
    alchemy_id: str = None,
    query: str = None,
    input_dirs: list = None,
    work_dir: Path = None,
    logger: logging.Logger = None,  # 从调用者接收logger对象
    should_resume: bool = False,  # 是否尝试从中断点恢复
    alchemy_manager = None,  # 添加任务管理器参数
    model_manager = None  # 添加模型管理器参数
) -> None:

    """统一的数据炼丹处理函数 - 支持新建和继续/恢复"""
    try:
        # 确保logger不为None
        if logger is None:
            # 创建默认logger
            logger = logging.getLogger("datamind_alchemy")
            logger.setLevel(logging.INFO)
            
            # 添加控制台处理器
            if not logger.handlers:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO)
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)
                
            logger.warning("未提供logger，已创建默认logger")
        
        # 确保work_dir不为None
        if work_dir is None:
            work_dir = Path("work_dir") / "data_alchemy"
            work_dir.mkdir(exist_ok=True, parents=True)
            logger.warning(f"未提供work_dir，使用默认目录: {work_dir}")
        
        # 如果没有传入任务管理器，创建一个新的
        if alchemy_manager is None:
            alchemy_manager = AlchemyManager(work_dir=work_dir.parent, logger=logger)  # logger传递给AlchemyManager
        
        # 在继续模式下，尝试获取原任务的查询文本和输入目录
        if alchemy_id and (should_resume or query is None):
            # 获取任务恢复信息
            resume_info = alchemy_manager.get_task_resume_info(alchemy_id)
            if resume_info:
                logger.info(f"找到任务 {alchemy_id} 的恢复信息")  # 使用logger记录信息
                
                # 在继续模式下，始终使用原任务的查询文本
                if resume_info.get("query"):
                    if query and query != resume_info["query"]:
                        logger.warning(f"继续任务模式下忽略新提供的查询文本，将使用原任务的查询文本")  # 使用logger记录警告
                    query = resume_info["query"]
                    logger.info(f"使用原任务的查询文本: {query}")  # 使用logger记录信息
                
                # 在继续模式下，始终使用原任务的输入目录
                if resume_info.get("input_dirs"):
                    if input_dirs and input_dirs != resume_info["input_dirs"]:
                        logger.warning(f"继续任务模式下忽略新提供的输入目录，将使用原任务的输入目录")  # 使用logger记录警告
                    input_dirs = resume_info["input_dirs"]
                    logger.info(f"使用原任务的输入目录: {input_dirs}")  # 使用logger记录信息
        
        # 创建DataMindAlchemy实例
        alchemy = DataMindAlchemy(
            work_dir=work_dir, 
            logger=logger,  # logger传递给DataMindAlchemy实例
            alchemy_id=alchemy_id,
            alchemy_manager=alchemy_manager,  # 传入任务管理器
            model_manager=model_manager  # 传入模型管理器
        )
        
        # 创建事件处理器并注册事件
        event_handler = AlchemyEventHandler(logger)  # logger传递给AlchemyEventHandler
        event_handler.register_events(alchemy)
        
        # 开始处理任务
        if should_resume and alchemy_id:
            # 尝试从中断点恢复
            logger.info(f"尝试从中断点恢复处理 (alchemy_id: {alchemy_id})")  # 使用logger记录信息
            process_task = asyncio.create_task(alchemy.resume_process(
                query=query,
                input_dirs=input_dirs
            ))
        else:
            # 正常处理（新建或继续）
            if alchemy_id:
                logger.info(f"继续已有炼丹流程的新迭代 (alchemy_id: {alchemy_id})")  # 使用logger记录信息
            else:
                logger.info(f"开始新的炼丹流程")  # 使用logger记录信息
                
            process_task = asyncio.create_task(alchemy.process(
                query=query,
                input_dirs=input_dirs
            ))
        
        try:
            # 等待处理完成
            result = await process_task
        except asyncio.CancelledError:
            # 如果任务被取消（可能是由于KeyboardInterrupt导致的）
            logger.info("处理任务被取消")  # 使用logger记录信息
            result = {
                'status': 'cancelled',
                'message': '处理任务被取消',
                'checkpoint': {
                    'alchemy_id': alchemy.alchemy_id
                }
            }
        
        # 如果处理被取消，记录alchemy_id以便后续恢复
        if result.get('status') == 'cancelled':
            logger.info(f"处理被取消，可以使用以下命令恢复: --mode=continue --id={result.get('checkpoint', {}).get('alchemy_id')} --resume")  # 使用logger记录信息
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
            logger.debug(f"保存恢复信息 - 任务ID: {alchemy.alchemy_id}")  # 使用logger记录调试信息
            logger.debug(f"保存恢复信息 - 任务目录: {alchemy.alchemy_dir}")  # 使用logger记录调试信息
            logger.debug(f"保存恢复信息 - 恢复文件: {resume_file}")  # 使用logger记录调试信息
            
            with open(resume_file, "w", encoding="utf-8") as f:
                json.dump(resume_info, f, ensure_ascii=False, indent=2)
            logger.info(f"恢复信息已保存到: {resume_file}")  # 使用logger记录信息
        
        return result
            
    except Exception as e:
        # 确保即使在异常情况下也能记录日志
        if logger:
            logger.error("数据炼丹处理失败: %s", str(e), exc_info=True)  # 使用logger记录错误
        else:
            print(f"错误: 数据炼丹处理失败: {str(e)}")
        raise


async def async_main():
    """异步主函数"""
    # 解析命令行参数
    arg_parser = ArgParser()
    args = arg_parser.parse_args()
    
    # 创建工作目录
    script_dir = Path(__file__).parent
    work_dir = script_dir.parent / "work_dir"
    work_dir.mkdir(exist_ok=True, parents=True)
    
    # 创建日志目录
    log_dir = work_dir / "logs"
    log_dir.mkdir(exist_ok=True, parents=True)
    
    # 设置日志文件名（使用时间戳确保唯一性）
    log_file = log_dir / f"datamind_{time.strftime('%Y%m%d_%H%M%S')}.log"
    
    # 初始化日志记录器
    logger = setup_logging()
    logger.setLevel(logging.INFO)  # 设置全局日志级别       
    logger.info("开始运行数据炼丹程序")
    
    try:
        # 加载配置
        config = ConfigManager(Path(args.config))
        
        # 创建炼丹客户端
        client = AlchemyClient(work_dir, logger)
        
        # 解析基本参数
        mode = args.mode or "new"  # 默认为新建模式
        should_cancel = args.cancel
        
        # 解析输入目录参数(仅在新建模式下)
        input_dirs = None
        if args.input_dirs and mode != "continue":
            input_dirs = arg_parser.parse_input_dirs(args.input_dirs)
        
        # 如果指定了取消参数，取消指定任务
        if should_cancel and args.id:
            await client.cancel_task(args.id)
            return
        
        if mode == "continue":
            # 获取继续模式的配置
            alchemy_id, should_resume = config.get_continue_mode_config(args.id, args.resume)
            
            # 如果是恢复模式且没有指定alchemy_id，尝试查找可恢复任务
            if should_resume and not alchemy_id:
                alchemy_id = client.find_resumable_task()
            
            # 继续/恢复任务
            await client.process_task(
                mode=mode,
                alchemy_id=alchemy_id,
                query=None,  # 将使用原任务查询
                input_dirs=None,  # 将使用原任务输入目录
                should_resume=should_resume
            )
        else:
            # 获取新建模式的配置
            query, config_input_dirs = config.get_new_mode_config(args.query, input_dirs)
            
            # 如果从命令行和配置文件都没有获取到输入目录，使用默认目录
            if not config_input_dirs:
                config_input_dirs = [str(client.test_data_dir)]
            
            # 新建任务
            await client.process_task(
                mode=mode,
                alchemy_id=None,
                query=query,
                input_dirs=config_input_dirs,
                should_resume=False
            )
        
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
        
        # 处理中断
        try:
            # 创建或获取logger
            try:
                logger = setup_logging()
                # 确保logger有处理器
                if not logger.handlers:
                    console_handler = logging.StreamHandler()
                    console_handler.setLevel(logging.INFO)
                    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                    console_handler.setFormatter(formatter)
                    logger.addHandler(console_handler)
            except Exception as log_error:
                print(f"创建日志记录器失败: {str(log_error)}")
                logger = logging.getLogger("emergency_logger")
                console_handler = logging.StreamHandler()
                logger.addHandler(console_handler)
            
            # 设置工作目录
            work_dir = Path(__file__).parent.parent / "work_dir"
            work_dir.mkdir(exist_ok=True, parents=True)
            
            # 加载配置
            try:
                config_path = work_dir / "config.json"
                config = ConfigManager(config_path)
                alchemy_id = config.get('alchemy_id')
                query = config.get('query')
                input_dirs = config.get('input_dirs')
            except Exception as config_error:
                logger.error(f"加载配置失败: {str(config_error)}")
                alchemy_id = None
                query = None
                input_dirs = None
            
            # 创建客户端并处理中断
            client = AlchemyClient(work_dir, logger)
            loop.run_until_complete(client.handle_interrupt(alchemy_id, query, input_dirs))
            
        except Exception as e:
            print(f"处理中断时发生错误: {str(e)}")
        finally:
            loop.close()
        
        print("程序已退出")
        sys.exit(1)


if __name__ == "__main__":
    main() 