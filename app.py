from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from flask_cors import CORS
import os, uuid
from werkzeug.utils import secure_filename
from jinja2.exceptions import TemplateNotFound

UPLOAD_FOLDER = 'generated'
ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_MUSIC = {'mp3', 'wav', 'ogg'}
MAX_GALLERY = 8

app = Flask(
    __name__,
    static_url_path="/static",
    static_folder="static",
    template_folder="templates"
)
CORS(app)

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed(filename, types):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in types


# ------------------------ Home ------------------------
@app.route("/")
def landing():
    return render_template("index.html")


# ------------------------ Generate ------------------------
@app.route("/generate", methods=["POST"])
def generate():
    try:
        name = request.form.get("name", "Friend")
        user_title = request.form.get("title", "").strip()

        # Messages list
        messages_raw = request.form.get("messages", "")
        messages = [m.strip() for m in messages_raw.split("\n") if m.strip()][:20]

        template = request.form.get("template", "birthday.html")

        # Auto default title
        if not user_title:
            titles = {
                "birthday.html": "🎉 Happy Birthday",
                "anniversary.html": "💖 Happy Anniversary",
                "congratulations.html": "🎊 Congratulations"
            }
            title = titles.get(template, "🎉 Celebration")
        else:
            title = user_title

        uid = uuid.uuid4().hex[:10]
        base = os.path.join(UPLOAD_FOLDER, uid)
        assets_dir = os.path.join(base, "assets")
        os.makedirs(assets_dir, exist_ok=True)

        # -------------------- Main Image --------------------
        main_image = None
        main_file = request.files.get("main_image")
        if main_file and allowed(main_file.filename, ALLOWED_IMAGES):
            file = uid + "_main_" + secure_filename(main_file.filename)
            path = os.path.join(assets_dir, file)
            main_file.save(path)
            main_image = url_for("assets", uid=uid, filename=file, _external=True)

        # -------------------- Gift Image --------------------
        gift_image = "/static/default_gift.png"
        gift_file = request.files.get("gift_image")
        gift_image_selected = request.form.get("gift_image_selected")

        if gift_file and allowed(gift_file.filename, ALLOWED_IMAGES):
            file = uid + "_gift_" + secure_filename(gift_file.filename)
            path = os.path.join(assets_dir, file)
            gift_file.save(path)
            gift_image = url_for("assets", uid=uid, filename=file, _external=True)
        elif gift_image_selected:
            gift_image = gift_image_selected

        # -------------------- Music --------------------
        music = "/static/default_music.mp3"
        music_file = request.files.get("music")
        music_selected = request.form.get("music_selected")
        music_option = request.form.get("music_option")

        if music_file and allowed(music_file.filename, ALLOWED_MUSIC):
            file = uid + "_music_" + secure_filename(music_file.filename)
            path = os.path.join(assets_dir, file)
            music_file.save(path)
            music = url_for("assets", uid=uid, filename=file, _external=True)
        elif music_selected:
            music = music_selected
        elif music_option:
            music = music_option

        # -------------------- Gallery Images (FIXED) --------------------
        gallery_images = []
        gallery_files = request.files.getlist("gallery[]")  # IMPORTANT FIX

        for g in gallery_files[:MAX_GALLERY]:
            if g and allowed(g.filename, ALLOWED_IMAGES):
                file = uid + "_g_" + secure_filename(g.filename)
                path = os.path.join(assets_dir, file)
                g.save(path)
                gallery_images.append(url_for("assets", uid=uid, filename=file, _external=True))

        print("Gallery Received:", gallery_images)  # Debug

        # -------------------- Render Main Template --------------------
        try:
            html = render_template(
                template,
                name=name,
                title=title,
                messages=messages,
                main_image=main_image,
                gift_image=gift_image,
                music=music,
                images=gallery_images,
                gallery_link=url_for("gallery_page", uid=uid, _external=True)
            )
        except TemplateNotFound:
            html = f"<h1>{title} {name}</h1>"

        with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

        # -------------------- Render Gallery Page Always (FIXED) --------------------
        gallery_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Gallery - {name}</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gradient-to-br from-blue-400 to-purple-600 min-h-screen p-8">
            <h1 class="text-center text-4xl text-white font-bold mb-8">Gallery of {name}</h1>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {''.join([f'<img src="{img}" class="w-full h-64 object-cover rounded-xl shadow-xl">' for img in gallery_images])}
            </div>

            <div class="text-center mt-8">
                <a href="{url_for('serve_generated', uid=uid, _external=True)}"
                   class="px-6 py-3 bg-white text-purple-700 font-bold rounded-full">
                    ← Back to Main Page
                </a>
            </div>

            <audio autoplay loop>
                <source src="{music}">
            </audio>
        </body>
        </html>
        """

        with open(os.path.join(base, "gallery.html"), "w", encoding="utf-8") as f:
            f.write(gallery_html)

        # -------------------- Final Link --------------------
        link = request.host_url.rstrip('/') + f"/generated/{uid}/"
        return redirect(link)

    except Exception as e:
        return f"Error: {e}", 500


# ------------------------ Routes ------------------------
@app.route('/generated/<uid>/')
def serve_generated(uid):
    folder = os.path.join(UPLOAD_FOLDER, uid)
    return send_from_directory(folder, "index.html")


@app.route('/generated/<uid>/gallery')
def gallery_page(uid):
    folder = os.path.join(UPLOAD_FOLDER, uid)
    return send_from_directory(folder, "gallery.html")


@app.route('/generated/<uid>/assets/<filename>')
def assets(uid, filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, uid, "assets"), filename)


# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
