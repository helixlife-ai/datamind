import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
import shutil
from datetime import datetime
import pandas as pd

class AlchemyManager:
    """数据炼丹任务管理器，用于管理多个alchemy任务实例"""
    
    def __init__(self, work_dir: Path, logger: logging.Logger = None):
        """初始化任务管理器
        
        Args:
            work_dir: 工作目录，用于存储所有alchemy任务
            logger: 日志记录器
        """
        self.work_dir = Path(work_dir)
        self.alchemy_dir = self.work_dir / "data_alchemy"
        self.alchemy_dir.mkdir(exist_ok=True, parents=True)
        
        # 创建任务索引目录
        self.index_dir = self.alchemy_dir / "_index"
        self.index_dir.mkdir(exist_ok=True)
        
        # 任务索引文件
        self.index_file = self.index_dir / "alchemy_index.json"
        
        # 日志记录器
        self.logger = logger or logging.getLogger(__name__)
        
        # 初始化任务索引
        self._initialize_index()
    
    def _initialize_index(self):
        """初始化或加载任务索引"""
        if not self.index_file.exists():
            # 如果索引不存在，创建空索引并扫描已有任务
            self.alchemy_index = {"tasks": {}}
            self._save_index()
            self.scan_existing_tasks()
        else:
            # 加载现有索引
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self.alchemy_index = json.load(f)
            except Exception as e:
                self.logger.error(f"加载任务索引失败: {str(e)}，将创建新索引")
                self.alchemy_index = {"tasks": {}}
                self._save_index()
    
    def _save_index(self):
        """保存任务索引到文件"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.alchemy_index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存任务索引失败: {str(e)}")
    
    def scan_existing_tasks(self):
        """扫描现有任务并更新索引"""
        # 查找所有可能的alchemy目录
        potential_tasks = [d for d in self.alchemy_dir.glob("*") 
                         if d.is_dir() and not d.name.startswith("_")]
        
        tasks_found = 0
        for task_dir in potential_tasks:
            alchemy_id = task_dir.name
            
            # 检查是否是有效的alchemy目录
            status_file = task_dir / "status.json"
            if not status_file.exists():
                continue
            
            # 如果任务已经在索引中，跳过
            if alchemy_id in self.alchemy_index["tasks"]:
                continue
            
            # 读取任务状态
            try:
                with open(status_file, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                
                # 提取关键信息
                latest_iteration = status_data.get("latest_iteration", 0)
                latest_query = status_data.get("latest_query", "未知查询")
                created_at = status_data.get("created_at")
                updated_at = status_data.get("updated_at")
                
                # 查找制品文件
                artifacts = []
                iterations_dir = task_dir / "iterations"
                if iterations_dir.exists():
                    for iter_dir in iterations_dir.glob("iter*"):
                        artifacts_dir = iter_dir / "artifacts"
                        if artifacts_dir.exists():
                            artifacts.extend([str(p.relative_to(self.work_dir)) 
                                           for p in artifacts_dir.glob("*.*")])
                
                # 添加到索引
                self.alchemy_index["tasks"][alchemy_id] = {
                    "id": alchemy_id,
                    "name": f"任务 {alchemy_id}",
                    "description": f"查询: {latest_query}",
                    "status": "completed" if latest_iteration > 0 else "unknown",
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "iterations": latest_iteration,
                    "latest_query": latest_query,
                    "artifacts_count": len(artifacts),
                    "artifacts": artifacts[:5],  # 只保存前5个制品路径
                    "tags": [],
                    "is_archived": False
                }
                
                tasks_found += 1
                
            except Exception as e:
                self.logger.error(f"处理任务 {alchemy_id} 时出错: {str(e)}")
        
        if tasks_found > 0:
            self.logger.info(f"扫描发现 {tasks_found} 个新任务")
            self._save_index()
    
    def register_task(self, alchemy_id: str, query: str, description: str = None):
        """注册新任务到索引
        
        Args:
            alchemy_id: 任务ID
            query: 查询文本
            description: 任务描述
        """
        now = datetime.now().isoformat()
        
        # 添加到索引
        self.alchemy_index["tasks"][alchemy_id] = {
            "id": alchemy_id,
            "name": f"任务 {alchemy_id}",
            "description": description or f"查询: {query}",
            "status": "created",
            "created_at": now,
            "updated_at": now,
            "iterations": 0,
            "latest_query": query,
            "artifacts_count": 0,
            "artifacts": [],
            "tags": [],
            "is_archived": False
        }
        
        self._save_index()
        return self.alchemy_index["tasks"][alchemy_id]
    
    def update_task(self, alchemy_id: str, updates: Dict):
        """更新任务信息
        
        Args:
            alchemy_id: 任务ID
            updates: 要更新的字段和值
        """
        if alchemy_id not in self.alchemy_index["tasks"]:
            self.logger.error(f"任务 {alchemy_id} 不存在，无法更新")
            return None
        
        # 更新字段
        task_info = self.alchemy_index["tasks"][alchemy_id]
        for key, value in updates.items():
            if key in task_info:
                task_info[key] = value
        
        # 更新时间
        task_info["updated_at"] = datetime.now().isoformat()
        
        self._save_index()
        return task_info
    
    def delete_task(self, alchemy_id: str, delete_files: bool = False):
        """删除任务
        
        Args:
            alchemy_id: 任务ID
            delete_files: 是否同时删除文件
        """
        if alchemy_id not in self.alchemy_index["tasks"]:
            self.logger.error(f"任务 {alchemy_id} 不存在，无法删除")
            return False
        
        # 从索引中删除
        del self.alchemy_index["tasks"][alchemy_id]
        self._save_index()
        
        # 如果需要，删除文件
        if delete_files:
            task_dir = self.alchemy_dir / alchemy_id
            if task_dir.exists():
                try:
                    shutil.rmtree(task_dir)
                    self.logger.info(f"删除任务文件: {task_dir}")
                except Exception as e:
                    self.logger.error(f"删除任务文件失败: {str(e)}")
                    return False
        
        return True
    
    def archive_task(self, alchemy_id: str):
        """归档任务"""
        return self.update_task(alchemy_id, {"is_archived": True})
    
    def unarchive_task(self, alchemy_id: str):
        """取消归档任务"""
        return self.update_task(alchemy_id, {"is_archived": False})
    
    def get_task(self, alchemy_id: str):
        """获取任务信息"""
        return self.alchemy_index["tasks"].get(alchemy_id)
    
    def get_all_tasks(self, include_archived: bool = False):
        """获取所有任务"""
        if include_archived:
            return list(self.alchemy_index["tasks"].values())
        else:
            return [task for task in self.alchemy_index["tasks"].values() 
                    if not task.get("is_archived", False)]
    
    def search_tasks(self, query: str):
        """搜索任务
        
        Args:
            query: 搜索关键词
        """
        results = []
        query = query.lower()
        
        for task in self.alchemy_index["tasks"].values():
            # 在各个字段中搜索
            if (query in task["id"].lower() or
                query in task.get("name", "").lower() or
                query in task.get("description", "").lower() or
                query in task.get("latest_query", "").lower() or
                any(query in tag.lower() for tag in task.get("tags", []))):
                results.append(task)
        
        return results
    
    def tag_task(self, alchemy_id: str, tag: str):
        """为任务添加标签"""
        if alchemy_id not in self.alchemy_index["tasks"]:
            return None
        
        task = self.alchemy_index["tasks"][alchemy_id]
        if "tags" not in task:
            task["tags"] = []
        
        if tag not in task["tags"]:
            task["tags"].append(tag)
            self._save_index()
        
        return task
    
    def untag_task(self, alchemy_id: str, tag: str):
        """移除任务标签"""
        if alchemy_id not in self.alchemy_index["tasks"]:
            return None
        
        task = self.alchemy_index["tasks"][alchemy_id]
        if "tags" in task and tag in task["tags"]:
            task["tags"].remove(tag)
            self._save_index()
        
        return task
    
    def export_tasks_to_csv(self, output_path: str = None):
        """导出任务列表到CSV文件
        
        Args:
            output_path: 输出文件路径，默认为工作目录下的alchemy_tasks.csv
        """
        if output_path is None:
            output_path = str(self.work_dir / "alchemy_tasks.csv")
        
        # 准备数据
        tasks = self.get_all_tasks(include_archived=True)
        
        # 转换为DataFrame
        df = pd.DataFrame(tasks)
        
        # 导出到CSV
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        return output_path
    
    def get_resumable_tasks(self):
        """获取所有可恢复的任务"""
        resumable_tasks = []
        
        for task_id, task_info in self.alchemy_index["tasks"].items():
            task_dir = self.alchemy_dir / task_id
            resume_info_path = task_dir / "resume_info.json"
            
            if resume_info_path.exists():
                try:
                    with open(resume_info_path, 'r', encoding='utf-8') as f:
                        resume_info = json.load(f)
                    
                    # 添加恢复信息到任务
                    task_with_resume = task_info.copy()
                    task_with_resume["resume_info"] = resume_info
                    task_with_resume["resume_file"] = str(resume_info_path)
                    resumable_tasks.append(task_with_resume)
                except Exception as e:
                    self.logger.error(f"读取任务 {task_id} 的恢复信息失败: {str(e)}")
        
        # 按更新时间排序
        resumable_tasks.sort(key=lambda x: x["resume_info"].get("timestamp", ""), reverse=True)
        return resumable_tasks
    
    def get_task_resume_info(self, alchemy_id: str):
        """获取指定任务的恢复信息"""
        task_dir = self.alchemy_dir / alchemy_id
        resume_info_path = task_dir / "resume_info.json"
        
        if resume_info_path.exists():
            try:
                with open(resume_info_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"读取任务 {alchemy_id} 的恢复信息失败: {str(e)}")
        
        return None
    
    def get_latest_resumable_task(self):
        """获取最近可恢复的任务"""
        resumable_tasks = self.get_resumable_tasks()
        if resumable_tasks:
            return resumable_tasks[0]
        return None 