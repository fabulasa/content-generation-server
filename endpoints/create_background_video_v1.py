from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import uuid
import os
from concurrent.futures import ThreadPoolExecutor
from fastapi.responses import JSONResponse
import os
import uuid
import requests
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip, TextClip, CompositeVideoClip, concatenate_audioclips, ColorClip


router = APIRouter()
executor = ThreadPoolExecutor(max_workers=4)
output_dir = "BackgroundVideos"

class VideoCreateRequest(BaseModel):
    audio_url: str
    assetUrls: List[str]
    background_music_url: str

@router.post("/create-background-video/v1")
async def create_video_background_video_v1_endpoint(request: VideoCreateRequest):
    try:
        audio_url = strip_url_params(request.audio_url)
        asset_urls = [strip_url_params(url) for url in request.assetUrls]
        background_music_url = strip_url_params(request.background_music_url)

        unique_filename = f"{uuid.uuid4()}.mp4"
        output_video_path = os.path.join(output_dir, unique_filename)
        
        executor.submit(create_video_background_video_v1, audio_url, asset_urls, background_music_url, output_video_path)
        
        return JSONResponse(content={"message": "Video processing started", "video_path": f"BackgroundVideos/{unique_filename}"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
def strip_url_params(url: str) -> str:
    # Split the URL at the '?' and return only the base URL
    return url.split('?')[0]

def create_video_background_video_v1(audio_url: str, asset_urls: List[str], background_music_url: str, output_video_path: str):
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
