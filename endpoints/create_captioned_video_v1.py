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
import json
import random



router = APIRouter()
executor = ThreadPoolExecutor(max_workers=4)
output_dir_for_final_captioned_videos_v1 = "Final_Videos"

# Determine the font path based on the environment variable
env = os.getenv('ENV')
if env == 'local':
    font_path = "/home/fbk001/Nexa Bold.ttf"
elif env == 'azure':
    font_path = "/home/azureuser/Nexa Bold.ttf"
else:
    raise EnvironmentError("Environment variable 'ENV' is not set or is invalid")

class CaptionVideoRequest(BaseModel):
    background_video_url: str
    captions: str

@router.post("/create-captioned-video/v1")
async def create_captioned_video_v1_endpoint(request: CaptionVideoRequest):
    try:
        print("Received request:")
        print(f"Background Video URL: {request.background_video_url}")
        print(f"Captions: {request.captions}")

        # Parse captions
        captions = json.loads(request.captions)
        
        # Paths
        background_video_path = f"{request.background_video_url}"

        unique_id = str(uuid.uuid4())
        output_video_path = os.path.join(output_dir_for_final_captioned_videos_v1, f"{unique_id}.mp4")

        
        # Respond with the output path before processing
        response = {"expected_output_video_url": output_video_path}
        print(response)
        
        # Submit video processing task to the executor
        executor.submit(create_captioned_video_v1, background_video_path, captions, output_video_path)
        
        return response
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    

def create_captioned_video_v1(background_video_path, captions, output_video_path):
    try:
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
