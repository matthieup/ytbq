let player;
let ws;
let currentVideoId = null;
let currentQuality = null;
let allowMultipleVideos = true;
let autoQueueEnabled = false;
let cache = new Map();
let preloadingVideoId = null;
let lastPlayNextCall = 0;
let stallRecoveryTimeout = null;
let lastProgress = { time: 0, timestamp: 0 };
let stallCount = 0;
let maxStallRetries = 3;
let isPlaying = false;
let bufferCheckInterval = null;
let lowBufferCount = 0;
let maxLowBufferRetries = 2;

let isFullscreen = false;

function init() {
    fetch('/api/current/clear', { method: 'POST' });
    
    player = videojs('videoPlayer', {
        controls: true,
        autoplay: false,
        preload: 'auto',
        responsive: true,
        maintainAspectRatio: true,
        html5: {
            vhs: {
                overrideNative: true,
                enableLowInitialPlaylist: true,
                smoothQualityChange: true,
                fastQualityChange: true,
            },
            nativeAudioTracks: false,
            nativeVideoTracks: false,
        },
    });

    player.on('ended', function() {
        console.log('Video ended event fired for:', currentVideoId);
        if (currentVideoId) {
            fetch(`/api/cache/${currentVideoId}`, { method: 'DELETE' })
                .then(() => console.log('Cached video removed:', currentVideoId))
                .catch(err => console.error('Failed to remove cache:', err));
            
            fetch('/api/cache/cleanup', { method: 'POST' })
                .then(() => console.log('Cache cleanup triggered'))
                .catch(err => console.error('Cleanup failed:', err));
        }
        playNext();
    });
    
    let errorRetryCount = 0;
    let lastErrorVideoId = null;
    
    player.on('error', function(e) {
        const error = player.error();
        console.error('Video.js error:', error);
        
        if (error && (error.code === 3 || error.code === 4)) {
            if (lastErrorVideoId === currentVideoId) {
                errorRetryCount++;
            } else {
                errorRetryCount = 1;
                lastErrorVideoId = currentVideoId;
            }
            
            if (errorRetryCount <= 2) {
                console.log(`Retrying video due to ${error.code === 3 ? 'decode' : 'source'} error (attempt ${errorRetryCount})`);
                if (errorRetryCount === 1 && currentQuality !== 720) {
                    console.log('Falling back to 720p quality');
                    currentQuality = 720;
                    const qualitySelect = document.getElementById('qualitySelect');
                    if (qualitySelect) {
                        qualitySelect.value = '720';
                    }
                }
                setTimeout(() => reloadCurrentVideo(), 500);
            } else {
                console.log('Max retries reached for decode error, skipping to next');
                if (currentVideoId) {
                    fetch(`/api/cache/${currentVideoId}`, { method: 'DELETE' }).catch(() => {});
                }
                errorRetryCount = 0;
                lastErrorVideoId = null;
                currentVideoId = null;
                player.reset();
                setTimeout(() => playNext(), 500);
            }
        }
    });
    
    player.on('loadstart', function() {
        console.log('Load started for:', currentVideoId);
        stallCount = 0;
    });
    
    player.on('loadeddata', function() {
        console.log('Data loaded for:', currentVideoId);
    });
    
    player.on('playing', function() {
        console.log('Now playing:', currentVideoId);
        stallCount = 0;
        lowBufferCount = 0;
        clearStallRecovery();
        isPlaying = true;
        startBufferMonitoring();
        preloadNextInQueue();
        downloadNextVideo();
    });
    
    player.on('pause', function() {
        console.log('Paused:', currentVideoId);
        isPlaying = false;
        stopBufferMonitoring();
    });
    
    player.on('ended', function() {
        console.log('Video ended event fired for:', currentVideoId);
        isPlaying = false;
        stopBufferMonitoring();
        playNext();
    });
    
    player.on('progress', function() {
        const currentTime = player.currentTime();
        const now = Date.now();
        if (currentTime > 0) {
            lastProgress = { time: currentTime, timestamp: now };
        }
    });
    
    player.on('timeupdate', function() {
        const currentTime = player.currentTime();
        const duration = player.duration();
        const now = Date.now();
        if (currentTime > 0) {
            lastProgress = { time: currentTime, timestamp: now };
        }
        
        if (duration > 0 && currentTime >= duration - 0.5 && !player.paused()) {
            console.log('Video near end via timeupdate, triggering playNext');
            player.pause();
            playNext();
        }
    });
    
    player.on('waiting', function() {
        console.log('Player waiting/buffering for:', currentVideoId);
        scheduleStallRecovery();
    });
    
    player.on('canplay', function() {
        console.log('Player can play:', currentVideoId);
        clearStallRecovery();
    });
    
    player.on('stalled', function() {
        console.log('Player stalled for:', currentVideoId);
        scheduleStallRecovery();
    });
    
    player.on('suspend', function() {
        console.log('Player suspended for:', currentVideoId);
    });
    
    player.on('abort', function() {
        console.log('Player abort for:', currentVideoId);
    });
    
    if (typeof window.VIDEO_QUALITY !== 'undefined') {
        currentQuality = window.VIDEO_QUALITY;
    }
    if (typeof window.ALLOW_MULTIPLE_VIDEOS !== 'undefined') {
        allowMultipleVideos = window.ALLOW_MULTIPLE_VIDEOS;
    }
    if (typeof window.AUTO_QUEUE_ENABLED !== 'undefined') {
        autoQueueEnabled = window.AUTO_QUEUE_ENABLED;
    }
    
    connectWebSocket();
    setupControls();
}

