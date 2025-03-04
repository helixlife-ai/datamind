const fs = require('fs');
const path = require('path');
const chokidar = require('chokidar');

/**
 * 设置文件监控
 * @param {Object} dir - 目录对象
 * @param {string} dirKey - 目录键
 * @param {Object} io - Socket.IO实例
 * @param {Object} config - 配置对象
 * @param {Function} updateFileStructure - 更新文件结构的函数
 * @returns {Object} 文件监控实例
 */
function setupFileWatcher(dir, dirKey, io, config, updateFileStructure) {
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
        updateFileStructure(null, io);
    });
    
    return watcher;
}

/**
 * 更新文件结构
 * @param {Array} watchDirs - 监控目录数组
 * @param {Object} io - Socket.IO实例
 */
function updateFileStructure(watchDirs, io) {
    const structure = {};
    
    // 如果没有提供watchDirs，使用全局变量
    const dirs = watchDirs || global.watchDirs;
    
    // 确保dirs存在且是数组
    if (!dirs || !Array.isArray(dirs)) {
        console.error('更新文件结构失败: 监控目录未定义或不是数组');
        return;
    }
    
    dirs.forEach(dir => {
        const dirKey = dir.path;
        structure[dirKey] = {
            name: dir.name || dirKey,
            description: dir.description || '',
            files: buildFileSystemStructure(dir.fullPath)
        };
    });
    
    io.emit('initialStructure', structure);
}

/**
 * 构建文件系统结构
 * @param {string} dirPath - 目录路径
 * @param {string} baseDir - 基础目录
 * @returns {Object} 文件系统结构对象
 */
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

/**
 * 获取相对路径
 * @param {string} fullPath - 完整路径
 * @param {Array} watchDirs - 监控目录数组
 * @returns {Object|null} 包含目录ID和相对路径的对象，或null
 */
function getRelativePath(fullPath, watchDirs) {
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

module.exports = {
    setupFileWatcher,
    updateFileStructure,
    buildFileSystemStructure,
    getRelativePath
}; 