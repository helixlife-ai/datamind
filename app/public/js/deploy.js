// 连接Socket.IO
const socket = io();

// 全局变量
let artifacts = [];
let selectedArtifacts = [];
let siteInfo = null;

// DOM元素
const artifactsContainer = document.getElementById('artifacts-container');
const deployActions = document.getElementById('deploy-actions');
const selectedCountElement = document.getElementById('selected-count');
const currentSiteInfo = document.getElementById('current-site-info');
const deployLog = document.getElementById('deploy-log');
const logContent = document.getElementById('log-content');

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', function() {
    // 初始化移动端菜单
    initMobileMenu();
    
    // 请求制品数据
    socket.emit('deploy:requestArtifacts');
    
    // 请求当前站点信息
    socket.emit('deploy:requestSiteInfo');
    
    // 添加按钮事件监听
    document.getElementById('refresh-artifacts').addEventListener('click', function() {
        socket.emit('deploy:requestArtifacts');
        showLoadingIndicator();
    });
    
    document.getElementById('cancel-selection').addEventListener('click', function() {
        clearSelection();
    });
    
    document.getElementById('confirm-selection').addEventListener('click', function() {
        if (selectedArtifacts.length > 0) {
            // 滚动到配置部分
            document.querySelector('.deploy-panel').scrollIntoView({ behavior: 'smooth' });
        }
    });
    
    document.getElementById('generate-files-btn').addEventListener('click', function() {
        generateDeployFiles();
    });
    
    document.getElementById('deploy-btn').addEventListener('click', function() {
        deployToGitHub();
    });
    
    // 加载保存的GitHub仓库配置
    loadSavedConfig();
});

// 初始化移动端菜单
function initMobileMenu() {
    const mobileMenuButton = document.getElementById('mobile-menu-button');
    const mobileMenu = document.getElementById('mobile-menu');
    
    mobileMenuButton.addEventListener('click', () => {
        mobileMenu.classList.toggle('d-none');
    });
    
    // 点击移动端菜单项后关闭菜单
    const mobileMenuItems = mobileMenu.querySelectorAll('a');
    mobileMenuItems.forEach(item => {
        item.addEventListener('click', () => {
            mobileMenu.classList.add('d-none');
        });
    });
}

// 显示加载指示器
function showLoadingIndicator() {
    artifactsContainer.innerHTML = `
        <div id="loading-indicator" class="col-12 text-center py-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">加载中...</span>
            </div>
            <p class="mt-2 text-muted">正在加载作品...</p>
        </div>
    `;
}

// 加载保存的配置
function loadSavedConfig() {
    const savedConfig = localStorage.getItem('deployConfig');
    if (savedConfig) {
        const config = JSON.parse(savedConfig);
        document.getElementById('repo-url').value = config.repoUrl || '';
        document.getElementById('branch').value = config.branch || 'gh-pages';
        // 出于安全考虑，不加载Token
    }
}

// 保存配置
function saveConfig() {
    const config = {
        repoUrl: document.getElementById('repo-url').value,
        branch: document.getElementById('branch').value
        // 出于安全考虑，不保存Token
    };
    localStorage.setItem('deployConfig', JSON.stringify(config));
}

// 监听制品数据更新
socket.on('deploy:artifacts', function(data) {
    artifacts = data;
    renderArtifactCards();
});

// 监听站点信息更新
socket.on('deploy:siteInfo', function(data) {
    siteInfo = data;
    renderSiteInfo();
});

// 监听部署日志更新
socket.on('deploy:log', function(message) {
    appendToLog(message);
});

// 监听部署完成事件
socket.on('deploy:complete', function(result) {
    if (result.success) {
        appendToLog(`\n✅ 部署成功！\n访问地址: ${result.url}`);
        
        // 更新站点信息
        socket.emit('deploy:requestSiteInfo');
    } else {
        appendToLog(`\n❌ 部署失败: ${result.error}`);
    }
});

// 监听生成文件完成事件
socket.on('deploy:filesGenerated', function(result) {
    if (result.success) {
        appendToLog(`\n✅ 文件生成成功！\n共选择了 ${result.artifactCount} 个作品，保存到 ${result.path}`);
        showNotification('文件生成成功', '现在可以部署到GitHub Pages了');
    } else {
        appendToLog(`\n❌ 文件生成失败: ${result.error}`);
    }
});

