const express = require('express');
const app = express();
const http = require('http').createServer(app);
const io = require('socket.io')(http);
const path = require('path');
const fs = require('fs');
const dotenv = require('dotenv');

// 导入自定义模块
const { setupConfig } = require('./modules/config');
const { setupApiClients } = require('./modules/api');
const { ChatSessionManager } = require('./modules/chat');
const { setupFileWatcher, updateFileStructure, buildFileSystemStructure } = require('./modules/fileWatcher');
const { setupProcessManager } = require('./modules/processManager');
const { setupRoutes } = require('./modules/routes');
const { emitTaskOutput } = require('./modules/taskOutput');

// 读取环境变量
dotenv.config();

// 打印环境变量加载路径
console.log(`dotenv配置路径: ${path.resolve('.env')}`);
console.log(`当前工作目录: ${process.cwd()}`);

// 初始化配置
const config = setupConfig();

// 设置Express应用
app.use(express.static('public'));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// 设置响应头，确保正确的字符编码
app.use((req, res, next) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    next();
});

// 初始化API客户端
const apiClients = setupApiClients();

// 处理监控目录的路径
const watchDirs = config.watchDirs.map(dir => ({
    ...dir,
    fullPath: path.join(__dirname, dir.path)
}));

// 设置全局变量，供fileWatcher模块使用
global.watchDirs = watchDirs;

// 确保所有监控目录都存在
watchDirs.forEach(dir => {
    if (!fs.existsSync(dir.fullPath)) {
        fs.mkdirSync(dir.fullPath, { recursive: true });
        console.log(`Created directory: ${dir.fullPath}`);
    }
});

// 创建聊天会话管理器实例
const chatSessionManager = new ChatSessionManager(config);

// 定期清理不活跃的会话(每小时)
setInterval(() => {
    chatSessionManager.cleanupSessions();
}, 60 * 60 * 1000);

// 初始化进程管理器
const processManager = setupProcessManager(io, emitTaskOutput);

// 初始化文件监控
let watchers = [];
watchDirs.forEach(dir => {
    const dirKey = dir.path;
    const watcher = setupFileWatcher(dir, dirKey, io, config, updateFileStructure);
    watchers.push(watcher);
});

// 初始化时发送文件结构
updateFileStructure(watchDirs, io);

// 设置路由
setupRoutes(app, io, watchDirs, config, chatSessionManager, apiClients, processManager);

// WebSocket连接处理
io.on('connection', (socket) => {
    console.log('Client connected');
    
    // 设置WebSocket编码
    socket.setEncoding && socket.setEncoding('utf8');
    
    // 发送配置信息
    socket.emit('configUpdate', config);

    // 发送初始文件系统结构
    try {
        const structure = {};
        watchDirs.forEach(dir => {
            structure[dir.path] = {
                name: dir.name,
                description: dir.description,
                files: buildFileSystemStructure(dir.fullPath)
            };
        });
        socket.emit('initialStructure', structure);
    } catch (err) {
        console.error('Error building file system structure:', err);
    }

    // 添加文件监听状态存储
    const watchingFiles = new Set();
    
    // 添加检查运行中任务的事件处理
    socket.on('checkRunningTasks', () => {
        // 检查是否有正在运行的Python进程
        processManager.findPythonProcesses((pids) => {
            const running = pids.length > 0;
            let taskId = null;
            
            if (running) {
                // 尝试从进程信息中获取任务ID
                taskId = processManager.getTaskIdFromRunningProcess(pids);
            }
            
            socket.emit('runningTasksResult', {
                running: running,
                taskId: taskId,
                pids: pids
            });
        });
    });
    
    // 添加开始监听文件的事件处理
    socket.on('watchFile', (data) => {
        const { dir, path: filePath } = data;
        const watchDir = watchDirs.find(d => d.path === dir);
        if (!watchDir) return;
        
        const fullPath = path.join(watchDir.fullPath, filePath);
        const watchId = `${dir}:${filePath}`;
        
        if (watchingFiles.has(watchId)) return;
        watchingFiles.add(watchId);
        
        let lastSize = 0;
        try {
            lastSize = fs.statSync(fullPath).size;
        } catch (err) {
            console.error('Error getting file size:', err);
            return;
        }
        
        // 设置文件监听间隔
        const fileWatcher = setInterval(() => {
            try {
                const stats = fs.statSync(fullPath);
                if (stats.size > lastSize) {
                    // 只读取新增的内容
                    const fd = fs.openSync(fullPath, 'r');
                    const buffer = Buffer.alloc(stats.size - lastSize);
                    fs.readSync(fd, buffer, 0, buffer.length, lastSize);
                    fs.closeSync(fd);
                    
                    const newContent = buffer.toString('utf8');
                    socket.emit('fileUpdate', {
                        dir,
                        path: filePath,
                        content: newContent,
                        append: true
                    });
                    
                    lastSize = stats.size;
                }
            } catch (err) {
                console.error('Error watching file:', err);
                clearInterval(fileWatcher);
                watchingFiles.delete(watchId);
            }
        }, 1000); // 每秒检查一次
        
        // 当连接断开时清理监听器
        socket.on('disconnect', () => {
            clearInterval(fileWatcher);
            watchingFiles.delete(watchId);
        });
        
        // 当客户端停止监听时清理
        socket.on('stopWatchFile', (stopData) => {
            if (stopData.dir === dir && stopData.path === filePath) {
                clearInterval(fileWatcher);
                watchingFiles.delete(watchId);
            }
        });
    });

    socket.on('disconnect', () => {
        console.log('Client disconnected');
    });
});

// 启动服务器
const PORT = config.port || 3000;
http.listen(PORT, () => {
    console.log(`服务器运行在 http://localhost:${PORT}`);
    console.log(`字符编码: ${Buffer.isEncoding('utf8') ? 'UTF-8支持正常' : 'UTF-8支持异常'}`);
    watchDirs.forEach(dir => {
        console.log(`监控目录: ${dir.fullPath}`);
    });
});

// 在应用退出时关闭所有文件监视器
process.on('SIGINT', () => {
    console.log('正在关闭服务器...');
    
    // 关闭所有文件监视器
    watchers.forEach(watcher => {
        try {
            watcher.close();
        } catch (err) {
            console.error('关闭文件监视器失败:', err);
        }
    });
    
    // 关闭所有子进程
    processManager.closeAllProcesses();
    
    // 等待所有子进程终止
    const waitForProcesses = new Promise((resolve) => {
        if (processManager.getActiveProcessCount() === 0) {
            resolve();
            return;
        }
        
        console.log('等待子进程终止...');
        const checkInterval = setInterval(() => {
            if (processManager.getActiveProcessCount() === 0) {
                clearInterval(checkInterval);
                resolve();
            }
        }, 100);
        
        // 最多等待3秒
        setTimeout(() => {
            clearInterval(checkInterval);
            if (processManager.getActiveProcessCount() > 0) {
                console.warn(`${processManager.getActiveProcessCount()} 个子进程未能正常终止`);
            }
            resolve();
        }, 3000);
    });
    
    // 等待子进程终止后关闭Socket.IO和HTTP服务器
    waitForProcesses.then(() => {
        // 关闭所有 Socket.IO 连接
        io.close(() => {
            console.log('Socket.IO 连接已关闭');
            
            // 关闭 HTTP 服务器
            http.close(() => {
                console.log('HTTP 服务器已关闭');
                process.exit(0);
            });
        });
    });
    
    // 添加超时机制，防止进程卡住
    setTimeout(() => {
        console.log('关闭超时，强制退出进程');
        process.exit(1);
    }, 5000); // 5秒后强制退出
});