"""
90Tools - yt-dlp Downloader API
Deploy this anywhere (Replit, Render, Railway, Koyeb, etc.)
Free hosting works!

API Endpoints:
  GET /api/download?url=VIDEO_URL&platform=youtube
  GET /api/info?url=VIDEO_URL
  GET /health

Returns JSON with video/audio URLs
"""

import os
import re
import json
import subprocess
import tempfile
import shutil
from flask import Flask, request, jsonify

app = Flask(__name__)

# Check if yt-dlp is available
YT_DLP = shutil.which('yt-dlp') or shutil.which('yt-dlp.exe') or '/usr/local/bin/yt-dlp'
FFMPEG = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe') or '/usr/local/bin/ffmpeg'


def run_ytdlp(args):
    """Run yt-dlp with given args and return output"""
    cmd = [YT_DLP] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return '', 'TIMEOUT', -1
    except FileNotFoundError:
        return '', 'yt-dlp not found', -1


@app.route('/health')
def health():
    """Health check endpoint"""
    yt_ver = ''
    ff_ver = ''
    
    try:
        out, _, _ = run_ytdlp(['--version'])
        yt_ver = out.strip()
    except:
        yt_ver = 'not installed'
    
    try:
        result = subprocess.run([FFMPEG, '-version'], capture_output=True, text=True, timeout=5)
        ff_ver = result.stdout.split('\n')[0] if result.stdout else 'not installed'
    except:
        ff_ver = 'not installed'

    return jsonify({
        'status': 'ok',
        'yt_dlp': yt_ver,
        'ffmpeg': ff_ver.split(' ')[2] if ff_ver != 'not installed' else 'not installed'
    })


@app.route('/api/info')
def get_info():
    """Get video info without downloading"""
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    stdout, stderr, code = run_ytdlp([
        '--dump-json',
        '--no-download',
        '--no-warnings',
        url
    ])
    
    if code != 0 or not stdout:
        return jsonify({'error': 'Failed to get info', 'details': stderr[:500]}), 400
    
    try:
        data = json.loads(stdout.strip().split('\n')[0])
        return jsonify({
            'title': data.get('title', ''),
            'duration': data.get('duration', 0),
            'thumbnail': data.get('thumbnail', ''),
            'uploader': data.get('uploader', ''),
            'views': data.get('view_count', 0),
            'formats': [
                {
                    'format_id': f.get('format_id'),
                    'ext': f.get('ext'),
                    'quality': f.get('height', 'audio'),
                    'filesize': f.get('filesize', 0),
                }
                for f in data.get('formats', [])[:20]
            ]
        })
    except json.JSONDecodeError:
        return jsonify({'error': 'Failed to parse video info'}), 500


@app.route('/api/download')
def download():
    """Download video and return URL/file"""
    url = request.args.get('url', '')
    quality = request.args.get('quality', 'best')  # best, medium, audio
    platform = request.args.get('platform', 'youtube')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    # Create temp directory for output
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
    
    try:
        if quality == 'audio':
            # Download audio only (MP3)
            args = [
                '-x', '--audio-format', 'mp3',
                '--audio-quality', '0',
                '--max-filesize', '50M',
                '-o', output_template,
                '--no-warnings',
                '--print', 'after_move:filepath',
                url
            ]
        else:
            # Download video
            format_str = 'best[ext=mp4]/best' if quality == 'best' else 'best[height<=720][ext=mp4]/best[height<=720]'
            args = [
                '-f', format_str,
                '--max-filesize', '50M',
                '-o', output_template,
                '--no-warnings',
                '--print', 'after_move:filepath',
                url
            ]
        
        stdout, stderr, code = run_ytdlp(args)
        
        if code != 0:
            return jsonify({'error': 'Download failed', 'details': stderr[:500]}), 400
        
        # Get the downloaded file path
        filepath = stdout.strip().split('\n')[-1] if stdout else ''
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'File not found after download'}), 500
        
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        
        # For small files, return as base64 or direct download
        # Since we can't serve files easily on free hosting,
        # we'll return a signed download URL or the file info
        
        return jsonify({
            'success': True,
            'title': os.path.splitext(filename)[0],
            'ext': os.path.splitext(filename)[1][1:],
            'filesize': filesize,
            'filesize_human': format_size(filesize),
            'filename': filename,
            'filepath': filepath,
            'temp_dir': temp_dir,
            'note': 'File is stored on server. Use /api/serve?file=PATH to download'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/serve')
def serve_file():
    """Serve a downloaded file"""
    filepath = request.args.get('file', '')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    filename = os.path.basename(filepath)
    
    try:
        from flask import send_file
        return send_file(filepath, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'error': f'Could not send file: {str(e)}'}), 500


@app.route('/api/download_direct', methods=['POST'])
def download_direct():
    """Download and return direct URL (for Telegram bot)"""
    data = request.get_json() or request.form
    url = data.get('url', '')
    quality = data.get('quality', 'best')
    
    if not url:
        return jsonify({'error': 'No URL'}), 400
    
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, 'video.%(ext)s')
    
    if quality == 'audio':
        args = ['-x', '--audio-format', 'mp3', '--max-filesize', '50M', '-o', output_template, '--no-warnings', '--print', 'after_move:filepath', url]
    else:
        args = ['-f', 'best[ext=mp4]/best', '--max-filesize', '50M', '-o', output_template, '--no-warnings', '--print', 'after_move:filepath', url]
    
    stdout, stderr, code = run_ytdlp(args)
    
    if code != 0:
        return jsonify({'error': 'Download failed', 'details': stderr[:300]}), 400
    
    filepath = stdout.strip().split('\n')[-1] if stdout else ''
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 500
    
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    
    return jsonify({
        'success': True,
        'download_url': f'/api/serve?file={os.path.abspath(filepath)}',
        'filename': filename,
        'filesize': filesize,
        'filesize_human': format_size(filesize),
    })


# Temp directory cleanup
@app.route('/api/cleanup')
def cleanup():
    """Clean old temp files"""
    temp_base = tempfile.gettempdir()
    cleaned = 0
    for d in os.listdir(temp_base):
        d_path = os.path.join(temp_base, d)
        if os.path.isdir(d_path) and d.startswith('tmp') or d.startswith('ytdl'):
            try:
                shutil.rmtree(d_path)
                cleaned += 1
            except:
                pass
    return jsonify({'cleaned': cleaned})


def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@app.route('/')
def index():
    return jsonify({
        'name': '90Tools Downloader API',
        'version': '1.0',
        'endpoints': {
            '/health': 'Check server status',
            '/api/info?url=...': 'Get video info',
            '/api/download?url=...': 'Download video (returns JSON)',
            '/api/download_direct': 'POST - download and get URL',
            '/api/serve?file=...': 'Download a file directly',
        }
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
