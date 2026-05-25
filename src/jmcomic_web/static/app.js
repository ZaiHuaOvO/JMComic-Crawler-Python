const API = '';

const state = {
  runId: null,
  runTimer: null,
  historyPage: 1,
  historyKeyword: '',
};

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(text) {
  return String(text ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

async function apiGet(url) {
  const resp = await fetch(url, { headers: { 'Accept': 'application/json' } });
  const data = await resp.json();
  if (!resp.ok || data.success === false) {
    throw new Error(data.error || `HTTP ${resp.status}`);
  }
  return data.data;
}

async function apiPost(url, body) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(body ?? {}),
  });
  const data = await resp.json();
  if (!resp.ok || data.success === false) {
    throw new Error(data.error || `HTTP ${resp.status}`);
  }
  return data.data;
}

function setBadge(text, tone = '') {
  const badge = $('healthBadge');
  if (!badge) return;
  badge.textContent = text;
  badge.className = `badge ${tone}`.trim();
}

function formatTags(record) {
  const raw = Array.isArray(record.raw_tags) ? record.raw_tags : [];
  const trans = Array.isArray(record.translated_tags) ? record.translated_tags : [];
  if (!raw.length && !trans.length) return '—';
  const source = raw.length ? raw : trans;
  return source.map((item) => escapeHtml(item)).join(', ');
}

function renderRun(runSnapshot) {
  if (!$('runSummary')) return;

  if (!runSnapshot || !runSnapshot.run) {
    $('runSummary').textContent = '尚无任务';
    $('runSummary').classList.add('empty');
    $('runProgress').classList.add('hidden');
    $('runItems').innerHTML = '';
    $('runLogs').innerHTML = '';
    return;
  }

  const run = runSnapshot.run;
  $('runSummary').classList.remove('empty');
  $('runSummary').innerHTML = `
    <div><strong>Run:</strong> ${escapeHtml(run.run_id)}</div>
    <div class="item-meta">状态：${escapeHtml(run.status)} | 完成：${run.completed_count}/${run.total_count} | 成功：${run.success_count} | 失败：${run.failed_count}</div>
  `;

  $('runProgress').classList.remove('hidden');
  const percent = typeof run.progress_percent === 'number' ? run.progress_percent : (run.total_count > 0 ? Math.round((run.completed_count / run.total_count) * 100) : 100);
  $('runProgressBar').style.width = `${Math.min(percent, 100)}%`;
  $('runProgressText').textContent = `${percent}% · ${run.completed_count}/${run.total_count}，成功 ${run.success_count}，失败 ${run.failed_count}`;

  const itemsHtml = (runSnapshot.items || []).map((item) => {
    const status = item.status || 'pending';
    const statusClass = ['success', 'failed', 'running'].includes(status) ? status : '';
    const transName = item.translated_name ? escapeHtml(item.translated_name) : '—';
    const err = item.error ? `<div class="item-subtitle">错误：${escapeHtml(item.error)}</div>` : '';
    return `
      <div class="item-card">
        <div class="item-card-head">
          <div>
            <div class="item-title">${escapeHtml(item.album_id)} · ${escapeHtml(item.original_name || '未获取标题')}</div>
            <div class="item-subtitle">${transName}</div>
          </div>
          <div class="item-status ${statusClass}">${escapeHtml(status)}</div>
        </div>
        <div class="item-meta">进度：${item.progress || 0}% | 章节：${item.completed_photos || 0}/${item.total_photos || 0}</div>
        ${err}
      </div>
    `;
  }).join('');
  $('runItems').innerHTML = itemsHtml || '<div class="summary empty">暂无任务明细</div>';

  const logsHtml = (runSnapshot.logs || []).map((log) => `
    <div class="log-line">[${escapeHtml(log.created_at)}] [${escapeHtml(log.level)}] ${escapeHtml(log.album_id || 'system')} - ${escapeHtml(log.message)}</div>
  `).join('');
  $('runLogs').innerHTML = logsHtml || '<div class="log-line">暂无日志</div>';
}

async function refreshCurrentRun() {
  if (!state.runId) {
    const params = new URLSearchParams(location.search);
    state.runId = params.get('run_id');
  }

  if (!state.runId) {
    renderRun(null);
    return;
  }

  const snapshot = await apiGet(`${API}/api/runs/${encodeURIComponent(state.runId)}`);
  renderRun(snapshot);
}

async function startDownload() {
  const ids = $('idsInput').value;
  const translateEnabled = $('translateToggle').checked;
  const translateProvider = $('translateProvider').value;
  const translateTargetLang = $('translateTargetLang').value;
  const startBtn = $('startBtn');
  startBtn.disabled = true;
  startBtn.textContent = '提交中...';
  try {
    const run = await apiPost('/api/downloads/batch', {
      ids,
      translate_enabled: translateEnabled,
      translate_provider: translateProvider,
      translate_target_lang: translateTargetLang,
    });
    state.runId = run.run_id;
    history.pushState({}, '', `/?run_id=${encodeURIComponent(run.run_id)}`);
    await refreshCurrentRun();
    startPolling();
  } catch (err) {
    alert(err.message || String(err));
  } finally {
    startBtn.disabled = false;
    startBtn.textContent = '开始下载';
  }
}

function startPolling() {
  if (state.runTimer) {
    clearInterval(state.runTimer);
  }
  state.runTimer = setInterval(() => {
    if (state.runId) {
      refreshCurrentRun().catch((err) => console.error(err));
    }
  }, 2000);
}

function stopPolling() {
  if (state.runTimer) {
    clearInterval(state.runTimer);
    state.runTimer = null;
  }
}

