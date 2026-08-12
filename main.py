from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn
import io
import fitz  # PyMuPDF library
from PIL import Image

app = FastAPI(title="Dizi-Style PVC Engine")

# CORS setup so your frontend can call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

def extract_secure_assets(pdf_bytes, password=""):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    # Unlock the PDF if a password is provided
    if doc.needs_pass:
        doc.authenticate(password)
        
    page = doc[0]
    images = page.get_images(full=True)
    
    photo_bytes = None
    qr_bytes = None
    
    # Smart Detection: QR is perfectly square, Photo is tall (portrait)
    for img in images:
        base_image = doc.extract_image(img[0])
        w, h = base_image["width"], base_image["height"]
        img_data = base_image["image"]
        
        if abs(w - h) < 15 and w > 100:  # If width & height are almost equal = QR Code
            qr_bytes = img_data
        elif h > w and h > 100:          # If height is greater than width = Photo
            photo_bytes = img_data
            
    return photo_bytes, qr_bytes

@app.post("/api/render-card")
async def render_card(
    file: UploadFile = File(...), 
    password: str = Form(""), 
    language: str = Form("default"),
    show_mobile: bool = Form(True)
):
    # 1. Read the uploaded PDF
    pdf_bytes = await file.read()
    
    # 2. Extract Photo & QR
    photo_data, qr_data = extract_secure_assets(pdf_bytes, password)
    
    # 3. Load your pristine Blank Template
    # (Aapko ek blank_template_front.png apni directory mein rakhni hogi)
    try:
        template = Image.open("blank_template_front.png").convert("RGBA")
    except FileNotFoundError:
        # Fallback if you haven't uploaded the template yet
        template = Image.new('RGBA', (2040, 1286), color=(255, 255, 255, 255))
    
    # 4. Paste the Extracted Assets onto the Template
    if photo_data:
        # Open, resize, and paste the user photo
        photo = Image.open(io.BytesIO(photo_data)).resize((340, 420))
        template.paste(photo, (180, 310)) # Update X,Y coordinates according to your template
        
    if qr_data:
        # Open, resize, and paste the QR code
        qr = Image.open(io.BytesIO(qr_data)).resize((300, 300))
        template.paste(qr, (1550, 250)) # Update X,Y coordinates according to your template
        
    # NOTE: Mobile Number and Language text overlay will be drawn here using ImageDraw!
    
    # 5. Send the final image straight back to the browser
    final_image = io.BytesIO()
    template.save(final_image, format='PNG')
    final_image.seek(0)
    
    return StreamingResponse(final_image, media_type="image/png")

# Run command for local testing
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
