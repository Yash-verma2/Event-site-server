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
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed(filename, types):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in types

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
    try:
        return render_template('index.html')
    except TemplateNotFound:
        # Fallback to a simple HTML page
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Birthday Page Generator</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-100 min-h-screen flex items-center justify-center">
            <div class="bg-white p-8 rounded-lg shadow-md max-w-md w-full text-center">
                <h1 class="text-2xl font-bold text-blue-600 mb-4">🎉 Birthday Page Generator</h1>
                <p class="text-gray-600 mb-4">Template files are being set up. Please check back soon!</p>
                <div class="space-y-2">
                    <a href="/test" class="block text-blue-500 hover:underline">Test Backend</a>
                    <a href="/health" class="block text-blue-500 hover:underline">Health Check</a>
                </div>
            </div>
        </body>
        </html>
        """

# ------------------------ GENERATOR ----------------------------
@app.route('/generate', methods=['POST'])
def generate():
    try:
        name = request.form.get('name', 'Friend')
        user_title = request.form.get('title', "").strip()
        messages_raw = request.form.get('messages', "")
        messages = [m.strip() for m in messages_raw.split("\n") if m.strip()][:20]

        # Get template from form, default to birthday.html
        template = request.form.get('template', 'birthday.html')

        # Determine default title based on template if user did not enter one
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

        # ------------ MAIN IMAGE ------------
        main_file = request.files.get("main_image")
        main_image = None
        if main_file and allowed(main_file.filename, ALLOWED_IMAGES):
            filename = uid + "_main_" + secure_filename(main_file.filename)
            filepath = os.path.join(asset_dir, filename)
            main_file.save(filepath)
            main_image = url_for("assets", uid=uid, filename=filename, _external=True)

        # ------------ GIFT IMAGE ------------
        gift_image_selected = request.form.get('gift_image_selected')
        gift_file = request.files.get("gift_image")
        
        gift_image = "/static/default_gift.png"  # default
        if gift_file and allowed(gift_file.filename, ALLOWED_IMAGES):
            filename = uid + "_gift_" + secure_filename(gift_file.filename)
            filepath = os.path.join(asset_dir, filename)
            gift_file.save(filepath)
            gift_image = url_for("assets", uid=uid, filename=filename, _external=True)
        elif gift_image_selected:
            gift_image = gift_image_selected

        # ------------ MUSIC ------------
        music_selected = request.form.get('music_selected')
        music_option = request.form.get('music_option')
        music_file = request.files.get("music")

        music = "/static/default_music.mp3"  # default
        if music_file and music_file.filename and allowed(music_file.filename, ALLOWED_MUSIC):
            filename = uid + "_music_" + secure_filename(music_file.filename)
            filepath = os.path.join(asset_dir, filename)
            music_file.save(filepath)
            music = url_for("assets", uid=uid, filename=filename, _external=True)
        elif music_selected and music_selected.strip():
            music = music_selected.strip()
        elif music_option and music_option.strip():
            music = music_option.strip()

        # ------------ GALLERY IMAGES ------------
        gallery_images = []
        for gallery_file in request.files.getlist("gallery")[:MAX_GALLERY]:
            if gallery_file and allowed(gallery_file.filename, ALLOWED_IMAGES):
                filename = uid + "_g_" + secure_filename(gallery_file.filename)
                filepath = os.path.join(asset_dir, filename)
                gallery_file.save(filepath)
                gallery_images.append(url_for("assets", uid=uid, filename=filename, _external=True))

        # ------------ Render Selected Template ------------
        try:
            html = render_template(
                template,
                name=name,
                title=title,
                messages=messages,
                main_image=main_image,
                gift_image=gift_image,
                music=music,
                gallery_link=url_for('gallery_page', uid=uid, _external=True)
            )
        except TemplateNotFound:
            # Fallback to simple template
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>{title} {name}</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="min-h-screen flex items-center justify-center p-8 bg-gradient-to-br from-pink-400 to-purple-600">
                <div class="bg-white/90 backdrop-blur-sm rounded-3xl shadow-2xl p-8 max-w-md w-full text-center">
                    <h1 class="text-4xl font-bold text-purple-700 mb-4">{title} {name}! 🎉</h1>
                    <div class="space-y-4 mb-6">
                        {"".join([f'<p class="text-lg text-gray-700">{message}</p>' for message in messages])}
                    </div>
                    {f'<img src="{main_image}" alt="Main" class="w-48 h-48 rounded-full mx-auto mb-6 object-cover border-4 border-purple-500">' if main_image else ''}
                    <audio autoplay loop>
                        <source src="{music}" type="audio/mpeg">
                        Your browser does not support the audio element.
                    </audio>
                    {f'<a href="{url_for("gallery_page", uid=uid, _external=True)}" class="inline-block bg-purple-600 text-white px-6 py-3 rounded-full hover:bg-purple-700 transition duration-300">View Gallery 📸</a>' if gallery_images else ''}
                    <div class="mt-4">
                        <a href="/" class="inline-block bg-gray-600 text-white px-6 py-3 rounded-full hover:bg-gray-700 transition duration-300">Create Another Page</a>
                    </div>
                </div>
            </body>
            </html>
            """

        # Write the main page - FIXED: Use different variable name
        with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as html_file:
            html_file.write(html)

        # ------------ Render Gallery Page ------------
        if gallery_images:
            gallery_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Gallery - {title} {name}</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="bg-gradient-to-br from-blue-400 to-purple-600 min-h-screen p-8">
                <div class="max-w-4xl mx-auto">
                    <h1 class="text-4xl font-bold text-white text-center mb-8">Gallery for {name}</h1>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {"".join([f'<img src="{img}" alt="Gallery image" class="w-full h-64 object-cover rounded-lg shadow-lg">' for img in gallery_images])}
                    </div>
                    <div class="text-center mt-8">
                        <a href="{url_for('serve_generated', uid=uid, _external=True)}" class="inline-block bg-white text-purple-600 px-6 py-3 rounded-full hover:bg-gray-100 transition duration-300">
                            ← Back to Main Page
                        </a>
                    </div>
                </div>
                <audio autoplay loop>
                    <source src="{music}" type="audio/mpeg">
                    Your browser does not support the audio element.
                </audio>
            </body>
            </html>
            """

            with open(os.path.join(base, "gallery.html"), "w", encoding="utf-8") as gallery_file:
                gallery_file.write(gallery_html)

        # ------------ FINAL LINK ------------
        base_url = os.environ.get('RENDER_EXTERNAL_URL', request.host_url.rstrip('/'))
        link = f"{base_url}/generated/{uid}/"

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"link": link})
        else:
            return redirect(link)

    except Exception as e:
        print(f"Error in generate: {str(e)}")
        import traceback
        print(traceback.format_exc())
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": str(e)}), 500
        else:
            return f"Error: {str(e)}", 500

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