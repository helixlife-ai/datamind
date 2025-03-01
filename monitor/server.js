const express = require('express');
const app = express();
const http = require('http').createServer(app);
const io = require('socket.io')(http);
const chokidar = require('chokidar');
const path = require('path');
const fs = require('fs');
const dotenv = require('dotenv');
const { OpenAI } = require('openai');
const crypto = require('crypto');
const fsPromises = require('fs').promises;
const { exec } = require('child_process');

// 读取环境变量
dotenv.config();

// 打印环境变量加载路径
console.log(`dotenv配置路径: ${path.resolve('.env')}`);
console.log(`当前工作目录: ${process.cwd()}`);

// 读取配置文件
let config;
try {
    config = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));
} catch (err) {
    console.error('Error reading config file:', err);
    config = {
        watchDirs: [{ path: 'watchdir', name: 'Default Watch Directory' }],
        port: 3000,
        excludePatterns: ['node_modules', '.git', '*.log']
    };
}

// 解析API密钥列表
function parseApiKeys(envValue) {
    console.log(`解析API密钥，原始值类型: ${typeof envValue}`);
    
    if (!envValue) {
        console.log('环境变量值为空');
        return [];
    }
    
    try {
        // 如果是字符串数组格式 ['key1','key2']
        if (typeof envValue === 'string') {
            console.log(`环境变量是字符串，长度: ${envValue.length}`);
            
            if (envValue.startsWith('[') && envValue.endsWith(']')) {
                console.log('检测到数组格式的字符串');
                // 移除方括号并分割字符串
                const keysString = envValue.slice(1, -1);
                
                // 使用正则表达式匹配引号内的内容
                const keyMatches = keysString.match(/'[^']*'|"[^"]*"/g) || [];
                console.log(`正则匹配到 ${keyMatches.length} 个密钥`);
                
                if (keyMatches.length === 0) {
                    // 尝试简单的逗号分割
                    console.log('尝试使用逗号分割');
                    const keys = keysString.split(',').map(k => k.trim().replace(/["']/g, ''));
                    console.log(`逗号分割得到 ${keys.length} 个密钥`);
                    return keys.filter(k => k);
                }
                
                const keys = keyMatches.map(k => k.slice(1, -1).trim());
                return keys.filter(k => k);  // 移除空值
            } else {
                // 单个字符串密钥
                return [envValue.trim()];
            }
        }
        // 如果已经是数组
        else if (Array.isArray(envValue)) {
            console.log(`环境变量是数组，长度: ${envValue.length}`);
            return envValue.filter(k => k);
        }
        
        console.log(`环境变量是其他类型: ${typeof envValue}`);
        return [];
    } catch (e) {
        console.error('解析API密钥失败:', e);
        return [];
    }
}

// 初始化API客户端
const OPENAI_CLIENTS = {
    'deepseek': [],
    'siliconflow': []
};

// 直接从.env文件读取内容，用于调试
try {
    const envContent = fs.readFileSync(path.resolve('.env'), 'utf8');
    const envLines = envContent.split('\n');
    console.log('直接读取.env文件内容:');
    envLines.forEach(line => {
        if (line.trim() && !line.startsWith('#')) {
            // 隐藏实际密钥值
            const parts = line.split('=');
            if (parts.length >= 2) {
                const key = parts[0].trim();
                console.log(`${key}=${key.includes('KEY') ? '[已隐藏]' : parts.slice(1).join('=')}`);
            } else {
                console.log(line);
            }
        }
    });
} catch (err) {
    console.log('无法直接读取.env文件:', err.message);
}

// 读取并解析DeepSeek API密钥
console.log('处理DeepSeek API密钥:');
console.log(`环境变量 DEEPSEEK_API_KEY: ${process.env.DEEPSEEK_API_KEY ? '存在' : '不存在'}`);
const deepseekApiKeys = parseApiKeys(process.env.DEEPSEEK_API_KEY);
console.log(`解析后的DeepSeek API密钥数量: ${deepseekApiKeys.length}`);

deepseekApiKeys.forEach((key, index) => {
    if (key) {
        try {
            OPENAI_CLIENTS.deepseek.push(new OpenAI({
                apiKey: key,
                baseURL: process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com'
            }));
            console.log(`成功添加DeepSeek API客户端 #${index+1}`);
        } catch (err) {
            console.error(`初始化DeepSeek API客户端 #${index+1} 失败:`, err);
        }
    } else {
        console.log(`跳过空的DeepSeek API密钥 #${index+1}`);
    }
});

// 读取并解析SiliconFlow API密钥
console.log('处理SiliconFlow API密钥:');
console.log(`环境变量 SILICONFLOW_API_KEY: ${process.env.SILICONFLOW_API_KEY ? '存在' : '不存在'}`);
const siliconflowApiKeys = parseApiKeys(process.env.SILICONFLOW_API_KEY);
console.log(`解析后的SiliconFlow API密钥数量: ${siliconflowApiKeys.length}`);

// 如果没有从环境变量中获取到密钥，尝试使用硬编码的备用密钥（仅用于测试）
if (siliconflowApiKeys.length === 0) {
    console.log('未从环境变量获取到SiliconFlow API密钥，尝试使用.env文件中的值');
    // 从.env文件中提取的值
    const backupKeys = [
        'sk-vetzamuciebbtsmwdllqxgvztzlfypvpcrhhgituizwppjzr',
        'sk-vungowlfsnzutpdkzmwplimgiktpounmjqqvjojhwnntrlyb'
    ];
    console.log(`使用备用密钥，数量: ${backupKeys.length}`);
    
    backupKeys.forEach((key, index) => {
        if (key) {
            try {
                OPENAI_CLIENTS.siliconflow.push(new OpenAI({
                    apiKey: key,
                    baseURL: process.env.SILICONFLOW_BASE_URL || 'https://api.siliconflow.cn/v1'
                }));
                console.log(`成功添加备用SiliconFlow API客户端 #${index+1}`);
            } catch (err) {
                console.error(`初始化备用SiliconFlow API客户端 #${index+1} 失败:`, err);
            }
        }
    });
} else {
    siliconflowApiKeys.forEach((key, index) => {
        if (key) {
            try {
                OPENAI_CLIENTS.siliconflow.push(new OpenAI({
                    apiKey: key,
                    baseURL: process.env.SILICONFLOW_BASE_URL || 'https://api.siliconflow.cn/v1'
                }));
                console.log(`成功添加SiliconFlow API客户端 #${index+1}`);
            } catch (err) {
                console.error(`初始化SiliconFlow API客户端 #${index+1} 失败:`, err);
            }
        } else {
            console.log(`跳过空的SiliconFlow API密钥 #${index+1}`);
        }
    });
}

console.log(`已加载 ${OPENAI_CLIENTS.deepseek.length} 个 DeepSeek API 客户端`);
console.log(`已加载 ${OPENAI_CLIENTS.siliconflow.length} 个 SiliconFlow API 客户端`);

// 打印环境变量原始值（隐藏实际密钥）
console.log(`环境变量 DEEPSEEK_API_KEY 是否存在: ${!!process.env.DEEPSEEK_API_KEY}`);
console.log(`环境变量 SILICONFLOW_API_KEY 是否存在: ${!!process.env.SILICONFLOW_API_KEY}`);
console.log(`环境变量 DEEPSEEK_BASE_URL: ${process.env.DEEPSEEK_BASE_URL}`);
console.log(`环境变量 SILICONFLOW_BASE_URL: ${process.env.SILICONFLOW_BASE_URL}`);

// API提供商和模型配置
const API_CONFIGS = {
    'deepseek': {
        defaultModel: 'deepseek-chat',
        reasoningModel: 'deepseek-reasoner',
        currentIndex: 0
    },
    'siliconflow': {
        defaultModel: 'Pro/deepseek-ai/DeepSeek-V3',
        reasoningModel: 'Pro/deepseek-ai/DeepSeek-R1',
        currentIndex: 0
    }
};

// 获取下一个API客户端
function getNextApiClient(provider) {
    if (!OPENAI_CLIENTS[provider] || OPENAI_CLIENTS[provider].length === 0) {
        console.error(`没有可用的 ${provider} API 客户端`);
        return null;
    }
    
    const index = API_CONFIGS[provider].currentIndex;
    API_CONFIGS[provider].currentIndex = (index + 1) % OPENAI_CLIENTS[provider].length;
    return OPENAI_CLIENTS[provider][index];
}

// 聊天会话管理
class ChatSessionManager {
    constructor(config) {
        // 尝试从顶级配置中查找聊天记录目录
        if (config.chatRecordDir && config.chatRecordDir.path) {
            this.chatRecordDir = config.chatRecordDir.path;
            this.chatRecordName = config.chatRecordDir.name || "聊天记录";
            this.fullChatRecordDir = path.join(__dirname, this.chatRecordDir);
            console.log(`使用顶级配置的聊天记录目录: ${this.chatRecordDir}`);
        } 
        // 向后兼容：从watchDirs中查找
        else {
            const chatDir = config.watchDirs.find(dir => dir.name === "聊天记录");
            
            if (chatDir) {
                this.chatRecordDir = chatDir.path;
                this.chatRecordName = chatDir.name;
                this.fullChatRecordDir = path.join(__dirname, this.chatRecordDir);
                console.log(`从watchDirs中使用聊天记录目录: ${this.chatRecordDir}`);
            } else {
                // 如果配置中没有找到，使用默认目录
                this.chatRecordDir = "../work_dir/data_alchemy/chat_records";
                this.chatRecordName = "聊天记录";
                this.fullChatRecordDir = path.join(__dirname, this.chatRecordDir);
                console.warn(`配置中未找到聊天记录目录，使用默认路径: ${this.chatRecordDir}`);
            }
        }
        
        this.sessions = new Map();
        this.initDirectory();
    }

    // 初始化聊天记录目录
    async initDirectory() {
        try {
            // 确保目录存在
            await fsPromises.mkdir(this.fullChatRecordDir, { recursive: true });
            console.log(`聊天记录目录已初始化: ${this.fullChatRecordDir}`);
            
            // 创建一个README文件，解释目录用途
            const readmePath = path.join(this.fullChatRecordDir, 'README.md');
            const readmeContent = `# 聊天记录\n\n此目录包含与AI助手的聊天历史记录。\n\n- *.json 文件包含原始对话数据\n- *.txt 文件是可读的对话文本版本\n\n创建时间: ${new Date().toLocaleString('zh-CN')}\n`;
            
            try {
                // 如果README不存在，创建它
                if (!fs.existsSync(readmePath)) {
                    await fsPromises.writeFile(readmePath, readmeContent, 'utf8');
                    console.log('已创建聊天记录README文件');
                }
            } catch (readmeErr) {
                console.warn('创建README文件失败:', readmeErr);
            }
        } catch (err) {
            console.error('初始化聊天记录目录失败:', err);
        }
    }

    // 生成会话ID
    generateSessionId() {
        return crypto.randomBytes(16).toString('hex');
    }

    // 获取或创建会话
    async getOrCreateSession(sessionId) {
        if (!sessionId) {
            sessionId = this.generateSessionId();
        }

        if (!this.sessions.has(sessionId)) {
            const messages = await this.loadChatHistory(sessionId);
            this.sessions.set(sessionId, {
                id: sessionId,
                messages: messages || [],
                lastActivity: Date.now()
            });
        }

        return {
            sessionId,
            session: this.sessions.get(sessionId)
        };
    }

    // 加载聊天历史
    async loadChatHistory(sessionId) {
        const filePath = path.join(this.fullChatRecordDir, `${sessionId}.json`);
        
        try {
            const data = await fsPromises.readFile(filePath, 'utf8');
            return JSON.parse(data);
        } catch (err) {
            // 文件不存在或其他错误，返回空数组
            if (err.code !== 'ENOENT') {
                console.error(`加载聊天历史失败 ${sessionId}:`, err);
            }
            return [];
        }
    }

    // 保存聊天历史 - 添加验证和错误处理
    async saveChatHistory(sessionId, messages) {
        if (!sessionId) return;
        
        // 验证保存路径是否在指定的聊天记录目录内
        const jsonFilePath = path.join(this.fullChatRecordDir, `${sessionId}.json`);
        const txtFilePath = path.join(this.fullChatRecordDir, `${sessionId}.txt`);
        
        // 确保文件路径在聊天记录目录内，防止路径遍历攻击
        if (!jsonFilePath.startsWith(this.fullChatRecordDir) || !txtFilePath.startsWith(this.fullChatRecordDir)) {
            console.error(`安全警告: 尝试在聊天记录目录外保存文件: ${jsonFilePath}`);
            return;
        }
        
        const session = this.sessions.get(sessionId);
        if (session) {
            session.messages = messages;
            session.lastActivity = Date.now();
        }
        
        try {
            // 创建带有日期和时间的消息格式
            const currentTimestamp = new Date().toLocaleString('zh-CN');
            
            // 保存JSON格式记录
            await fsPromises.writeFile(jsonFilePath, JSON.stringify(messages, null, 2), 'utf8');
            
            // 创建可读性更好的文本版本
            const textContent = messages.map(msg => {
                const isUser = msg.role === 'user';
                const roleLabel = isUser ? '👤 用户' : '🤖 AI助手';
                return `${roleLabel} [${currentTimestamp}]\n${msg.content}\n\n`;
            }).join('---\n\n');
            
            await fsPromises.writeFile(txtFilePath, textContent, 'utf8');
            console.log(`已保存聊天记录: ${sessionId}`);
        } catch (err) {
            console.error(`保存聊天历史失败 ${sessionId}:`, err);
        }
    }

    // 清理不活跃的会话
    cleanupSessions(maxAgeMs = 24 * 60 * 60 * 1000) {
        const now = Date.now();
        for (const [sessionId, session] of this.sessions.entries()) {
            if (now - session.lastActivity > maxAgeMs) {
                this.sessions.delete(sessionId);
            }
        }
    }
}

// 创建聊天会话管理器实例
const chatSessionManager = new ChatSessionManager(config);

// 定期清理不活跃的会话(每小时)
setInterval(() => {
    chatSessionManager.cleanupSessions();
}, 60 * 60 * 1000);

// 设置Express应用
app.use(express.static('public'));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// 设置响应头，确保正确的字符编码
app.use((req, res, next) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    next();
});

// 处理监控目录的路径
const watchDirs = config.watchDirs.map(dir => ({
    ...dir,
    fullPath: path.join(__dirname, dir.path)
}));

// 确保所有监控目录都存在
watchDirs.forEach(dir => {
    if (!fs.existsSync(dir.fullPath)) {
        fs.mkdirSync(dir.fullPath, { recursive: true });
        console.log(`Created directory: ${dir.fullPath}`);
    }
});

// 设置文件监控函数
function setupFileWatcher(dir, dirKey) {
    const watcher = chokidar.watch(dir.fullPath, {
        ignored: config.excludePatterns,
        persistent: true,
        ignoreInitial: true, // 忽略初始扫描事件
        awaitWriteFinish: {
            stabilityThreshold: 1000, // 等待文件写入完成
            pollInterval: 100
        }
    });
    
    // 监听文件变化事件
    watcher.on('all', (event, path) => {
        const relativePath = path.replace(dir.fullPath, '').replace(/^[\/\\]/, '');
        const time = new Date().toLocaleTimeString();
        
        // 记录到服务器日志，但不发送到客户端终端
        console.log(`[文件变化] ${event}: ${dirKey}/${relativePath} (${time})`);
        
        // 仅发送文件变化事件，不包含在终端输出中
        io.emit('fileChange', {
            type: event,
            dir: dirKey,
            path: relativePath,
            time: time,
            shouldDisplay: false // 添加标志，表示不应在终端显示
        });
        
        // 更新文件结构
        updateFileStructure();
    });
    
    return watcher;
}

// 更新文件结构函数
function updateFileStructure() {
    const structure = {};
    
    watchDirs.forEach(dir => {
        const dirKey = dir.path;
        structure[dirKey] = {
            name: dir.name || dirKey,
            description: dir.description || '',
            files: buildFileSystemStructure(dir.fullPath)
        };
    });
    
    io.emit('initialStructure', structure);
}

// 初始化文件监控
let watchers = [];
watchDirs.forEach(dir => {
    const dirKey = dir.path;
    const watcher = setupFileWatcher(dir, dirKey);
    watchers.push(watcher);
});

// 初始化时发送文件结构
updateFileStructure();

// 构建文件系统结构的函数
function buildFileSystemStructure(dirPath, baseDir = dirPath) {
    const structure = {};
    try {
        const items = fs.readdirSync(dirPath);
        items.forEach(item => {
            const fullPath = path.join(dirPath, item);
            const stat = fs.statSync(fullPath);

            if (stat.isDirectory()) {
                structure[item] = buildFileSystemStructure(fullPath, baseDir);
            } else {
                structure[item] = true;
            }
        });
    } catch (err) {
        console.error(`Error reading directory ${dirPath}:`, err);
    }
    return structure;
}

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
        
        const client = getNextApiClient(provider);
        if (!client) {
            return res.status(503).json({ error: 'API服务不可用' });
        }
        
        const modelName = API_CONFIGS[provider].defaultModel;
        
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
        findPythonProcesses((pids) => {
            const running = pids.length > 0;
            let taskId = null;
            
            if (running) {
                // 尝试从进程信息中获取任务ID
                // 这里可能需要根据实际情况调整获取任务ID的逻辑
                taskId = getTaskIdFromRunningProcess(pids);
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

// 添加全局变量定义
const activeProcesses = new Set();

// 修改执行任务API，添加子进程跟踪
app.post('/api/execute-task', async (req, res) => {
    const { mode, query, alchemy_id, resume } = req.body;
    
    try {
        // 构建命令参数
        const args = [
            'examples/example_usage.py',
            `--mode=${mode}`,
            `--query=${query}`
        ];
        
        if (mode === 'continue' && alchemy_id) {
            args.push(`--id=${alchemy_id}`);
            
            if (resume) {
                args.push('--resume');
            }
        }
        
        // 使用child_process执行命令
        const { spawn } = require('child_process');
        const workDir = path.join(__dirname, '..');
        
        // 确定 Python 解释器路径
        const pythonPath = process.env.PYTHON_PATH || 'python';
        
        // 构建脚本的绝对路径
        const scriptPath = path.join(workDir, 'examples', 'example_usage.py');
        console.log(`工作目录: ${workDir}`);
        console.log(`脚本路径: ${scriptPath}`);
        console.log(`Python解释器路径: ${pythonPath}`);
        console.log(`检查脚本是否存在: ${fs.existsSync(scriptPath) ? '存在' : '不存在'}`);
        
        // 更新参数，使用绝对路径
        args[0] = scriptPath;
        
        console.log(`执行命令: ${pythonPath} ${args.join(' ')}`);
        
        const pythonProcess = spawn(pythonPath, args, {
            cwd: workDir,
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
        });
        
        // 添加到活动进程集合
        const processInfo = { 
            pid: pythonProcess.pid, 
            taskId: alchemy_id,
            startTime: new Date()
        };
        activeProcesses.add(processInfo);
        
        // 生成任务ID
        const taskId = alchemy_id || crypto.randomBytes(8).toString('hex');
        
        // 设置输出处理
        pythonProcess.stdout.on('data', (data) => {
            const output = data.toString('utf8');
            console.log(`[Task ${taskId}] ${output}`);
            
            // 通过WebSocket发送输出
            io.emit('taskOutput', {
                alchemy_id: taskId,
                output: output,
                encoding: 'utf8' // 明确指定编码
            });
            
            // 尝试从输出中提取alchemy_id
            const idMatch = output.match(/ID: ([a-f0-9]+)/i);
            if (idMatch && idMatch[1]) {
                // 更新任务ID
                taskId = idMatch[1];
            }
        });
        
        pythonProcess.stderr.on('data', (data) => {
            const output = data.toString('utf8');
            console.error(`[Task ${taskId} STDERR] ${output}`);
            
            // 检查是否为真正的错误信息
            const isRealError = output.includes('Error') || 
                               output.includes('错误') || 
                               output.includes('Exception') || 
                               output.includes('异常') ||
                               output.includes('Failed') ||
                               output.includes('失败');
            
            // 通过WebSocket发送错误输出，但不再自动添加[错误]前缀
            io.emit('taskOutput', {
                alchemy_id: taskId,
                output: isRealError ? `[错误] ${output}` : output,
                encoding: 'utf8', // 明确指定编码
                isError: isRealError // 添加错误标志
            });
        });
        
        pythonProcess.on('close', (code) => {
            console.log(`[Task ${taskId}] 进程退出，代码: ${code}`);
            
            // 从活动进程集合中移除
            for (const process of activeProcesses) {
                if (process.taskId === alchemy_id) {
                    activeProcesses.delete(process);
                    break;
                }
            }
            
            // 通过WebSocket发送完成消息
            io.emit('taskOutput', {
                alchemy_id: taskId,
                output: `\n[任务完成] 退出代码: ${code}\n`,
                encoding: 'utf8' // 明确指定编码
            });
        });
        
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

// 添加停止任务API（合并取消任务和中止任务）
app.post('/api/stop-task', async (req, res) => {
    const { alchemy_id, stop_type = 'force' } = req.body;
    
    if (!alchemy_id) {
        return res.status(400).json({
            success: false,
            error: '缺少任务ID'
        });
    }
    
    try {
        console.log(`尝试强制停止任务: ${alchemy_id}`);
        // 查找包含特定任务ID的Python进程
        const findCmd = process.platform === 'win32' 
            ? `tasklist /FI "IMAGENAME eq python.exe" /FO CSV` 
            : `ps aux | grep "python.*${alchemy_id}" | grep -v grep`;
        
        exec(findCmd, (error, stdout, stderr) => {
            if (error) {
                console.error('查找进程失败:', error);
                return res.status(500).json({
                    success: false,
                    error: '查找进程失败: ' + error.message
                });
            }
            
            // 解析进程ID
            let pids = [];
            if (process.platform === 'win32') {
                // Windows下解析tasklist输出
                const lines = stdout.split('\n').filter(line => line.includes('python.exe'));
                
                // 如果有alchemy_id，先尝试查找包含该ID的进程
                if (alchemy_id) {
                    // 获取所有Python进程的PID
                    const pythonPids = [];
                    lines.forEach(line => {
                        const match = line.match(/"python.exe","(\d+)",/);
                        if (match && match[1]) {
                            pythonPids.push(match[1]);
                        }
                    });
                    
                    // 对于每个Python进程，检查其命令行是否包含alchemy_id
                    if (pythonPids.length > 0) {
                        // 使用wmic查询每个进程的命令行
                        const wmicPromises = pythonPids.map(pid => {
                            return new Promise((resolve) => {
                                exec(`wmic process where "ProcessId=${pid}" get CommandLine`, (wmicError, wmicStdout) => {
                                    if (!wmicError && wmicStdout.includes(alchemy_id)) {
                                        resolve(pid);
                                    } else {
                                        resolve(null);
                                    }
                                });
                            });
                        });
                        
                        // 等待所有wmic查询完成
                        Promise.all(wmicPromises).then(matchedPids => {
                            pids = matchedPids.filter(pid => pid !== null);
                            
                            if (pids.length === 0) {
                                // 如果没有找到匹配的进程，使用备用方法
                                lines.forEach(line => {
                                    const match = line.match(/"python.exe","(\d+)",/);
                                    if (match && match[1]) {
                                        pids.push(match[1]);
                                    }
                                });
                            }
                            
                            // 继续处理找到的PID
                            handleFoundPids(pids);
                        });
                        
                        // 提前返回，等待异步处理完成
                        return;
                    }
                }
                
                // 如果没有alchemy_id或者上面的方法没有找到进程，使用简单方法
                lines.forEach(line => {
                    const match = line.match(/"python.exe","(\d+)",/);
                    if (match && match[1]) {
                        pids.push(match[1]);
                    }
                });
            } else {
                // Linux/Mac下解析ps输出
                const lines = stdout.split('\n');
                lines.forEach(line => {
                    const parts = line.trim().split(/\s+/);
                    if (parts.length > 1) {
                        pids.push(parts[1]);
                    }
                });
            }
            
            // 处理找到的PID
            handleFoundPids(pids);
        });
        
        // 处理找到的PID的函数
        function handleFoundPids(pids) {
            if (pids.length === 0) {
                // 没有找到相关进程
                io.emit('taskOutput', {
                    alchemy_id: alchemy_id,
                    output: `\n[停止请求] 未找到相关任务进程\n`,
                    encoding: 'utf8' // 明确指定编码
                });
                
                return res.json({
                    success: true,
                    message: '未找到相关任务进程'
                });
            }
            
            // 终止找到的进程
            const killCmd = process.platform === 'win32'
                ? `taskkill /F /PID ${pids.join(' /PID ')}` 
                : `kill -9 ${pids.join(' ')}`;
            
            exec(killCmd, (killError, killStdout, killStderr) => {
                if (killError) {
                    console.error('终止进程失败:', killError);
                    io.emit('taskOutput', {
                        alchemy_id: alchemy_id,
                        output: `\n[停止请求失败] ${killError.message}\n`,
                        encoding: 'utf8' // 明确指定编码
                    });
                    
                    return res.status(500).json({
                        success: false,
                        error: '终止进程失败: ' + killError.message
                    });
                }
                
                // 通知客户端任务已停止
                io.emit('taskStatus', {
                    alchemy_id: alchemy_id,
                    status: 'stopped',
                    pids: pids
                });
                
                // 发送任务停止消息
                emitTaskOutput(alchemy_id, `\n[任务停止] 任务已被强制停止 (ID: ${alchemy_id})\n`, false);
                
                // 清理任务历史记录（延迟执行）
                cleanupTaskHistory(alchemy_id);
                
                // 从活动进程集合中移除
                for (const process of activeProcesses) {
                    if (process.taskId === alchemy_id) {
                        activeProcesses.delete(process);
                        break;
                    }
                }
                
                res.json({
                    success: true,
                    message: '已强制终止任务进程',
                    pids: pids
                });
            });
        }
    } catch (error) {
        console.error('停止任务失败:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// 处理任务中断后的操作，类似于handle_keyboard_interrupt
function handleTaskInterrupt(alchemy_id) {
    try {
        console.log(`处理任务中断，尝试保存恢复信息: ${alchemy_id}`);
        
        // 构建工作目录和任务目录路径
        const workDir = path.join(__dirname, '..');
        const alchemyDir = path.join(workDir, 'work_dir', 'data_alchemy');
        const taskDir = path.join(alchemyDir, 'alchemy_runs', `alchemy_${alchemy_id}`);
        
        console.log(`工作目录: ${workDir}`);
        console.log(`任务目录: ${taskDir}`);
        
        // 检查任务目录是否存在
        if (fs.existsSync(taskDir)) {
            console.log(`任务目录存在: ${taskDir}`);
            
            // 列出任务目录内容
            const taskFiles = fs.readdirSync(taskDir);
            console.log(`任务目录文件: ${taskFiles.join(', ')}`);
            
            // 尝试从resume_info.json读取额外信息
            const resumeInfoPath = path.join(taskDir, 'resume_info.json');
            if (fs.existsSync(resumeInfoPath)) {
                const resumeInfo = JSON.parse(fs.readFileSync(resumeInfoPath, 'utf8'));
                console.log(`恢复信息: ${JSON.stringify(resumeInfo)}`);
                
                // 更新恢复信息，添加中断标记
                resumeInfo.interrupted = true;
                resumeInfo.interrupt_time = new Date().toISOString();
                resumeInfo.interrupt_type = 'forced';
                
                // 保存更新后的恢复信息
                fs.writeFileSync(resumeInfoPath, JSON.stringify(resumeInfo, null, 2), 'utf8');
                console.log(`已更新恢复信息: ${resumeInfoPath}`);
                
                // 通过WebSocket发送恢复指令
                io.emit('taskOutput', {
                    alchemy_id: alchemy_id,
                    output: `\n[恢复信息] 任务已保存中断状态，可以使用以下命令恢复:\npython examples/example_usage.py --mode=continue --id=${alchemy_id} --resume\n`,
                    encoding: 'utf8'
                });
            } else {
                console.log(`恢复信息文件不存在: ${resumeInfoPath}`);
                
                // 创建基本的恢复信息
                const basicResumeInfo = {
                    alchemy_id: alchemy_id,
                    timestamp: new Date().toISOString(),
                    interrupted: true,
                    interrupt_type: 'forced',
                    current_step: 'unknown'
                };
                
                // 保存基本恢复信息
                fs.writeFileSync(resumeInfoPath, JSON.stringify(basicResumeInfo, null, 2), 'utf8');
                console.log(`已创建基本恢复信息: ${resumeInfoPath}`);
                
                emitTaskOutput(alchemy_id, `\n[恢复信息] 已创建基本恢复信息，可以尝试使用以下命令恢复:\npython examples/example_usage.py --mode=continue --id=${alchemy_id} --resume\n`, false);
            }
            
            // 尝试执行Python脚本来保存检查点
            try {
                const { spawn } = require('child_process');
                
                // 构建脚本的绝对路径
                const scriptPath = path.join(workDir, 'examples', 'example_usage.py');
                console.log(`保存检查点 - 工作目录: ${workDir}`);
                console.log(`保存检查点 - 脚本路径: ${scriptPath}`);
                console.log(`保存检查点 - 检查脚本是否存在: ${fs.existsSync(scriptPath) ? '存在' : '不存在'}`);
                
                const saveCheckpointProcess = spawn('python', [
                    scriptPath,
                    `--id=${alchemy_id}`,
                    '--cancel'
                ], {
                    cwd: workDir,
                    env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
                });
                
                saveCheckpointProcess.stdout.on('data', (data) => {
                    const output = data.toString('utf8');
                    console.log(`[保存检查点] ${output}`);
                    
                    // 将检查点保存的输出发送到客户端
                    emitTaskOutput(alchemy_id, `[检查点保存] ${output}`, false);
                });
                
                saveCheckpointProcess.stderr.on('data', (data) => {
                    const output = data.toString('utf8');
                    console.error(`[保存检查点错误] ${output}`);
                });
                
                saveCheckpointProcess.on('close', (code) => {
                    console.log(`保存检查点进程退出，代码: ${code}`);
                });
            } catch (error) {
                console.error(`执行保存检查点脚本失败: ${error.message}`);
            }
        } else {
            console.log(`任务目录不存在: ${taskDir}`);
            io.emit('taskOutput', {
                alchemy_id: alchemy_id,
                output: `\n[警告] 任务目录不存在，无法保存恢复信息\n`,
                encoding: 'utf8'
            });
        }
        
        console.log("中断处理完成");
    } catch (error) {
        console.error(`处理任务中断时发生错误: ${error.message}`);
        io.emit('taskOutput', {
            alchemy_id: alchemy_id,
            output: `\n[错误] 处理任务中断时发生错误: ${error.message}\n`,
            encoding: 'utf8'
        });
    }
}

// 保留原有API端点以保持向后兼容
app.post('/api/cancel-task', async (req, res) => {
    const { alchemy_id } = req.body;
    
    if (!alchemy_id) {
        return res.status(400).json({
            success: false,
            error: '缺少任务ID'
        });
    }
    
    // 直接调用新API的处理逻辑
    req.body.stop_type = 'force';
    req.url = '/api/stop-task';
    app.handle(req, res);
});

app.post('/api/terminate-task', async (req, res) => {
    const { alchemy_id } = req.body;
    
    if (!alchemy_id) {
        return res.status(400).json({
            success: false,
            error: '缺少任务ID'
        });
    }
    
    // 直接调用新API的处理逻辑
    req.body.stop_type = 'force';
    req.url = '/api/stop-task';
    app.handle(req, res);
});

// 添加获取可恢复任务API
app.get('/api/resumable-tasks', async (req, res) => {
    try {
        console.log('开始获取可恢复任务...');
        
        // 确定 Python 解释器路径
        const pythonPath = process.env.PYTHON_PATH || 'python';
        
        // 构建命令
        const command = `${pythonPath} examples/alchemy_manager_cli.py resumable --json`;
        console.log(`执行命令: ${command}`);
        
        // 使用child_process执行命令
        exec(command, {
            cwd: path.join(__dirname, '..'),
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' } // 确保Python输出使用UTF-8编码
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
            
            try {
                const tasks = JSON.parse(stdout);
                console.log(`成功解析到 ${tasks.length} 个可恢复任务`);
                res.json({
                    success: true,
                    tasks: tasks
                });
            } catch (parseError) {
                console.error('解析可恢复任务失败:', parseError);
                console.error('原始输出:', stdout);
                res.status(500).json({
                    success: false,
                    error: `解析任务数据失败: ${parseError.message}`,
                    rawOutput: stdout
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

// 添加获取当前运行任务的API
app.get('/api/running-tasks', (req, res) => {
    try {
        // 检查是否有活动的进程
        if (activeProcesses.size > 0) {
            // 返回第一个活动进程的信息
            const firstProcess = Array.from(activeProcesses)[0];
            const taskId = firstProcess.taskId || '未知ID';
            
            res.json({
                success: true,
                running_task: {
                    id: taskId,
                    status: 'running'
                }
            });
        } else {
            res.json({
                success: true,
                running_task: null
            });
        }
    } catch (error) {
        console.error('获取运行中任务失败:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// 添加任务历史记录存储
const taskOutputHistory = {};
const MAX_HISTORY_ITEMS = 1000; // 每个任务最多保存的输出条数

// 在处理任务输出的地方添加历史记录功能
// 例如，在处理 taskOutput 事件的地方
io.on('connection', (socket) => {
    // ... existing code ...
    
    // 检查运行中的任务
    socket.on('checkRunningTasks', () => {
        // 检查是否有正在运行的Python进程
        findPythonProcesses((pids) => {
            const running = pids.length > 0;
            let taskId = null;
            
            if (running) {
                // 尝试从进程信息中获取任务ID
                // 这里可能需要根据实际情况调整获取任务ID的逻辑
                taskId = getTaskIdFromRunningProcess(pids);
            }
            
            socket.emit('runningTasksResult', {
                running: running,
                taskId: taskId,
                pids: pids
            });
        });
    });
    
    // 添加获取任务历史的API
    app.get('/api/task-history', (req, res) => {
        const taskId = req.query.id;
        
        if (!taskId) {
            return res.json({ success: false, error: '未提供任务ID' });
        }
        
        const history = taskOutputHistory[taskId] || [];
        
        res.json({
            success: true,
            history: history
        });
    });
});

// 在发送任务输出到客户端的地方，同时保存到历史记录
function emitTaskOutput(alchemy_id, output, isError = false) {
    // 发送到所有连接的客户端
    io.emit('taskOutput', {
        alchemy_id: alchemy_id,
        output: output,
        isError: isError,
        encoding: 'utf8'
    });
    
    // 保存到历史记录
    if (alchemy_id) {
        if (!taskOutputHistory[alchemy_id]) {
            taskOutputHistory[alchemy_id] = [];
        }
        
        // 添加新的输出记录
        taskOutputHistory[alchemy_id].push({
            output: output,
            isError: isError,
            timestamp: new Date().toISOString()
        });
        
        // 限制历史记录大小
        if (taskOutputHistory[alchemy_id].length > MAX_HISTORY_ITEMS) {
            taskOutputHistory[alchemy_id] = taskOutputHistory[alchemy_id].slice(-MAX_HISTORY_ITEMS);
        }
    }
}

// 从运行中的进程获取任务ID
function getTaskIdFromRunningProcess(pids) {
    // 首先检查活动进程集合
    for (const process of activeProcesses) {
        if (pids.includes(String(process.pid))) {
            return process.taskId;
        }
    }
    
    // 如果在活动进程集合中没有找到，尝试从命令行参数中提取
    // 这需要在系统上执行额外的命令，可能会有一些延迟
    try {
        const { execSync } = require('child_process');
        
        for (const pid of pids) {
            let cmdOutput;
            
            if (process.platform === 'win32') {
                // Windows
                cmdOutput = execSync(`wmic process where processid=${pid} get commandline`, { encoding: 'utf8' });
            } else {
                // Linux/Mac
                cmdOutput = execSync(`ps -p ${pid} -o command=`, { encoding: 'utf8' });
            }
            
            // 尝试从命令行中提取 --id= 参数
            const match = cmdOutput.match(/--id=([a-zA-Z0-9_-]+)/);
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
}

// 在任务完成或被取消时清理历史记录
function cleanupTaskHistory(alchemy_id) {
    // 可选：在任务完成一段时间后清理历史记录
    setTimeout(() => {
        if (taskOutputHistory[alchemy_id]) {
            delete taskOutputHistory[alchemy_id];
            console.log(`已清理任务历史记录: ${alchemy_id}`);
        }
    }, 30 * 60 * 1000); // 30分钟后清理
}

// 查找与数据炼丹相关的Python进程
function findPythonProcesses(callback) {
    const { exec } = require('child_process');
    
    // 根据操作系统选择不同的命令
    let cmd;
    if (process.platform === 'win32') {
        // Windows: 使用 tasklist 查找 python 进程，并过滤包含 example_usage.py 的进程
        cmd = 'tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH';
    } else {
        // Linux/Mac: 使用 ps 和 grep 查找 python 进程
        cmd = 'ps aux | grep python | grep example_usage.py | grep -v grep';
    }
    
    exec(cmd, (error, stdout, stderr) => {
        if (error && error.code !== 1) {
            // 命令执行错误（但grep没有匹配项时返回1，这不是错误）
            console.error(`查找Python进程失败: ${error.message}`);
            return callback([]);
        }
        
        const pids = [];
        
        if (process.platform === 'win32') {
            // 解析Windows tasklist输出
            const lines = stdout.trim().split('\n');
            
            // 如果没有找到任何进程，直接调用回调
            if (lines.length === 0) {
                return callback(pids);
            }
            
            // 使用更简单的方法：直接检查命令行参数
            exec('wmic process where "name=\'python.exe\'" get processid,commandline', (err, wmicOutput) => {
                if (err) {
                    console.error(`获取Python进程命令行失败: ${err.message}`);
                    return callback(pids);
                }
                
                const wmicLines = wmicOutput.trim().split('\n');
                // 跳过标题行
                for (let i = 1; i < wmicLines.length; i++) {
                    const line = wmicLines[i].trim();
                    if (line && line.includes('example_usage.py')) {
                        // 提取PID（最后一列）
                        const pid = line.trim().split(/\s+/).pop();
                        if (pid && /^\d+$/.test(pid)) {
                            pids.push(pid);
                        }
                    }
                }
                
                callback(pids);
            });
        } else {
            // 解析Linux/Mac ps输出
            const lines = stdout.trim().split('\n');
            for (const line of lines) {
                if (line.trim()) {
                    const parts = line.trim().split(/\s+/);
                    if (parts.length >= 2) {
                        pids.push(parts[1]); // 第二列是PID
                    }
                }
            }
            callback(pids);
        }
    });
}

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
    console.log(`正在终止 ${activeProcesses.size} 个活动子进程...`);
    for (const proc of activeProcesses) {
        try {
            // 在Windows上，需要使用特殊方法终止进程树
            if (process.platform === 'win32') {
                // 使用taskkill终止进程及其子进程
                require('child_process').execSync(`taskkill /pid ${proc.pid} /T /F`, {
                    stdio: 'ignore'
                });
            } else {
                // 在Unix系统上，发送SIGTERM信号
                proc.kill('SIGTERM');
                
                // 如果进程没有在1秒内退出，发送SIGKILL
                setTimeout(() => {
                    try {
                        if (!proc.killed) {
                            proc.kill('SIGKILL');
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
    
    // 等待所有子进程终止
    const waitForProcesses = new Promise((resolve) => {
        if (activeProcesses.size === 0) {
            resolve();
            return;
        }
        
        console.log('等待子进程终止...');
        const checkInterval = setInterval(() => {
            if (activeProcesses.size === 0) {
                clearInterval(checkInterval);
                resolve();
            }
        }, 100);
        
        // 最多等待3秒
        setTimeout(() => {
            clearInterval(checkInterval);
            if (activeProcesses.size > 0) {
                console.warn(`${activeProcesses.size} 个子进程未能正常终止`);
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