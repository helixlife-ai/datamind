const express = require('express');
const app = express();
const http = require('http').createServer(app);
const io = require('socket.io')(http);
const chokidar = require('chokidar');
const path = require('path');
const fs = require('fs');

// 读取配置文件
let config;
try {
    config = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));
} catch (err) {
    console.error('Error reading config file:', err);
    config = {
        watchDirs: [{ path: 'watchdir', name: '默认监控目录' }],
        port: 3000,
        excludePatterns: ['node_modules', '.git', '*.log']
    };
}

// 设置静态文件目录
app.use(express.static('public'));

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

    socket.on('disconnect', () => {
        console.log('Client disconnected');
    });
});

// 文件变化事件处理
watcher
    .on('addDir', (fullPath) => {
        const pathInfo = getRelativePath(fullPath);
        if (pathInfo) {
            console.log(`Directory ${pathInfo.relativePath} has been added`);
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
            console.log(`Directory ${pathInfo.relativePath} has been removed`);
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
            console.log(`File ${pathInfo.relativePath} has been added`);
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
            console.log(`File ${pathInfo.relativePath} has been changed`);
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
            console.log(`File ${pathInfo.relativePath} has been removed`);
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
    console.log(`Server is running on http://localhost:${PORT}`);
    watchDirs.forEach(dir => {
        console.log(`Monitoring directory: ${dir.fullPath}`);
    });
});