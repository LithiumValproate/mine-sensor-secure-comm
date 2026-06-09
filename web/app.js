let lastPayload = null;
let latestLogDetails = new Map();

document.addEventListener('DOMContentLoaded', function() {
    refreshDashboard();
    setInterval(refreshDashboard, 2000);

    document.getElementById('refresh-btn').addEventListener('click', function() {
        refreshDashboard();
    });

    document.getElementById('run-test-btn').addEventListener('click', function() {
        updateTestResults(lastPayload);
    });
});

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatDuration(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = Math.floor(totalSeconds % 60);
    return [hours, minutes, seconds]
        .map((value) => String(value).padStart(2, '0'))
        .join(':');
}

function statusLabel(status) {
    const labels = {
        online: '在线',
        running: '运行中',
        offline: '离线',
        stopped: '已停止',
        unknown: '未知',
    };
    return labels[status] || status || '未知';
}

function componentStatus(payload, kind) {
    const components = payload?.components || [];
    const matches = components.filter((component) => component.kind === kind);
    if (!matches.length) {
        return 'unknown';
    }
    return matches.some((component) => component.running) ? 'running' : 'stopped';
}

function setStatus(elementId, status) {
    const element = document.getElementById(elementId);
    const isOnline = ['online', 'running'].includes(status);
    element.textContent = statusLabel(status);
    element.className = `value ${isOnline ? 'status-online' : 'status-offline'}`;
}

function chooseSensor(sensors, matcher) {
    return sensors.find((sensor) => {
        const sensorType = String(sensor.sensor_type || '').toLowerCase();
        const unit = String(sensor.unit || '').toLowerCase();
        return matcher(sensorType, unit);
    });
}

function updateTemperature(sensor) {
    const value = Number(sensor?.value);
    if (!Number.isFinite(value)) {
        document.getElementById('temp-value').textContent = '--';
        document.getElementById('temp-fill').style.width = '0%';
        return;
    }

    document.getElementById('temp-value').textContent = value.toFixed(1);
    const percentage = ((value - 15) / 20) * 100;
    document.getElementById('temp-fill').style.width = `${Math.min(100, Math.max(0, percentage))}%`;
}

function updateGas(sensor) {
    const value = Number(sensor?.value);
    const gasValueElement = document.getElementById('gas-value');
    const gasWarningElement = document.getElementById('gas-warning');
    const gasProgressElement = document.getElementById('gas-progress');

    if (!Number.isFinite(value)) {
        gasValueElement.textContent = '--';
        gasValueElement.className = 'gas-value';
        gasWarningElement.textContent = '';
        gasWarningElement.classList.remove('show');
        gasProgressElement.style.width = '0%';
        return;
    }

    gasValueElement.textContent = value.toFixed(4);
    gasValueElement.className = 'gas-value';

    const thresholds = sensor.thresholds || {};
    const warning = Number(thresholds.warning ?? 0.7);
    const critical = Number(thresholds.critical ?? 1.0);
    if (value >= critical) {
        gasValueElement.classList.add('danger');
        gasWarningElement.textContent = '瓦斯浓度达到 critical 阈值';
        gasWarningElement.classList.add('show');
    } else if (value >= warning) {
        gasValueElement.classList.add('warning');
        gasWarningElement.textContent = '瓦斯浓度达到 warning 阈值';
        gasWarningElement.classList.add('show');
    } else {
        gasValueElement.classList.add('normal');
        gasWarningElement.textContent = '';
        gasWarningElement.classList.remove('show');
    }

    const maxValue = Math.max(critical * 2, 1);
    const percentage = (value / maxValue) * 100;
    gasProgressElement.style.width = `${Math.min(100, Math.max(0, percentage))}%`;
}