// 监听连接错误
socket.on('connect_error', function(error) {
    console.error('Socket.IO连接错误:', error);
    appendToLog('连接服务器时出错，请检查网络连接');
    
    // 显示错误信息
    artifactsContainer.innerHTML = `
        <div class="col-12 text-center py-5">
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle-fill"></i> 连接服务器失败，请刷新页面重试
            </div>
        </div>
    `;
});

// 监听一般错误
socket.on('deploy:error', function(error) {
    appendToLog(`错误: ${error.message}`);
});

// 添加一个调试事件
document.getElementById('refresh-artifacts').addEventListener('dblclick', function() {
    // 双击刷新按钮时，创建样本数据
    const sampleArtifacts = [
        {
            alchemyId: '001',
            alchemyDir: 'alchemy_001',
            query: '分析中国近十年GDP增长趋势',
            timestamp: '2023-05-15T08:30:00Z',
            iteration: 3,
            screenshot: null,
            relativePath: 'artifacts/001.html'
        },
        {
            alchemyId: '002',
            alchemyDir: 'alchemy_002',
            query: '预测2023年全球主要股市走势',
            timestamp: '2023-06-22T14:45:00Z',
            iteration: 2,
            screenshot: null,
            relativePath: 'artifacts/002.html'
        }
    ];
    artifacts = sampleArtifacts;
    renderArtifactCards();
    appendToLog('使用样本数据替代实际制品数据');
});

// 渲染站点信息
function renderSiteInfo() {
    if (!siteInfo) {
        currentSiteInfo.innerHTML = `
            <div class="alert alert-warning">
                <i class="bi bi-exclamation-triangle-fill"></i> 未找到已部署的站点信息
            </div>
        `;
        return;
    }
    
    const lastDeployDate = new Date(siteInfo.lastDeploy).toLocaleString();
    
    currentSiteInfo.innerHTML = `
        <div class="mb-2">
            <strong>上次部署时间:</strong> ${lastDeployDate}
        </div>
        <div class="mb-2">
            <strong>仓库:</strong> ${siteInfo.repoUrl}
        </div>
        <div class="mb-2">
            <strong>分支:</strong> ${siteInfo.branch}
        </div>
        <div class="mb-2">
            <strong>作品数量:</strong> ${siteInfo.artifactCount}
        </div>
        <div class="mt-3">
            <a href="${siteInfo.url}" target="_blank" class="site-preview-link">
                <i class="bi bi-box-arrow-up-right"></i> 访问站点
            </a>
        </div>
    `;
}