async function loadHistory(page = state.historyPage) {
  state.historyPage = page;
  const keyword = state.historyKeyword || '';
  const data = await apiGet(`/api/downloads?page=${encodeURIComponent(page)}&page_size=20&keyword=${encodeURIComponent(keyword)}`);
  const rows = data.items || [];
  const tbody = $('historyBody');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="item-meta">暂无记录</td></tr>';
    renderPager(data.total || 0, data.page || 1, data.page_size || 20);
    return;
  }

  tbody.innerHTML = rows.map((record) => {
    const statusClass = ['success', 'failed', 'running', 'skipped'].includes(record.latest_status) ? record.latest_status : '';
    return `
      <tr>
        <td>${escapeHtml(record.album_id)}</td>
        <td>${escapeHtml(record.original_name || '—')}</td>
        <td>${escapeHtml(record.translated_name || '—')}</td>
        <td>${formatTags(record)}</td>
        <td>${escapeHtml(record.download_time || '—')}</td>
        <td><span class="status-pill ${statusClass}">${escapeHtml(record.latest_status || 'pending')}</span></td>
        <td>
          <div class="action-row">
            <button class="button ghost" type="button" data-cover="${escapeHtml(record.album_id)}">查看封面</button>
            <button class="button primary" type="button" data-redownload="${escapeHtml(record.album_id)}">重新下载</button>
          </div>
        </td>
      </tr>
    `;
  }).join('') || '<tr><td colspan="7" class="item-meta">暂无记录</td></tr>';

  renderPager(data.total || 0, data.page || 1, data.page_size || 20);
}

function renderPager(total, page, pageSize) {
  const pager = $('historyPager');
  const safePageSize = Math.max(Number(pageSize) || 1, 1);
  const totalPages = Math.max(1, Math.ceil(total / safePageSize));
  pager.innerHTML = `
    <span class="item-meta">共 ${total} 条，${page}/${totalPages} 页</span>
    <button class="button ghost" ${page <= 1 ? 'disabled' : ''} id="prevPageBtn">上一页</button>
    <button class="button ghost" ${page >= totalPages ? 'disabled' : ''} id="nextPageBtn">下一页</button>
  `;
  const prev = $('prevPageBtn');
  const next = $('nextPageBtn');
  if (prev) prev.onclick = () => loadHistory(page - 1).catch((err) => alert(err.message || String(err)));
  if (next) next.onclick = () => loadHistory(page + 1).catch((err) => alert(err.message || String(err)));
}

async function openCover(albumId) {
  const dialog = $('coverDialog');
  const img = $('coverImage');
  const title = $('coverTitle');
  title.textContent = `封面预览 · ${albumId}`;
  img.src = `/api/downloads/${encodeURIComponent(albumId)}/cover?t=${Date.now()}`;
  if (dialog.showModal) {
    dialog.showModal();
  } else {
    dialog.setAttribute('open', 'open');
  }
}

function bindCoverClose() {
  const dialog = $('coverDialog');
  const closeBtn = $('coverCloseBtn');
  const close = () => {
    if (dialog.close) {
      dialog.close();
    } else {
      dialog.removeAttribute('open');
    }
  };
  if (closeBtn) closeBtn.onclick = close;
  if (dialog) dialog.addEventListener('click', (event) => {
    if (event.target === dialog) close();
  });
}

function bindIndexPage(config) {
  $('startBtn').onclick = () => startDownload();
  $('refreshRunBtn').onclick = () => refreshCurrentRun().catch((err) => alert(err.message || String(err)));
  $('translateToggle').checked = Boolean(config && config.translate_enabled);
  $('translateProvider').value = (config && config.translate_provider) || 'google';
  const targetLang = $('translateTargetLang');
  if (targetLang) targetLang.value = (config && config.translate_target_lang) || 'zh-CN';
  bindCoverClose();
}

function bindHistoryPage() {
  $('historySearchBtn').onclick = () => {
    state.historyKeyword = $('historyKeyword').value.trim();
    loadHistory(1).catch((err) => alert(err.message || String(err)));
  };
  $('historyReloadBtn').onclick = () => loadHistory(state.historyPage).catch((err) => alert(err.message || String(err)));
  $('historyBody').addEventListener('click', async (event) => {
    const coverBtn = event.target.closest('[data-cover]');
    if (coverBtn) {
      await openCover(coverBtn.getAttribute('data-cover'));
      return;
    }

    const redownloadBtn = event.target.closest('[data-redownload]');
    if (redownloadBtn) {
      const albumId = redownloadBtn.getAttribute('data-redownload');
      try {
        const run = await apiPost(`/api/downloads/${encodeURIComponent(albumId)}/redownload`, {});
        location.href = `/?run_id=${encodeURIComponent(run.run_id)}`;
      } catch (err) {
        alert(err.message || String(err));
      }
    }
  });
  bindCoverClose();
  loadHistory().catch((err) => alert(err.message || String(err)));
}

async function initHealth() {
  try {
    const data = await apiGet('/api/health');
    setBadge(data.title || '可用', '');
  } catch (err) {
    setBadge('不可用', 'danger');
  }
}

async function initPage() {
  await initHealth();
  const page = document.body.dataset.page;
  if (page === 'index') {
    const config = await apiGet('/api/config').catch(() => null);
    bindIndexPage(config || {});
    await refreshCurrentRun();
    startPolling();
  } else if (page === 'history') {
    bindHistoryPage();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initPage().catch((err) => {
    console.error(err);
    alert(err.message || String(err));
  });
});
