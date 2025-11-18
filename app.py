from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from flask_cors import CORS
import os, uuid
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'generated'
ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_MUSIC = {'mp3', 'wav', 'ogg'}
MAX_GALLERY = 8

app = Flask(__name__, static_url_path="/static", static_folder="static")
CORS(app, resources={r"/*": {"origins": "*"}})

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed(filename, types):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in types

# ------------------------ Landing Page -------------------------
@app.route('/')
def landing():
    return render_template('landing.html')

# ------------------------ GENERATOR ----------------------------
@app.route('/generate', methods=['POST'])
def generate():
    name = request.form.get('name')
    user_title = request.form.get('title', "").strip()
    messages_raw = request.form.get('messages', "")
    messages = [m.strip() for m in messages_raw.split("\n") if m.strip()][:20]

    # Get template from form, default to birthday.html
    template = request.form.get('template', 'birthday.html')

    # Determine default title based on template if user did not enter one
    if not user_title:
        if template == 'birthday.html':
            title = f"🎉 Happy Birthday"
        elif template == 'anniversary.html':
            title = f"💖 Happy Anniversary"
        elif template == 'congratulations.html':
            title = f"🎊 Congratulations"
        else:  # custom.html or unknown
            title = ""
    else:
        title = user_title

    uid = uuid.uuid4().hex[:10]
    base = os.path.join(app.config['UPLOAD_FOLDER'], uid)
    asset_dir = os.path.join(base, "assets")
    os.makedirs(asset_dir, exist_ok=True)

    # ------------ MAIN IMAGE ------------
    f = request.files.get("main_image")
    main_image = None
    if f and allowed(f.filename, ALLOWED_IMAGES):
        filename = uid + "_main_" + secure_filename(f.filename)
        f.save(os.path.join(asset_dir, filename))
        main_image = url_for("assets", uid=uid, filename=filename)

    # ------------ GIFT IMAGE ------------
    gift_image_selected = request.form.get('gift_image_selected')
    f = request.files.get("gift_image")
    
    if f and allowed(f.filename, ALLOWED_IMAGES):
        filename = uid + "_gift_" + secure_filename(f.filename)
        f.save(os.path.join(asset_dir, filename))
        gift_image = url_for("assets", uid=uid, filename=filename)
    elif gift_image_selected:
        gift_image = gift_image_selected
    else:
        gift_image = "/static/default_gift.png"

    # ------------ MUSIC ------------
    music_selected = request.form.get('music_selected')
    music_option = request.form.get('music_option')
    f = request.files.get("music")

    if f and f.filename and allowed(f.filename, ALLOWED_MUSIC):
        # User uploaded a music file
        filename = uid + "_music_" + secure_filename(f.filename)
        f.save(os.path.join(asset_dir, filename))
        music = url_for("assets", uid=uid, filename=filename)
    elif music_selected and music_selected.strip():
        # User selected a preset music
        music = music_selected.strip()
    elif music_option and music_option.strip():
        # User selected a preset music from dropdown
        music = music_option.strip()
    else:
        # Default music
        music = "/static/default_music.mp3"

    # ------------ GALLERY IMAGES ------------
    gallery_images = []
    for f in request.files.getlist("gallery")[:MAX_GALLERY]:
        if f and allowed(f.filename, ALLOWED_IMAGES):
            filename = uid + "_g_" + secure_filename(f.filename)
            f.save(os.path.join(asset_dir, filename))
            gallery_images.append(url_for("assets", uid=uid, filename=filename))

    # ------------ Render Selected Template ------------
    html = render_template(
        template,
        name=name,
        title=title,
        messages=messages,
        main_image=main_image,
        gift_image=gift_image,
        music=music,
        gallery_link=url_for('gallery_page', uid=uid)
    )

    with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # ------------ Render Gallery Page (universal) ------------
    gallery_html = render_template(
        "gallery.html",
        name=name,
        title=title,
        images=gallery_images,
        music=music
    )

    with open(os.path.join(base, "gallery.html"), "w", encoding="utf-8") as f:
        f.write(gallery_html)

    # ------------ FINAL LINK ------------
    # Use environment variable for host or fallback to request host
    base_url = os.environ.get('RENDER_EXTERNAL_URL', f"http://{request.host}")
    link = f"{base_url}/generated/{uid}/"

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {"link": link}
    else:
        return redirect(link)

# ---------------------- SERVE STATIC FILES ----------------------
@app.route('/generated/<uid>/')
def serve_generated(uid):
    path = os.path.join(app.config['UPLOAD_FOLDER'], uid)
    return send_from_directory(path, "index.html")

@app.route('/generated/<uid>/gallery')
def gallery_page(uid):
    path = os.path.join(app.config['UPLOAD_FOLDER'], uid)
    return send_from_directory(path, "gallery.html")

@app.route('/generated/<uid>/assets/<filename>')
def assets(uid, filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], uid, "assets")
    return send_from_directory(path, filename)

# ----------------------------- RUN SERVER -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5001))
    app.run(host="0.0.0.0", port=port, debug=False)