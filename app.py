from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session, jsonify
from utils import read_file, humanize_text, fake_ai_score, get_readability_score, get_available_models, get_model_info, get_supported_languages, get_language_info
from docx import Document
import tempfile
import os
from datetime import datetime, timedelta
import json
import traceback

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Simple rate limiting storage (use Redis in production)
request_log = {}

def check_rate_limit(ip):
    now = datetime.now()
    if ip in request_log:
        if now - request_log[ip] < timedelta(seconds=30):
            return False
    request_log[ip] = now
    return True

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        client_ip = request.remote_addr
        if not check_rate_limit(client_ip):
            flash("Rate limit exceeded. Please wait 30 seconds between requests.", "error")
            return redirect(url_for('index'))
        
        text = request.form.get("input_text", "").strip()
        file = request.files.get("file")
        tone = request.form.get("tone", "Professional")
        intensity = request.form.get("intensity", "Medium")
        model = request.form.get("model", "meta-llama/llama-3.1-8b-instruct")
        language = request.form.get("language", "english")

        print(f"=== FORM SUBMISSION DEBUG ===")
        print(f"Text input: '{text}'")
        print(f"File received: {file}")
        
        if file:
            print(f"File filename: '{file.filename}'")
            # Check file content
            file.seek(0, 2)  # Go to end to get size
            file_size = file.tell()
            file.seek(0)  # Reset to beginning
            print(f"File size: {file_size} bytes")

        # Validate input FIRST - check both text and file
        has_text = bool(text and text.strip())
        has_file = bool(file and file.filename and file.filename.strip())
        
        print(f"Has text: {has_text}, Has file: {has_file}")
        
        if not has_text and not has_file:
            flash("Please provide text or upload a file.", "error")
            return redirect(url_for('index'))

        processed_text = ""

        # Process file if uploaded
        if has_file:
            print(f"Processing file: {file.filename}")
            
            allowed_extensions = {'.txt', '.pdf', '.docx'}
            file_ext = os.path.splitext(file.filename)[1].lower()
            
            if file_ext not in allowed_extensions:
                flash("Invalid file type. Please upload TXT, PDF, or DOCX files.", "error")
                return redirect(url_for('index'))
            
            try:
                # Read file content
                file_content = read_file(file)
                print(f"File content read successfully, length: {len(file_content)}")
                
                if file_content and file_content.strip():
                    processed_text = file_content.strip()
                    print(f"Using file content: {len(processed_text)} characters")
                else:
                    flash("The uploaded file appears to be empty.", "error")
                    return redirect(url_for('index'))
                    
            except Exception as e:
                print(f"File reading error: {str(e)}")
                flash(f"Error reading file: {str(e)}", "error")
                return redirect(url_for('index'))
        else:
            # Use text input
            processed_text = text
            print(f"Using text input: {len(processed_text)} characters")

        # Final validation
        if not processed_text or not processed_text.strip():
            flash("No text content found. Please provide text or upload a valid file.", "error")
            return redirect(url_for('index'))

        if len(processed_text) > 10000:
            flash("Text exceeds maximum length of 10,000 characters.", "error")
            return redirect(url_for('index'))

        if len(processed_text) < 10:
            flash("Text is too short. Please provide at least 10 characters.", "error")
            return redirect(url_for('index'))

        print(f"SUCCESS: Text ready for processing - {len(processed_text)} characters")

        # Store in session for progress tracking
        session['processing_data'] = {
            'text': processed_text,
            'tone': tone,
            'intensity': intensity,
            'model': model,
            'language': language
        }

        return render_template("processing.html")
    
    models = get_available_models()
    languages = get_supported_languages()
    return render_template("index.html", models=models, languages=languages)

@app.route("/process", methods=["POST"])
def process_text():
    data = session.get('processing_data')
    if not data:
        flash("Session expired. Please try again.", "error")
        return redirect(url_for('index'))
    
    try:
        text = data['text']
        
        # Check if the text is an error message from file extraction
        if text.startswith("Unable to extract") or text.startswith("Error extracting") or text.startswith("Document appears"):
            flash(f"{text}", "error")
            return redirect(url_for('index'))
        
        before_score = fake_ai_score(text)
        rewritten = humanize_text(text, data['tone'], data['intensity'], data['model'], data['language'])
        after_score = fake_ai_score(rewritten)
        readability = get_readability_score(rewritten)
        
        # Clear session data
        session.pop('processing_data', None)
        
        return render_template(
            "result.html",
            original=text,
            output=rewritten,
            before_score=before_score,
            after_score=after_score,
            readability=readability,
            tone=data['tone'],
            intensity=data['intensity'],
            model=get_model_info(data['model']),
            language=get_language_info(data['language'])
        )
    except Exception as e:
        # Clear session on error
        session.pop('processing_data', None)
        flash(f"{str(e)}", "error")
        return redirect(url_for('index'))

@app.route("/download", methods=["POST"])
def download():
    text = request.form["text"]
    file_format = request.form["format"]

    try:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_format}")
        if file_format == "txt":
            with open(temp_file.name, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            doc = Document()
            doc.add_paragraph(text)
            doc.save(temp_file.name)

        return send_file(temp_file.name, as_attachment=True, download_name=f"humanized_text.{file_format}")
    except Exception as e:
        flash(f"Download error: {str(e)}", "error")
        return redirect(url_for('index'))

@app.errorhandler(413)
def too_large(e):
    flash("File too large. Maximum size is 16MB.", "error")
    return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    flash("An internal error occurred. Please try again.", "error")
    return redirect(url_for('index'))

@app.route("/extract-text", methods=["POST"])
def extract_text():
    try:
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        print(f"Extracting text from: {file.filename}")
        extracted_text = read_file(file)
        
        # Check if extraction was successful
        if (extracted_text and 
            not extracted_text.startswith("Unable to extract") and 
            not extracted_text.startswith("Error extracting") and
            not extracted_text.startswith("Document appears") and
            not extracted_text.startswith("Unsupported file format")):
            
            print(f"Successfully extracted {len(extracted_text)} characters")
            return jsonify({
                'success': True, 
                'text': extracted_text,
                'characters': len(extracted_text)
            })
        else:
            print(f"Extraction failed: {extracted_text}")
            return jsonify({
                'success': False, 
                'error': extracted_text if extracted_text else 'Unknown extraction error'
            })
            
    except Exception as e:
        print(f"Extraction error: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f"Server error: {str(e)}"
        })

if __name__ == "__main__":
    app.run(debug=True)