function scheduleStallRecovery() {
    clearStallRecovery();
    stallRecoveryTimeout = setTimeout(() => {
        attemptStallRecovery();
    }, 5000);
}

function clearStallRecovery() {
    if (stallRecoveryTimeout) {
        clearTimeout(stallRecoveryTimeout);
        stallRecoveryTimeout = null;
    }
}

function startBufferMonitoring() {
    stopBufferMonitoring();
    bufferCheckInterval = setInterval(checkBufferHealth, 2000);
}

function stopBufferMonitoring() {
    if (bufferCheckInterval) {
        clearInterval(bufferCheckInterval);
        bufferCheckInterval = null;
    }
}

function checkBufferHealth() {
    if (!player || player.paused() || !currentVideoId) return;
    
    const buffered = player.buffered();
    const currentTime = player.currentTime();
    const duration = player.duration();
    
    if (!buffered || buffered.length === 0 || !duration) return;
    
    let bufferEnd = 0;
    for (let i = 0; i < buffered.length; i++) {
        if (buffered.start(i) <= currentTime && buffered.end(i) > currentTime) {
            bufferEnd = buffered.end(i);
            break;
        }
    }
    
    const bufferAhead = bufferEnd - currentTime;
    const remainingTime = duration - currentTime;
    
    if (bufferAhead < 2 && remainingTime > 5) {
        lowBufferCount++;
        console.log(`Low buffer detected: ${bufferAhead.toFixed(1)}s ahead (count: ${lowBufferCount})`);
        
        if (lowBufferCount >= 3) {
            console.log('Buffer critically low, attempting reload');
            lowBufferCount = 0;
            reloadCurrentVideo();
        }
    } else if (bufferAhead > 5) {
        lowBufferCount = Math.max(0, lowBufferCount - 1);
    }
}

function attemptStallRecovery() {
    if (!player || player.paused()) return;
    
    const now = Date.now();
    const timeSinceProgress = now - lastProgress.timestamp;
    
    if (timeSinceProgress < 3000) return;
    
    stallCount++;
    console.log(`Stall recovery attempt ${stallCount}/${maxStallRetries} for:`, currentVideoId);
    
    if (stallCount > maxStallRetries) {
        console.log('Max stall retries reached, skipping to next video');
        stallCount = 0;
        playNext();
        return;
    }
    
    const currentTime = player.currentTime();
    const duration = player.duration();
    
    if (duration > 0 && currentTime >= duration - 1) {
        console.log('Near end of video, treating as ended');
        playNext();
        return;
    }
    
    try {
        player.currentTime(currentTime + 0.1);
        const playPromise = player.play();
        if (playPromise !== undefined) {
            playPromise.catch(error => {
                console.log('Play failed during stall recovery:', error);
                if (stallCount >= 2) {
                    reloadCurrentVideo();
                }
            });
        }
    } catch (error) {
        console.error('Stall recovery error:', error);
    }
}

