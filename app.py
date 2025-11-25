import os
import uuid
import json
import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, render_template, request, url_for, jsonify, abort
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from PIL import Image
import io

# Cloudinary Imports
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------------- LOGGING CONFIGURATION ----------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ---------------- CONFIGURATION ----------------
class Config:
    # Cloudinary Config
    CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')
    
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-dev-key-please-change')
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024 
    ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ALLOWED_MUSIC = {'mp3', 'wav', 'ogg'}
    MAX_GALLERY = 8
    MAX_IMAGE_SIZE = (1024, 1024)

# Initialize App
app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
app.config.from_object(Config)

# Configure Cloudinary
if Config.CLOUDINARY_CLOUD_NAME and Config.CLOUDINARY_API_KEY and Config.CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=Config.CLOUDINARY_CLOUD_NAME,
        api_key=Config.CLOUDINARY_API_KEY,
        api_secret=Config.CLOUDINARY_API_SECRET
    )
    logger.info("Cloudinary configured successfully.")
else:
    logger.warning("Cloudinary credentials missing! App will fail to upload.")

CORS(app, resources={r"/*": {"origins": "*"}})

# Thread pool
executor = ThreadPoolExecutor(max_workers=4)

# ---------------- SECURITY HEADERS ----------------
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
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

def upload_image_task(file_storage, public_id, folder):
    """
    Worker function to upload images to Cloudinary.
    """
    try:
        # Reset file pointer
        file_storage.seek(0)
        
        # Upload to Cloudinary
        # transformation={'width': 1024, 'height': 1024, 'crop': 'limit', 'quality': 'auto'}
        result = cloudinary.uploader.upload(
            file_storage,
            public_id=public_id,
            folder=folder,
            resource_type="image",
            transformation=[
                {'width': 1024, 'height': 1024, 'crop': 'limit'},
                {'quality': 'auto', 'fetch_format': 'auto'}
            ]
        )
        return result.get('secure_url')
    except Exception as e:
        logger.error(f"Failed to upload image {public_id}: {str(e)}")
        return None

def upload_raw_task(data, public_id, folder):
    """
    Uploads JSON data as a raw file to Cloudinary.
    """
    try:
        # Convert dict to JSON string bytes
        json_data = json.dumps(data).encode('utf-8')
        
        result = cloudinary.uploader.upload(
            json_data,
            public_id=public_id,
            folder=folder,
            resource_type="raw",
            format="json" # Force extension
        )
        return result.get('secure_url')
    except Exception as e:
        logger.error(f"Failed to upload manifest {public_id}: {str(e)}")
        return None

def get_manifest_from_cloudinary(uid):
    """
    Fetches the manifest.json from Cloudinary using the public ID convention.
    """
    try:
        # Construct the URL based on convention: folder/manifest_{uid}.json
        # Or search for it. But constructing URL is faster if we know the structure.
        # However, 'raw' files in Cloudinary might have version numbers in URL.
        # Better to use the Admin API or just try to fetch via a predictable URL if possible.
        # BUT, Cloudinary URLs for raw files usually look like:
        # https://res.cloudinary.com/<cloud_name>/raw/upload/v<version>/<folder>/<public_id>
        # We don't know the version.
        # Alternative: Use the Search API (rate limited) or just store the manifest URL in the client?
        # The client only has the UID.
        # 
        # SOLUTION: We will use `cloudinary.api.resource` to get the details (including URL)
        # This requires the Admin API (which uses the same credentials).
        
        public_id = f"birthday_app/{uid}/manifest_{uid}.json"
        # Note: For raw files, the extension is part of the public_id usually if specified, 
        # but let's check how we uploaded it.
        
        # Actually, for high traffic, using the Admin API for every read is bad (rate limits).
        # A better stateless way:
        # When we generate, we return the UID.
        # The manifest URL is NOT predictable without the version if we want to be 100% sure, 
        # BUT Cloudinary supports fetching without version if we accept cached content.
        # URL format: https://res.cloudinary.com/<cloud_name>/raw/upload/<folder>/<public_id>
        
        cloud_name = Config.CLOUDINARY_CLOUD_NAME
        url = f"https://res.cloudinary.com/{cloud_name}/raw/upload/birthday_app/{uid}/manifest_{uid}.json"
        
        # Fetch the JSON
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Manifest not found at {url}: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching manifest for {uid}: {e}")
        return None

