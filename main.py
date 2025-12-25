import os
import time
import glob
from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# 1. SETUP GOOGLE GEMINI
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def download_video(video_url):
    """Downloads a YouTube video to a temporary file in Stealth Mode."""
    timestamp = int(time.time())
    output_template = f"video_{timestamp}.%(ext)s"
    
    # SPEED OPTIMIZATION: Force lowest quality and strict timeouts
    ydl_opts = {
        'format': 'worst', # Absolute smallest file (144p/240p) - FASTEST
        'outtmpl': output_template,
        'noplaylist': True,
        'max_filesize': 50 * 1024 * 1024,
        
        # TIMEOUTS (Fail fast if YouTube is slow)
        'socket_timeout': 10,
        'quiet': True,
        
        # ANTI-BLOCKING: THE ANDROID DISGUISE
        # We tell YouTube we are an Android phone, which they block less often.
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'geo_bypass': True,
        'nocheckcertificate': True,
        'source_address': '0.0.0.0',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        # Find the file we just downloaded
        list_of_files = glob.glob(f"video_{timestamp}.*")
        if not list_of_files:
            return None
        return list_of_files[0]
    except Exception as e:
        print(f"Download error: {e}")
        return None

def analyze_with_gemini(video_path):
    """Uploads video to Gemini and gets a multimodal analysis."""
    try:
        print(f"Uploading {video_path} to Gemini...")
        video_file = genai.upload_file(path=video_path)
        
        # Wait for processing
        attempts = 0
        while video_file.state.name == "PROCESSING" and attempts < 10:
            time.sleep(2)
            video_file = genai.get_file(video_file.name)
            attempts += 1

        if video_file.state.name == "FAILED":
            return "Error: Gemini failed to process the video file."

        # THE PROMPT
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        prompt = (
            "Analyze this video quickly.\n"
            "1. VISUALS: Brief description of setting and action.\n"
            "2. AUDIO: Mood of music or sound.\n"
            "3. SUMMARY: 1-sentence summary."
        )

        response = model.generate_content([video_file, prompt])
        genai.delete_file(video_file.name)
        return response.text

    except Exception as e:
        return f"AI Analysis Error: {str(e)}"
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

@app.route('/', methods=['GET'])
def health_check():
    return "Stealth Vision Server Running!", 200

@app.route('/analyze', methods=['POST'])
def analyze_video():
    data = request.json
    video_url = data.get('url')

    if not video_url:
        return jsonify({"error": "No URL provided"}), 400

    print(f"Stealth request for: {video_url}")

    # Step 1: Download
    video_path = download_video(video_url)
    if not video_path:
        # Return specific error so client can fallback to Tavily
        return jsonify({"error": "Download failed (Server Blocked or Timeout)"}), 500

    # Step 2: Analyze
    analysis = analyze_with_gemini(video_path)
    
    return jsonify({
        "status": "success",
        "analysis": analysis
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