function reloadCurrentVideo() {
    if (!currentVideoId) return;
    
    console.log('Reloading current video:', currentVideoId);
    const savedTime = player.currentTime();
    stopBufferMonitoring();
    
    player.reset();
    let proxyUrl = `/api/proxy/${currentVideoId}`;
    if (currentQuality) {
        proxyUrl += `?quality=${currentQuality}`;
    }
    player.src({ src: proxyUrl, type: 'video/mp4' });
    
    player.one('loadedmetadata', function() {
        if (savedTime > 0) {
            player.currentTime(savedTime);
        }
        player.play().catch(e => console.log('Play after reload failed:', e));
    });
    
    player.load();
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {};

    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === 'state') {
            updateQueueUI(message.data);
        }
    };

    ws.onclose = (event) => {
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (error) => {};
}

function updateQueueUI(state) {
    const queueList = document.getElementById('queueList');
    const currentTitle = document.getElementById('currentTitle');
    const currentChannel = document.getElementById('currentChannel');
    const queueCount = document.getElementById('queueCount');

    if (queueCount) {
        queueCount.textContent = state.items ? state.items.length : 0;
    }

    if (state.current) {
        currentTitle.textContent = state.current.title;
        currentChannel.textContent = state.current.channel || '';
        currentVideoId = state.current.id;
        if (state.current.play_count) {
            const playCountEl = document.getElementById('currentPlayCount');
            if (playCountEl) {
                playCountEl.textContent = `Played ${state.current.play_count}x`;
            }
        }
    } else {
        currentTitle.textContent = 'No video playing';
        currentChannel.textContent = '';
        currentVideoId = null;
        const playCountEl = document.getElementById('currentPlayCount');
        if (playCountEl) {
            playCountEl.textContent = '';
        }
    }

    if (state.items && state.items.length > 0) {
        queueItems = state.items;
        if (!state.current) {
            preloadNextVideo(state.items[0]);
        }
        const showAsPlaying = state.current !== null;
        queueList.innerHTML = `
            <button class="start-playing-btn" onclick="playNext()" ${showAsPlaying ? 'disabled style="opacity:0.5"' : ''}>
                <svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24">
                    <path d="M8 5v14l11-7z"/>
                </svg>
                ${showAsPlaying ? 'Now Playing' : 'Start Playing'}
            </button>
            ${state.items.map((item, index) => `
                <div class="queue-item ${index === 0 && !showAsPlaying ? 'next-up' : ''}" data-index="${index}" data-id="${item.id}" draggable="true">
                    <img class="queue-item-thumb" src="${item.thumbnail}" alt="${item.title}">
                    <div class="queue-item-info">
                        <div class="queue-item-title">${item.title}</div>
                        <div class="queue-item-meta">
                            ${item.channel ? `<span class="queue-item-channel">${item.channel}</span>` : ''}
                            ${item.duration ? `<span class="queue-item-duration">${item.duration}</span>` : ''}
                            ${item.added_by ? `<span class="queue-item-added-by">by ${item.added_by}</span>` : ''}
                        </div>
                    </div>
                    <button class="queue-item-play" onclick="event.stopPropagation(); playQueueItem(${index})" title="Play now">
                        <svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                    </button>
                    <button class="queue-item-remove" onclick="event.stopPropagation(); removeFromQueue(${index})" title="Remove">
                        <svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
                            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                        </svg>
                    </button>
                </div>
            `).join('')}
        `;
        setupDragAndDrop();
    } else {
        queueItems = [];
        queueList.innerHTML = `
            <div class="empty-queue">
                <p>No videos in queue</p>
                <p class="hint">Scan the QR code to add videos!</p>
            </div>
        `;
    }
}

async function preloadNextVideo(video) {
    if (!video || preloadingVideoId === video.id) return;
    preloadingVideoId = video.id;
    
    try {
        let proxyUrl = `/api/proxy/${video.id}`;
        if (currentQuality) {
            proxyUrl += `?quality=${currentQuality}`;
        }
        
        cache.set(video.id, { src: proxyUrl, type: 'video/mp4' });
    } catch (error) {
        preloadingVideoId = null;
    }
}

let queueItems = [];

function preloadNextInQueue() {
    if (queueItems.length > 0) {
        preloadNextVideo(queueItems[0]);
    }
}

