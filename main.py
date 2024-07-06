import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from endpoints import create_background_video_v1, create_captioned_video_v1, create_background_video_v2, create_captioned_video_v2, transcribe_audio, transcribe_word_level, upload_to_youtube

app = FastAPI()

# Create output directories if they do not exist
output_dirs = [
    "BackgroundVideos", 
    "Final_Videos", 
    "SemanticVideosBackgrounds", 
    "FinalSemanticVideos", 
    "tokens"
]


for dir in output_dirs:
    os.makedirs(dir, exist_ok=True)
    
@app.get("/")
async def read_root():
    return {"message": "Server working"}

# Include routers from endpoint modules
app.include_router(transcribe_audio.router)
app.include_router(transcribe_word_level.router)
app.include_router(create_background_video_v1.router)
app.include_router(create_captioned_video_v1.router)
app.include_router(create_background_video_v2.router)
app.include_router(create_captioned_video_v2.router)
app.include_router(upload_to_youtube.router)

# Mount static files
app.mount("/BackgroundVideos", StaticFiles(directory="BackgroundVideos"), name="BackgroundVideos")
app.mount("/Final_Videos", StaticFiles(directory="Final_Videos"), name="Final_Videos")
app.mount("/SemanticVideosBackgrounds", StaticFiles(directory="SemanticVideosBackgrounds"), name="SemanticVideosBackgrounds")
app.mount("/FinalSemanticVideos", StaticFiles(directory="FinalSemanticVideos"), name="FinalSemanticVideos")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
