from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import io
import base64
import fitz  # PyMuPDF library
import re
import os
import urllib.request
from PIL import Image, ImageDraw, ImageFont

app = FastAPI(title="PVC Print Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# AUTO-DOWNLOAD HD FONTS FOR RENDER.COM
# ==========================================
def ensure_fonts_exist():
    font_url = "https://github.com/matomo-org/travis-scripts/raw/master/fonts/Arial.ttf"
    if not os.path.exists("arial.ttf"):
        print("Downloading Arial font for HD text rendering...")
        try:
            urllib.request.urlretrieve(font_url, "arial.ttf")
        except Exception as e:
            print("Font download failed:", e)

ensure_fonts_exist()

def extract_full_data(pdf_bytes, password=""):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.needs_pass:
        doc.authenticate(password)
        
    page = doc[0]
    
    # 1. EXTRACT IMAGES (Photo & QR)
    images = page.get_images(full=True)
    photo_bytes = None
    qr_bytes = None
    max_qr_size = 0
    
    for img in images:
        base_image = doc.extract_image(img[0])
        w, h = base_image["width"], base_image["height"]
        img_data = base_image["image"]
        
        # QR Code is a square. Lowered limit to 50px to catch smaller embedded QRs
        if abs(w - h) < 20 and w > 50:
            if w > max_qr_size:  # Grab the largest square if there are multiple
                qr_bytes = img_data
                max_qr_size = w
        # Photo is usually a tall rectangle
        elif h > w and h > 80:
            photo_bytes = img_data

    # 2. EXTRACT TEXT (Name, DOB, Gender, ID)
    raw_text = page.get_text("text")
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    
    user_data = {
        "name": "",
        "dob": "",
        "gender": "",
        "id_number": ""
    }
    
    for i, line in enumerate(lines):
        # Find DOB
        if "DOB" in line or "Year of Birth" in line or re.search(r'\d{2}/\d{2}/\d{4}', line):
            user_data["dob"] = line
            # Name is usually right above DOB
            if i > 0 and not user_data["name"]:
                user_data["name"] = lines[i-1]
                
        # Find Gender
        if "MALE" in line.upper() or "FEMALE" in line.upper():
            user_data["gender"] = line
            
        # Find 12-digit ID number
        id_match = re.search(r'\b\d{4}\s\d{4}\s\d{4}\b', line)
        if id_match:
            user_data["id_number"] = id_match.group(0)

    return photo_bytes, qr_bytes, user_data

@app.post("/api/render-card")
async def render_card(
    file: UploadFile = File(...), 
    password: str = Form(""), 
    language: str = Form("default"),
    show_mobile: str = Form("true")
):
    try:
        pdf_bytes = await file.read()
        photo_data, qr_data, user_data = extract_full_data(pdf_bytes, password)
        
        # Load Blank HD Templates
        try:
            front = Image.open("blank_template_front.png").convert("RGBA")
            back = Image.open("blank_template_back.png").convert("RGBA")
        except FileNotFoundError:
            front = Image.new('RGBA', (2040, 1286), color=(255, 255, 255, 255))
            back = Image.new('RGBA', (2040, 1286), color=(255, 255, 255, 255))
        
        draw_front = ImageDraw.Draw(front)
        
        # Load the downloaded HD Font
        try:
            font_regular = ImageFont.truetype("arial.ttf", 45)
            font_bold = ImageFont.truetype("arial.ttf", 65) # Using Arial for bold too if bold missing
        except IOError:
            font_regular = ImageFont.load_default()
            font_bold = ImageFont.load_default()

        # Paste Photo
        if photo_data:
            photo = Image.open(io.BytesIO(photo_data)).resize((340, 420))
            front.paste(photo, (180, 310))
            
        # Paste QR Code on Back
        if qr_data:
            qr = Image.open(io.BytesIO(qr_data)).resize((400, 400))
            back.paste(qr, (1500, 250)) 

        # TEXT RENDERING - Adjust these coordinates based on your blank template!
        text_x = 580
        
        if user_data["name"]:
            draw_front.text((text_x, 350), user_data["name"], fill=(0, 0, 0), font=font_bold)
            
        if user_data["dob"]:
            draw_front.text((text_x, 430), user_data["dob"], fill=(0, 0, 0), font=font_regular)
            
        if user_data["gender"]:
            draw_front.text((text_x, 510), user_data["gender"], fill=(0, 0, 0), font=font_regular)
            
        if user_data["id_number"]:
            # Redacted placeholder processing for safety compliance if needed, but normally prints extracted ID
            draw_front.text((700, 950), user_data["id_number"], fill=(0, 0, 0), font=font_bold)

        if show_mobile.lower() == "true":
            draw_front.text((text_x, 590), "Mobile: Included", fill=(0, 0, 0), font=font_regular)

        if language != "default":
            draw_front.rectangle([(100, 1100), (1940, 1250)], fill=(255, 255, 255))
            banner_text = "MERA AADHAAR, MERI PEHCHAAN" if language == "english" else "ਮੇਰਾ ਆਧਾਰ, ਮੇਰੀ ਪਛਾਣ"
            draw_front.text((1020, 1175), banner_text, fill=(229, 0, 0), font=font_bold, anchor="mm")

        buf_front = io.BytesIO()
        front.save(buf_front, format='PNG')
        b64_front = "data:image/png;base64," + base64.b64encode(buf_front.getvalue()).decode('utf-8')
        
        buf_back = io.BytesIO()
        back.save(buf_back, format='PNG')
        b64_back = "data:image/png;base64," + base64.b64encode(buf_back.getvalue()).decode('utf-8')
        
        return {
            "success": True,
            "front_card": b64_front,
            "back_card": b64_back,
            "extracted_data": user_data
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