async function downloadNextVideo() {
    if (!queueItems || queueItems.length === 0) return;
    
    const nextVideo = queueItems[0];
    if (!nextVideo || nextVideo.id === currentVideoId) return;
    
    console.log('Triggering background download of next video:', nextVideo.id);
    
    try {
        let prepareUrl = `/api/cache/${nextVideo.id}/prepare`;
        if (currentQuality) {
            prepareUrl += `?quality=${currentQuality}`;
        }
        
        fetch(prepareUrl, { method: 'POST' }).then(response => {
            if (response.ok) {
                console.log('Next video download triggered successfully');
            } else {
                console.error('Failed to trigger download');
            }
        }).catch(err => {
            console.error('Download trigger failed:', err);
        });
    } catch (error) {
        console.error('Failed to initiate download:', error);
    }
}

async function playNext() {
    const now = Date.now();
    if (now - lastPlayNextCall < 2000) {
        console.log('playNext: debounced, called too recently');
        return;
    }
    lastPlayNextCall = now;
    stallCount = 0;
    clearStallRecovery();
    
    try {
        const response = await fetch('/api/next', { method: 'POST' });
        const data = await response.json();
        
        if (data.video) {
            await loadAndPlay(data.video);
        } else {
            player.reset();
            await fetch('/api/current/clear', { method: 'POST' });
        }
    } catch (error) {
        console.error('playNext error:', error);
    }
}

async function loadAndPlay(video) {
    try {
        const wasFullscreen = isFullscreen;
        player.reset();
        stallCount = 0;
        clearStallRecovery();
        
        let cached = cache.get(video.id);
        if (cached) {
            player.src(cached);
            cache.delete(video.id);
        } else {
            let proxyUrl = `/api/proxy/${video.id}`;
            if (currentQuality) {
                proxyUrl += `?quality=${currentQuality}`;
            }
            
            const streamData = await fetch(`/api/stream/${video.id}${currentQuality ? '?quality=' + currentQuality : ''}`).then(r => r.json());
            
            player.src({ src: proxyUrl, type: 'video/mp4' });
        }
        currentVideoId = video.id;
        
        const playPromise = player.play();
        if (playPromise !== undefined) {
            await playPromise;
        }
        
        if (wasFullscreen) {
            const videoWrapper = document.querySelector('.video-wrapper');
            if (videoWrapper && videoWrapper.requestFullscreen) {
                videoWrapper.requestFullscreen();
            }
        }
    } catch (error) {
        console.error('Playback error:', error);
        stallCount++;
        if (stallCount <= maxStallRetries) {
            console.log(`Retrying playback (attempt ${stallCount}/${maxStallRetries})`);
            setTimeout(() => loadAndPlay(video), 1000);
        } else {
            stallCount = 0;
            setTimeout(() => playNext(), 1000);
        }
    }
}

async function removeFromQueue(index) {
    try {
        await fetch(`/api/queue/${index}`, { method: 'DELETE' });
    } catch (error) {}
}

async function playQueueItem(index) {
    try {
        const url = `/api/queue/${index}/play`;
        const response = await fetch(url, { method: 'POST' });
        const data = await response.json();
        
        if (data.video) {
            await loadAndPlay(data.video);
        }
    } catch (error) {}
}

