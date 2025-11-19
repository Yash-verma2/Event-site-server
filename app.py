from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from flask_cors import CORS
import os, uuid
from werkzeug.utils import secure_filename
from jinja2.exceptions import TemplateNotFound

UPLOAD_FOLDER = 'generated'
ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_MUSIC = {'mp3', 'wav', 'ogg'}
MAX_GALLERY = 8

app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
CORS(app, resources={r"/*": {"origins": "*"}})

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def allowed(filename, types):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in types


# ------------------------ Base display of generated page -------------------------
@app.route('/generated/<uid>/')
def generated_page(uid):
    # Return generated index.html
    path = os.path.join(app.config['UPLOAD_FOLDER'], uid)
    return send_from_directory(path, "index.html")


# ------------------------ Test Routes -------------------------
@app.route('/test')
def test():
    return {"status": "success", "message": "Backend is working!"}


@app.route('/health')
def health():
    return "OK"


# ------------------------ Landing Page -------------------------
@app.route('/')
def landing():
    return render_template("index.html")


# ------------------------ GENERATOR ----------------------------
@app.route('/generate', methods=['POST'])
def generate():
    try:
        name = request.form.get('name', 'Friend')
        user_title = request.form.get('title', "").strip()
        messages_raw = request.form.get('messages', "")
        messages = [m.strip() for m in messages_raw.split("\n") if m.strip()][:20]

        template = request.form.get('template', 'birthday.html')

        if not user_title:
            if template == 'birthday.html':
                title = "🎉 Happy Birthday"
            elif template == 'anniversary.html':
                title = "💖 Happy Anniversary"
            elif template == 'congratulations.html':
                title = "🎊 Congratulations"
            else:
                title = "🎉 Celebration"
        else:
            title = user_title

        uid = uuid.uuid4().hex[:10]
        base = os.path.join(app.config['UPLOAD_FOLDER'], uid)
        asset_dir = os.path.join(base, "assets")
        os.makedirs(asset_dir, exist_ok=True)

        # MAIN IMAGE
        main_image = None
        main_file = request.files.get("main_image")
        if main_file and allowed(main_file.filename, ALLOWED_IMAGES):
            filename = uid + "_main_" + secure_filename(main_file.filename)
            main_file.save(os.path.join(asset_dir, filename))
            main_image = url_for("assets", uid=uid, filename=filename, _external=True)

        # GIFT IMAGE
        gift_image_selected = request.form.get('gift_image_selected')
        gift_file = request.files.get("gift_image")

        gift_image = "/static/default_gift.png"
        if gift_file and allowed(gift_file.filename, ALLOWED_IMAGES):
            filename = uid + "_gift_" + secure_filename(gift_file.filename)
            gift_file.save(os.path.join(asset_dir, filename))
            gift_image = url_for("assets", uid=uid, filename=filename, _external=True)
        elif gift_image_selected:
            gift_image = gift_image_selected

        # MUSIC
        music_selected = request.form.get('music_selected')
        music_option = request.form.get('music_option')
        music_file = request.files.get("music")

        music = "/static/default_music.mp3"
        if music_file and allowed(music_file.filename, ALLOWED_MUSIC):
            filename = uid + "_music_" + secure_filename(music_file.filename)
            music_file.save(os.path.join(asset_dir, filename))
            music = url_for("assets", uid=uid, filename=filename, _external=True)
        elif music_selected:
            music = music_selected
        elif music_option:
            music = music_option

        # GALLERY IMAGES
        gallery_images = []
        for gallery_file in request.files.getlist("gallery")[:MAX_GALLERY]:
            if gallery_file and allowed(gallery_file.filename, ALLOWED_IMAGES):
                filename = uid + "_g_" + secure_filename(gallery_file.filename)
                gallery_file.save(os.path.join(asset_dir, filename))
                gallery_images.append(url_for("assets", uid=uid, filename=filename, _external=True))

        # Render main page
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

        # Write gallery.html (only for fallback – your template WILL be used)
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

        # Final link
        link = request.host_url.rstrip('/') + f"/generated/{uid}/"

        return jsonify({"link": link})

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ---------------------- GALLERY PAGE (USE TEMPLATE) ----------------------
@app.route('/generated/<uid>/gallery')
def gallery_page(uid):
    asset_path = os.path.join(app.config['UPLOAD_FOLDER'], uid, "assets")

    # -------- Load Gallery Images --------
    images = []
    for file in os.listdir(asset_path):
        if file.startswith(uid + "_g_"):
            images.append(url_for("assets", uid=uid, filename=file, _external=True))

    # -------- Load Music --------
    music = None
    for file in os.listdir(asset_path):
        if file.startswith(uid + "_music_"):
            music = url_for("assets", uid=uid, filename=file, _external=True)

    # If no music uploaded, use default
    if not music:
        music = "/static/default_music.mp3"

    return render_template(
        "gallery.html",
        name="Gallery",
        title="Memories",
        images=images,     # IMPORTANT FIX
        music=music        # IMPORTANT FIX
    )




# ---------------------- SERVE STATIC ASSETS ----------------------
@app.route('/generated/<uid>/assets/<filename>')
def assets(uid, filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], uid, "assets"), filename)


# ----------------------------- RUN SERVER -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)

