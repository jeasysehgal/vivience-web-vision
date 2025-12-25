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
    
    # STEALTH MODE CONFIGURATION
    ydl_opts = {
        'format': 'worst[ext=mp4]/worst', # Smallest MP4 file (fastest for AI to "watch")
        'outtmpl': output_template,
        'noplaylist': True,
        'max_filesize': 50 * 1024 * 1024, # 50MB Limit
        
        # ANTI-BLOCKING MEASURES
        'geo_bypass': True,
        'nocheckcertificate': True,
        'source_address': '0.0.0.0', # Force IPv4
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36',
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
        
        # Wait for processing (Gemini needs to 'watch' it)
        # We limit waiting to 20 seconds to prevent timeouts
        attempts = 0
        while video_file.state.name == "PROCESSING" and attempts < 10:
            print("Processing video...")
            time.sleep(2)
            video_file = genai.get_file(video_file.name)
            attempts += 1

        if video_file.state.name == "FAILED":
            return "Error: Gemini failed to process the video file."

        # THE PROMPT: This ensures we get AUDIO and VISUAL analysis
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        prompt = (
            "You are a multimodal AI assistant. Analyze this video deeply.\n"
            "1. VISUALS: Describe the setting, lighting, objects, and actions you see.\n"
            "2. AUDIO: Describe the music genre/mood, sound effects, and voice tone.\n"
            "3. SUMMARY: What is the core message?"
        )

        response = model.generate_content([video_file, prompt])
        
        # Clean up cloud file
        genai.delete_file(video_file.name)
        
        return response.text

    except Exception as e:
        return f"AI Analysis Error: {str(e)}"
    finally:
        # Clean up local file
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

    # Step 1: Download (Stealth Mode)
    video_path = download_video(video_url)
    if not video_path:
        return jsonify({"error": "Download failed. YouTube blocked the server request."}), 500

    # Step 2: Analyze
    analysis = analyze_with_gemini(video_path)
    
    return jsonify({
        "status": "success",
        "analysis": analysis
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
