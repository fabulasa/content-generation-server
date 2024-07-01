import time
import whisper
import aiohttp
import os
from pydantic import BaseModel
import os
import uuid
import requests
import json
import random
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip, concatenate_audioclips, TextClip, CompositeVideoClip
from concurrent.futures import ThreadPoolExecutor
import http.client
import httplib2
from fastapi import FastAPI, HTTPException, Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from PIL import Image
import numpy as np
import math
from typing import List



# Create output directory if not exists
output_dir = "BackgroundVideos"
os.makedirs(output_dir, exist_ok=True)

output_dir_for_final_videos = "Final_Videos"
os.makedirs(output_dir_for_final_videos, exist_ok=True)

output_dir_for_semantic_videos_backgrounds = "SemanticVideosBackgrounds"
os.makedirs(output_dir_for_semantic_videos_backgrounds, exist_ok=True)

output_dir_for_final_semantic_videos = "FinalSemanticVideos"
os.makedirs(output_dir_for_final_semantic_videos, exist_ok=True)


class CaptionedVideoRequest(BaseModel):
    background_video_url: str
    captions: str


class VideoData(BaseModel):
    file: str
    title: str
    description: str
    keywords: str = ""
    category: str = "22"
    privacyStatus: str = "public"

app = FastAPI()


# Thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=4)

class VideoCreateRequest(BaseModel):
    audio_url: str
    assetUrls: List[str]
    background_music_url: str

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
                    "end": word['end']
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
        return JSONResponse(content={"message": "Video processing started", "video_path": f"BackgroundVideos/{unique_filename}"})
    
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
        
