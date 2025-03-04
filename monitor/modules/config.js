const fs = require('fs');
const path = require('path');

/**
 * 加载配置文件并返回配置对象
 * @returns {Object} 配置对象
 */
function setupConfig() {
    let config;
    try {
        config = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'config.json'), 'utf8'));
    } catch (err) {
        console.error('Error reading config file:', err);
        config = {
            watchDirs: [{ path: 'watchdir', name: 'Default Watch Directory' }],
            port: 3000,
            excludePatterns: ['node_modules', '.git', '*.log']
        };
    }
    return config;
}

module.exports = {
    setupConfig
}; 