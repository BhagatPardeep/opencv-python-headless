from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import cv2
import numpy as np
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ImageData(BaseModel):
    image: str

@app.post("/api/detect")
async def detect_cards(data: ImageData):
    try:
        # 1. Decode the image
        img_str = data.image.split(",")[-1]
        img_bytes = base64.b64decode(img_str)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise ValueError("Could not decode image")

        # 2. Convert to Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 3. Thresholding: Make it pure black and white (inverts so lines are white)
        _, thresh = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)
        
        # 4. MORPHOLOGICAL CLOSING: This connects the "dashed / dotted" cut-lines on Aadhaar cards!
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        # 5. Find Contours
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        card_rects = []
        img_area = img.shape[0] * img.shape[1]
        
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            
            # Avoid divide by zero
            if h == 0:
                continue
                
            aspect_ratio = float(w) / h
            
            # MATHEMATICAL FILTER 1: Aspect Ratio
            # CR80 ID Card ratio is ~1.58. We accept 1.3 to 1.8 (Landscape) OR 0.55 to 0.75 (Portrait)
            is_valid_ratio = (1.3 < aspect_ratio < 1.85) or (0.55 < aspect_ratio < 0.75)
            
            # MATHEMATICAL FILTER 2: Size Limit
            # A real ID card on an A4 sheet takes up roughly 5% to 20% of the page. 
            # Reject massive boxes (like the top half of the letter) or tiny dust specs.
            is_valid_area = (img_area * 0.03) < area < (img_area * 0.25)
            
            if is_valid_ratio and is_valid_area:
                ymin = int((y / img.shape[0]) * 1000)
                xmin = int((x / img.shape[1]) * 1000)
                ymax = int(((y + h) / img.shape[0]) * 1000)
                xmax = int(((x + w) / img.shape[1]) * 1000)
                
                card_rects.append({
                    "box_2d": [ymin, xmin, ymax, xmax],
                    "area": area
                })
                
        # Sort best candidates by area
        card_rects.sort(key=lambda x: x["area"], reverse=True)
        top_cards = card_rects[:2]
        
        # Sort top 2 by Y-axis so the Front card (higher up on page) is always first
        top_cards.sort(key=lambda x: x["box_2d"][0]) 
        
        return {"cards": top_cards}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
