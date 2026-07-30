import os
import json
import subprocess
import tempfile
import shutil
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

YT_DLP = shutil.which('yt-dlp') or shutil.which('yt-dlp.exe') or '/usr/local/bin/yt-dlp'
FFMPEG = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe') or '/usr/local/bin/ffmpeg'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(BASE_DIR, 'cookies.txt')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'

if not os.path.exists(COOKIES_FILE):
    COOKIES_FILE = os.environ.get('COOKIES_FILE', '')

def base_args():
    args = ['--user-agent', UA, '--no-warnings', '--ignore-errors']
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        args += ['--cookies', COOKIES_FILE]
    else:
        args += ['--extractor-args', 'youtube:player_client=web_embedded']
    return args

def run_ytdlp(args):
    cmd = [YT_DLP] + base_args() + args
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
    yt_ver = ff_ver = ''
    try:
        out, _, _ = run_ytdlp(['--version'])
        yt_ver = out.strip()
    except:
        yt_ver = 'error'
    try:
        result = subprocess.run([FFMPEG, '-version'], capture_output=True, text=True, timeout=5)
        ff_ver = result.stdout.split('\n')[0] if result.stdout else 'error'
    except:
        ff_ver = 'error'
    return jsonify({'status': 'ok', 'yt_dlp': yt_ver, 'ffmpeg': ff_ver.split(' ')[2] if ff_ver != 'error' else 'not installed'})

@app.route('/api/info')
def get_info():
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    stdout, stderr, code = run_ytdlp(['--dump-json', '--no-download', url])
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
            'formats': [{'format_id': f.get('format_id'), 'ext': f.get('ext'), 'quality': f.get('height', 'audio'), 'filesize': f.get('filesize', 0)} for f in data.get('formats', [])[:20]]
        })
    except json.JSONDecodeError:
        return jsonify({'error': 'Failed to parse video info'}), 500

@app.route('/api/download')
def download():
    url = request.args.get('url', '')
    quality = request.args.get('quality', 'best')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
    try:
        if quality == 'audio':
            args = ['-x', '--audio-format', 'mp3', '--audio-quality', '0', '--max-filesize', '100M', '-o', output_template, '--print', 'after_move:filepath', url]
        else:
            fmt = 'best[ext=mp4]/best' if quality == 'best' else f'best[height<={quality}][ext=mp4]/best[height<={quality}]'
            args = ['-f', fmt, '--max-filesize', '100M', '-o', output_template, '--print', 'after_move:filepath', url]
        stdout, stderr, code = run_ytdlp(args)
        if code != 0:
            return jsonify({'error': 'Download failed', 'details': stderr[:500]}), 400
        filepath = stdout.strip().split('\n')[-1] if stdout else ''
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'File not found after download'}), 500
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        return jsonify({'success': True, 'title': os.path.splitext(filename)[0], 'ext': os.path.splitext(filename)[1][1:], 'filesize': filesize, 'filesize_human': format_size(filesize), 'filename': filename, 'filepath': filepath})
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
    output_template = os.path.join(temp_dir, 'video.%(ext)s')
    if quality == 'audio':
        args = ['-x', '--audio-format', 'mp3', '--audio-quality', '0', '--max-filesize', '100M', '-o', output_template, '--print', 'after_move:filepath', url]
    else:
        fmt = 'best[ext=mp4]/best' if quality == 'best' else f'best[height<={quality}][ext=mp4]/best[height<={quality}]'
        args = ['-f', fmt, '--max-filesize', '100M', '-o', output_template, '--print', 'after_move:filepath', url]
    stdout, stderr, code = run_ytdlp(args)
    if code != 0:
        return jsonify({'error': 'Download failed', 'details': stderr[:300]}), 400
    filepath = stdout.strip().split('\n')[-1] if stdout else ''
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 500
    return jsonify({'success': True, 'download_url': f'/api/serve?file={os.path.abspath(filepath)}', 'filename': os.path.basename(filepath), 'filesize': os.path.getsize(filepath), 'filesize_human': format_size(os.path.getsize(filepath))})

@app.route('/api/cleanup')
def cleanup():
    temp_base = tempfile.gettempdir()
    cleaned = 0
    for d in os.listdir(temp_base):
        d_path = os.path.join(temp_base, d)
        if os.path.isdir(d_path) and (d.startswith('tmp') or d.startswith('ytdl')):
            try:
                shutil.rmtree(d_path)
                cleaned += 1
            except:
                pass
    return jsonify({'cleaned': cleaned})

@app.route('/')
def index():
    return jsonify({
        'name': '90Tools Downloader API',
        'version': '2.1',
        'endpoints': {
            '/health': 'Check server status',
            '/api/info?url=...': 'Get video info',
            '/api/download?url=...quality=...': 'Download video (returns JSON)',
            '/api/download_direct': 'POST {url, quality} - download and get URL',
            '/api/serve?file=...': 'Download a file directly',
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
