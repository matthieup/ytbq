let ws;
let userName = null;
let userId = null;

function init() {
    loadUser();
    if (userName) {
        showMainScreen();
        setupSearch();
        connectWebSocket();
    } else {
        showNameScreen();
    }
}

function loadUser() {
    userName = localStorage.getItem('ytbq_user_name');
    userId = localStorage.getItem('ytbq_user_id');
    if (!userId) {
        userId = generateUserId();
        localStorage.setItem('ytbq_user_id', userId);
    }
}

function generateUserId() {
    return 'user_' + Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
}

function showNameScreen() {
    document.getElementById('nameScreen').style.display = 'flex';
    document.getElementById('mainScreen').style.display = 'none';
    
    const nameForm = document.getElementById('nameForm');
    nameForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const name = document.getElementById('nameInput').value.trim();
        if (name) {
            userName = name;
            localStorage.setItem('ytbq_user_name', userName);
            showMainScreen();
            setupSearch();
            connectWebSocket();
        }
    });
}

function showMainScreen() {
    document.getElementById('nameScreen').style.display = 'none';
    document.getElementById('mainScreen').style.display = 'block';
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === 'state') {
            updateQueueUI(message.data);
        }
    };

    ws.onclose = () => {
        setTimeout(connectWebSocket, 3000);
    };
}

function updateQueueUI(state) {
    const countEl = document.getElementById('queueCount');
    const queueList = document.getElementById('guestQueueList');
    const count = state.items ? state.items.length : 0;
    countEl.textContent = count;

    if (state.items && state.items.length > 0) {
        queueList.innerHTML = state.items.map(item => `
            <div class="guest-queue-item">
                <img class="guest-queue-item-thumb" src="${item.thumbnail}" alt="${escapeHtml(item.title)}">
                <div class="guest-queue-item-info">
                    <div class="guest-queue-item-title">${escapeHtml(item.title)}</div>
                    ${item.added_by ? `<div class="guest-queue-item-added-by">Added by <span>${escapeHtml(item.added_by)}</span></div>` : ''}
                </div>
            </div>
        `).join('');
    } else {
        queueList.innerHTML = '<div class="empty-queue"><p>No videos in queue</p></div>';
    }
}

function setupSearch() {
    const form = document.getElementById('searchForm');
    const input = document.getElementById('searchInput');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = input.value.trim();
        if (query) {
            await searchVideos(query);
        }
    });
}

async function searchVideos(query) {
    const resultsList = document.getElementById('resultsList');
    resultsList.innerHTML = '<div class="loading"></div>';

    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const videos = await response.json();

        if (videos.length === 0) {
            resultsList.innerHTML = '<div class="empty-queue"><p>No videos found</p></div>';
            return;
        }

        resultsList.innerHTML = videos.map(video => `
            <div class="result-item" data-id="${video.id}" onclick="addToQueue('${video.id}', '${escapeHtml(video.title)}', '${video.thumbnail}', '${escapeHtml(video.channel || '')}')">
                <div class="result-thumb">
                    <img src="${video.thumbnail}" alt="${escapeHtml(video.title)}">
                    ${video.duration ? `<span class="result-duration">${video.duration}</span>` : ''}
                </div>
                <div class="result-info">
                    <div class="result-title">${escapeHtml(video.title)}</div>
                    <div class="result-channel">${escapeHtml(video.channel || '')}</div>
                </div>
                <div class="result-add-icon">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
                    </svg>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Search error:', error);
        resultsList.innerHTML = '<div class="empty-queue"><p>Search failed. Try again.</p></div>';
    }
}

async function addToQueue(id, title, thumbnail, channel) {
    const item = document.querySelector(`.result-item[data-id="${id}"]`);
    if (item.classList.contains('added')) return;

    try {
        const response = await fetch('/api/queue', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                id: id,
                title: title,
                thumbnail: thumbnail,
                channel: channel,
                added_by: userName,
                user_id: userId,
            }),
        });

        const data = await response.json();

        if (data.success) {
            item.classList.add('added');
            showToast(`Added: ${title}`, 'success');
        } else if (data.error) {
            showToast(data.error, 'error');
        } else {
            showToast('Failed to add video', 'error');
        }
    } catch (error) {
        console.error('Add to queue error:', error);
        showToast('Failed to add video', 'error');
    }
}

function showToast(message, type = 'info') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.remove(), 3000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', init);
