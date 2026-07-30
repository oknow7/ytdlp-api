import os
import json
import subprocess
import tempfile
import shutil
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

YT_DLP = shutil.which('yt-dlp') or shutil.which('yt-dlp.exe') or '/usr/local/bin/yt-dlp'
FFMPEG = shutil.which('ffmpeg') or '/usr/local/bin/ffmpeg'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(BASE_DIR, 'cookies.txt')
if not os.path.exists(COOKIES_FILE):
    COOKIES_FILE = ''

def build_args(extra):
    args = ['--no-warnings', '--ignore-errors', '--extractor-args', 'youtube:player_client=web_embedded']
    if COOKIES_FILE:
        args += ['--cookies', COOKIES_FILE]
    return [YT_DLP] + args + extra

def run_ytdlp(extra):
    cmd = build_args(extra)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return '', 'TIMEOUT', -1
    except FileNotFoundError:
        return '', 'yt-dlp not found', -1

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

@app.route('/health')
def health():
    try:
        out, _, _ = run_ytdlp(['--version'])
        ff = subprocess.run([FFMPEG, '-version'], capture_output=True, text=True, timeout=5).stdout.split('\n')[0] if FFMPEG else 'N/A'
        return jsonify({'status': 'ok', 'yt_dlp': out.strip()[:20], 'ffmpeg': ff.split(' ')[2] if ff else 'no', 'cookies': bool(COOKIES_FILE)})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/api/info')
def get_info():
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    stdout, stderr, code = run_ytdlp(['--dump-json', '--no-download', url])
    if code != 0 or not stdout:
        return jsonify({'error': 'Failed to get info', 'details': (stderr or '')[:500]}), 400
    try:
        data = json.loads(stdout.strip().split('\n')[0])
        return jsonify({'title': data.get('title', ''), 'duration': data.get('duration', 0), 'thumbnail': data.get('thumbnail', ''), 'uploader': data.get('uploader', ''), 'views': data.get('view_count', 0), 'formats': [{'format_id': f.get('format_id'), 'ext': f.get('ext'), 'quality': f.get('height', 'audio'), 'filesize': f.get('filesize', 0)} for f in data.get('formats', [])[:20]]})
    except Exception:
        return jsonify({'error': 'Failed to parse video info'}), 500

@app.route('/api/download')
def download():
    url = request.args.get('url', '')
    quality = request.args.get('quality', 'best')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    temp_dir = tempfile.mkdtemp()
    try:
        if quality == 'audio':
            args = ['-x', '--audio-format', 'mp3', '--audio-quality', '0', '--max-filesize', '100M', '-o', os.path.join(temp_dir, '%(title)s.%(ext)s'), '--print', 'after_move:filepath', url]
        else:
            fmt = 'best[ext=mp4]/best' if quality == 'best' else f'best[height<={quality}][ext=mp4]/best[height<={quality}]'
            args = ['-f', fmt, '--max-filesize', '100M', '-o', os.path.join(temp_dir, '%(title)s.%(ext)s'), '--print', 'after_move:filepath', url]
        stdout, stderr, code = run_ytdlp(args)
        if code != 0:
            return jsonify({'error': 'Download failed', 'details': (stderr or '')[:500]}), 400
        filepath = stdout.strip().split('\n')[-1] if stdout else ''
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'File not found after download'}), 500
        return jsonify({'success': True, 'title': os.path.splitext(os.path.basename(filepath))[0], 'ext': os.path.splitext(os.path.basename(filepath))[1][1:], 'filesize': os.path.getsize(filepath), 'filesize_human': format_size(os.path.getsize(filepath))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/serve')
def serve_file():
    filepath = request.args.get('file', '')
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    return send_file(filepath, as_attachment=True, download_name=os.path.basename(filepath))

@app.route('/api/download_direct', methods=['POST'])
def download_direct():
    data = request.get_json() or request.form
    url = data.get('url', '')
    quality = data.get('quality', 'best')
    if not url:
        return jsonify({'error': 'No URL'}), 400
    temp_dir = tempfile.mkdtemp()
    try:
        if quality == 'audio':
            args = ['-x', '--audio-format', 'mp3', '--audio-quality', '0', '--max-filesize', '100M', '-o', os.path.join(temp_dir, 'video.%(ext)s'), '--print', 'after_move:filepath', url]
        else:
            fmt = 'best[ext=mp4]/best' if quality == 'best' else f'best[height<={quality}][ext=mp4]/best[height<={quality}]'
            args = ['-f', fmt, '--max-filesize', '100M', '-o', os.path.join(temp_dir, 'video.%(ext)s'), '--print', 'after_move:filepath', url]
        stdout, stderr, code = run_ytdlp(args)
        if code != 0:
            return jsonify({'error': 'Download failed', 'details': (stderr or '')[:300]}), 400
        filepath = stdout.strip().split('\n')[-1] if stdout else ''
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 500
        return jsonify({'success': True, 'download_url': f'/api/serve?file={os.path.abspath(filepath)}', 'filename': os.path.basename(filepath), 'filesize': os.path.getsize(filepath), 'filesize_human': format_size(os.path.getsize(filepath))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cleanup')
def cleanup():
    cleaned = 0
    for d in os.listdir(tempfile.gettempdir()):
        dp = os.path.join(tempfile.gettempdir(), d)
        if os.path.isdir(dp) and (d.startswith('tmp') or d.startswith('ytdl')):
            try:
                shutil.rmtree(dp); cleaned += 1
            except:
                pass
    return jsonify({'cleaned': cleaned})

@app.route('/')
def index():
    return jsonify({'name': '90Tools Downloader API', 'version': '2.2', 'endpoints': {'/health': 'Check server', '/api/info': 'GET video info', '/api/download': 'GET download video', '/api/download_direct': 'POST download', '/api/serve': 'GET file'}})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
