// 连接Socket.IO
const socket = io();

// 全局变量
let artifacts = [];
let selectedArtifacts = [];
let siteInfo = null;
let deployedArtifactIds = []; // 存储已部署的作品ID
let currentFilter = null; // 当前筛选的炼丹ID

// DOM元素
const artifactsContainer = document.getElementById('artifacts-container');
const alchemyList = document.getElementById('alchemy-list');
const deployActions = document.getElementById('deploy-actions');
const selectedCountElement = document.getElementById('selected-count');
const currentSiteInfo = document.getElementById('current-site-info');
const deployLog = document.getElementById('deploy-log');
const logContent = document.getElementById('log-content');

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', function() {
    // 初始化移动端菜单
    initMobileMenu();
    
    // 请求当前站点信息
    socket.emit('deploy:requestSiteInfo');
    
    // 请求已部署的制品数据
    socket.emit('deploy:requestDeployedArtifacts');
    
    // 请求最新的制品数据
    socket.emit('deploy:requestArtifacts');
    showLoadingIndicator();
    
    // 添加按钮事件监听
    document.getElementById('cancel-selection').addEventListener('click', function() {
        clearSelection();
    });
    
    document.getElementById('confirm-selection').addEventListener('click', function() {
        if (selectedArtifacts.length > 0) {
            // 滚动到配置部分
            document.querySelector('.deploy-panel').scrollIntoView({ behavior: 'smooth' });
            
            // 设置一个短暂的延迟，确保滚动完成后才设置焦点
            setTimeout(() => {
                // 将焦点设置到"生成部署文件"按钮
                document.getElementById('generate-files-btn').focus();
            }, 500);
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
    
    // 根据已部署的作品ID自动选择
    selectDeployedArtifacts();
    
    // 渲染左侧一览列表
    renderAlchemyList();
    
    // 渲染卡片
    renderArtifactCards();
});

// 渲染左侧炼丹ID一览列表
function renderAlchemyList() {
    if (!artifacts || artifacts.length === 0) {
        alchemyList.innerHTML = `
            <div class="text-center py-3">
                <p class="text-muted">暂无作品</p>
            </div>
        `;
        return;
    }
    
    // 提取唯一的炼丹ID并计算每个ID下有多少个制品
    const alchemyIds = {};
    artifacts.forEach(artifact => {
        if (!alchemyIds[artifact.alchemyId]) {
            alchemyIds[artifact.alchemyId] = 1;
        } else {
            alchemyIds[artifact.alchemyId]++;
        }
    });
    
    // 构建HTML
    let listHtml = `
        <button class="all-artifacts-btn ${currentFilter === null ? 'active' : ''}" id="show-all-artifacts">
            显示全部作品
        </button>
        <div class="list-group">
    `;
    
    // 按照ID排序
    const sortedIds = Object.keys(alchemyIds).sort((a, b) => {
        // 如果是纯数字，则按数字排序
        const numA = parseInt(a, 10);
        const numB = parseInt(b, 10);
        if (!isNaN(numA) && !isNaN(numB)) {
            return numA - numB;
        }
        // 否则按字符串排序
        return a.localeCompare(b);
    });
    
    // 生成列表项
    sortedIds.forEach(id => {
        listHtml += `
            <div class="alchemy-item ${currentFilter === id ? 'active' : ''}" data-alchemy-id="${id}">
                <span class="alchemy-item-title">#${id}</span>
                <span class="badge">${alchemyIds[id]}</span>
            </div>
        `;
    });
    
    listHtml += `</div>`;
    alchemyList.innerHTML = listHtml;
    
    // 添加点击事件
    document.getElementById('show-all-artifacts').addEventListener('click', function() {
        currentFilter = null;
        this.classList.add('active');
        document.querySelectorAll('.alchemy-item').forEach(item => {
            item.classList.remove('active');
        });
        renderArtifactCards();
    });
    
    document.querySelectorAll('.alchemy-item').forEach(item => {
        item.addEventListener('click', function() {
            const alchemyId = this.getAttribute('data-alchemy-id');
            
            // 更新选中状态
            document.querySelectorAll('.alchemy-item').forEach(i => {
                i.classList.remove('active');
            });
            document.getElementById('show-all-artifacts').classList.remove('active');
            this.classList.add('active');
            
            // 设置过滤器并重新渲染
            currentFilter = alchemyId;
            renderArtifactCards();
        });
    });
}

// 监听站点信息更新
socket.on('deploy:siteInfo', function(data) {
    siteInfo = data;
    renderSiteInfo();
    
    // 如果站点信息中包含repoUrl，则自动填充表单
    if (siteInfo && siteInfo.repoUrl && siteInfo.repoUrl !== '未部署' && siteInfo.repoUrl !== '尚未部署') {
        document.getElementById('repo-url').value = siteInfo.repoUrl;
        document.getElementById('branch').value = siteInfo.branch || 'gh-pages';
        
        // 保存配置到localStorage
        saveConfig();
    }
});

// 监听已部署的作品数据
socket.on('deploy:deployedArtifacts', function(data) {
    if (data && Array.isArray(data)) {
        // 不再只存储alchemyId，而是存储完整的部署作品信息
        deployedArtifactIds = data;
        console.log('已部署的作品:', deployedArtifactIds);
        
        // 如果制品数据已加载，自动选择已部署的作品
        if (artifacts.length > 0) {
            selectDeployedArtifacts();
            renderArtifactCards();
        }
    }
});

// 自动选择已部署的作品
function selectDeployedArtifacts() {
    // 清除当前选择
    selectedArtifacts = [];
    
    // 遍历当前制品列表，自动选中已部署的作品
    for (let i = 0; i < artifacts.length; i++) {
        const artifact = artifacts[i];
        
        // 检查制品的alchemyId和iteration是否与已部署的制品匹配
        const isDeployed = deployedArtifactIds.some(deployedArtifact => 
            deployedArtifact.alchemyId === artifact.alchemyId && 
            deployedArtifact.iteration === artifact.iteration
        );
        
        if (isDeployed) {
            selectedArtifacts.push(artifact);
        }
    }
    
    // 更新选择计数
    updateSelectionCount();
    
    console.log(`自动选择了 ${selectedArtifacts.length} 个已部署的作品`);
}

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
        
        // 重新获取已部署的作品列表
        socket.emit('deploy:requestDeployedArtifacts');
    } else {
        appendToLog(`\n❌ 部署失败: ${result.error}`);
    }
});

