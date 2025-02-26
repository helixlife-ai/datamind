import os
import sys
import json
import asyncio
import threading
import queue
from pathlib import Path
import logging
from datetime import datetime
import traceback
import time
from enum import Enum, auto
from typing import Dict, List, Callable, Union
import argparse

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

# 导入真实的DataMindAlchemy类和setup_logging
from datamind.utils.common import setup_logging
from datamind.services.alchemy_service import DataMindAlchemy

# 定义任务类型枚举
class TaskType(Enum):
    PROCESS_QUERY = auto()
    SHUTDOWN = auto()

# 定义任务事件类
class AlchemyTask:
    def __init__(
        self, 
        task_type: TaskType,
        query: str = None,
        input_dirs: List[str] = None,
        work_dir: Path = None,
        callback: Callable = None,
        task_id: str = None
    ):
        self.task_id = task_id or f"task_{int(time.time())}_{hash(query) if query else 0}"
        self.task_type = task_type
        self.query = query
        self.input_dirs = input_dirs or []
        self.work_dir = work_dir
        self.callback = callback
        self.created_at = datetime.now()
        
    def __str__(self):
        if self.query:
            return f"AlchemyTask({self.task_id}, {self.task_type}, query={self.query[:20]}...)"
        return f"AlchemyTask({self.task_id}, {self.task_type})"