# ---------------- ROUTES ----------------

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "storage": "cloudinary"}), 200

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
                'birthday2.html': "🎊 Happy Birthday",
                'birthday3.html': "🎊 Happy Birthday"
            }
            title = title_map.get(template, "🎉 Celebration")
        else:
            title = user_title

        # Unique ID for this page
        uid = uuid.uuid4().hex[:10]
        folder_name = f"birthday_app/{uid}"

        # --- Parallel Asset Processing ---
        futures = {} # map future to type
        
        # Helper to process an upload
        def handle_upload(file_obj, prefix):
            if file_obj and allowed(file_obj.filename, Config.ALLOWED_IMAGES):
                safe_name = secure_filename(file_obj.filename).rsplit('.', 1)[0] # remove extension
                public_id = f"{prefix}_{safe_name}"
                return executor.submit(upload_image_task, file_obj, public_id, folder_name)
            return None

        # 1. Main & Gift Images
        main_future = handle_upload(request.files.get("main_image"), "main")
        gift_future = handle_upload(request.files.get("gift_image"), "gift")

        # 2. Gallery Images
        gallery_futures = []
        for i, g_file in enumerate(request.files.getlist("gallery")[:Config.MAX_GALLERY]):
            fut = handle_upload(g_file, f"gallery_{i}")
            if fut:
                gallery_futures.append(fut)

        # 3. Music (Upload as raw or video resource_type='video' for audio in Cloudinary)
        # For simplicity, let's keep music handling simple. 
        # If user uploads music, we upload it.
        music_file = request.files.get("music")
        music_url = "/static/default_music.mp3" # Default fallback
        music_future = None
        
        if music_file and allowed(music_file.filename, Config.ALLOWED_MUSIC):
             # Cloudinary treats audio as 'video' resource type usually, or 'raw'
             # Let's use 'video' for audio to get streaming capabilities if needed, or just 'auto'
             # For simple mp3, 'video' resource type is correct.
             pass 
             # TODO: Implement music upload if needed. For now, let's stick to defaults or external URLs 
             # to save bandwidth/complexity, or upload as raw.
             # Let's skip custom music upload to Cloudinary for this iteration to reduce risk, 
             # unless requested. The prompt didn't explicitly ask for music persistence but "link" persistence.
             # But if we don't persist music, the custom music will be lost.
             # Let's try to upload it.
             
             def upload_music_task(f_obj, pid, fldr):
                 f_obj.seek(0)
                 res = cloudinary.uploader.upload(f_obj, public_id=pid, folder=fldr, resource_type="video")
                 return res.get('secure_url')
                 
             safe_music_name = secure_filename(music_file.filename).rsplit('.', 1)[0]
             music_future = executor.submit(upload_music_task, music_file, f"music_{safe_music_name}", folder_name)

        # --- Resolve Futures ---
        
        # Main Image
        main_url = None
        if main_future:
            main_url = main_future.result()
        if not main_url:
            main_url = request.form.get("main_image_selected")

        # Gift Image
        gift_url = None
        if gift_future:
            gift_url = gift_future.result()
        if not gift_url:
            gift_url = request.form.get("gift_image_selected") or "/static/default_gift.png"

        # Gallery Images
        gallery_urls = []
        for fut in gallery_futures:
            url = fut.result()
            if url:
                gallery_urls.append(url)
        
        # Music
        if music_future:
            uploaded_music_url = music_future.result()
            if uploaded_music_url:
                music_url = uploaded_music_url
        else:
             music_url = request.form.get('music_selected') or request.form.get('music_option') or music_url

        # --- Create Manifest ---
        manifest_data = {
            "template": template,
            "created_at": time.time(),
            "uid": uid,
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

        # Upload Manifest to Cloudinary
        # We upload it as a raw file so we can fetch it back later
        manifest_url = upload_raw_task(manifest_data, f"manifest_{uid}.json", folder_name)
        
        if not manifest_url:
            raise Exception("Failed to save page data (manifest upload failed)")

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
        data = get_manifest_from_cloudinary(uid)
        
        if not data:
            abort(404)

        return render_template(data['template'], **data['context'])
    except Exception as e:
        logger.error(f"Error serving page {uid}: {e}")
        abort(404)

@app.route('/generated/<uid>/gallery')
def gallery_page(uid):
    try:
        data = get_manifest_from_cloudinary(uid)
        
        if not data:
            abort(404)
            
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

if __name__ == "__main__":
    print("WARNING: Run with Gunicorn in production!")
    app.run(host="0.0.0.0", port=5001, debug=True)