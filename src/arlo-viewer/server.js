const express = require('express');
const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');
const crypto = require('crypto');

const app = express();
const PORT = 3003;
const RECORDINGS_DIR = '/home/randy/arlo-recordings';

// Simple auth configuration
const AUTH_PASSWORD = 'farmernet';
const AUTH_COOKIE_NAME = 'arlo_auth';
const AUTH_SECRET = 'arlo-security-2026';

function swizzle(password) {
    return crypto.createHash('sha256').update(password + AUTH_SECRET).digest('hex').substring(0, 32);
}

const VALID_TOKEN = swizzle(AUTH_PASSWORD);

// Login page HTML
const LOGIN_PAGE = `<!DOCTYPE html>
<html><head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Security Login</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #1a1a1a; color: #e0e0e0;
               display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #2a2a2a; padding: 40px; border-radius: 8px; text-align: center; }
        h2 { margin-bottom: 20px; }
        input { padding: 12px; font-size: 16px; border: none; border-radius: 4px; margin-bottom: 15px; width: 200px; }
        button { padding: 12px 30px; font-size: 16px; background: #2196F3; color: white;
                 border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0b7dda; }
        .error { color: #f44336; margin-bottom: 15px; }
    </style>
</head><body>
    <div class="login-box">
        <h2>Security Cameras</h2>
        <div id="error" class="error" style="display:none;">Incorrect password</div>
        <form method="POST" action="/login">
            <input type="password" name="password" placeholder="Password" autofocus required><br>
            <button type="submit">Enter</button>
        </form>
    </div>
</body></html>`;

// Parse cookies middleware
app.use((req, res, next) => {
    const cookies = {};
    const cookieHeader = req.headers.cookie;
    if (cookieHeader) {
        cookieHeader.split(';').forEach(cookie => {
            const [name, value] = cookie.trim().split('=');
            cookies[name] = value;
        });
    }
    req.cookies = cookies;
    next();
});

// Auth middleware - check cookie on all requests except /login and /api/thumbnail
app.use((req, res, next) => {
    // Allow login and thumbnail endpoints without auth (thumbnails needed for ntfy notifications)
    if (req.path === '/login' || req.path.startsWith('/api/thumbnail/')) return next();

    const token = req.cookies[AUTH_COOKIE_NAME];
    if (token === VALID_TOKEN) {
        return next();
    }

    // Not authenticated - show login page
    res.send(LOGIN_PAGE);
});

// Login endpoint
app.use(express.urlencoded({ extended: true }));
app.post('/login', (req, res) => {
    const password = req.body.password;
    if (password === AUTH_PASSWORD) {
        res.setHeader('Set-Cookie', `${AUTH_COOKIE_NAME}=${VALID_TOKEN}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000`);
        res.redirect('/');
    } else {
        res.send(LOGIN_PAGE.replace('style="display:none;"', ''));
    }
});

// Load camera aliases from config
let CAMERA_ALIASES = {};
try {
    const configPath = '/opt/arlo-cam-api/config.yaml';
    const configFile = fs.readFileSync(configPath, 'utf8');
    const config = yaml.load(configFile);
    CAMERA_ALIASES = config.CameraAliases || {};
    console.log('Loaded camera aliases:', CAMERA_ALIASES);
} catch (err) {
    console.log('Warning: Could not load camera aliases from config:', err.message);
}

// Serve static files (HTML, CSS, JS)
app.use(express.static('public'));
app.use(express.json());

// Proxy for camera status API (Flask runs on port 5000)
app.get('/api/cameras/status', (req, res) => {
    const http = require('http');
    http.get('http://localhost:5000/cameras/status', (apiRes) => {
        let data = '';
        apiRes.on('data', (chunk) => data += chunk);
        apiRes.on('end', () => {
            res.setHeader('Content-Type', 'application/json');
            res.send(data);
        });
    }).on('error', (err) => {
        res.status(500).json({ error: 'Failed to fetch camera status' });
    });
});