# 事件驱动的数据炼丹服务线程
class DataMindAlchemyService(threading.Thread):
    def __init__(
        self,
        work_dir: Union[str, Path] = None,
        max_queue_size: int = 100,
        logger: logging.Logger = None,
        config_path: Union[str, Path] = None
    ):
        super().__init__(daemon=True)
        self.logger = logger or logging.getLogger(__name__)
        
        # 确定项目根目录
        if not work_dir:
            current_file = Path(__file__).parent
            project_root = current_file.parent
            work_dir = project_root / "work_dir"
        else:
            work_dir = Path(work_dir)
            
        self.work_dir = work_dir
        self.work_dir.mkdir(exist_ok=True, parents=True)
        
        # 读取配置文件（如果提供）
        self.config = {}
        if config_path:
            config_path = Path(config_path)
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        self.config = json.load(f)
                    self.logger.info(f"从配置文件加载: {config_path}")
                except Exception as e:
                    self.logger.error(f"读取配置文件失败: {str(e)}")
        
        # 创建任务队列
        self.task_queue = queue.Queue(maxsize=max_queue_size)
        
        # 创建事件循环
        self.loop = None
        self.running = False
        self.is_ready = False  # 添加一个标志表示服务是否准备就绪
        self.processing = False
        
        # 保存任务状态
        self.tasks = {}
        self.results = {}
        
        self.logger.info(f"数据炼丹服务初始化完成，工作目录：{self.work_dir}")
        
    def submit_task(
        self, 
        query: str, 
        input_dirs: List[str] = None,
        task_id: str = None,
        callback: Callable = None,
        mode: str = "new",
        alchemy_id: str = None
    ) -> str:
        """提交查询任务到队列
        
        Args:
            query: 查询文本
            input_dirs: 输入数据目录列表
            task_id: 任务ID，默认自动生成
            callback: 任务完成回调函数
            mode: 运行模式，"new"(新建)或"continue"(继续)
            alchemy_id: 要继续的炼丹ID，仅在continue模式下有效
            
        Returns:
            str: 任务ID
        """
        if not self.is_ready:
            raise RuntimeError("服务尚未准备就绪")
            
        # 创建任务
        task = AlchemyTask(
            task_type=TaskType.PROCESS_QUERY,
            query=query,
            input_dirs=input_dirs,
            work_dir=self.work_dir / "data_alchemy",
            callback=callback,
            task_id=task_id
        )
        
        # 添加额外的任务信息
        task.mode = mode
        task.alchemy_id = alchemy_id
        
        # 将任务加入队列
        try:
            self.task_queue.put(task, block=False)
            self.tasks[task.task_id] = {
                "status": "queued",
                "submitted_at": datetime.now().isoformat(),
                "task": task,
                "mode": mode,
                "alchemy_id": alchemy_id if mode == "continue" else None
            }
            self.logger.info(f"任务 {task.task_id} 已提交到队列，模式：{mode}")
            return task.task_id
        except queue.Full:
            self.logger.error("任务队列已满，无法提交新任务")
            raise RuntimeError("任务队列已满，请稍后再试")
    
    def get_task_status(self, task_id: str) -> Dict:
        """获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 任务状态信息
        """
        if task_id in self.tasks:
            status_info = self.tasks[task_id].copy()
            # 移除任务对象，避免序列化问题
            if "task" in status_info:
                del status_info["task"]
            return status_info
        return {"status": "unknown", "message": "任务不存在"}
    
    def get_result(self, task_id: str) -> Dict:
        """获取任务结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 任务结果
        """
        if task_id in self.results:
            return self.results[task_id]
        return None
    
    def shutdown(self):
        """关闭服务"""
        if not self.running:
            return
            
        self.logger.info("正在关闭数据炼丹服务...")
        shutdown_task = AlchemyTask(task_type=TaskType.SHUTDOWN)
        self.task_queue.put(shutdown_task)
        self.join(timeout=30)  # 等待线程结束，最多30秒
        self.logger.info("数据炼丹服务已关闭")
    
    def _update_task_status(self, task_id: str, status: str, message: str = None, result: Dict = None):
        """更新任务状态"""
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = status
            self.tasks[task_id]["updated_at"] = datetime.now().isoformat()
            if message:
                self.tasks[task_id]["message"] = message
            if result:
                self.results[task_id] = result
                self.tasks[task_id]["result_available"] = True
        
    def run(self):
        """线程主运行方法"""
        self.logger.info("数据炼丹服务线程启动")
        self.running = True
        
        # 创建新的事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            # 标记服务已准备就绪
            self.is_ready = True
            self.logger.info("数据炼丹服务已准备就绪，可以接受任务")
            
            while self.running:
                try:
                    # 从队列获取任务，等待1秒
                    task = self.task_queue.get(timeout=1)
                    self.processing = True
                    
                    if task.task_type == TaskType.SHUTDOWN:
                        self.logger.info("收到关闭命令，服务即将停止")
                        self.running = False
                        break
                    
                    # 处理查询任务
                    elif task.task_type == TaskType.PROCESS_QUERY:
                        self._update_task_status(task.task_id, "processing")
                        self.logger.info(f"开始处理任务 {task.task_id}: {task.query[:50]}...")
                        
                        try:
                            # 执行任务
                            result = self.loop.run_until_complete(
                                self._process_query_task(task)
                            )
                            
                            # 更新任务状态
                            if result["status"] == "success":
                                self._update_task_status(
                                    task.task_id, 
                                    "completed", 
                                    "任务处理成功", 
                                    result
                                )
                            else:
                                self._update_task_status(
                                    task.task_id, 
                                    "failed", 
                                    result.get("message", "任务处理失败"), 
                                    result
                                )
                                
                            # 执行回调
                            if task.callback:
                                try:
                                    task.callback(task.task_id, result)
                                except Exception as e:
                                    self.logger.error(f"任务回调执行失败: {str(e)}")
                                    
                        except Exception as e:
                            error_msg = f"任务处理异常: {str(e)}"
                            self.logger.error(error_msg, exc_info=True)
                            self._update_task_status(
                                task.task_id, 
                                "error", 
                                error_msg, 
                                {"status": "error", "message": error_msg}
                            )
                            
                            # 执行回调，传递错误信息
                            if task.callback:
                                try:
                                    task.callback(
                                        task.task_id, 
                                        {"status": "error", "message": error_msg}
                                    )
                                except Exception as cb_err:
                                    self.logger.error(f"错误回调执行失败: {str(cb_err)}")
                    
                    # 标记任务完成
                    self.task_queue.task_done()
                    self.processing = False
                    
                except queue.Empty:
                    # 队列为空，继续等待
                    pass
                except Exception as e:
                    self.logger.error(f"任务处理循环异常: {str(e)}", exc_info=True)
                    time.sleep(1)  # 避免异常情况下的高速循环
        
        except Exception as e:
            self.logger.error(f"服务线程异常: {str(e)}", exc_info=True)
        finally:
            # 关闭事件循环
            if self.loop:
                self.loop.close()
            self.running = False
            self.logger.info("数据炼丹服务线程已停止")
    
    async def _process_query_task(self, task: AlchemyTask) -> Dict:
        """处理查询任务"""
        start_time = datetime.now()
        task_dir = self.work_dir / "tasks" / task.task_id
        task_dir.mkdir(exist_ok=True, parents=True)
        
        # 保存任务信息
        task_info = {
            "task_id": task.task_id,
            "query": task.query,
            "input_dirs": task.input_dirs,
            "created_at": task.created_at.isoformat(),
            "started_at": start_time.isoformat(),
            "mode": getattr(task, "mode", "new"),
            "alchemy_id": getattr(task, "alchemy_id", None)
        }
        
        # 使用异步方式写入文件
        await asyncio.to_thread(
            lambda: open(task_dir / "task_info.json", "w", encoding="utf-8").write(
                json.dumps(task_info, ensure_ascii=False, indent=2)
            )
        )
        
        try:
            # 创建任务专用的工作目录
            alchemy_work_dir = self.work_dir / "data_alchemy"
            alchemy_work_dir.mkdir(exist_ok=True, parents=True)
            
            # 准备输入目录
            input_dirs = task.input_dirs or []
            if not input_dirs:
                # 使用默认的测试数据目录
                default_data_dir = self.work_dir / "test_data"
                if default_data_dir.exists():
                    input_dirs = [str(default_data_dir)]
            
            # 创建上下文信息
            context = None
            mode = getattr(task, "mode", "new")
            if mode == "continue":
                context = {
                    "original_query": task.query,
                    "continuation": True,
                    "previous_task_id": task.task_id
                }
            
            # 创建DataMindAlchemy实例
            if mode == "continue" and getattr(task, "alchemy_id", None):
                # 继续模式：使用指定的alchemy_id初始化
                self.logger.info(f"继续已有的炼丹流程，alchemy_id: {task.alchemy_id}")
                alchemy = DataMindAlchemy(
                    work_dir=alchemy_work_dir, 
                    logger=self.logger,
                    alchemy_id=task.alchemy_id
                )
            else:
                # 新建模式
                self.logger.info("启动新的炼丹流程")
                alchemy = DataMindAlchemy(
                    work_dir=alchemy_work_dir, 
                    logger=self.logger
                )
            
            # 调用处理方法
            self.logger.info(f"执行查询: {task.query}")
            result = await alchemy.process(
                query=task.query,
                input_dirs=input_dirs,
                context=context
            )
            
            # 记录处理时间
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # 保存结果
            result_info = {
                "task_id": task.task_id,
                "status": result["status"],
                "duration_seconds": duration,
                "completed_at": end_time.isoformat()
            }
            
            if result["status"] == "success":
                # 记录成功信息
                artifacts = result["results"].get("artifacts", [])
                result_info["artifacts_count"] = len(artifacts)
                result_info["artifacts"] = [Path(path).name for path in artifacts]
                
                if result["results"].get("optimization_suggestions"):
                    result_info["optimization_count"] = len(result["results"]["optimization_suggestions"])
                
                # 记录解析结果和搜索计划等信息
                if result["results"].get("parsed_intent"):
                    result_info["parsed_intent"] = result["results"]["parsed_intent"]
                
                if result["results"].get("search_plan"):
                    result_info["search_plan"] = result["results"]["search_plan"]
                
                if result["results"].get("search_results"):
                    result_info["search_results_stats"] = result["results"]["search_results"].get("stats", {})
                
                self.logger.info(f"任务 {task.task_id} 完成，耗时 {duration:.2f} 秒，生成 {len(artifacts)} 个制品")
            else:
                # 记录失败信息
                result_info["error"] = result.get("message", "未知错误")
                self.logger.error(f"任务 {task.task_id} 失败: {result_info['error']}")
            
            # 使用异步方式写入文件
            await asyncio.to_thread(
                lambda: open(task_dir / "result_summary.json", "w", encoding="utf-8").write(
                    json.dumps(result_info, ensure_ascii=False, indent=2)
                )
            )
            
            # 保存完整结果
            await asyncio.to_thread(
                lambda: open(task_dir / "result_full.json", "w", encoding="utf-8").write(
                    json.dumps(result, ensure_ascii=False, indent=2)
                )
            )
            
            return result
            
        except Exception as e:
            error_msg = f"处理查询失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            
            # 保存错误信息
            error_info = {
                "task_id": task.task_id,
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
                "duration_seconds": (datetime.now() - start_time).total_seconds(),
                "completed_at": datetime.now().isoformat()
            }
            
            # 使用异步方式写入错误信息
            await asyncio.to_thread(
                lambda: open(task_dir / "error.json", "w", encoding="utf-8").write(
                    json.dumps(error_info, ensure_ascii=False, indent=2)
                )
            )
            
            return {
                "status": "error",
                "message": error_msg,
                "results": None
            }

