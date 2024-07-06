from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import uuid
import os
from concurrent.futures import ThreadPoolExecutor
from fastapi.responses import JSONResponse
import requests
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip, ImageClip, concatenate_audioclips
from PIL import Image
import math
import numpy as np

router = APIRouter()
executor = ThreadPoolExecutor(max_workers=4)
output_dir_for_semantic_videos_backgrounds = "SemanticVideosBackgrounds"

class VideoCreateRequestFromSemanticImages(BaseModel):
    audio_url: str
    semantic_structure: List[dict]
    background_music_url: str

@router.post("/create-background-video/v2")
async def create_video_background_video_v2_endpoint(request: VideoCreateRequestFromSemanticImages):
    try:
        print("Received POST data:", request)

        # Create a unique file path
        unique_filename = f"{uuid.uuid4()}.mp4"
        output_video_path = os.path.join(output_dir_for_semantic_videos_backgrounds, unique_filename)

        # Return the file path in the response before starting video processing
        response = {
            "message": "Data logged successfully",
            "video_path": output_video_path
        }
        print(response)

        # Submit the video creation task to the executor
        executor.submit(create_video_background_video_v2, request.audio_url, request.semantic_structure, request.background_music_url, output_video_path)
        
        return JSONResponse(content=response)

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

def zoom_in_effect(clip, zoom_ratio=0.04):
    def effect(get_frame, t):
        img = Image.fromarray(get_frame(t))
        base_size = img.size

        new_size = [
            math.ceil(img.size[0] * (1 + (zoom_ratio * t))),
            math.ceil(img.size[1] * (1 + (zoom_ratio * t)))
        ]

        # The new dimensions must be even.
        new_size[0] = new_size[0] + (new_size[0] % 2)
        new_size[1] = new_size[1] + (new_size[1] % 2)

        img = img.resize(new_size, Image.LANCZOS)

        x = math.ceil((new_size[0] - base_size[0]) / 2)
        y = math.ceil((new_size[1] - base_size[1]) / 2)

        img = img.crop([
            x, y, new_size[0] - x, new_size[1] - y
        ]).resize(base_size, Image.LANCZOS)

        result = np.array(img)
        img.close()

        return result

    return clip.fl(effect)

def is_video_file(url):
    video_extensions = ['.mp4', '.mov', '.avi', '.mkv']
    return any(url.lower().endswith(ext) for ext in video_extensions)

def create_video_background_video_v2(audio_url: str, semantic_structure: list, background_music_url: str, output_video_path: str):
    try:
        # Download main audio file
        print("Downloading main audio...")
        audio_response = requests.get(audio_url)
        audio_path = os.path.join(output_dir_for_semantic_videos_backgrounds, f"audio_{uuid.uuid4()}.mp3")
        with open(audio_path, 'wb') as f:
            f.write(audio_response.content)
        
        # Load main audio file
        audio_clip = AudioFileClip(audio_path)
        audio_duration = audio_clip.duration
        print(f"Main audio duration: {audio_duration} seconds")

        # Download background music
        print("Downloading background music...")
        bg_music_response = requests.get(background_music_url)
        bg_music_path = os.path.join(output_dir_for_semantic_videos_backgrounds, f"background_music_{uuid.uuid4()}.mp3")
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
        
        # Download and process semantic structure videos
        video_clips = []
        temp_files = [audio_path, bg_music_path]  # To keep track of intermediate files for deletion

        target_size = (1080, 1920)  # YouTube Shorts dimensions

        for i, scene in enumerate(semantic_structure):
            semantic_sentence = scene['semantic_sentence']
            scene_urls = scene['scene_image_url'].split(',')
            start_time = scene['start_time']
            end_time = scene['end_time']
            duration = end_time - start_time

            print(f"Scene {i+1}:")
            print(f"  Semantic Sentence: {semantic_sentence}")
            print(f"  URLs: {scene_urls}")
            print(f"  Duration should be {duration} seconds, from {start_time} to {end_time}")

            individual_duration = duration / len(scene_urls)

            for url in scene_urls:
                if is_video_file(url):
                    # Download and process video
                    scene_response = requests.get(url)
                    scene_path = os.path.join(output_dir_for_semantic_videos_backgrounds, f"scene_{uuid.uuid4()}.mp4")
                    temp_files.append(scene_path)
                    with open(scene_path, 'wb') as f:
                        f.write(scene_response.content)
                    
                    scene_clip = VideoFileClip(scene_path).subclip(0, individual_duration).resize(width=target_size[0])
                else:
                    # Download and process image
                    scene_response = requests.get(url)
                    scene_path = os.path.join(output_dir_for_semantic_videos_backgrounds, f"scene_{uuid.uuid4()}.jpg")
                    temp_files.append(scene_path)
                    with open(scene_path, 'wb') as f:
                        f.write(scene_response.content)
                    
                    # Create a video clip from the scene image with zoom effect
                    scene_clip = (ImageClip(scene_path)
                                  .set_duration(individual_duration)
                                  .resize(width=target_size[0])  # Resize to fit the width of YouTube Shorts
                                  .fx(zoom_in_effect, zoom_ratio=0.04)
                                  .crossfadein(1.2))

                # Check for silence and adjust the duration of the current scene to fill the gap
                if i > 0 and len(video_clips) > 0:
                    previous_end_time = semantic_structure[i-1]['end_time']
                    gap_duration = start_time - previous_end_time
                    if gap_duration > 0:
                        print(f"  Filling silence gap of {gap_duration} seconds between scenes {i} and {i+1}")
                        video_clips[-1] = video_clips[-1].set_duration(video_clips[-1].duration + gap_duration)
                
                video_clips.append(scene_clip)
                print(f"  Actual duration: {scene_clip.duration} seconds")

        # Concatenate video clips
        final_video = concatenate_videoclips(video_clips, method="compose")

        # Ensure the final video duration matches the audio duration
        final_video = final_video.set_duration(audio_duration).set_audio(combined_audio)
        
        print(f"Writing final video to {output_video_path}...")
        final_video.write_videofile(output_video_path, codec="libx264", audio_codec="aac", fps=24)
        
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