function setupControls() {
    const skipBtn = document.getElementById('skipBtn');
    if (skipBtn) {
        skipBtn.addEventListener('click', playNext);
    }
    
    const playPauseBtn = document.getElementById('playPauseBtn');
    const playIcon = document.getElementById('playIcon');
    const pauseIcon = document.getElementById('pauseIcon');
    const volumeSlider = document.getElementById('volumeSlider');
    const volumeIcon = document.querySelector('.volume-icon');
    const fullscreenBtn = document.getElementById('fullscreenBtn');
    const qualitySelect = document.getElementById('qualitySelect');
    const multipleVideosToggle = document.getElementById('multipleVideosToggle');
    
    const videoWrapper = document.querySelector('.video-wrapper');
    
    if (fullscreenBtn) {
        fullscreenBtn.addEventListener('click', () => {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else if (videoWrapper.requestFullscreen) {
                videoWrapper.requestFullscreen();
            } else if (videoWrapper.webkitRequestFullscreen) {
                videoWrapper.webkitRequestFullscreen();
            }
        });
    }
    
    document.addEventListener('fullscreenchange', () => {
        isFullscreen = !!document.fullscreenElement;
    });
    
    document.addEventListener('webkitfullscreenchange', () => {
        isFullscreen = !!document.webkitFullscreenElement;
    });

    if (videoWrapper) {
        videoWrapper.addEventListener('dblclick', () => {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            }
        });
    }

    if (playPauseBtn) {
        playPauseBtn.addEventListener('click', () => {
            if (player.paused()) {
                player.play();
            } else {
                player.pause();
            }
        });
        
        player.on('play', () => {
            playIcon.style.display = 'none';
            pauseIcon.style.display = 'block';
        });
        
        player.on('pause', () => {
            playIcon.style.display = 'block';
            pauseIcon.style.display = 'none';
        });
    }

    if (volumeIcon) {
        volumeIcon.style.cursor = 'pointer';
        volumeIcon.addEventListener('click', () => {
            if (player.muted()) {
                player.muted(false);
                volumeSlider.value = player.volume() * 100;
            } else {
                player.muted(true);
            }
        });
        
        player.on('volumechange', () => {
            if (player.muted()) {
                volumeIcon.style.opacity = '0.5';
            } else {
                volumeIcon.style.opacity = '1';
            }
        });
    }

    if (volumeSlider) {
        const savedVolume = localStorage.getItem('ytbq_volume');
        const savedMuted = localStorage.getItem('ytbq_muted');
        
        if (savedVolume !== null) {
            player.volume(parseFloat(savedVolume));
            volumeSlider.value = parseFloat(savedVolume) * 100;
        } else {
            player.volume(volumeSlider.value / 100);
        }
        
        if (savedMuted === 'true') {
            player.muted(true);
        }
        
        volumeSlider.addEventListener('input', (e) => {
            const vol = e.target.value / 100;
            player.volume(vol);
            localStorage.setItem('ytbq_volume', vol);
            if (vol > 0) {
                player.muted(false);
                localStorage.setItem('ytbq_muted', 'false');
            }
        });
        
        player.on('volumechange', () => {
            localStorage.setItem('ytbq_volume', player.volume());
            localStorage.setItem('ytbq_muted', player.muted());
        });
    }

    if (qualitySelect) {
        if (currentQuality) {
            qualitySelect.value = currentQuality;
        }
        qualitySelect.addEventListener('change', async (e) => {
            currentQuality = parseInt(e.target.value);
            if (currentVideoId) {
                const currentTitle = document.getElementById('currentTitle').textContent;
                const currentChannel = document.getElementById('currentChannel').textContent;
                await loadAndPlay({
                    id: currentVideoId,
                    title: currentTitle,
                    channel: currentChannel
                });
            }
        });
    }

    if (multipleVideosToggle) {
        multipleVideosToggle.checked = allowMultipleVideos;
        if (window.MULTIPLE_VIDEOS_LOCKED) {
            multipleVideosToggle.disabled = true;
            multipleVideosToggle.parentElement.classList.add('disabled');
        } else {
            multipleVideosToggle.addEventListener('change', (e) => {
                allowMultipleVideos = e.target.checked;
                fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: 'allow_multiple_videos', value: allowMultipleVideos })
                });
            });
        }
    }

    const autoQueueToggle = document.getElementById('autoQueueToggle');
    if (autoQueueToggle) {
        autoQueueToggle.checked = autoQueueEnabled;
        if (window.AUTO_QUEUE_LOCKED) {
            autoQueueToggle.disabled = true;
            autoQueueToggle.parentElement.classList.add('disabled');
        } else {
            autoQueueToggle.addEventListener('change', (e) => {
                autoQueueEnabled = e.target.checked;
                fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: 'auto_queue_enabled', value: autoQueueEnabled })
                });
            });
        }
    }

    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme === 'light') {
            document.documentElement.setAttribute('data-theme', 'light');
            themeToggle.checked = true;
        }
        themeToggle.addEventListener('change', (e) => {
            if (e.target.checked) {
                document.documentElement.setAttribute('data-theme', 'light');
                localStorage.setItem('theme', 'light');
            } else {
                document.documentElement.removeAttribute('data-theme');
                localStorage.setItem('theme', 'dark');
            }
        });
    }

    const clearQueueBtn = document.getElementById('clearQueueBtn');
    if (clearQueueBtn) {
        clearQueueBtn.addEventListener('click', async () => {
            if (confirm('Clear all videos from the queue?')) {
                try {
                    await fetch('/api/queue/clear', { method: 'POST' });
                } catch (error) {}
            }
        });
    }

    setupMainSearch();
}

