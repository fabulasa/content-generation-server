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
output_dir_for_final_semantic_videos = "FinalSemanticVideos"

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

@router.post("/create-captioned-video/v2")
async def create_captioned_video_v2_endpoint(request: CaptionVideoRequest):
    try:
        print("Received request:")
        print(f"Background Video URL: {request.background_video_url}")
        print(f"Captions: {request.captions}")

        # Parse captions
        captions = json.loads(request.captions)
        
        # Paths
        background_video_path = f"{request.background_video_url}"

        unique_id = str(uuid.uuid4())
        output_video_path = os.path.join(output_dir_for_final_semantic_videos, f"{unique_id}.mp4")

        # Respond with the output path before processing
        response = {"expected_output_video_url": output_video_path}
        print(response)
        
        # Submit video processing task to the executor
        executor.submit(create_captioned_video_v2, background_video_path, captions, output_video_path)
        
        return response
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))  

def create_captioned_video_v2(background_video_path, captions, output_video_path):
    try:
        # Load background video
        background_video = VideoFileClip(background_video_path)  # Load full video

        # Define target size for YouTube Shorts
        target_size = (1080, 1920)
        
        # Resize background video to fit within 1080x1920
        background_video = background_video.resize(width=target_size[0]).set_position("center")

        def create_text_clips(captions, framesize, font=font_path, fontsize=70, color='white'):
            word_clips = []
            y_pos = framesize[1] * 3 // 4
            frame_width = framesize[0]
            space_width = TextClip(" ", font=font, fontsize=fontsize, color=color).size[0]
            
            i = 0
            while i < len(captions):
                line_clips = []
                total_width = 0
                max_end_time = 0
                line_completed = False

                # Determine the end of the current line
                j = 0
                while i + j < len(captions) and j < 3 and not line_completed:
                    txt = captions[i + j]['word']
                    if '.' in txt or '?' in txt or ',' in txt:
                        line_completed = True
                    j += 1

                # Calculate the total width of the line
                for k in range(j):
                    txt = captions[i + k]['word']
                    word_clip = TextClip(txt, font=font, fontsize=fontsize, color=color, stroke_color='black', stroke_width=4)
                    word_width, _ = word_clip.size
                    total_width += word_width
                    if k < j - 1:
                        total_width += space_width
                    if captions[i + k]['end'] > max_end_time:
                        max_end_time = captions[i + k]['end']

                x_pos = (frame_width - total_width) // 2  # Center the total width

                for k in range(j):
                    caption = captions[i + k]
                    txt = caption['word']
                    start = caption['start']
                    end = caption['end']
                    duration = end - start

                    word_clip = TextClip(txt, font=font, fontsize=fontsize, color=color, stroke_color='black', stroke_width=4).set_start(start).set_duration(max_end_time - start)
                    word_width, word_height = word_clip.size
                    
                    # Position the word clip
                    word_clip = word_clip.set_position((x_pos, y_pos))
                    x_pos += word_width + space_width
                    line_clips.append(word_clip)

                # Append the line clips to word_clips
                word_clips.extend(line_clips)

                # Add a blank clip to clear the line after the last word is done
                clear_clip = ColorClip(size=(frame_width, word_height + 40), color=(0, 0, 0, 0)).set_start(max_end_time).set_duration(0.01).set_position((0, y_pos))
                word_clips.append(clear_clip)

                # Move to the next line
                i += j

            return word_clips

        # Create text clips
        text_clips = create_text_clips(captions, target_size)

        # Create final video with scrolling captions
        final_video = CompositeVideoClip([background_video] + text_clips, size=target_size)
        
        # Save the final video
        final_video.write_videofile(output_video_path, codec="libx264", audio_codec="aac")
        
        # Delete the original asset video
        os.remove(background_video_path)
    except Exception as e:
        print(f"Error: {e}")