function renderSensors(sensors) {
    const container = document.getElementById('sensors-list');
    document.getElementById('sensor-count').textContent = sensors.length;

    if (!sensors.length) {
        container.innerHTML = '<div class="sensors-empty">配置里没有传感器</div>';
        return;
    }

    container.innerHTML = sensors
        .map((sensor) => {
            const status = sensor.status || 'unknown';
            const isOnline = ['online', 'running'].includes(status);
            const statusColor = isOnline ? '#10b981' : '#ef4444';
            const value = sensor.value === undefined || sensor.value === null
                ? '--'
                : `${escapeHtml(sensor.value)}${escapeHtml(sensor.unit || '')}`;
            return `
                <div class="sensor-item ${isOnline ? 'online' : 'offline'}" data-id="${escapeHtml(sensor.sensor_id)}">
                    <div class="sensor-info">
                        <div class="sensor-id">${escapeHtml(sensor.sensor_id)}</div>
                        <div class="sensor-location">${escapeHtml(sensor.location || '未配置位置')}</div>
                    </div>
                    <div class="sensor-data">
                        <div class="sensor-temp">${value}</div>
                        <div class="sensor-gas">电量 ${escapeHtml(sensor.battery ?? '--')}%</div>
                        <div class="sensor-status" style="color: ${statusColor}">${statusLabel(status)}</div>
                    </div>
                </div>
            `;
        })
        .join('');
}

function logTypeFromEntry(entry) {
    const line = String(entry.line || '').toLowerCase();
    if (line.includes('critical') || line.includes('error') || line.includes('exceeded')) {
        return 'danger';
    }
    if (line.includes('warning') || line.includes('warn')) {
        return 'warning';
    }
    return 'normal';
}

function renderLogs(logs, alerts) {
    const container = document.getElementById('log-container');
    const rows = [
        ...alerts.map((alert) => ({
            timeStr: alert.ts,
            dateStr: new Date().toLocaleDateString('zh-CN'),
            content: `${alert.sensor_id}: ${alert.message || alert.code}`,
            type: alert.severity === 'high' ? 'danger' : 'warning',
        })),
        ...logs.map((entry) => ({
            timeStr: entry.ts,
            dateStr: new Date().toLocaleDateString('zh-CN'),
            content: `[${entry.source}] ${entry.line}`,
            type: logTypeFromEntry(entry),
        })),
    ].slice(-20).reverse();

    latestLogDetails = new Map();

    if (!rows.length) {
        container.innerHTML = '<div class="log-empty">暂无日志</div>';
        document.querySelector('.log-count').textContent = '0/20';
        return;
    }

    container.innerHTML = rows
        .map((row, index) => {
            const id = `log-${index}`;
            latestLogDetails.set(id, row);
            const className = row.type === 'danger' ? 'danger' : row.type === 'warning' ? 'warning' : '';
            return `
                <div class="log-item ${className}" data-id="${id}">
                    <div class="log-time">${escapeHtml(row.timeStr)}</div>
                    <div class="log-content">${escapeHtml(row.content)}</div>
                    <div class="log-click-hint">点击查看详情</div>
                </div>
            `;
        })
        .join('');

    for (const item of container.querySelectorAll('.log-item')) {
        item.addEventListener('click', function() {
            showLogDetail(latestLogDetails.get(item.dataset.id));
        });
    }

    document.querySelector('.log-count').textContent = `${rows.length}/20`;
}

function updateTestItem(elementId, result) {
    const element = document.getElementById(elementId);
    if (result === null) {
        element.textContent = '未知';
        element.className = 'test-value';
    } else if (result === true) {
        element.textContent = 'PASS';
        element.className = 'test-value pass';
    } else {
        element.textContent = 'FAIL';
        element.className = 'test-value fail';
    }
}

function updateTestResults(payload) {
    const button = document.getElementById('run-test-btn');
    const status = document.getElementById('test-status');

    if (!payload) {
        status.textContent = '尚未连接到后端';
        updateTestItem('test-encryption', false);
        updateTestItem('test-packing', false);
        updateTestItem('test-connection', false);
        updateTestItem('test-full-flow', false);
        return;
    }

    const sensors = payload.sensors || [];
    const components = payload.components || [];
    const hasConfig = Boolean(payload.config?.sensor_config && payload.config?.psk_config);
    const hasBroker = components.some((component) => component.kind === 'broker' && component.running);
    const hasCenter = components.some((component) => component.kind === 'center' && component.running);
    const hasSensorRuntime = components.some((component) => component.kind === 'sensor' && component.running);
    const hasReading = sensors.some((sensor) => sensor.value !== undefined && sensor.value !== null);

    updateTestItem('test-encryption', hasCenter || null);
    updateTestItem('test-packing', hasConfig);
    updateTestItem('test-connection', hasBroker && hasCenter);
    updateTestItem('test-full-flow', hasSensorRuntime && hasReading);

    const passed = [hasCenter || null, hasConfig, hasBroker && hasCenter, hasSensorRuntime && hasReading]
        .filter((item) => item === true)
        .length;
    status.textContent = `状态检查完成: ${passed}/4 通过`;
    button.disabled = false;
    document.getElementById('test-time').textContent = new Date().toLocaleTimeString('zh-CN');
}

