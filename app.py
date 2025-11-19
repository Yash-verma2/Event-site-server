from flask import Flask, render_template, request, url_for, send_from_directory, jsonify
from flask_cors import CORS
import os, uuid
from werkzeug.utils import secure_filename
from PIL import Image  # For fast image resizing

UPLOAD_FOLDER = 'generated'
ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_MUSIC = {'mp3', 'wav', 'ogg'}
MAX_GALLERY = 8
MAX_IMAGE_SIZE = (1024, 1024)  # Resize large images

app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
CORS(app, resources={r"/*": {"origins": "*"}})

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed(filename, types):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in types


def save_image(file, path):
    """Resize image to MAX_IMAGE_SIZE and save"""
    img = Image.open(file)
    img.thumbnail(MAX_IMAGE_SIZE)
    img.save(path)


# ------------------------ GENERATOR ----------------------------
@app.route('/generate', methods=['POST'])
def generate():
    try:
        name = request.form.get('name', 'Friend')
        user_title = request.form.get('title', "").strip()
        messages = [m.strip() for m in request.form.get('messages', "").split("\n") if m.strip()][:20]
        template = request.form.get('template', 'birthday.html')

        title = user_title or {
            'birthday.html': "🎉 Happy Birthday",
            'anniversary.html': "💖 Happy Anniversary",
            'congratulations.html': "🎊 Congratulations"
        }.get(template, "🎉 Celebration")

        uid = uuid.uuid4().hex[:10]
        base = os.path.join(app.config['UPLOAD_FOLDER'], uid)
        asset_dir = os.path.join(base, "assets")
        os.makedirs(asset_dir, exist_ok=True)

        # ----------------- Handle Images -----------------
        def handle_file(file_key, default, prefix, types=ALLOWED_IMAGES):
            f = request.files.get(file_key)
            if f and allowed(f.filename, types):
                filename = f"{uid}_{prefix}_{secure_filename(f.filename)}"
                save_image(f, os.path.join(asset_dir, filename)) if types == ALLOWED_IMAGES else f.save(os.path.join(asset_dir, filename))
                return url_for("assets", uid=uid, filename=filename)
            return request.form.get(f"{file_key}_selected") or default

        main_image = handle_file("main_image", None, "main")
        gift_image = handle_file("gift_image", "/static/default_gift.png", "gift")
        music = handle_file("music", "/static/default_music.mp3", "music", ALLOWED_MUSIC)

        # ----------------- Gallery -----------------
        gallery_images = []
        for gallery_file in request.files.getlist("gallery")[:MAX_GALLERY]:
            if gallery_file and allowed(gallery_file.filename, ALLOWED_IMAGES):
                filename = f"{uid}_g_{secure_filename(gallery_file.filename)}"
                save_image(gallery_file, os.path.join(asset_dir, filename))
                gallery_images.append(url_for("assets", uid=uid, filename=filename))

        # ----------------- Render Main Page -----------------
        html = render_template(
            template,
            name=name,
            title=title,
            messages=messages,
            main_image=main_image,
            gift_image=gift_image,
            music=music,
            gallery_link=url_for("gallery_page", uid=uid)
        )
        with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

        # Only render gallery.html if gallery images exist
        if gallery_images:
            gallery_html = render_template("gallery.html", name=name, title=title, images=gallery_images, music=music)
            with open(os.path.join(base, "gallery.html"), "w", encoding="utf-8") as f:
                f.write(gallery_html)

        link = request.host_url.rstrip('/') + f"/generated/{uid}/"
        return jsonify({"link": link})

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ---------------------- GALLERY PAGE ----------------------
@app.route('/generated/<uid>/gallery')
def gallery_page(uid):
    asset_path = os.path.join(app.config['UPLOAD_FOLDER'], uid, "assets")
    images = [url_for("assets", uid=uid, filename=f) for f in os.listdir(asset_path) if f.startswith(uid + "_g_")]
    music_files = [f for f in os.listdir(asset_path) if f.startswith(uid + "_music_")]
    music = url_for("assets", uid=uid, filename=music_files[0]) if music_files else "/static/default_music.mp3"
    return render_template("gallery.html", name="Gallery", title="Memories", images=images, music=music)


# ---------------------- Serve Static Assets ----------------------
@app.route('/generated/<uid>/assets/<filename>')
def assets(uid, filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], uid, "assets"), filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