function setupDragAndDrop() {
    const queueItems = document.querySelectorAll('.queue-item');
    let draggedItem = null;

    queueItems.forEach(item => {
        item.addEventListener('dragstart', (e) => {
            draggedItem = item;
            item.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });

        item.addEventListener('dragend', () => {
            item.classList.remove('dragging');
            document.querySelectorAll('.queue-item').forEach(i => i.classList.remove('drag-over'));
        });

        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const draggingItem = document.querySelector('.dragging');
            if (draggingItem && item !== draggingItem) {
                item.classList.add('drag-over');
            }
        });

        item.addEventListener('dragleave', () => {
            item.classList.remove('drag-over');
        });

        item.addEventListener('drop', async (e) => {
            e.preventDefault();
            item.classList.remove('drag-over');
            
            if (draggedItem && draggedItem !== item) {
                const fromIndex = parseInt(draggedItem.dataset.index);
                const toIndex = parseInt(item.dataset.index);
                
                if (!isNaN(fromIndex) && !isNaN(toIndex)) {
                    await reorderQueue(fromIndex, toIndex);
                }
            }
        });
    });
}

async function reorderQueue(fromIndex, toIndex) {
    try {
        await fetch('/api/queue/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ from_index: fromIndex, to_index: toIndex })
        });
    } catch (error) {}
}

function setupMainSearch() {
    const form = document.getElementById('mainSearchForm');
    const input = document.getElementById('mainSearchInput');
    const clearBtn = document.getElementById('clearMainSearchBtn');

    if (!form || !input) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = input.value.trim();
        if (query) {
            await searchVideos(query);
        }
    });
    
    if (clearBtn) {
        input.addEventListener('input', () => {
            clearBtn.style.display = input.value ? 'flex' : 'none';
        });
        
        clearBtn.addEventListener('click', () => {
            input.value = '';
            clearBtn.style.display = 'none';
            document.getElementById('mainSearchResults').innerHTML = '';
            input.focus();
        });
    }
}

async function searchVideos(query) {
    const resultsContainer = document.getElementById('mainSearchResults');
    resultsContainer.innerHTML = '<div class="loading"></div>';

    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const videos = await response.json();

        if (videos.length === 0) {
            resultsContainer.innerHTML = '<div class="empty-queue"><p>No videos found</p></div>';
            return;
        }

        resultsContainer.innerHTML = `
            <div class="results-list">
                ${videos.map(video => `
                    <div class="result-item" data-id="${video.id}" data-duration="${video.duration || ''}">
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
                `).join('')}
            </div>
        `;

        document.querySelectorAll('.result-item').forEach(item => {
            item.addEventListener('click', () => {
                addToQueue(item.dataset.id, item);
            });
        });
    } catch (error) {
        resultsContainer.innerHTML = '<div class="empty-queue"><p>Search failed. Try again.</p></div>';
    }
}

async function addToQueue(videoId, element) {
    if (element.classList.contains('added')) return;

    if (!allowMultipleVideos) {
        const existing = document.querySelectorAll('.result-item.added');
        if (existing.length > 0) {
            showToast('Multiple videos disabled', 'error');
            return;
        }
    }

    element.classList.add('added');

    const title = element.querySelector('.result-title').textContent;
    const thumbnail = element.querySelector('.result-thumb img').src;
    const channel = element.querySelector('.result-channel').textContent;
    const duration = element.dataset.duration || '';

    try {
        const response = await fetch('/api/queue', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                id: videoId,
                title: title,
                thumbnail: thumbnail,
                channel: channel,
                duration: duration,
            }),
        });

        const data = await response.json();

        if (data.success) {
            showToast(`Added: ${title}`, 'success');
        } else {
            element.classList.remove('added');
            showToast('Failed to add video', 'error');
        }
    } catch (error) {
        element.classList.remove('added');
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
