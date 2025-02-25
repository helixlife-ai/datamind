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

// 读取环境变量
dotenv.config();

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
    if (!envValue) return [];
    
    try {
        if (envValue.startsWith('[') && envValue.endsWith(']')) {
            // 移除方括号并分割字符串
            const keys = envValue.slice(1, -1).split(',').map(k => k.trim().replace(/["']/g, ''));
            return keys.filter(k => k);  // 移除空值
        }
        return [envValue];  // 如果不是列表格式，返回单个值的列表
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

// 读取并解析DeepSeek API密钥
const deepseekApiKeys = parseApiKeys(process.env.DEEPSEEK_API_KEY);
deepseekApiKeys.forEach(key => {
    OPENAI_CLIENTS.deepseek.push(new OpenAI({
        apiKey: key,
        baseURL: process.env.DEEPSEEK_BASE_URL
    }));
});

// 读取并解析SiliconFlow API密钥
const siliconflowApiKeys = parseApiKeys(process.env.SILICONFLOW_API_KEY);
siliconflowApiKeys.forEach(key => {
    OPENAI_CLIENTS.siliconflow.push(new OpenAI({
        apiKey: key,
        baseURL: process.env.SILICONFLOW_BASE_URL
    }));
});

console.log(`已加载 ${OPENAI_CLIENTS.deepseek.length} 个 DeepSeek API 密钥`);
console.log(`已加载 ${OPENAI_CLIENTS.siliconflow.length} 个 SiliconFlow API 密钥`);

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

// 设置静态文件目录
app.use(express.static('public'));
app.use(express.json());

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

// 初始化文件监控
const watcher = chokidar.watch(watchDirs.map(dir => dir.fullPath), {
    ignored: config.excludePatterns,
    persistent: true,
    alwaysStat: true
});

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

// 文件变化事件处理
watcher
    .on('addDir', (fullPath) => {
        const pathInfo = getRelativePath(fullPath);
        if (pathInfo) {
            console.log(`Directory added: ${pathInfo.relativePath}`);
            io.emit('fileChange', {
                type: 'addDir',
                dir: pathInfo.dirId,
                path: pathInfo.relativePath,
                time: new Date().toLocaleString()
            });
        }
    })
    .on('unlinkDir', (fullPath) => {
        const pathInfo = getRelativePath(fullPath);
        if (pathInfo) {
            console.log(`Directory removed: ${pathInfo.relativePath}`);
            io.emit('fileChange', {
                type: 'removeDir',
                dir: pathInfo.dirId,
                path: pathInfo.relativePath,
                time: new Date().toLocaleString()
            });
        }
    })
    .on('add', (fullPath) => {
        const pathInfo = getRelativePath(fullPath);
        if (pathInfo) {
            console.log(`File added: ${pathInfo.relativePath}`);
            io.emit('fileChange', {
                type: 'add',
                dir: pathInfo.dirId,
                path: pathInfo.relativePath,
                time: new Date().toLocaleString()
            });
        }
    })
    .on('change', (fullPath) => {
        const pathInfo = getRelativePath(fullPath);
        if (pathInfo) {
            console.log(`File changed: ${pathInfo.relativePath}`);
            io.emit('fileChange', {
                type: 'change',
                dir: pathInfo.dirId,
                path: pathInfo.relativePath,
                time: new Date().toLocaleString()
            });
        }
    })
    .on('unlink', (fullPath) => {
        const pathInfo = getRelativePath(fullPath);
        if (pathInfo) {
            console.log(`File removed: ${pathInfo.relativePath}`);
            io.emit('fileChange', {
                type: 'remove',
                dir: pathInfo.dirId,
                path: pathInfo.relativePath,
                time: new Date().toLocaleString()
            });
        }
    })
    .on('error', error => {
        console.error('Watcher error:', error);
    });

// 启动服务器
const PORT = config.port || 3000;
http.listen(PORT, () => {
    console.log(`服务器运行在 http://localhost:${PORT}`);
    watchDirs.forEach(dir => {
        console.log(`监控目录: ${dir.fullPath}`);
    });
});