// Proxy for camera arm API (enable motion detection)
app.post('/api/camera/:serial/arm', (req, res) => {
    const http = require('http');
    const serial = req.params.serial;

    const postData = JSON.stringify({
        PIRTargetState: 'Armed',
        VideoMotionEstimationEnable: true,
        AudioTargetState: 'Disarmed'
    });

    const options = {
        hostname: 'localhost',
        port: 5000,
        path: `/camera/${serial}/arm`,
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': postData.length
        }
    };

    const proxyReq = http.request(options, (apiRes) => {
        let data = '';
        apiRes.on('data', (chunk) => data += chunk);
        apiRes.on('end', () => {
            res.setHeader('Content-Type', 'application/json');
            res.send(data);
        });
    });

    proxyReq.on('error', (err) => {
        res.status(500).json({ error: 'Failed to arm camera' });
    });

    proxyReq.write(postData);
    proxyReq.end();
});

// Proxy for camera disarm API (disable motion detection for charging)
app.post('/api/camera/:serial/disarm', (req, res) => {
    const http = require('http');
    const serial = req.params.serial;

    const postData = JSON.stringify({
        PIRTargetState: 'Disarmed',
        VideoMotionEstimationEnable: false,
        AudioTargetState: 'Disarmed'
    });

    const options = {
        hostname: 'localhost',
        port: 5000,
        path: `/camera/${serial}/arm`,
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': postData.length
        }
    };

    const proxyReq = http.request(options, (apiRes) => {
        let data = '';
        apiRes.on('data', (chunk) => data += chunk);
        apiRes.on('end', () => {
            res.setHeader('Content-Type', 'application/json');
            res.send(data);
        });
    });

    proxyReq.on('error', (err) => {
        res.status(500).json({ error: 'Failed to disarm camera' });
    });

    proxyReq.write(postData);
    proxyReq.end();
});

// API: List all recordings
// Cleanup old recordings (older than 7 days)
const RETENTION_DAYS = 7;

function cleanupOldRecordings(callback) {
    const maxAge = Date.now() - (RETENTION_DAYS * 24 * 60 * 60 * 1000);

    fs.readdir(RECORDINGS_DIR, (err, files) => {
        if (err) return callback(err);

        const videoFiles = files.filter(f => f.endsWith('.mp4') || f.endsWith('.mkv'));
        let pending = videoFiles.length;
        let deleted = 0;

        if (pending === 0) return callback(null, 0);

        videoFiles.forEach(file => {
            const filePath = path.join(RECORDINGS_DIR, file);
            fs.stat(filePath, (err, stats) => {
                if (!err && stats.mtime.getTime() < maxAge) {
                    // Delete video file and associated files (.jpg, .log)
                    const baseName = file.replace(/\.(mp4|mkv)$/, '');
                    const filesToDelete = [
                        filePath,
                        path.join(RECORDINGS_DIR, baseName + '.jpg'),
                        path.join(RECORDINGS_DIR, 'ffmpeg-' + baseName.replace('arlo-', '') + '.log')
                    ];

                    filesToDelete.forEach(f => {
                        fs.unlink(f, (unlinkErr) => {
                            if (!unlinkErr) {
                                console.log(`[CLEANUP] Deleted old file: ${path.basename(f)}`);
                            }
                        });
                    });
                    deleted++;
                }

                pending--;
                if (pending === 0) callback(null, deleted);
            });
        });
    });
}

