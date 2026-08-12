from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import io
import base64
import fitz  # PyMuPDF library
import re
from PIL import Image, ImageDraw, ImageFont

app = FastAPI(title="PVC Print Engine API")

# CORS setup is crucial for Blogger integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def extract_full_data(pdf_bytes, password=""):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.needs_pass:
        doc.authenticate(password)
        
    page = doc[0]
    
    # 1. EXTRACT IMAGES (Photo & QR)
    images = page.get_images(full=True)
    photo_bytes = None
    qr_bytes = None
    
    for img in images:
        base_image = doc.extract_image(img[0])
        w, h = base_image["width"], base_image["height"]
        img_data = base_image["image"]
        
        # QR Code is usually a large perfect square
        if abs(w - h) < 15 and w > 150:
            qr_bytes = img_data
        # Photo is usually a tall rectangle
        elif h > w and h > 100:
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
    
    # Simple regex parsing based on standard document structure
    for i, line in enumerate(lines):
        # Find DOB
        if "DOB" in line or "Year of Birth" in line or re.search(r'\d{2}/\d{2}/\d{4}', line):
            user_data["dob"] = line
            # Usually, the line right before DOB is the English Name
            if i > 0 and not user_data["name"]:
                user_data["name"] = lines[i-1]
                
        # Find Gender
        if "MALE" in line.upper() or "FEMALE" in line.upper():
            user_data["gender"] = line
            
        # Find 12-digit ID number (Format: XXXX XXXX XXXX)
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
        
        # Initialize ImageDraw to type text onto the template
        draw_front = ImageDraw.Draw(front)
        
        # Load fonts (Upload 'arial.ttf' and a bold version to your Render folder)
        try:
            font_regular = ImageFont.truetype("arial.ttf", 45)
            font_bold = ImageFont.truetype("arialbd.ttf", 65)
        except IOError:
            # Fallback if fonts are missing
            font_regular = ImageFont.load_default()
            font_bold = ImageFont.load_default()

        # Paste Photo
        if photo_data:
            photo = Image.open(io.BytesIO(photo_data)).resize((380, 480))
            front.paste(photo, (150, 320)) # Adjust coordinates based on your template
            
        # Paste QR Code on Back
        if qr_data:
            qr = Image.open(io.BytesIO(qr_data)).resize((400, 400))
            back.paste(qr, (1500, 250)) # Adjust coordinates based on your template

        # Draw Extracted Text on Front Card
        # Note: You will need to tweak these X, Y coordinates (e.g., 580, 350) to perfectly align with your blank template
        text_x = 580
        
        if user_data["name"]:
            draw_front.text((text_x, 350), user_data["name"], fill=(0, 0, 0), font=font_regular)
            
        if user_data["dob"]:
            draw_front.text((text_x, 430), user_data["dob"], fill=(0, 0, 0), font=font_regular)
            
        if user_data["gender"]:
            draw_front.text((text_x, 510), user_data["gender"], fill=(0, 0, 0), font=font_regular)
            
        if user_data["id_number"]:
            # Centered large ID number at the bottom
            draw_front.text((700, 950), user_data["id_number"], fill=(0, 0, 0), font=font_bold)

        # Handle Language/Mobile Overlays just like Dizi Print does
        if show_mobile.lower() == "true":
            # Simulate drawing mobile number if required
            draw_front.text((text_x, 590), "Mobile: 8556XXXXXX", fill=(0, 0, 0), font=font_regular)

        if language != "default":
            # Draw the red translated banner at the bottom
            draw_front.rectangle([(100, 1100), (1940, 1250)], fill=(255, 255, 255)) # White out area
            banner_text = "MERA AADHAAR, MERI PEHCHAAN" if language == "english" else "ਮੇਰਾ ਆਧਾਰ, ਮੇਰੀ ਪਛਾਣ"
            draw_front.text((1020, 1175), banner_text, fill=(229, 0, 0), font=font_bold, anchor="mm")

        # Convert rendered images to Base64 to send via AJAX
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
            "extracted_data": user_data # Sending this back so you can see it in browser console
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
