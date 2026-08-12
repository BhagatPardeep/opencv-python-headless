from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import io
import base64
import fitz  # PyMuPDF library
from PIL import Image

app = FastAPI(title="PVC Print Engine API")

# CORS setup is crucial for Blogger integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def extract_secure_assets(pdf_bytes, password=""):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if doc.needs_pass:
        doc.authenticate(password)
        
    page = doc[0]
    images = page.get_images(full=True)
    
    photo_bytes = None
    qr_bytes = None
    
    for img in images:
        base_image = doc.extract_image(img[0])
        w, h = base_image["width"], base_image["height"]
        img_data = base_image["image"]
        
        # Logic: QR is a square, Photo is a rectangle
        if abs(w - h) < 15 and w > 100:
            qr_bytes = img_data
        elif h > w and h > 100:
            photo_bytes = img_data
            
    return photo_bytes, qr_bytes

@app.post("/api/render-card")
async def render_card(
    file: UploadFile = File(...), 
    password: str = Form(""), 
    language: str = Form("default"),
    show_mobile: str = Form("true")
):
    try:
        pdf_bytes = await file.read()
        photo_data, qr_data = extract_secure_assets(pdf_bytes, password)
        
        # Load Blank HD Templates (Ensure these exist on your Render server)
        try:
            front = Image.open("blank_template_front.png").convert("RGBA")
            back = Image.open("blank_template_back.png").convert("RGBA")
        except FileNotFoundError:
            # Fallback blank canvas if templates are missing
            front = Image.new('RGBA', (2040, 1286), color=(255, 255, 255, 255))
            back = Image.new('RGBA', (2040, 1286), color=(255, 255, 255, 255))
        
        # Paste Extracted Assets onto Front Template
        if photo_data:
            photo = Image.open(io.BytesIO(photo_data)).resize((340, 420))
            front.paste(photo, (180, 310)) # Adjust X, Y coordinates
            
        if qr_data:
            qr = Image.open(io.BytesIO(qr_data)).resize((300, 300))
            back.paste(qr, (1550, 250)) # Pasting QR on the back card template
            
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
            "back_card": b64_back
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
