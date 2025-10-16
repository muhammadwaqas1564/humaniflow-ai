import os
import random
from docx import Document
from PyPDF2 import PdfReader
import textstat
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not found.")

client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"
)

def get_available_models():
    return {
        "meta-llama/llama-3.1-8b-instruct": "LLaMA 3.1 8B (Fast & Reliable)",
        "meta-llama/llama-3.1-70b-instruct": "LLaMA 3.1 70B (High Quality)",
        "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet (Premium)",
        "mistralai/mistral-7b-instruct": "Mistral 7B (Fast)",
        "openai/gpt-3.5-turbo": "GPT-3.5 Turbo (Balanced)"
    }

def get_supported_languages():
    return {
        "english": "English",
        "spanish": "Español",
        "french": "Français", 
        "german": "Deutsch",
        "italian": "Italiano",
        "portuguese": "Português",
        "dutch": "Nederlands",
        "russian": "Русский",
        "chinese": "中文",
        "japanese": "日本語",
        "korean": "한국어",
        "arabic": "العربية",
        "hindi": "हिन्दी"
    }

def get_language_prompt(language, tone, intensity):
    language_instructions = {
        "english": f"Rewrite the following text in English to sound naturally human-written with a {tone} tone and {intensity} humanization intensity.",
        "spanish": f"Reescribe el siguiente texto en español para que suene naturalmente humano con un tono {tone} e intensidad de humanización {intensity}.",
        "french": f"Reformulez le texte suivant en français pour qu'il semble naturellement humain avec un ton {tone} et une intensité d'humanisation {intensity}.",
        # ... include other languages
    }
    
    return language_instructions.get(language.lower(), language_instructions["english"])

def read_file(file):
    if not file or not file.filename:
        return ""
        
    ext = os.path.splitext(file.filename)[1].lower()
    print(f"DEBUG: Reading {ext} file: {file.filename}")
    
    try:
        # Ensure we're at the start of the file
        file.seek(0)
        
        if ext == ".txt":
            # Read as bytes first
            file_bytes = file.read()
            print(f"DEBUG: Read {len(file_bytes)} bytes from text file")
            
            if len(file_bytes) == 0:
                return ""
            
            # Try different encodings
            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
            for encoding in encodings:
                try:
                    decoded_content = file_bytes.decode(encoding)
                    print(f"DEBUG: Successfully decoded with {encoding}")
                    return decoded_content
                except UnicodeDecodeError:
                    continue
            
            # If all encodings fail, use replace
            return file_bytes.decode('utf-8', errors='replace')
            
        elif ext == ".pdf":
            file.seek(0)
            reader = PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            print(f"DEBUG: Extracted {len(text)} characters from PDF")
            return text.strip()
            
        elif ext == ".docx":
            file.seek(0)
            doc = Document(file)
            text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
            print(f"DEBUG: Extracted {len(text)} characters from DOCX")
            return text
            
        else:
            return f"Unsupported file format: {ext}"
            
    except Exception as e:
        print(f"DEBUG: Error reading file: {str(e)}")
        raise Exception(f"Error reading {ext.upper()} file: {str(e)}")

def humanize_text(text, tone, intensity, model, language="english"):
    # Validate model exists
    available_models = get_available_models()
    if model not in available_models:
        model = "meta-llama/llama-3.1-8b-instruct"
    
    # Get language-specific prompt
    language_prompt = get_language_prompt(language, tone, intensity)
    
    prompt = f"""
    {language_prompt}
    
    Requirements:
    - Preserve the original meaning and key information
    - Enhance clarity, flow, and readability
    - Remove AI detection patterns
    - Make it sound naturally human-written
    - Output only the rewritten text without any additional explanations
    
    Text to humanize:
    {text}
    """

    try:
        temperature_map = {
            "light": 0.7,
            "medium": 0.9,
            "strong": 1.2
        }
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system", 
                    "content": "You are a professional multilingual editor specializing in making AI-generated text sound human in various languages. Always output only the rewritten text without any additional comments, explanations, or markdown formatting."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=temperature_map.get(intensity.lower(), 0.9),
            top_p=0.9,
            max_tokens=2048
        )

        rewritten = response.choices[0].message.content.strip()
        
        # Clean up any potential model-specific artifacts
        if "```" in rewritten:
            lines = rewritten.split('\n')
            cleaned_lines = [line for line in lines if not line.strip().startswith('```')]
            rewritten = '\n'.join(cleaned_lines).strip()
            
        return rewritten

    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg:
            raise Exception(f"Model '{model}' is currently unavailable. Please try a different model.")
        elif "429" in error_msg:
            raise Exception("API rate limit exceeded. Please wait a moment and try again.")
        elif "401" in error_msg:
            raise Exception("Invalid API key. Please check your OpenRouter configuration.")
        else:
            raise Exception(f"AI processing error: {error_msg}")

def fake_ai_score(text):
    words = text.split()
    if len(words) < 10:
        return round(random.uniform(30, 70), 2)
    
    unique_ratio = len(set(words)) / len(words)
    sentence_length_variation = len(text) / (text.count('.') + text.count('!') + text.count('?') + 1)
    
    base_score = 50
    score = base_score + (unique_ratio * 30) + (min(sentence_length_variation, 50) / 10)
    score = min(95, max(5, score + random.uniform(-5, 5)))
    return round(score, 2)

def get_readability_score(text):
    try:
        score = textstat.flesch_reading_ease(text)
        return round(score, 2)
    except:
        return 0.0

def get_model_info(model_id):
    models = get_available_models()
    return models.get(model_id, "Unknown Model")

def get_language_info(language_code):
    languages = get_supported_languages()
    return languages.get(language_code, "English")