import time
import whisper
import aiohttp
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import uuid
import requests
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip, concatenate_audioclips
from concurrent.futures import ThreadPoolExecutor


# Create output directory if not exists
output_dir = "BackgroundVideos"
os.makedirs(output_dir, exist_ok=True)

app = FastAPI()

# Thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=4)

class VideoCreateRequest(BaseModel):
    audio_url: str
    assetUrls: list[str]

model = whisper.load_model("tiny.en")

class TranscriptionRequest(BaseModel):
    voice_over_url: str

@app.get("/")
async def read_root():
    return {"message": "Server working"}

@app.post("/transcribe/")
async def transcribe_audio(request: TranscriptionRequest):
    try:
        # Download the audio file from the provided URL
        audio_path = "audio.mp3"
        async with aiohttp.ClientSession() as session:
            async with session.get(request.voice_over_url) as response:
                if response.status != 200:
                    raise HTTPException(status_code=404, detail="Audio file not found")
                with open(audio_path, "wb") as f:
                    f.write(await response.read())

        # Start the timer
        start_time = time.time()

        # Transcribe the audio file
        result = model.transcribe(audio_path)

        # End the timer
        end_time = time.time()

        # Calculate the elapsed time
        elapsed_time = end_time - start_time

        # Extract the text transcript
        transcript = result['text']

        # Remove the downloaded audio file
        os.remove(audio_path)

        return {
            "transcript": transcript,
            "transcription_time": f"{elapsed_time:.2f} seconds"
        }
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe/word-level/")
async def transcribe_word_level(request: TranscriptionRequest):
    try:
        # Download the audio file from the provided URL
        audio_path = "audio.mp3"
        async with aiohttp.ClientSession() as session:
            async with session.get(request.voice_over_url) as response:
                if response.status != 200:
                    raise HTTPException(status_code=404, detail="Audio file not found")
                with open(audio_path, "wb") as f:
                    f.write(await response.read())

        # Start the timer
        start_time = time.time()

        # Transcribe the audio file
        result = model.transcribe(audio_path, word_timestamps=True)
        # End the timer
        end_time = time.time()

        # Calculate the elapsed time
        elapsed_time = end_time - start_time

        # Extract the word-level transcript
        # Extract the word-level transcripts
        word_transcripts = []
        for segment in result['segments']:
            for word in segment['words']:
                word_transcripts.append({
                    "word": word['word'],
                    "start": word['start'],
                    "end": word['end'],
                    "probability": word['probability']
                })
        # Remove the downloaded audio file
        os.remove(audio_path)

        return {
            "word_transcripts": word_transcripts,
            "transcription_time": f"{elapsed_time:.2f} seconds"
        }
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/create-video/")
async def transcribe_audio(request: VideoCreateRequest):
    try:
        print("Received request:", request.json())  # Log the incoming JSON data
        audio_url = request.audio_url
        asset_urls = request.assetUrls
        background_music_url = request.background_music_url

        unique_filename = f"{uuid.uuid4()}.mp4"
        output_video_path = os.path.join(output_dir, unique_filename)
        
        # Submit the video creation task to the executor
        executor.submit(create_video, audio_url, asset_urls, background_music_url, output_video_path)
        
        # Return the URL where the video will be stored
        return JSONResponse(content={"message": "Video processing started", "video_path": f"/BackgroundVideos/{unique_filename}"})
    
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def create_video(audio_url: str, asset_urls: list[str], background_music_url: str, output_video_path: str):
    try:
        # Download main audio file
        print("Downloading main audio...")
        audio_response = requests.get(audio_url)
        audio_path = os.path.join(output_dir, f"audio_{uuid.uuid4()}.mp3")
        with open(audio_path, 'wb') as f:
            f.write(audio_response.content)
        
        # Get the length of the main audio file
        print("Loading main audio file...")
        audio_clip = AudioFileClip(audio_path)
        audio_duration = audio_clip.duration
        print(f"Main audio duration: {audio_duration} seconds")

        # Download background music
        print("Downloading background music...")
        bg_music_response = requests.get(background_music_url)
        bg_music_path = os.path.join(output_dir, f"background_music_{uuid.uuid4()}.mp3")
        with open(bg_music_path, 'wb') as f:
            f.write(bg_music_response.content)
        
        # Load background music and set volume to 20%
        bg_music_clip = AudioFileClip(bg_music_path).volumex(0.14)

        # Manually loop the background music to match the duration of the main audio
        bg_music_clips = []
        total_bg_duration = 0
        while total_bg_duration < audio_duration:
            bg_music_clips.append(bg_music_clip)
            total_bg_duration += bg_music_clip.duration

        combined_bg_music_clip = concatenate_audioclips(bg_music_clips).subclip(0, audio_duration)
        
        # Combine the main audio and background music
        combined_audio = CompositeAudioClip([audio_clip, combined_bg_music_clip])
        
        # Download and process asset videos
        video_clips = []
        target_size = (1920, 1080)  # Example target size (width, height)
        temp_files = [audio_path, bg_music_path]  # To keep track of intermediate files for deletion

        for i, url in enumerate(asset_urls):
            print(f"Downloading video {i+1}/{len(asset_urls)}...")
            video_response = requests.get(url)
            video_path = os.path.join(output_dir, f"asset_{uuid.uuid4()}.mp4")
            temp_files.append(video_path)
            with open(video_path, 'wb') as f:
                f.write(video_response.content)
            
            video_clip = VideoFileClip(video_path).subclip(0, min(5, VideoFileClip(video_path).duration))
            
            # Resize the video to have the same dimensions, maintaining aspect ratio
            video_clip = video_clip.resize(height=target_size[1]).set_position("center")
            video_clips.append(video_clip)
            print(f"Video {i+1} duration: {video_clip.duration} seconds")
        
        # Concatenate video clips to match audio length
        final_clips = []
        total_duration = 0
        clip_index = 0
        print("Concatenating video clips to match audio duration...")
        while total_duration < audio_duration:
            clip = video_clips[clip_index].subclip(0, min(5, video_clips[clip_index].duration))
            if total_duration + clip.duration > audio_duration:
                clip = clip.subclip(0, audio_duration - total_duration)
            final_clips.append(clip)
            total_duration += clip.duration
            clip_index = (clip_index + 1) % len(video_clips)
            print(f"Total video duration: {total_duration} seconds")
        
        final_video = concatenate_videoclips(final_clips, method="compose")
        final_video = final_video.set_audio(combined_audio)
        
        print(f"Writing final video to {output_video_path}...")
        final_video.write_videofile(output_video_path, codec="libx264", audio_codec="aac")
        
        # Clean up intermediate files
        print("Cleaning up temporary files...")
        for file_path in temp_files:
            try:
                os.remove(file_path)
                print(f"Deleted {file_path}")
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
        
        print("Video created successfully")
    
    except Exception as e:
        print(f"Error: {e}")

# Mount the static files directory
app.mount("/BackgroundVideos", StaticFiles(directory=output_dir), name="BackgroundVideos")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
