from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import cv2
import numpy as np
import base64

app = FastAPI()

# Allow your Blogger site to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # You can lock this down to 'https://common-service-centre.blogspot.com' later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ImageData(BaseModel):
    image: str

@app.post("/api/detect")
async def detect_cards(data: ImageData):
    try:
        # 1. Strip the Base64 header and decode the image
        img_str = data.image.split(",")[-1]
        img_bytes = base64.b64decode(img_str)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise ValueError("Could not decode image")

        # 2. Computer Vision: Grayscale, Blur, and Edge Detection
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        
        # 3. Find the borders (contours)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        card_rects = []
        img_area = img.shape[0] * img.shape[1]
        
        # 4. Filter out small specs of dust, only keep big rectangles (ID Cards)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > (img_area * 0.04): # Card must be at least 4% of the scanned page
                x, y, w, h = cv2.boundingRect(cnt)
                
                # Convert to a 1000-point scale for your frontend JavaScript math
                ymin = int((y / img.shape[0]) * 1000)
                xmin = int((x / img.shape[1]) * 1000)
                ymax = int(((y + h) / img.shape[0]) * 1000)
                xmax = int(((x + w) / img.shape[1]) * 1000)
                
                card_rects.append({
                    "box_2d": [ymin, xmin, ymax, xmax],
                    "area": area
                })
                
        # 5. Sort the boxes by size (biggest first) and grab the top 2
        card_rects.sort(key=lambda x: x["area"], reverse=True)
        
        # Sort top 2 by Y-axis so the Front card is always first, Back card second
        top_cards = card_rects[:2]
        top_cards.sort(key=lambda x: x["box_2d"][0]) 
        
        return {"cards": top_cards}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
