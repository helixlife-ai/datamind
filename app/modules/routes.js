const path = require('path');
const fs = require('fs');
const fsPromises = require('fs').promises;
const { exec } = require('child_process');

/**
 * 设置所有API路由
 * @param {Object} app - Express应用实例
 * @param {Object} io - Socket.IO实例
 * @param {Array} watchDirs - 监控目录配置
 * @param {Object} config - 应用配置
 * @param {Object} chatSessionManager - 聊天会话管理器
 * @param {Object} apiClients - API客户端
 * @param {Object} processManager - 进程管理器
 */
function setupRoutes(app, io, watchDirs, config, chatSessionManager, apiClients, processManager) {
    // 获取相对路径的函数
    function getRelativePath(fullPath) {
        for (const dir of watchDirs) {
            if (fullPath.startsWith(dir.fullPath)) {
                return {
                    dirId: dir.path,
                    relativePath: path.relative(dir.fullPath, fullPath).replace(/\\/g, '/')
                };
            }
        }
        return null;
    }

    // 添加配置API
    app.get('/api/config', (req, res) => {
        res.json({
            watchDirs: config.watchDirs,
            excludePatterns: config.excludePatterns
        });
    });

    // 添加获取配置文件API
    app.get('/api/get-config', (req, res) => {
        try {
            const configPath = path.join(__dirname, '..', '..', 'work_dir', 'config.json');
            if (fs.existsSync(configPath)) {
                const configData = JSON.parse(fs.readFileSync(configPath, 'utf8'));
                res.json(configData);
            } else {
                res.json({ message: '配置文件不存在' });
            }
        } catch (error) {
            console.error('读取配置文件失败:', error);
            res.status(500).json({ error: `读取配置文件失败: ${error.message}` });
        }
    });

    // 添加浏览文件夹API
    app.get('/api/browse-folders', (req, res) => {
        try {
            // 首先尝试使用Electron的对话框
            let electronAvailable = false;
            try {
                // 检查是否在Electron环境中
                const electron = require('electron');
                electronAvailable = !!electron.dialog;
            } catch (e) {
                console.log('不在Electron环境中，将使用备用方法');
                electronAvailable = false;
            }
            
            if (electronAvailable) {
                // 使用Electron对话框
                const { dialog } = require('electron');
                const BrowserWindow = require('electron').BrowserWindow;
                const win = BrowserWindow.getFocusedWindow();
                
                dialog.showOpenDialog(win, {
                    properties: ['openDirectory'],
                    defaultPath: path.join(__dirname, '..', '..', 'work_dir')
                }).then(result => {
                    if (result.canceled || result.filePaths.length === 0) {
                        return res.json({ success: false, message: '用户取消选择' });
                    }
                    
                    const selectedPath = result.filePaths[0];
                    res.json({ success: true, path: selectedPath });
                }).catch(err => {
                    console.error('打开文件夹对话框失败:', err);
                    useBackupMethod();
                });
            } else {
                // 使用备用方法
                useBackupMethod();
            }
            
            // 备用方法：返回work_dir目录下的文件夹列表
            function useBackupMethod() {
                try {
                    // 获取请求中的当前路径参数
                    const currentPath = req.query.path || path.join(__dirname, '..', '..', 'work_dir');
                    
                    // 确保路径存在
                    if (!fs.existsSync(currentPath)) {
                        return res.json({ 
                            success: false, 
                            error: `路径不存在: ${currentPath}` 
                        });
                    }
                    
                    // 确保路径是目录
                    const stats = fs.statSync(currentPath);
                    if (!stats.isDirectory()) {
                        return res.json({ 
                            success: false, 
                            error: `不是目录: ${currentPath}` 
                        });
                    }
                    
                    // 读取目录内容
                    const items = fs.readdirSync(currentPath, { withFileTypes: true });
                    
                    // 过滤出目录
                    const dirs = items
                        .filter(item => item.isDirectory())
                        .map(item => {
                            const fullPath = path.join(currentPath, item.name);
                            return {
                                name: item.name,
                                path: fullPath,
                                isParent: false
                            };
                        });
                    
                    // 添加父目录（如果不是根目录）
                    const parentDir = path.dirname(currentPath);
                    if (parentDir !== currentPath) {
                        dirs.unshift({
                            name: '..',
                            path: parentDir,
                            isParent: true
                        });
                    }
                    
                    // 如果是直接选择路径的请求
                    if (req.query.select === 'true') {
                        return res.json({ 
                            success: true, 
                            path: currentPath 
                        });
                    }
                    
                    // 返回目录列表和当前路径
                    res.json({ 
                        success: true, 
                        current_path: currentPath,
                        directories: dirs,
                        is_backup_method: true
                    });
                } catch (error) {
                    console.error('备用方法失败:', error);
                    res.status(500).json({ 
                        success: false, 
                        error: `浏览文件夹失败: ${error.message}` 
                    });
                }
            }
        } catch (error) {
            console.error('浏览文件夹失败:', error);
            res.status(500).json({ 
                success: false, 
                error: `浏览文件夹失败: ${error.message}` 
            });
        }
    });

    // 添加获取任务信息API
    app.get('/api/task-info', async (req, res) => {
        try {
            const taskId = req.query.id;
            if (!taskId) {
                return res.status(400).json({ error: '缺少任务ID参数' });
            }
            
            console.log(`获取任务信息: ${taskId}`);
            
            // 构建任务目录路径
            const workDir = path.join(__dirname, '..', '..');
            const alchemyDir = path.join(workDir, 'work_dir', 'data_alchemy');
            const runsDir = path.join(alchemyDir, 'alchemy_runs');
            const taskDir = path.join(runsDir, `alchemy_${taskId}`);
            
            // 检查任务目录是否存在
            if (!fs.existsSync(taskDir)) {
                return res.status(404).json({ error: `任务 ${taskId} 不存在` });
            }
            
            // 读取恢复信息
            const resumeInfoPath = path.join(taskDir, 'resume_info.json');
            let resumeInfo = null;
            if (fs.existsSync(resumeInfoPath)) {
                try {
                    resumeInfo = JSON.parse(fs.readFileSync(resumeInfoPath, 'utf8'));
                } catch (e) {
                    console.warn(`读取恢复信息失败: ${e.message}`);
                }
            }
            
            // 读取下一轮迭代配置
            const nextConfigPath = path.join(taskDir, 'next_iteration_config.json');
            let nextIterationConfig = null;
            if (fs.existsSync(nextConfigPath)) {
                try {
                    nextIterationConfig = JSON.parse(fs.readFileSync(nextConfigPath, 'utf8'));
                } catch (e) {
                    console.warn(`读取下一轮迭代配置失败: ${e.message}`);
                }
            }
            
            // 读取状态信息
            const statusPath = path.join(taskDir, 'status.json');
            let statusInfo = null;
            if (fs.existsSync(statusPath)) {
                try {
                    statusInfo = JSON.parse(fs.readFileSync(statusPath, 'utf8'));
                } catch (e) {
                    console.warn(`读取状态信息失败: ${e.message}`);
                }
            }
            
            // 构建任务信息对象
            const taskInfo = {
                id: taskId,
                task_dir: taskDir,
                resume_info: resumeInfo,
                next_iteration_config: nextIterationConfig,
                status: statusInfo
            };
            
            res.json(taskInfo);
        } catch (error) {
            console.error('获取任务信息失败:', error);
            res.status(500).json({ error: `获取任务信息失败: ${error.message}` });
        }
    });

    // 修改文件读取API
    app.get('/api/file', (req, res) => {
        const dirPath = req.query.dir;
        const filePath = req.query.path;
        
        // 增加调试日志
        console.log('Received directory path:', dirPath);
        console.log('Received file path:', filePath);
        console.log('Available watch directories:', watchDirs.map(d => d.path));

        // 修改目录匹配逻辑
        const watchDir = watchDirs.find(d => {
            // 使用路径解析来确保格式一致
            const configPath = path.resolve(d.path);
            const requestPath = path.resolve(dirPath);
            return configPath === requestPath;
        });

        if (!watchDir) {
            console.error('Directory not found:', dirPath);
            return res.status(404).json({ error: 'Directory not found' });
        }

        // 修改路径构建方式
        const fullPath = path.join(watchDir.fullPath, filePath);
        console.log('Constructed full path:', fullPath);

        // 验证文件路径是否在监控目录下
        if (!fullPath.startsWith(path.resolve(watchDir.fullPath))) {
            return res.status(403).json({ error: 'Access denied' });
        }

        try {
            // 检查文件是否存在
            if (!fs.existsSync(fullPath)) {
                return res.status(404).json({ 
                    error: `File not found: ${filePath}`
                });
            }

            // 检查是否是文件而不是目录
            const stats = fs.statSync(fullPath);
            if (!stats.isFile()) {
                return res.status(400).json({ error: 'Not a file' });
            }

            // 明确指定UTF-8编码读取文件
            const content = fs.readFileSync(fullPath, 'utf8');
            res.json({ content });
        } catch (err) {
            console.error('Error reading file:', err);
            res.status(500).json({ 
                error: 'Failed to read file: ' + err.message
            });
        }
    });

    // 添加聊天API
    app.post('/api/chat', async (req, res) => {
        const { messages, provider = 'siliconflow', stream = true, sessionId } = req.body;
        
        if (!messages || !Array.isArray(messages) || messages.length === 0) {
            return res.status(400).json({ error: '无效的消息格式' });
        }
        
        try {
            // 获取或创建会话
            const { sessionId: activeSessionId, session } = await chatSessionManager.getOrCreateSession(sessionId);
            
            // 如果没有提供消息历史，使用会话中的历史
            const chatMessages = messages.length > 1 ? messages : [...session.messages, ...messages];
            
            const client = apiClients.getNextApiClient(provider);
            if (!client) {
                return res.status(503).json({ error: 'API服务不可用' });
            }
            
            const modelName = apiClients.getModelName(provider);
            
            if (stream) {
                // 流式响应
                res.setHeader('Content-Type', 'text/event-stream');
                res.setHeader('Cache-Control', 'no-cache');
                res.setHeader('Connection', 'keep-alive');
                
                // 用于记录完整响应
                let fullResponse = '';
                
                const stream = await client.chat.completions.create({
                    model: modelName,
                    messages: chatMessages,
                    stream: true
                });
                
                // 发送会话ID
                res.write(`data: ${JSON.stringify({ sessionId: activeSessionId })}\n\n`);
                
                for await (const chunk of stream) {
                    const content = chunk.choices[0]?.delta?.content || '';
                    if (content) {
                        fullResponse += content;
                        res.write(`data: ${JSON.stringify({ content })}\n\n`);
                    }
                }
                
                // 保存完整的对话历史
                if (fullResponse) {
                    const updatedMessages = [
                        ...chatMessages,
                        { role: 'assistant', content: fullResponse }
                    ];
                    await chatSessionManager.saveChatHistory(activeSessionId, updatedMessages);
                }
                
                res.write('data: [DONE]\n\n');
                res.end();
            } else {
                // 非流式响应
                const response = await client.chat.completions.create({
                    model: modelName,
                    messages: chatMessages,
                    stream: false
                });
                
                const responseContent = response.choices[0]?.message?.content || '';
                
                // 保存完整的对话历史
                if (responseContent) {
                    const updatedMessages = [
                        ...chatMessages,
                        { role: 'assistant', content: responseContent }
                    ];
                    await chatSessionManager.saveChatHistory(activeSessionId, updatedMessages);
                }
                
                res.json({
                    sessionId: activeSessionId,
                    content: responseContent,
                    usage: response.usage
                });
            }
        } catch (error) {
            console.error('聊天API调用失败:', error);
            // 如果流已经开始，发送错误事件
            if (res.headersSent) {
                res.write(`data: ${JSON.stringify({ error: error.message })}\n\n`);
                res.end();
            } else {
                res.status(500).json({ error: error.message });
            }
        }
    });

    // 添加获取可恢复任务API
    app.get('/api/resumable-tasks', async (req, res) => {
        try {
            console.log('开始获取可恢复任务...');
            
            // 确定 Python 解释器路径
            const pythonPath = process.env.PYTHON_PATH || 'python';
            
            // 构建命令
            const command = `${pythonPath} scripts/alchemy_manager_cli.py resumable --json`;
            console.log(`执行命令: ${command}`);
            
            // 使用child_process执行命令
            exec(command, {
                cwd: path.join(__dirname, '..', '..'),
                env: { ...process.env, PYTHONIOENCODING: 'utf-8' }, // 确保Python输出使用UTF-8编码
                maxBuffer: 1024 * 1024 // 增加缓冲区大小到1MB
            }, (error, stdout, stderr) => {
                if (error) {
                    console.error('获取可恢复任务失败:', error);
                    console.error('命令输出 (stderr):', stderr);
                    
                    // 如果有stderr输出，返回更详细的错误信息
                    if (stderr) {
                        return res.status(500).json({
                            success: false,
                            error: `命令执行失败: ${stderr}`
                        });
                    }
                    
                    return res.status(500).json({
                        success: false,
                        error: `命令执行失败: ${error.message}`
                    });
                }
                
                // 检查stdout是否为空
                if (!stdout || stdout.trim() === '') {
                    console.log('命令执行成功，但没有输出数据');
                    return res.json({
                        success: true,
                        tasks: []
                    });
                }
                
                console.log('命令执行成功，尝试解析JSON输出');
                console.log('原始输出前50个字符:', stdout.substring(0, 50) + '...');
                
                try {
                    // 尝试清理输出中可能存在的非JSON内容
                    let cleanedOutput = stdout.trim();
                    // 查找第一个 [ 和最后一个 ] 之间的内容
                    const startIdx = cleanedOutput.indexOf('[');
                    const endIdx = cleanedOutput.lastIndexOf(']');
                    
                    if (startIdx >= 0 && endIdx > startIdx) {
                        cleanedOutput = cleanedOutput.substring(startIdx, endIdx + 1);
                        console.log('已清理输出，提取JSON数组');
                    }
                    
                    // 解析JSON
                    const tasks = JSON.parse(cleanedOutput);
                    
                    // 验证解析结果是否为数组
                    if (!Array.isArray(tasks)) {
                        console.error('解析结果不是数组:', typeof tasks);
                        throw new Error('解析结果不是数组');
                    }
                    
                    console.log(`成功解析到 ${tasks.length} 个可恢复任务`);
                    
                    // 验证每个任务是否有必要的字段
                    const validTasks = tasks.filter(task => {
                        if (!task || typeof task !== 'object') {
                            console.warn('任务不是对象:', task);
                            return false;
                        }
                        
                        if (!task.id) {
                            console.warn('任务缺少ID:', task);
                            return false;
                        }
                        
                        return true;
                    });
                    
                    console.log(`有效任务数量: ${validTasks.length}`);
                    
                    // 返回有效的任务列表
                    res.json({
                        success: true,
                        tasks: validTasks,
                        original_count: tasks.length,
                        valid_count: validTasks.length
                    });
                } catch (parseError) {
                    console.error('解析可恢复任务失败:', parseError);
                    console.error('原始输出:', stdout);
                    
                    // 尝试直接返回一个硬编码的示例任务，用于调试
                    const fallbackTasks = [];
                    
                    // 尝试从stdout中提取任务ID
                    const idMatches = stdout.match(/alchemy_([a-zA-Z0-9_]+)/g);
                    if (idMatches && idMatches.length > 0) {
                        console.log('从输出中提取到任务ID:', idMatches);
                        
                        // 为每个匹配的ID创建一个简单的任务对象
                        idMatches.forEach((match, index) => {
                            const taskId = match.replace('alchemy_', '');
                            fallbackTasks.push({
                                id: taskId,
                                name: `恢复的任务 ${index + 1}`,
                                resume_info: {
                                    query: "从错误中恢复的查询",
                                    timestamp: new Date().toISOString()
                                }
                            });
                        });
                        
                        console.log(`创建了 ${fallbackTasks.length} 个备用任务`);
                        
                        // 返回备用任务
                        return res.json({
                            success: true,
                            tasks: fallbackTasks,
                            is_fallback: true,
                            parse_error: parseError.message
                        });
                    }
                    
                    // 如果无法提取任务ID，返回错误
                    res.status(500).json({
                        success: false,
                        error: `解析任务数据失败: ${parseError.message}`,
                        rawOutput: stdout.substring(0, 1000) // 只返回前1000个字符，避免响应过大
                    });
                }
            });
        } catch (error) {
            console.error('获取可恢复任务失败:', error);
            res.status(500).json({
                success: false,
                error: error.message
            });
        }
    });

    // 添加直接从文件系统获取可恢复任务的API
    app.get('/api/direct-resumable-tasks', async (req, res) => {
        try {
            console.log('开始直接从文件系统获取可恢复任务...');
            
            // 工作目录路径
            const workDir = path.join(__dirname, '..', '..');
            const alchemyDir = path.join(workDir, 'work_dir', 'data_alchemy');
            const runsDir = path.join(alchemyDir, 'alchemy_runs');
            
            console.log(`查找目录: ${runsDir}`);
            
            // 检查目录是否存在
            if (!fs.existsSync(runsDir)) {
                console.log(`目录不存在: ${runsDir}`);
                return res.json({
                    success: true,
                    tasks: [],
                    message: '任务目录不存在'
                });
            }
            
            // 读取目录内容
            const dirEntries = fs.readdirSync(runsDir, { withFileTypes: true });
            
            // 过滤出alchemy_开头的目录
            const alchemyDirs = dirEntries.filter(entry => 
                entry.isDirectory() && entry.name.startsWith('alchemy_')
            );
            
            console.log(`找到 ${alchemyDirs.length} 个可能的任务目录`);
            
            // 收集可恢复任务
            const resumableTasks = [];
            
            for (const dir of alchemyDirs) {
                const taskId = dir.name.replace('alchemy_', '');
                const taskDir = path.join(runsDir, dir.name);
                const resumeInfoPath = path.join(taskDir, 'resume_info.json');
                
                // 检查是否有恢复信息文件
                if (fs.existsSync(resumeInfoPath)) {
                    try {
                        // 读取恢复信息
                        const resumeInfo = JSON.parse(fs.readFileSync(resumeInfoPath, 'utf8'));
                        
                        // 读取状态信息（如果存在）
                        let statusInfo = {};
                        const statusPath = path.join(taskDir, 'status.json');
                        if (fs.existsSync(statusPath)) {
                            try {
                                statusInfo = JSON.parse(fs.readFileSync(statusPath, 'utf8'));
                            } catch (e) {
                                console.warn(`读取状态文件失败 ${taskId}: ${e.message}`);
                            }
                        }
                        
                        // 构建任务对象
                        const task = {
                            id: taskId,
                            name: statusInfo.name || `任务 ${taskId}`,
                            description: statusInfo.description || '',
                            latest_query: resumeInfo.query || (statusInfo.latest_query || ''),
                            resume_info: resumeInfo,
                            status: statusInfo.status || 'unknown',
                            created_at: statusInfo.created_at || resumeInfo.timestamp,
                            updated_at: statusInfo.updated_at || resumeInfo.timestamp
                        };
                        
                        resumableTasks.push(task);
                        console.log(`添加可恢复任务: ${taskId}`);
                    } catch (e) {
                        console.error(`处理任务 ${taskId} 失败: ${e.message}`);
                    }
                }
            }
            
            // 按时间戳排序（最新的在前）
            resumableTasks.sort((a, b) => {
                const timeA = a.resume_info?.timestamp || '';
                const timeB = b.resume_info?.timestamp || '';
                return timeB.localeCompare(timeA);
            });
            
            console.log(`找到 ${resumableTasks.length} 个可恢复任务`);
            
            // 返回结果
            res.json({
                success: true,
                tasks: resumableTasks,
                count: resumableTasks.length,
                method: 'direct'
            });
            
        } catch (error) {
            console.error('直接获取可恢复任务失败:', error);
            res.status(500).json({
                success: false,
                error: error.message
            });
        }
    });

    // 添加执行任务API
    app.post('/api/execute-task', async (req, res) => {
        const { mode, query, alchemy_id, resume, input_dirs } = req.body;
        
        try {
            // 验证必填参数
            if (mode === "new" && !query) {
                return res.status(400).json({
                    success: false,
                    error: '新建任务模式下查询文本不能为空'
                });
            }
            
            // 在continue模式下验证任务ID
            if (mode === 'continue' && !alchemy_id) {
                return res.status(400).json({
                    success: false,
                    error: '继续任务模式下必须提供任务ID'
                });
            }
            
            console.log(`开始执行任务: ${alchemy_id || '新任务'}, 模式: ${mode}`);
            
            // 使用processManager的executeTask方法
            const taskId = await processManager.executeTask(mode, query, alchemy_id, resume, input_dirs);
            
            res.json({
                success: true,
                alchemy_id: taskId,
                message: '任务已启动'
            });
        } catch (error) {
            console.error('执行任务失败:', error);
            res.status(500).json({
                success: false,
                error: error.message
            });
        }
    });

    // 添加停止任务API
    app.post('/api/stop-task', async (req, res) => {
        const { alchemy_id, stop_type } = req.body;
        
        try {
            // 验证必填参数
            if (!alchemy_id) {
                return res.status(400).json({
                    success: false,
                    error: '任务ID不能为空'
                });
            }
            
            console.log(`收到停止任务请求: ID=${alchemy_id}, 类型=${stop_type || 'force'}`);
            
            // 使用processManager的stopTask方法
            const result = await processManager.stopTask(alchemy_id, stop_type);
            
            // 返回结果
            res.json({
                success: true,
                message: result.message,
                alchemy_id: alchemy_id,
                method: result.method
            });
        } catch (error) {
            console.error('停止任务失败:', error);
            res.status(500).json({
                success: false,
                error: error.message
            });
        }
    });

    // 添加保存下一轮迭代配置API
    app.post('/api/save-next-iteration-config', async (req, res) => {
        try {
            const { alchemy_id, config } = req.body;
            
            if (!alchemy_id) {
                return res.status(400).json({ 
                    success: false, 
                    error: '缺少任务ID参数' 
                });
            }
            
            if (!config || typeof config !== 'object') {
                return res.status(400).json({ 
                    success: false, 
                    error: '配置数据无效' 
                });
            }
            
            // 构建任务目录路径
            const workDir = path.join(__dirname, '..', '..');
            const alchemyDir = path.join(workDir, 'work_dir', 'data_alchemy');
            const runsDir = path.join(alchemyDir, 'alchemy_runs');
            const taskDir = path.join(runsDir, `alchemy_${alchemy_id}`);
            
            // 检查任务目录是否存在
            if (!fs.existsSync(taskDir)) {
                return res.status(404).json({ 
                    success: false, 
                    error: `任务 ${alchemy_id} 不存在` 
                });
            }
            
            // 保存配置文件
            const configPath = path.join(taskDir, 'next_iteration_config.json');
            await fsPromises.writeFile(configPath, JSON.stringify(config, null, 2), 'utf8');
            
            console.log(`已保存任务 ${alchemy_id} 的下一轮迭代配置`);
            
            res.json({
                success: true,
                message: `已保存任务 ${alchemy_id} 的下一轮迭代配置`
            });
        } catch (error) {
            console.error('保存下一轮迭代配置失败:', error);
            res.status(500).json({
                success: false,
                error: error.message
            });
        }
    });
}

module.exports = { setupRoutes }; 