// 渲染制品卡片
function renderArtifactCards() {
    if (!artifacts || artifacts.length === 0) {
        artifactsContainer.innerHTML = `
            <div class="col-12 text-center py-5">
                <p class="text-muted">暂无制品，请先创建炼丹任务</p>
            </div>
        `;
        return;
    }
    
    let cardsHtml = '';
    
    artifacts.forEach((artifact, index) => {
        // 检查是否已被选择
        const isSelected = selectedArtifacts.some(item => item.alchemyId === artifact.alchemyId);
        
        // 截断过长的查询文本
        const queryText = artifact.query.length > 80 
            ? artifact.query.substring(0, 80) + '...' 
            : artifact.query;
            
        // 格式化时间戳
        const date = new Date(artifact.timestamp);
        const formattedDate = `${date.getFullYear()}-${(date.getMonth()+1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
        
        // 生成预览图URL - 优先使用screenshot字段，如果不存在则使用默认图片
        const previewImgUrl = artifact.screenshot 
            ? `/api/artifacts/${artifact.alchemyDir}/${artifact.screenshot}`
            : "https://images.unsplash.com/photo-1581291518633-83b4ebd1d83e?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400&q=80";
        
        cardsHtml += `
        <div class="col-12 col-sm-6 col-md-6 col-lg-4">
            <div class="card h-100 ${isSelected ? 'card-selected' : ''}">
                <input type="checkbox" class="artifact-checkbox" 
                       data-alchemy-id="${artifact.alchemyId}" 
                       ${isSelected ? 'checked' : ''}>
                <div class="card-img-container">
                    <img src="${previewImgUrl}" alt="制品预览" class="card-img" loading="lazy">
                </div>
                <div class="card-body">
                    <h5 class="card-title">炼丹 #${artifact.alchemyId}</h5>
                    <p class="card-text">${queryText}</p>
                    <p class="card-text text-muted small">迭代: ${artifact.iteration} | 创建于: ${formattedDate}</p>
                </div>
                <div class="card-footer bg-white border-top-0 d-flex justify-content-between align-items-center">
                    <a href="${artifact.relativePath}" class="btn btn-outline-primary btn-sm" target="_blank">预览</a>
                    <button class="btn ${isSelected ? 'btn-danger' : 'btn-primary'} btn-sm select-artifact-btn" 
                            data-index="${index}">
                        ${isSelected ? '取消选择' : '选择'}
                    </button>
                </div>
            </div>
        </div>
        `;
    });
    
    artifactsContainer.innerHTML = cardsHtml;
    
    // 添加卡片选择事件监听
    document.querySelectorAll('.select-artifact-btn').forEach(button => {
        button.addEventListener('click', function() {
            const index = parseInt(this.getAttribute('data-index'));
            toggleArtifactSelection(index);
        });
    });
    
    // 添加复选框事件监听
    document.querySelectorAll('.artifact-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const alchemyId = this.getAttribute('data-alchemy-id');
            const artifact = artifacts.find(item => item.alchemyId === alchemyId);
            const index = artifacts.indexOf(artifact);
            
            if (index !== -1) {
                toggleArtifactSelection(index);
            }
        });
    });
    
    // 更新选择计数
    updateSelectionCount();
}

// 切换制品选择状态
function toggleArtifactSelection(index) {
    const artifact = artifacts[index];
    const alreadySelectedIndex = selectedArtifacts.findIndex(item => item.alchemyId === artifact.alchemyId);
    
    if (alreadySelectedIndex === -1) {
        // 添加到选择列表
        selectedArtifacts.push(artifact);
    } else {
        // 从选择列表中移除
        selectedArtifacts.splice(alreadySelectedIndex, 1);
    }
    
    // 重新渲染卡片
    renderArtifactCards();
    
    // 更新选择计数
    updateSelectionCount();
}

// 更新选择计数
function updateSelectionCount() {
    const count = selectedArtifacts.length;
    selectedCountElement.textContent = count;
    
    if (count > 0) {
        deployActions.classList.remove('hidden');
    } else {
        deployActions.classList.add('hidden');
    }
}

// 清除所有选择
function clearSelection() {
    selectedArtifacts = [];
    renderArtifactCards();
    updateSelectionCount();
}

// 向日志添加内容
function appendToLog(message) {
    // 显示日志区域
    deployLog.style.display = 'block';
    
    // 添加时间戳
    const now = new Date();
    const timestamp = `[${now.toLocaleTimeString()}] `;
    
    // 将消息添加到日志
    logContent.textContent += timestamp + message + '\n';
    
    // 滚动到底部
    logContent.scrollTop = logContent.scrollHeight;
}

// 显示通知
function showNotification(title, message) {
    // 检查浏览器是否支持通知
    if ('Notification' in window) {
        // 请求通知权限
        Notification.requestPermission().then(permission => {
            if (permission === 'granted') {
                new Notification(title, {
                    body: message,
                    icon: '/favicon.ico'
                });
            }
        });
    }
}

// 生成部署文件
function generateDeployFiles() {
    if (selectedArtifacts.length === 0) {
        alert('请先选择要部署的作品');
        return;
    }
    
    // 显示日志区域
    deployLog.style.display = 'block';
    logContent.textContent = '';
    appendToLog('开始生成部署文件...');
    
    // 发送请求到服务器
    socket.emit('deploy:generateFiles', {
        artifacts: selectedArtifacts
    });
    
    // 保存配置
    saveConfig();
}

// 部署到GitHub
function deployToGitHub() {
    const repoUrl = document.getElementById('repo-url').value.trim();
    const branch = document.getElementById('branch').value.trim();
    const commitMessage = document.getElementById('commit-message').value.trim();
    const githubToken = document.getElementById('github-token').value.trim();
    
    if (!repoUrl) {
        alert('请输入GitHub仓库地址');
        return;
    }
    
    if (!branch) {
        alert('请输入部署分支');
        return;
    }
    
    // 显示日志区域
    deployLog.style.display = 'block';
    logContent.textContent = '';
    appendToLog('开始部署到GitHub Pages...');
    
    // 发送部署请求到服务器
    socket.emit('deploy:toGitHub', {
        repoUrl,
        branch,
        commitMessage: commitMessage || `更新网站内容 - ${new Date().toLocaleString()}`,
        token: githubToken
    });
    
    // 保存配置
    saveConfig();
} 