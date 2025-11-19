import os
import uuid
import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, render_template, request, url_for, send_from_directory, jsonify, abort
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from PIL import Image

# ---------------- LOGGING CONFIGURATION ----------------
# Production logging format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ---------------- CONFIGURATION ----------------
class Config:
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'generated')
    # Secret key should be loaded from environment variable in production
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-dev-key-please-change')
    # Limit max upload size to 100MB to prevent DoS attacks
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024 
    ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ALLOWED_MUSIC = {'mp3', 'wav', 'ogg'}
    MAX_GALLERY = 8
    MAX_IMAGE_SIZE = (1024, 1024)

# Initialize App
app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
app.config.from_object(Config)

# CORS: Allow all origins for now, but in real production, restrict this to your frontend domain
CORS(app, resources={r"/*": {"origins": "*"}})

# Ensure storage exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Thread pool for async tasks (1 pool per worker process)
executor = ThreadPoolExecutor(max_workers=4)

# ---------------- SECURITY HEADERS ----------------
@app.after_request
def add_security_headers(response):
    """Add standard security headers for production."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # HSTS - Force HTTPS (Uncomment if running strictly over HTTPS)
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# ---------------- ERROR HANDLERS ----------------
@app.errorhandler(413)
@app.errorhandler(RequestEntityTooLarge)
def file_too_large(e):
    return jsonify({"error": "File is too large. Maximum limit is 100MB."}), 413

@app.errorhandler(404)
def page_not_found(e):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Server Error: {e}")
    return jsonify({"error": "Internal server error"}), 500

# ---------------- UTILITIES ----------------
def allowed(filename, types):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in types

def process_image_task(file_storage, save_path):
    """
    Worker function to resize and optimize images.
    Run in a separate thread to avoid blocking the main request.
    """
    try:
        img = Image.open(file_storage)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        img.thumbnail(Config.MAX_IMAGE_SIZE)
        
        # optimize=True strips metadata, quality=85 balances size/visuals
        img.save(save_path, optimize=True, quality=85) 
        return True
    except Exception as e:
        logger.error(f"Failed to process image {save_path}: {str(e)}")
        return False

# ---------------- ROUTES ----------------

@app.route('/health')
def health():
    """
    Production health check. 
    Verifies the app is running AND filesystem is writable.
    """
    try:
        # Check write permissions
        test_file = os.path.join(app.config['UPLOAD_FOLDER'], '.health')
        with open(test_file, 'w') as f:
            f.write('ok')
        os.remove(test_file)
        return jsonify({"status": "healthy", "storage": "writable"}), 200
    except Exception as e:
        logger.critical(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 503

@app.route('/')
def landing():
    return render_template("index.html")

@app.route('/generate', methods=['POST'])
def generate():
    start_time = time.time()
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[{request_id}] Starting generation request")

    try:
        # --- Input Validation & Setup ---
        name = request.form.get('name', 'Friend')
        user_title = request.form.get('title', "").strip()
        raw_messages = request.form.get('messages', "")
        messages = [m.strip() for m in raw_messages.split("\n") if m.strip()][:20]
        template = request.form.get('template', 'birthday.html')

        # Safe title logic
        if not user_title:
            title_map = {
                'birthday.html': "🎉 Happy Birthday",
                'anniversary.html': "💖 Happy Anniversary",
                'congratulations.html': "🎊 Congratulations"
            }
            title = title_map.get(template, "🎉 Celebration")
        else:
            title = user_title

        # Create directory structure
        uid = uuid.uuid4().hex[:10]
        base_path = os.path.join(app.config['UPLOAD_FOLDER'], uid)
        asset_dir = os.path.join(base_path, "assets")
        os.makedirs(asset_dir, exist_ok=True)

        # --- Parallel Asset Processing ---
        futures = []
        
        def get_asset_url(fname):
            return url_for("assets", uid=uid, filename=fname, _external=True)

        # Helper to process an upload
        def handle_upload(file_obj, prefix, default_url):
            if file_obj and allowed(file_obj.filename, Config.ALLOWED_IMAGES):
                safe_name = secure_filename(file_obj.filename)
                fname = f"{uid}_{prefix}_{safe_name}"
                save_path = os.path.join(asset_dir, fname)
                futures.append(executor.submit(process_image_task, file_obj, save_path))
                return get_asset_url(fname)
            return None

        # 1. Main & Gift Images
        main_url = handle_upload(request.files.get("main_image"), "main", None)
        if not main_url: 
            main_url = request.form.get("main_image_selected")

        gift_url = handle_upload(request.files.get("gift_image"), "gift", None)
        if not gift_url:
            gift_url = request.form.get("gift_image_selected") or "/static/default_gift.png"

        # 2. Gallery Images
        gallery_urls = []
        for g_file in request.files.getlist("gallery")[:Config.MAX_GALLERY]:
            url = handle_upload(g_file, "g", None)
            if url:
                gallery_urls.append(url)

        # 3. Music (Synchronous copy)
        music_file = request.files.get("music")
        music_url = "/static/default_music.mp3"
        
        if music_file and allowed(music_file.filename, Config.ALLOWED_MUSIC):
            fname = f"{uid}_music_{secure_filename(music_file.filename)}"
            music_file.save(os.path.join(asset_dir, fname))
            music_url = get_asset_url(fname)
        else:
            # Fallback options
            music_url = request.form.get('music_selected') or request.form.get('music_option') or music_url

        # --- Wait for Image Processing ---
        # We wait for images to ensure they exist before sending the JSON response
        for future in futures:
            future.result()

        # --- Create Manifest ---
        manifest_data = {
            "template": template,
            "created_at": time.time(),
            "context": {
                "name": name,
                "title": title,
                "messages": messages,
                "main_image": main_url,
                "gift_image": gift_url,
                "music": music_url,
                "gallery_link": url_for("gallery_page", uid=uid, _external=True),
                "gallery_images": gallery_urls
            }
        }

        with open(os.path.join(base_path, "manifest.json"), "w") as f:
            json.dump(manifest_data, f)

        duration = time.time() - start_time
        logger.info(f"[{request_id}] Generation complete in {duration:.2f}s. UID: {uid}")
        
        link = request.host_url.rstrip('/') + f"/generated/{uid}/"
        return jsonify({"link": link, "uid": uid})

    except Exception as e:
        logger.error(f"[{request_id}] Generation failed: {str(e)}", exc_info=True)
        return jsonify({"error": "An error occurred while generating your page."}), 500

# ---------------- PAGE SERVING ----------------

@app.route('/generated/<uid>/')
def generated_page(uid):
    try:
        base_path = os.path.join(app.config['UPLOAD_FOLDER'], uid)
        manifest_path = os.path.join(base_path, "manifest.json")
        
        if not os.path.exists(manifest_path):
            abort(404)

        with open(manifest_path, 'r') as f:
            data = json.load(f)

        return render_template(data['template'], **data['context'])
    except Exception as e:
        logger.error(f"Error serving page {uid}: {e}")
        abort(404)

@app.route('/generated/<uid>/gallery')
def gallery_page(uid):
    try:
        base_path = os.path.join(app.config['UPLOAD_FOLDER'], uid)
        manifest_path = os.path.join(base_path, "manifest.json")
        
        if not os.path.exists(manifest_path):
            abort(404)
            
        with open(manifest_path, 'r') as f:
            data = json.load(f)
            
        ctx = data['context']
        return render_template(
            "gallery.html",
            name="Gallery",
            title="Memories",
            images=ctx.get('gallery_images', []),
            music=ctx.get('music')
        )
    except Exception:
        abort(404)

@app.route('/generated/<uid>/assets/<filename>')
def assets(uid, filename):
    # Securely serve files from the specific UID folder
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], uid, "assets"), filename)

if __name__ == "__main__":
    print("WARNING: Run with Gunicorn in production!")
    print("Example: gunicorn -c gunicorn_config.py app:app")
    app.run(host="0.0.0.0", port=5001, debug=True)