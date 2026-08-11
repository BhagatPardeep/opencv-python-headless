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

        # 2. Advanced Pre-processing for Dashed Lines
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Adaptive thresholding handles varying backgrounds and PDF shading
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        
        # Dilation acts as "glue" to connect the dotted scissor lines on Aadhaar cards
        kernel = np.ones((5,5), np.uint8)
        dilated = cv2.dilate(thresh, kernel, iterations=2)
        
        # 3. Find all possible shapes, even nested ones
        contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        img_area = img.shape[0] * img.shape[1]
        
        # 4. Intelligent Scoring Engine
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            if h == 0: continue
            aspect_ratio = float(w) / h
            
            # Broad filter: Ignore tiny text specs and the massive full-page border
            if area < (img_area * 0.02) or area > (img_area * 0.35):
                continue
                
            # CR80 ID Card ideal ratios
            ratio_diff_landscape = abs(aspect_ratio - 1.58)
            ratio_diff_portrait = abs(aspect_ratio - 0.63)
            
            # Find which orientation it matches best
            best_diff = min(ratio_diff_landscape, ratio_diff_portrait)
            
            # If the shape is reasonably close to an ID card (tolerance of 0.4)
            if best_diff < 0.4:
                ymin = int((y / img.shape[0]) * 1000)
                xmin = int((x / img.shape[1]) * 1000)
                ymax = int(((y + h) / img.shape[0]) * 1000)
                xmax = int(((x + w) / img.shape[1]) * 1000)
                
                candidates.append({
                    "box_2d": [ymin, xmin, ymax, xmax],
                    "area": area,
                    "score": best_diff # Lower score is better (closer to perfect card ratio)
                })
        
        # 5. The Bulletproof Fallback (For terrible scans or borderless PDFs)
        if not candidates or len(candidates) < 2:
            # Standard e-Aadhaar Layout: Front is bottom-left, Back is bottom-right
            return {"cards": [
                {"box_2d": [665, 80, 920, 485], "area": 0},  # Front Card Fallback Coordinates
                {"box_2d": [665, 515, 920, 920], "area": 0}   # Back Card Fallback Coordinates
            ]}
                
        # 6. Sort by best shape match
        candidates.sort(key=lambda x: x["score"])
        
        # Take the 2 most perfect card shapes found
        top_cards = candidates[:2]
        
        # Sort them by X-axis (Left to Right) so Front card is always first
        top_cards.sort(key=lambda x: x["box_2d"][1]) 
        
        return {"cards": top_cards}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