app.get('/api/recordings', (req, res) => {
    // First cleanup old recordings, then return the list
    cleanupOldRecordings((err, deletedCount) => {
        if (deletedCount > 0) {
            console.log(`[CLEANUP] Removed ${deletedCount} recordings older than ${RETENTION_DAYS} days`);
        }

        fs.readdir(RECORDINGS_DIR, (err, files) => {
            if (err) {
                return res.status(500).json({ error: 'Failed to read recordings directory' });
            }

            // Filter for video files and get file stats
            const mp4Files = files.filter(f => f.endsWith('.mp4') || f.endsWith('.mkv'));
            const recordings = [];

            let pending = mp4Files.length;
            if (pending === 0) {
                return res.json([]);
            }

            mp4Files.forEach(file => {
                const filePath = path.join(RECORDINGS_DIR, file);
                fs.stat(filePath, (err, stats) => {
                    if (!err) {
                        // Parse timestamp from filename: arlo-SERIAL-20251219-140803.mp4 or .mkv
                        const match = file.match(/arlo-([^-]+)-(\d{8})-(\d{6})\.(mp4|mkv)/);
                        let timestamp = null;
                        let cameraSerial = null;
                        if (match) {
                            cameraSerial = match[1]; // 5EM1877DA41B6
                            const date = match[2]; // 20251219
                            const time = match[3]; // 140803
                            // Format: 2025-12-19 14:08:03
                            timestamp = `${date.substr(0,4)}-${date.substr(4,2)}-${date.substr(6,2)} ${time.substr(0,2)}:${time.substr(2,2)}:${time.substr(4,2)}`;
                        }

                        // Use friendly name from aliases if available
                        const cameraName = cameraSerial ? (CAMERA_ALIASES[cameraSerial] || cameraSerial) : 'unknown';

                        recordings.push({
                            filename: file,
                            size: stats.size,
                            timestamp: timestamp || new Date(stats.mtime).toISOString(),
                            mtime: stats.mtime,
                            camera: cameraName
                        });
                    }

                    pending--;
                    if (pending === 0) {
                        // Sort by timestamp descending (newest first)
                        recordings.sort((a, b) => new Date(b.mtime) - new Date(a.mtime));
                        res.json(recordings);
                    }
                });
            });
        });
    });
});

// API: Serve video file
app.get('/api/video/:filename', (req, res) => {
    const filename = req.params.filename;
    const filePath = path.join(RECORDINGS_DIR, filename);

    // Security check: ensure filename doesn't contain path traversal
    if (filename.includes('..') || filename.includes('/')) {
        return res.status(400).json({ error: 'Invalid filename' });
    }

    // Check if file exists
    if (!fs.existsSync(filePath)) {
        return res.status(404).json({ error: 'File not found' });
    }

    // Stream the video file
    const stat = fs.statSync(filePath);
    const fileSize = stat.size;
    const range = req.headers.range;
    const contentType = filename.endsWith('.mkv') ? 'video/x-matroska' : 'video/mp4';

    if (range) {
        // Handle range requests for video seeking
        const parts = range.replace(/bytes=/, "").split("-");
        let start = parseInt(parts[0], 10);
        let end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;

        // Handle invalid ranges
        if (isNaN(start)) start = 0;
        if (isNaN(end)) end = fileSize - 1;

        // Ensure valid range
        if (start < 0) start = 0;
        if (end >= fileSize) end = fileSize - 1;
        if (start > end) start = end;

        const chunksize = (end - start) + 1;
        const file = fs.createReadStream(filePath, { start, end });
        const head = {
            'Content-Range': `bytes ${start}-${end}/${fileSize}`,
            'Accept-Ranges': 'bytes',
            'Content-Length': chunksize,
            'Content-Type': contentType,
        };
        res.writeHead(206, head);
        file.pipe(res);
    } else {
        // Send full file
        const head = {
            'Content-Length': fileSize,
            'Content-Type': contentType,
        };
        res.writeHead(200, head);
        fs.createReadStream(filePath).pipe(res);
    }
});

// API: Serve thumbnail image
app.get('/api/thumbnail/:filename', (req, res) => {
    const filename = req.params.filename;

    // Security check: ensure filename doesn't contain path traversal
    if (filename.includes('..') || filename.includes('/')) {
        return res.status(400).json({ error: 'Invalid filename' });
    }

    // Serve the thumbnail file directly (should be .jpg)
    const filePath = path.join(RECORDINGS_DIR, filename);

    // Check if thumbnail exists
    if (!fs.existsSync(filePath)) {
        return res.status(404).json({ error: 'Thumbnail not found' });
    }

    // Serve the thumbnail image
    res.sendFile(filePath);
});