# 示例：如何使用服务
def example_service_usage():
    """服务用法示例"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='数据炼丹服务示例')
    parser.add_argument('--query', type=str, help='查询文本')
    parser.add_argument('--config', type=str, help='配置文件路径', default='work_dir/config.json')
    parser.add_argument('--mode', type=str, choices=['new', 'continue'], help='运行模式: new(新建) 或 continue(继续)')
    parser.add_argument('--id', type=str, help='要继续的alchemy_id（仅在continue模式下有效）')
    parser.add_argument('--input_dir', type=str, action='append', help='输入目录，可多次使用此参数指定多个目录')
    args = parser.parse_args()
    
    logger = setup_logging()
    
    # 默认参数
    query = "请生成一份关于AI发展的报告"
    input_dirs = []
    mode = "new"
    alchemy_id = None
    config_path = args.config
    
    # 读取配置文件
    if config_path:
        config_file = Path(config_path)
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logger.info(f"从配置文件加载: {config_file}")
                
                # 从配置中读取参数
                if 'query' in config:
                    query = config['query']
                if 'input_dirs' in config:
                    input_dirs = config['input_dirs']
                if 'mode' in config:
                    mode = config['mode']
                if 'alchemy_id' in config:
                    alchemy_id = config['alchemy_id']
            except Exception as e:
                logger.error(f"读取配置文件失败: {str(e)}")
    
    # 命令行参数优先级高于配置文件
    if args.query:
        query = args.query
    if args.mode:
        mode = args.mode
    if args.id:
        alchemy_id = args.id
    if args.input_dir:
        input_dirs = args.input_dir
    
    # 验证继续模式下必须提供alchemy_id
    if mode == "continue" and not alchemy_id:
        logger.error("错误: 在continue模式下必须提供alchemy_id！使用--id参数或在配置文件中指定")
        return
    
    # 创建服务实例
    service = DataMindAlchemyService(
        logger=logger,
        config_path=config_path
    )
    service.start()  # 启动服务线程
    
    try:
        # 等待服务准备就绪
        wait_count = 0
        while not service.is_ready and wait_count < 10:  # 最多等待10秒
            print("等待服务就绪...")
            time.sleep(1)
            wait_count += 1
            
        if not service.is_ready:
            logger.error("服务启动超时，请检查服务日志！")
            return
            
        # 定义回调函数
        def on_task_complete(task_id, result):
            print(f"\n任务 {task_id} 完成:")
            if result["status"] == "success":
                artifacts = result["results"].get("artifacts", [])
                print(f"- 生成了 {len(artifacts)} 个制品文件")
                if artifacts:
                    print("- 制品列表:")
                    for artifact in artifacts:
                        print(f"  * {Path(artifact).name}")
                
                # 显示解析结果和搜索计划
                if result["results"].get("parsed_intent"):
                    print("- 解析结果:")
                    print(f"  {json.dumps(result['results']['parsed_intent'], ensure_ascii=False)}")
                
                if result["results"].get("optimization_suggestions"):
                    print("- 优化建议:")
                    for suggestion in result["results"]["optimization_suggestions"]:
                        print(f"  * {suggestion}")
            else:
                print(f"- 处理失败: {result.get('message', '未知错误')}")
        
        # 提交任务
        task_id = service.submit_task(
            query=query,
            input_dirs=input_dirs,
            callback=on_task_complete,
            mode=mode,
            alchemy_id=alchemy_id
        )
        
        print(f"任务已提交，ID: {task_id}，模式: {mode}")
        
        # 等待任务处理完成
        while True:
            status = service.get_task_status(task_id)
            print(f"任务状态: {status['status']}")
            
            if status['status'] in ["completed", "failed", "error"]:
                break
                
            time.sleep(2)
        
        # 获取任务结果
        result = service.get_result(task_id)
        if result:
            print(f"任务最终状态: {result['status']}")
    
    finally:
        # 关闭服务
        service.shutdown()

if __name__ == "__main__":
    # 直接运行此文件时执行示例
    example_service_usage()