const { exec, execSync } = require('child_process');
const path = require('path');

/**
 * 进程管理器
 * @param {Object} io - Socket.IO实例
 * @param {Function} emitTaskOutput - 发送任务输出的函数
 * @returns {Object} 进程管理器对象
 */
function setupProcessManager(io, emitTaskOutput) {
    // 活动进程集合
    const activeProcesses = new Set();
    
    // 任务历史记录存储
    const taskOutputHistory = {};
    const MAX_HISTORY_ITEMS = 1000; // 每个任务最多保存的输出条数
    
    return {
        /**
         * 获取活动进程数量
         * @returns {number} 活动进程数量
         */
        getActiveProcessCount() {
            return activeProcesses.size;
        },
        
        /**
         * 获取活动进程集合
         * @returns {Set} 活动进程集合
         */
        getActiveProcesses() {
            return activeProcesses;
        },
        
        /**
         * 添加进程
         * @param {Object} process - 进程对象
         */
        addProcess(process) {
            activeProcesses.add(process);
        },
        
        /**
         * 移除进程
         * @param {Object} process - 进程对象
         */
        removeProcess(process) {
            activeProcesses.delete(process);
        },
        
        /**
         * 获取任务输出历史
         * @param {string} alchemy_id - 任务ID
         * @returns {Array} 任务输出历史
         */
        getTaskHistory(alchemy_id) {
            return taskOutputHistory[alchemy_id] || [];
        },
        
        /**
         * 添加任务输出历史
         * @param {string} alchemy_id - 任务ID
         * @param {string} output - 输出内容
         * @param {boolean} isError - 是否为错误
         */
        addTaskHistory(alchemy_id, output, isError = false) {
            if (!alchemy_id) return;
            
            if (!taskOutputHistory[alchemy_id]) {
                taskOutputHistory[alchemy_id] = [];
            }
            
            taskOutputHistory[alchemy_id].push({
                output,
                isError,
                timestamp: new Date().toISOString()
            });
            
            // 限制历史记录大小
            if (taskOutputHistory[alchemy_id].length > MAX_HISTORY_ITEMS) {
                taskOutputHistory[alchemy_id] = taskOutputHistory[alchemy_id].slice(-MAX_HISTORY_ITEMS);
            }
        },
        
        /**
         * 清理任务历史
         * @param {string} alchemy_id - 任务ID
         */
        cleanupTaskHistory(alchemy_id) {
            // 可选：在任务完成一段时间后清理历史记录
            setTimeout(() => {
                if (taskOutputHistory[alchemy_id]) {
                    delete taskOutputHistory[alchemy_id];
                    console.log(`已清理任务历史记录: ${alchemy_id}`);
                }
            }, 30 * 60 * 1000); // 30分钟后清理
        },
        
        /**
         * 执行任务
         * @param {string} mode - 任务模式 (new/continue)
         * @param {string} query - 查询文本
         * @param {string} alchemy_id - 任务ID (续期模式下必填)
         * @param {boolean} resume - 是否恢复执行
         * @param {Array} input_dirs - 输入目录列表
         * @returns {Promise<string>} 任务ID
         */
        async executeTask(mode, query, alchemy_id, resume, input_dirs) {
            return new Promise((resolve, reject) => {
                try {
                    // 确定Python解释器路径
                    const pythonPath = process.env.PYTHON_PATH || 'python';
                    
                    // 生成任务ID（如果是新任务）
                    const taskId = mode === 'new' ? 
                        `task_${Date.now().toString(36)}_${Math.random().toString(36).substr(2, 5)}` : 
                        alchemy_id;
                    
                    console.log(`开始执行任务: ${taskId}, 模式: ${mode}`);
                    
                    // 构建命令参数
                    let cmdArgs = [];
                    if (mode === 'new') {
                        cmdArgs = [
                            'examples/alchemy_manager_cli.py',
                            'start',
                            `--query="${query}"`,
                            `--id=${taskId}`
                        ];
                        
                        // 添加输入目录（如果有）
                        if (input_dirs && input_dirs.length > 0) {
                            cmdArgs.push(`--input_dirs=${input_dirs.join(',')}`);
                        }
                    } else if (mode === 'continue') {
                        cmdArgs = [
                            'examples/alchemy_manager_cli.py',
                            resume ? 'resume' : 'continue',
                            `--id=${taskId}`
                        ];
                        
                        // 如果提供了新查询，添加到命令中
                        if (query) {
                            cmdArgs.push(`--query="${query}"`);
                        }
                    }
                    
                    // 启动子进程
                    const { spawn } = require('child_process');
                    const proc = spawn(pythonPath, cmdArgs, {
                        cwd: path.join(__dirname, '..', '..'),
                        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
                        detached: true // 子进程独立运行，即使父进程退出
                    });
                    
                    // 保存进程信息
                    proc.taskId = taskId;
                    this.addProcess(proc);
                    
                    // 处理标准输出
                    proc.stdout.on('data', (data) => {
                        const output = data.toString('utf8');
                        emitTaskOutput(taskId, output, false, io);
                    });
                    
                    // 处理标准错误
                    proc.stderr.on('data', (data) => {
                        const output = data.toString('utf8');
                        emitTaskOutput(taskId, output, true, io);
                    });
                    
                    // 进程结束事件处理
                    proc.on('close', (code) => {
                        const exitMsg = `任务进程退出，退出码: ${code}`;
                        console.log(exitMsg);
                        
                        io.emit('taskOutput', {
                            alchemy_id: taskId,
                            output: exitMsg,
                            isError: code !== 0,
                            end: true // 标记任务结束
                        });
                        
                        // 从活动进程集合中移除
                        this.removeProcess(proc);
                        
                        // 任务完成后清理历史记录
                        this.cleanupTaskHistory(taskId);
                    });
                    
                    // 设置错误处理
                    proc.on('error', (err) => {
                        console.error(`任务进程错误:`, err);
                        emitTaskOutput(taskId, `任务进程错误: ${err.message}`, true, io);
                        
                        // 从活动进程集合中移除
                        this.removeProcess(proc);
                        
                        reject(err);
                    });
                    
                    // 等待进程启动成功
                    setTimeout(() => {
                        if (proc.exitCode === null) {
                            // 进程仍在运行，视为成功启动
                            resolve(taskId);
                        }
                        // 如果进程已退出，将在error或close事件中处理
                    }, 500);
                    
                } catch (error) {
                    console.error('执行任务失败:', error);
                    reject(error);
                }
            });
        },
        
        /**
         * 停止任务
         * @param {string} alchemy_id - 任务ID
         * @param {string} stop_type - 停止类型 (force/graceful)
         * @returns {Promise<Object>} 结果对象
         */
        async stopTask(alchemy_id, stop_type = 'force') {
            return new Promise((resolve) => {
                // 在活动进程中查找任务
                let found = false;
                let method = 'unknown';
                
                for (const proc of activeProcesses) {
                    if (proc.taskId === alchemy_id) {
                        // 尝试终止进程
                        try {
                            if (process.platform === 'win32') {
                                // 在Windows上使用taskkill终止进程树
                                exec(`taskkill /pid ${proc.pid} /T /F`, (error) => {
                                    if (error) {
                                        console.error(`终止任务进程失败: ${error.message}`);
                                    }
                                });
                                method = 'windows-taskkill';
                            } else {
                                // 在Unix系统上发送SIGTERM信号
                                process.kill(proc.pid, 'SIGTERM');
                                method = 'unix-signal';
                            }
                            
                            found = true;
                            console.log(`已发送终止信号到任务进程: ${alchemy_id}`);
                            
                            // 移除进程
                            this.removeProcess(proc);
                            
                            // 发送任务已停止的消息
                            emitTaskOutput(alchemy_id, '任务已通过API请求停止', false, io);
                            
                            io.emit('taskOutput', {
                                alchemy_id: alchemy_id,
                                output: '任务已通过API请求停止',
                                isError: false,
                                end: true // 标记任务结束
                            });
                            
                            break;
                        } catch (err) {
                            console.error(`停止任务进程失败: ${err.message}`);
                            resolve({
                                success: false,
                                message: `停止任务进程失败: ${err.message}`,
                                method: 'error'
                            });
                            return;
                        }
                    }
                }
                
                // 如果没有找到活动进程，但任务ID有效，尝试在系统中查找
                if (!found) {
                    // 尝试在Python进程中查找任务ID
                    this.findPythonProcesses((pids) => {
                        if (pids.length > 0) {
                            // 尝试从进程命令行中匹配任务ID
                            pids.forEach(pid => {
                                try {
                                    let cmd;
                                    if (process.platform === 'win32') {
                                        cmd = `wmic process where "processid=${pid}" get commandline`;
                                    } else {
                                        cmd = `ps -p ${pid} -o command=`;
                                    }
                                    
                                    const output = execSync(cmd, { encoding: 'utf8' });
                                    
                                    if (output.includes(alchemy_id)) {
                                        console.log(`在系统进程中找到任务: ${alchemy_id}，PID: ${pid}`);
                                        
                                        // 终止进程
                                        if (process.platform === 'win32') {
                                            execSync(`taskkill /pid ${pid} /T /F`);
                                            method = 'system-windows-taskkill';
                                        } else {
                                            execSync(`kill -TERM ${pid}`);
                                            method = 'system-unix-kill';
                                        }
                                        
                                        found = true;
                                        console.log(`已发送终止信号到系统进程: ${pid}`);
                                    }
                                } catch (err) {
                                    // 忽略错误，继续检查其他PID
                                }
                            });
                        }
                        
                        resolve({
                            success: true,
                            message: found ? 
                                '已发送终止信号到任务进程' : 
                                '任务进程未找到，可能已结束',
                            method: method
                        });
                    });
                } else {
                    // 如果已经在活动进程中找到并处理了，直接返回成功
                    resolve({
                        success: true,
                        message: '已发送终止信号到任务进程',
                        method: method
                    });
                }
            });
        },
        
        /**
         * 查找Python进程
         * @param {Function} callback - 回调函数
         */
        findPythonProcesses(callback) {
            // 根据操作系统选择不同的命令
            let cmd;
            if (process.platform === 'win32') {
                // Windows: 使用 wmic 查找 python 进程，并过滤包含 datamind 相关关键词的进程
                cmd = 'wmic process where "name=\'python.exe\'" get processid,commandline';
            } else {
                // Linux/Mac: 使用 ps 和 grep 查找 python 进程，并过滤包含 datamind 相关关键词的进程
                cmd = 'ps aux | grep python | grep -E "datamind|example_usage.py|alchemy_manager_cli.py" | grep -v grep';
            }
            
            exec(cmd, (error, stdout, stderr) => {
                if (error && error.code !== 1) {
                    // 命令执行错误（但grep没有匹配项时返回1，这不是错误）
                    console.error(`查找Python进程失败: ${error.message}`);
                    return callback([]);
                }
                
                const pids = [];
                
                if (process.platform === 'win32') {
                    // 解析Windows wmic输出
                    const lines = stdout.trim().split('\n');
                    
                    // 如果没有找到任何进程，直接调用回调
                    if (lines.length === 0) {
                        return callback(pids);
                    }
                    
                    // 跳过标题行
                    for (let i = 1; i < lines.length; i++) {
                        const line = lines[i].trim();
                        // 只处理包含项目相关关键词的进程
                        if (line && (line.includes('datamind') || 
                                    line.includes('example_usage.py') || 
                                    line.includes('alchemy_manager_cli.py'))) {
                            // 提取PID（最后一列）
                            const pid = line.trim().split(/\s+/).pop();
                            if (pid && /^\d+$/.test(pid)) {
                                pids.push(pid);
                            }
                        }
                    }
                    
                    callback(pids);
                } else {
                    // 解析Linux/Mac ps输出
                    const lines = stdout.trim().split('\n');
                    for (const line of lines) {
                        const parts = line.trim().split(/\s+/);
                        if (parts.length > 1) {
                            pids.push(parts[1]);
                        }
                    }
                    callback(pids);
                }
            });
        },
        
        /**
         * 从运行中的进程获取任务ID
         * @param {Array} pids - 进程ID数组
         * @returns {string} 任务ID
         */
        getTaskIdFromRunningProcess(pids) {
            // 首先检查活动进程集合
            for (const process of activeProcesses) {
                if (pids.includes(String(process.pid))) {
                    return process.taskId;
                }
            }
            
            // 如果在活动进程集合中没有找到，尝试从命令行参数中提取
            try {
                for (const pid of pids) {
                    let cmdOutput;
                    
                    if (process.platform === 'win32') {
                        // Windows
                        cmdOutput = execSync(`wmic process where processid=${pid} get commandline`, { encoding: 'utf8' });
                    } else {
                        // Linux/Mac
                        cmdOutput = execSync(`ps -p ${pid} -o command=`, { encoding: 'utf8' });
                    }
                    
                    // 首先尝试从命令行中提取 --id= 参数
                    let match = cmdOutput.match(/--id=([a-zA-Z0-9_-]+)/);
                    if (match && match[1]) {
                        return match[1];
                    }
                    
                    // 然后尝试从命令行中提取 alchemy_id= 参数
                    match = cmdOutput.match(/alchemy_id=([a-zA-Z0-9_-]+)/);
                    if (match && match[1]) {
                        return match[1];
                    }
                    
                    // 最后尝试从路径中提取 alchemy_{id} 格式的任务ID
                    match = cmdOutput.match(/alchemy_([a-zA-Z0-9_-]+)/);
                    if (match && match[1]) {
                        return match[1];
                    }
                }
            } catch (error) {
                console.error(`从进程命令行获取任务ID失败: ${error.message}`);
            }
            
            // 如果上述方法都失败，回退到检查最近的任务
            const recentTasks = Object.keys(taskOutputHistory);
            if (recentTasks.length > 0) {
                // 返回最近的任务ID
                return recentTasks[recentTasks.length - 1];
            }
            
            // 如果所有方法都失败，返回一个占位符
            return "未知任务";
        },
        
        /**
         * 关闭所有进程
         */
        closeAllProcesses() {
            console.log(`正在终止 ${activeProcesses.size} 个活动子进程...`);
            for (const proc of activeProcesses) {
                try {
                    // 在Windows上，需要使用特殊方法终止进程树
                    if (process.platform === 'win32') {
                        // 使用taskkill终止进程及其子进程
                        execSync(`taskkill /pid ${proc.pid} /T /F`, {
                            stdio: 'ignore'
                        });
                    } else {
                        // 在Unix系统上，发送SIGTERM信号
                        process.kill(proc.pid, 'SIGTERM');
                        
                        // 如果进程没有在1秒内退出，发送SIGKILL
                        setTimeout(() => {
                            try {
                                if (!proc.killed) {
                                    process.kill(proc.pid, 'SIGKILL');
                                }
                            } catch (e) {
                                // 忽略错误，可能进程已经退出
                            }
                        }, 1000);
                    }
                } catch (err) {
                    console.error(`终止子进程 ${proc.pid} 失败:`, err);
                }
            }
        }
    };
}

module.exports = {
    setupProcessManager
}; 