def process_video(background_video_path, captions, output_video_path):
    try:
        font_path = "/home/ubuntu/Nexa Bold.otf"
        # font_path = "/home/fbk001/Nexa Bold.otf"

        # Load background video
        background_video = VideoFileClip(background_video_path)  # Load full video

        # Define target size for YouTube Shorts
        target_size = (1080, 1920)
        
        # Resize background video to fit within 1080x1920
        background_video = background_video.resize(width=target_size[0]).set_position("center")

        def scale_text_clip(txt_clip, start, end, special=False):
            duration = end - start
            if special:
                def resize(t):
                    third_duration = duration / 3
                    if t < third_duration:
                        scale_factor = 1.0 + 0.15 * (t / third_duration)
                    elif t < 2 * third_duration:
                        scale_factor = 1.15 - 0.2 * ((t - third_duration) / third_duration)
                    else:
                        scale_factor = 0.9 + 0.1 * ((t - 2 * third_duration) / third_duration)
                    return scale_factor
            else:
                def resize(t):
                    half_duration = duration / 2
                    if t < half_duration:
                        scale_factor = 1.0 + 0.1 * (t / half_duration)
                    else:
                        scale_factor = 1.1 - 0.1 * ((t - half_duration) / half_duration)
                    return scale_factor

            return txt_clip.resize(lambda t: resize(t)).set_start(start).set_duration(duration)

        # Create text clips for each caption
        text_clips = []
        special_indices = random.sample(range(len(captions)), int(0.3 * len(captions)))  # Randomly select 30% of the indices

        for i, caption in enumerate(captions):
            txt = caption['word']
            start = caption['start']
            end = caption['end']
            duration = end - start
            
            if duration > 0:
                # Create the primary text clip
                text_clip = (TextClip(txt, fontsize=100, font=font_path, color='white', stroke_color='white', stroke_width=4, kerning=8)
                             .set_position(('center', target_size[1] // 3)))

                # Create a second text clip with a black stroke
                text_clip_black = (TextClip(txt, fontsize=106, font=font_path, color='transparent', stroke_color='black', stroke_width=6, kerning=8)
                                   .set_position(('center', target_size[1] // 3)))

                glow_offsets = [(0, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
                glow_clips = [TextClip(txt, fontsize=108, font=font_path, color='transparent', stroke_color='rgb(206, 202, 198)', stroke_width=6, kerning=6)
                              .set_position(('center', target_size[1] // 3))
                              for x, y in glow_offsets]

                text_clip_bold = text_clip.set_position(('center', target_size[1] // 3 + 1))

                # Determine if this caption should have the special transformation
                special = i in special_indices

                # Scale the text clips
                scaled_text_clip = scale_text_clip(text_clip, start, end, special=special)
                scaled_text_clip_black = scale_text_clip(text_clip_black, start, end, special=special)
                scaled_glow_clips = [scale_text_clip(glow_clip, start, end, special=special) for glow_clip in glow_clips]

                # Append the clips in the correct order to create the desired effect
                text_clips.append(scaled_text_clip_black)
                # text_clips.extend(scaled_glow_clips)
                text_clips.append(scaled_text_clip)
                # text_clips.append(text_clip_bold)

        # Create final video with scrolling captions
        final_video = CompositeVideoClip([background_video] + text_clips, size=target_size)
        
        # Save the final video
        final_video.write_videofile(output_video_path, codec="libx264", audio_codec="aac")
        
        # Delete the original asset video
        os.remove(background_video_path)
    except Exception as e:
        print(f"Error: {e}")

@app.post("/create-captioned-videos/")
async def create_captioned_videos(request: CaptionedVideoRequest):
    try:
        print("Received request:")
        print(f"Background Video URL: {request.background_video_url}")
        print(f"Captions: {request.captions}")

        # Parse captions
        captions = json.loads(request.captions)
        
        # Paths
        background_video_path = f"{request.background_video_url}"

        unique_id = str(uuid.uuid4())
        output_video_path = os.path.join(output_dir_for_final_videos, f"output_captioned_video_{unique_id}.mp4")

        
        # Respond with the output path before processing
        response = {"expected_output_video_url": output_video_path}
        print(response)
        
        # Submit video processing task to the executor
        executor.submit(process_video, background_video_path, captions, output_video_path)
        
        return response
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
CLIENT_SECRETS_FILE = "client_secrets.json"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
MISSING_CLIENT_SECRETS_MESSAGE = f"""
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

   {os.path.abspath(os.path.join(os.path.dirname(__file__), CLIENT_SECRETS_FILE))}

with information from the API Console
https://console.cloud.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
"""

RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError,
                        http.client.NotConnected, http.client.IncompleteRead,
                        http.client.ImproperConnectionState, http.client.CannotSendRequest,
                        http.client.CannotSendHeader, http.client.ResponseNotReady,
                        http.client.BadStatusLine)
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
MAX_RETRIES = 10
CLIENT_SECRETS_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = "token.json"



def get_authenticated_service():
    credentials = None

    # Load credentials from file if available
    if os.path.exists(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # If no valid credentials are available, prompt the user to log in
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(credentials.to_json())

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials)

def initialize_upload(youtube, video_data: VideoData):
    tags = video_data.keywords.split(",") if video_data.keywords else None

    body = dict(
        snippet=dict(
            title=video_data.title,
            description=video_data.description,
            tags=tags,
            categoryId=video_data.category
        ),
        status=dict(
            privacyStatus=video_data.privacyStatus
        )
    )

    # Get the absolute path to the video file
    file_path = os.path.abspath(video_data.file)

    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(file_path, chunksize=-1, resumable=True)
    )

    return resumable_upload(insert_request)

def resumable_upload(insert_request):
    response = None
    error = None
    retry = 0
    while response is None:
        try:
            print("Uploading file...")
            status, response = insert_request.next_chunk()
            if response is not None:
                if 'id' in response:
                    print(f"Video id '{response['id']}' was successfully uploaded.")
                    return response
                else:
                    raise HTTPException(status_code=500, detail="The upload failed with an unexpected response.")
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = f"A retriable HTTP error {e.resp.status} occurred:\n{e.content}"
            else:
                raise HTTPException(status_code=e.resp.status, detail=e.content)
        except RETRIABLE_EXCEPTIONS as e:
            error = f"A retriable error occurred: {e}"

        if error is not None:
            print(error)
            retry += 1
            if retry > MAX_RETRIES:
                raise HTTPException(status_code=500, detail="No longer attempting to retry.")

            max_sleep = 2 ** retry
            sleep_seconds = random.random() * max_sleep
            print(f"Sleeping {sleep_seconds} seconds and then retrying...")
            time.sleep(sleep_seconds)

@app.post("/uploadToYouTube")
async def upload_to_youtube(video_data: VideoData):
    try:
        youtube = get_authenticated_service()
        response = initialize_upload(youtube, video_data)
        return {"id": response['id']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class VideoCreateRequestFromSemanticImages(BaseModel):
    audio_url: str
    semantic_structure: list
    background_music_url: str

@app.post("/create-video-from-semantic-images/")
async def create_video_from_semantic_images(request: VideoCreateRequestFromSemanticImages):
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
        executor.submit(create__semantic_background_video, request.audio_url, request.semantic_structure, request.background_music_url, output_video_path)
        
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

def create__semantic_background_video(audio_url: str, semantic_structure: list, background_music_url: str, output_video_path: str):
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

        for i, scene in enumerate(semantic_structure):
            semantic_sentence = scene['semantic_sentence']
            scene_image_urls = scene['scene_image_url'].split(',')
            start_time = scene['start_time']
            end_time = scene['end_time']
            duration = end_time - start_time

            print(f"Scene {i+1}:")
            print(f"  Semantic Sentence: {semantic_sentence}")
            print(f"  Image URLs: {scene_image_urls}")
            print(f"  Duration should be {duration} seconds, from {start_time} to {end_time}")

            individual_duration = duration / len(scene_image_urls)

            for img_url in scene_image_urls:
                scene_response = requests.get(img_url)
                scene_path = os.path.join(output_dir_for_semantic_videos_backgrounds, f"scene_{uuid.uuid4()}.jpg")
                temp_files.append(scene_path)
                with open(scene_path, 'wb') as f:
                    f.write(scene_response.content)
                
                # Create a video clip from the scene image with zoom effect
                scene_clip = (ImageClip(scene_path)
                              .set_duration(individual_duration)
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
        
        
def create_captioned_semantic_video(background_video_path, captions, output_video_path):
    try:
        # font_path = "/home/ubuntu/Nexa Bold.otf"
        font_path = "/home/fbk001/Nexa Bold.otf"

        # Load background video
        background_video = VideoFileClip(background_video_path)  # Load full video

        # Define target size for YouTube Shorts
        target_size = (1080, 1920)
        
        # Resize background video to fit within 1080x1920
        background_video = background_video.resize(width=target_size[0]).set_position("center")

        def scale_text_clip(txt_clip, start, end, special=False):
            duration = end - start
            if special:
                def resize(t):
                    third_duration = duration / 3
                    if t < third_duration:
                        scale_factor = 1.0 + 0.15 * (t / third_duration)
                    elif t < 2 * third_duration:
                        scale_factor = 1.15 - 0.2 * ((t - third_duration) / third_duration)
                    else:
                        scale_factor = 0.9 + 0.1 * ((t - 2 * third_duration) / third_duration)
                    return scale_factor
            else:
                def resize(t):
                    half_duration = duration / 2
                    if t < half_duration:
                        scale_factor = 1.0 + 0.1 * (t / half_duration)
                    else:
                        scale_factor = 1.1 - 0.1 * ((t - half_duration) / half_duration)
                    return scale_factor

            return txt_clip.resize(lambda t: resize(t)).set_start(start).set_duration(duration)

        # Create text clips for each caption
        text_clips = []
        special_indices = random.sample(range(len(captions)), int(0.3 * len(captions)))  # Randomly select 30% of the indices

        for i, caption in enumerate(captions):
            txt = caption['word']
            start = caption['start']
            end = caption['end']
            duration = end - start
            
            if duration > 0:
                # Create the primary text clip
                text_clip = (TextClip(txt, fontsize=70, font=font_path, color='white', stroke_color='white', stroke_width=4, kerning=8)
                             .set_position(('center', target_size[1] * 3 // 4)))
                
                # Create a second text clip with a black stroke
                text_clip_black = (TextClip(txt, fontsize=74, font=font_path, color='transparent', stroke_color='black', stroke_width=6, kerning=8)
                                   .set_position(('center', target_size[1] * 3 // 4)))

                glow_offsets = [(0, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
                glow_clips = [TextClip(txt, fontsize=79, font=font_path, color='transparent', stroke_color='rgb(206, 202, 198)', stroke_width=6, kerning=6)
                              .set_position(('center', target_size[1] * 3 // 4))
                              for x, y in glow_offsets]

                text_clip_bold = text_clip.set_position(('center', target_size[1] // 3 + 1))

                # Determine if this caption should have the special transformation
                special = i in special_indices

                # Scale the text clips
                scaled_text_clip = scale_text_clip(text_clip, start, end, special=special)
                scaled_text_clip_black = scale_text_clip(text_clip_black, start, end, special=special)
                scaled_glow_clips = [scale_text_clip(glow_clip, start, end, special=special) for glow_clip in glow_clips]

                # Append the clips in the correct order to create the desired effect
                text_clips.append(scaled_text_clip_black)
                # text_clips.extend(scaled_glow_clips)
                text_clips.append(scaled_text_clip)
                # text_clips.append(text_clip_bold)

        # Create final video with scrolling captions
        final_video = CompositeVideoClip([background_video] + text_clips, size=target_size)
        
        # Save the final video
        final_video.write_videofile(output_video_path, codec="libx264", audio_codec="aac")
        
        # Delete the original asset video
        # os.remove(background_video_path)
    except Exception as e:
        print(f"Error: {e}")

@app.post("/create-captioned-semantic-videos/")
async def create_captioned_videos(request: CaptionedVideoRequest):
    try:
        print("Received request:")
        print(f"Background Video URL: {request.background_video_url}")
        print(f"Captions: {request.captions}")

        # Parse captions
        captions = json.loads(request.captions)
        
        # Paths
        background_video_path = f"{request.background_video_url}"

        unique_id = str(uuid.uuid4())
        output_video_path = os.path.join(output_dir_for_final_semantic_videos, f"output_captioned_semantic_video_{unique_id}.mp4")

        
        # Respond with the output path before processing
        response = {"expected_output_video_url": output_video_path}
        print(response)
        
        # Submit video processing task to the executor
        executor.submit(create_captioned_semantic_video, background_video_path, captions, output_video_path)
        
        return response
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Mount the static files directory
app.mount("/BackgroundVideos", StaticFiles(directory="BackgroundVideos"), name="BackgroundVideos")

app.mount("/Final_Videos", StaticFiles(directory="Final_Videos"), name="Final_Videos")

app.mount("/SemanticVideosBackgrounds", StaticFiles(directory="SemanticVideosBackgrounds"), name="SemanticVideosBackgrounds")

app.mount("/FinalSemanticVideos", StaticFiles(directory="FinalSemanticVideos"), name="FinalSemanticVideos")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
