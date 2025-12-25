import os
import time
import glob
from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def download_video(video_url):
    timestamp = int(time.time())
    output_template = f"video_{timestamp}.%(ext)s"
    ydl_opts = {
        'format': 'worst',
        'outtmpl': output_template,
        'noplaylist': True,
        'max_filesize': 50 * 1024 * 1024,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        list_of_files = glob.glob(f"video_{timestamp}.*")
        if not list_of_files: return None
        return list_of_files[0]
    except Exception as e:
        print(f"Download Error: {e}")
        return None

def analyze_with_gemini(video_path):
    try:
        video_file = genai.upload_file(path=video_path)
        while video_file.state.name == "PROCESSING":
            time.sleep(2)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED": return "Error: Google processing failed."

        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        response = model.generate_content([video_file, "Describe visuals, audio mood, and content summary."])
        genai.delete_file(video_file.name)
        return response.text
    except Exception as e:
        return f"Analysis Error: {str(e)}"
    finally:
        if os.path.exists(video_path): os.remove(video_path)

@app.route('/', methods=['GET'])
def health_check(): return "Server Running", 200

@app.route('/analyze', methods=['POST'])
def analyze_video():
    data = request.json
    if not data or not data.get('url'): return jsonify({"error": "No URL"}), 400

    path = download_video(data.get('url'))
    if not path: return jsonify({"error": "Download failed"}), 500

    analysis = analyze_with_gemini(path)
    return jsonify({"status": "success", "analysis": analysis})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
