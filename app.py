from flask import Flask, render_template, request, url_for, send_from_directory, jsonify
from flask_cors import CORS
import os, uuid, json
from werkzeug.utils import secure_filename
from PIL import Image
from io import BytesIO

# ---------------- CONFIG ----------------
UPLOAD_FOLDER = 'generated'
ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_MUSIC = {'mp3', 'wav', 'ogg'}
MAX_GALLERY = 8
MAX_IMAGE_SIZE = (1024, 1024)

app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
CORS(app, resources={r"/*": {"origins": "*"}})
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- UTILITIES ----------------
def allowed(filename, types):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in types

def save_image(file, path):
    """Resize and save image efficiently"""
    img = Image.open(file)
    img.thumbnail(MAX_IMAGE_SIZE)
    img.save(path)

# ---------------- BASE PAGE ----------------
@app.route('/generated/<uid>/')
def generated_page(uid):
    path = os.path.join(app.config['UPLOAD_FOLDER'], uid)
    return send_from_directory(path, "index.html")

# ---------------- TEST / HEALTH ----------------
@app.route('/test')
def test():
    return {"status": "success", "message": "Backend is working!"}

@app.route('/health')
def health():
    return "OK"

# ---------------- LANDING PAGE ----------------
@app.route('/')
def landing():
    return render_template("index.html")

# ---------------- GENERATOR ----------------
@app.route('/generate', methods=['POST'])
def generate():
    try:
        # ---------- Form Data ----------
        name = request.form.get('name', 'Friend')
        user_title = request.form.get('title', "").strip()
        messages = [m.strip() for m in request.form.get('messages', "").split("\n") if m.strip()][:20]
        template = request.form.get('template', 'birthday.html')

        # ---------- Determine Title ----------
        if not user_title:
            title = {
                'birthday.html': "🎉 Happy Birthday",
                'anniversary.html': "💖 Happy Anniversary",
                'congratulations.html': "🎊 Congratulations"
            }.get(template, "🎉 Celebration")
        else:
            title = user_title

        # ---------- Prepare Folder ----------
        uid = uuid.uuid4().hex[:10]
        base = os.path.join(app.config['UPLOAD_FOLDER'], uid)
        asset_dir = os.path.join(base, "assets")
        os.makedirs(asset_dir, exist_ok=True)

        # ---------- Handle Images ----------
        def handle_image(file_key, default="/static/default.png", prefix="img"):
            file = request.files.get(file_key)
            selected = request.form.get(f"{file_key}_selected")
            if file and allowed(file.filename, ALLOWED_IMAGES):
                filename = f"{uid}_{prefix}_{secure_filename(file.filename)}"
                save_image(file, os.path.join(asset_dir, filename))
                return url_for("assets", uid=uid, filename=filename, _external=True)
            elif selected:
                return selected
            return default

        main_image = handle_image("main_image", default=None, prefix="main")
        gift_image = handle_image("gift_image", default="/static/default_gift.png", prefix="gift")

        # ---------- Handle Music ----------
        music_file = request.files.get("music")
        music_selected = request.form.get('music_selected')
        music_option = request.form.get('music_option')
        if music_file and allowed(music_file.filename, ALLOWED_MUSIC):
            filename = f"{uid}_music_{secure_filename(music_file.filename)}"
            music_file.save(os.path.join(asset_dir, filename))
            music = url_for("assets", uid=uid, filename=filename, _external=True)
        elif music_selected:
            music = music_selected
        elif music_option:
            music = music_option
        else:
            music = "/static/default_music.mp3"

        # ---------- Handle Gallery ----------
        gallery_images = []
        for gallery_file in request.files.getlist("gallery")[:MAX_GALLERY]:
            if gallery_file and allowed(gallery_file.filename, ALLOWED_IMAGES):
                filename = f"{uid}_g_{secure_filename(gallery_file.filename)}"
                save_image(gallery_file, os.path.join(asset_dir, filename))
                gallery_images.append(url_for("assets", uid=uid, filename=filename, _external=True))

        # ---------- Render Index Page ----------
        html = render_template(
            template,
            name=name,
            title=title,
            messages=messages,
            main_image=main_image,
            gift_image=gift_image,
            music=music,
            gallery_link=url_for("gallery_page", uid=uid, _external=True)
        )
        with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

        # ---------- Render Gallery Page (if images exist) ----------
        if gallery_images:
            gallery_html = render_template(
                "gallery.html",
                name=name,
                title=title,
                images=gallery_images,
                music=music
            )
            with open(os.path.join(base, "gallery.html"), "w", encoding="utf-8") as f:
                f.write(gallery_html)

        # ---------- Return Link ----------
        link = request.host_url.rstrip('/') + f"/generated/{uid}/"
        return jsonify({"link": link})

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500

# ---------------- GALLERY PAGE ----------------
@app.route('/generated/<uid>/gallery')
def gallery_page(uid):
    base = os.path.join(app.config['UPLOAD_FOLDER'], uid)
    asset_path = os.path.join(base, "assets")
    
    # Load gallery images
    images = [url_for("assets", uid=uid, filename=f, _external=True)
              for f in os.listdir(asset_path) if f.startswith(uid + "_g_")]
    
    # Load music
    music_files = [f for f in os.listdir(asset_path) if f.startswith(uid + "_music_")]
    music = url_for("assets", uid=uid, filename=music_files[0], _external=True) if music_files else "/static/default_music.mp3"
    
    return render_template(
        "gallery.html",
        name="Gallery",
        title="Memories",
        images=images,
        music=music
    )

# ---------------- SERVE ASSETS ----------------
@app.route('/generated/<uid>/assets/<filename>')
def assets(uid, filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], uid, "assets"), filename)

# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