async function refreshDashboard() {
    try {
        const response = await fetch('/api/status', { cache: 'no-store' });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const payload = await response.json();
        lastPayload = payload;
        const sensors = payload.sensors || [];
        const alerts = payload.alerts || [];
        const logs = payload.logs || [];
        const temperatureSensor = chooseSensor(sensors, (sensorType, unit) => sensorType.includes('temp') || unit === '°c');
        const gasSensor = chooseSensor(sensors, (sensorType, unit) => sensorType.includes('gas') || unit.includes('lel') || unit === '%');
        const sensorRunning = sensors.some((sensor) => ['online', 'running'].includes(sensor.status));

        document.querySelector('.status-text').textContent = '已连接后端';
        document.getElementById('last-update').textContent = new Date().toLocaleTimeString('zh-CN');
        document.getElementById('uptime').textContent = formatDuration(payload.uptime_seconds || 0);
        document.getElementById('seq-num').textContent = String(logs.length);

        setStatus('broker-status', componentStatus(payload, 'broker'));
        setStatus('center-status', componentStatus(payload, 'center'));
        setStatus('sensor-status', sensorRunning ? 'running' : componentStatus(payload, 'sensor'));
        updateTemperature(temperatureSensor);
        updateGas(gasSensor);
        renderSensors(sensors);
        renderLogs(logs, alerts);
        updateTestResults(payload);
    } catch (error) {
        lastPayload = null;
        document.querySelector('.status-text').textContent = '未连接后端';
        setStatus('broker-status', 'offline');
        setStatus('center-status', 'offline');
        setStatus('sensor-status', 'offline');
        document.getElementById('last-update').textContent = '--';
        document.getElementById('seq-num').textContent = '--';
        document.getElementById('sensors-list').innerHTML = `<div class="sensors-empty">${escapeHtml(error.message)}</div>`;
        document.getElementById('log-container').innerHTML = '<div class="log-empty">请通过 scripts/start_system.py --web 启动后端</div>';
        updateTemperature(null);
        updateGas(null);
        updateTestResults(null);
    }
}

function showLogDetail(log) {
    if (!log) {
        return;
    }

    let modal = document.getElementById('log-detail-modal');
    const bodyHtml = `
        <div class="detail-item">
            <span class="detail-label">日期</span>
            <span class="detail-value">${escapeHtml(log.dateStr)}</span>
        </div>
        <div class="detail-item">
            <span class="detail-label">时间</span>
            <span class="detail-value">${escapeHtml(log.timeStr)}</span>
        </div>
        <div class="detail-item">
            <span class="detail-label">类型</span>
            <span class="detail-value ${escapeHtml(log.type)}">${escapeHtml(log.type === 'danger' ? '危险告警' : log.type === 'warning' ? '警告' : '正常')}</span>
        </div>
        <div class="detail-item">
            <span class="detail-label">内容</span>
            <span class="detail-value content">${escapeHtml(log.content)}</span>
        </div>
    `;

    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'log-detail-modal';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h3>日志详情</h3>
                    <button class="modal-close" onclick="closeLogDetail()">&times;</button>
                </div>
                <div class="modal-body">${bodyHtml}</div>
                <div class="modal-footer">
                    <button class="btn btn-close" onclick="closeLogDetail()">关闭</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        modal.addEventListener('click', function(event) {
            if (event.target === modal) {
                closeLogDetail();
            }
        });
    } else {
        modal.querySelector('.modal-body').innerHTML = bodyHtml;
    }

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function closeLogDetail() {
    const modal = document.getElementById('log-detail-modal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
}