// 监听生成文件完成事件
socket.on('deploy:filesGenerated', function(result) {
    if (result.success) {
        appendToLog(`\n✅ 文件生成成功！\n共选择了 ${result.artifactCount} 个作品，保存到 ${result.path}`);
        showNotification('文件生成成功', '现在可以部署到GitHub Pages了');
        
        // 重新获取已部署的作品列表
        socket.emit('deploy:requestDeployedArtifacts');
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
    
    // 根据当前过滤器筛选要显示的制品
    let filteredArtifacts = artifacts;
    if (currentFilter !== null) {
        filteredArtifacts = artifacts.filter(artifact => artifact.alchemyId === currentFilter);
    }
    
    if (filteredArtifacts.length === 0) {
        artifactsContainer.innerHTML = `
            <div class="col-12 text-center py-5">
                <p class="text-muted">没有符合筛选条件的制品</p>
            </div>
        `;
        return;
    }
    
    let cardsHtml = '';
    
    filteredArtifacts.forEach((artifact, index) => {
        // 创建唯一标识符
        const uniqueId = `${artifact.alchemyId}_${artifact.iteration}`;
        
        // 检查是否已被选择
        const isSelected = selectedArtifacts.some(item => 
            `${item.alchemyId}_${item.iteration}` === uniqueId
        );
        
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
        <div class="col-12 col-sm-6 col-md-12 col-lg-6">
            <div class="card h-100 ${isSelected ? 'card-selected' : ''}">
                <input type="checkbox" class="artifact-checkbox" 
                       data-alchemy-id="${artifact.alchemyId}"
                       data-iteration="${artifact.iteration}"
                       ${isSelected ? 'checked' : ''}>
                <div class="card-img-container">
                    <img src="${previewImgUrl}" alt="制品预览" class="card-img" loading="lazy">
                </div>
                <div class="card-body">
                    <p class="card-text">${queryText}</p>
                    <p class="card-text text-muted small">迭代: ${artifact.iteration} | 创建于: ${formattedDate}</p>
                    <div class="text-end mb-2">
                        <span class="badge bg-light text-secondary">#${artifact.alchemyId}</span>
                    </div>
                </div>
                <div class="card-footer bg-white border-top-0 d-flex justify-content-between align-items-center">
                    <a href="${artifact.relativePath}" class="btn btn-outline-primary btn-sm" target="_blank">预览</a>
                    <button class="btn ${isSelected ? 'btn-danger' : 'btn-primary'} btn-sm select-artifact-btn" 
                            data-index="${artifacts.indexOf(artifact)}">
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
    
    // 修改复选框事件监听
    document.querySelectorAll('.artifact-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const alchemyId = this.getAttribute('data-alchemy-id');
            const iteration = parseInt(this.getAttribute('data-iteration'));
            
            // 根据alchemyId和iteration找到对应的制品
            const index = artifacts.findIndex(item => 
                item.alchemyId === alchemyId && item.iteration === iteration
            );
            
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
    // 使用唯一标识符来识别每个制品，组合alchemyId和iteration
    const uniqueId = `${artifact.alchemyId}_${artifact.iteration}`;
    
    // 查找是否已经选择了这个制品
    const alreadySelectedIndex = selectedArtifacts.findIndex(item => 
        `${item.alchemyId}_${item.iteration}` === uniqueId
    );
    
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
        // 只在小屏幕设备上显示浮动操作栏
        if (window.innerWidth < 768) {
            deployActions.classList.remove('hidden');
        } else {
            deployActions.classList.add('hidden');
        }
    } else {
        deployActions.classList.add('hidden');
    }
}

// 添加窗口大小变化监听，以便动态调整浮动栏的显示
window.addEventListener('resize', function() {
    updateSelectionCount();
});

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