// API: Delete recording (and associated thumbnail)
app.delete('/api/recordings/:filename', (req, res) => {
    const filename = req.params.filename;
    const filePath = path.join(RECORDINGS_DIR, filename);

    // Security check
    if (filename.includes('..') || filename.includes('/')) {
        return res.status(400).json({ error: 'Invalid filename' });
    }

    // Check if file exists
    if (!fs.existsSync(filePath)) {
        return res.status(404).json({ error: 'File not found' });
    }

    // Delete the video file
    fs.unlink(filePath, (err) => {
        if (err) {
            return res.status(500).json({ error: 'Failed to delete file' });
        }

        // Also delete the thumbnail if it exists
        const thumbnailFilename = filename.replace(/\.(mkv|mp4)$/, '.jpg');
        const thumbnailPath = path.join(RECORDINGS_DIR, thumbnailFilename);

        if (fs.existsSync(thumbnailPath)) {
            fs.unlink(thumbnailPath, (thumbErr) => {
                if (thumbErr) {
                    console.log(`Warning: Failed to delete thumbnail ${thumbnailFilename}: ${thumbErr}`);
                }
            });
        }

        res.json({ success: true, message: 'File deleted successfully' });
    });
});

// Proxy for stream start API
app.post('/api/camera/:serial/stream/start', (req, res) => {
    const http = require('http');
    const serial = req.params.serial;

    const options = {
        hostname: 'localhost',
        port: 5000,
        path: `/camera/${serial}/stream/start`,
        method: 'POST'
    };

    const proxyReq = http.request(options, (apiRes) => {
        let data = '';
        apiRes.on('data', (chunk) => data += chunk);
        apiRes.on('end', () => {
            res.setHeader('Content-Type', 'application/json');
            res.send(data);
        });
    });

    proxyReq.on('error', (err) => {
        res.status(500).json({ error: 'Failed to start stream' });
    });

    proxyReq.end();
});

// Proxy for stream stop API
app.post('/api/camera/:serial/stream/stop', (req, res) => {
    const http = require('http');
    const serial = req.params.serial;

    const options = {
        hostname: 'localhost',
        port: 5000,
        path: `/camera/${serial}/stream/stop`,
        method: 'POST'
    };

    const proxyReq = http.request(options, (apiRes) => {
        let data = '';
        apiRes.on('data', (chunk) => data += chunk);
        apiRes.on('end', () => {
            res.setHeader('Content-Type', 'application/json');
            res.send(data);
        });
    });

    proxyReq.on('error', (err) => {
        res.status(500).json({ error: 'Failed to stop stream' });
    });

    proxyReq.end();
});

// Proxy for stream status API
app.get('/api/camera/:serial/stream/status', (req, res) => {
    const http = require('http');
    const serial = req.params.serial;

    http.get(`http://localhost:5000/camera/${serial}/stream/status`, (apiRes) => {
        let data = '';
        apiRes.on('data', (chunk) => data += chunk);
        apiRes.on('end', () => {
            res.setHeader('Content-Type', 'application/json');
            res.send(data);
        });
    }).on('error', (err) => {
        res.status(500).json({ error: 'Failed to fetch stream status' });
    });
});

// Serve HLS files (.m3u8 playlists and .ts segments)
app.get('/api/stream/:serial/:file', (req, res) => {
    const serial = req.params.serial;
    const file = req.params.file;

    // Security check: ensure filename doesn't contain path traversal
    if (file.includes('..') || file.includes('/') || serial.includes('..') || serial.includes('/')) {
        return res.status(400).json({ error: 'Invalid path' });
    }

    const filePath = path.join('/tmp/arlo-stream', serial, file);

    // Check if file exists
    if (!fs.existsSync(filePath)) {
        return res.status(404).json({ error: 'Stream file not found' });
    }

    // Set appropriate content type
    let contentType;
    if (file.endsWith('.m3u8')) {
        contentType = 'application/vnd.apple.mpegurl';
    } else if (file.endsWith('.ts')) {
        contentType = 'video/mp2t';
    } else {
        return res.status(400).json({ error: 'Unsupported file type' });
    }

    // Set headers
    res.setHeader('Content-Type', contentType);
    res.setHeader('Cache-Control', 'no-cache');

    // Stream the file
    fs.createReadStream(filePath).pipe(res);
});

app.listen(PORT, () => {
    console.log(`Arlo Viewer running on http://localhost:${PORT}`);
});
