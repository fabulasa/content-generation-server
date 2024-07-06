from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import whisper
import aiohttp
import os
import time

router = APIRouter()

model = whisper.load_model("tiny.en")

class TranscriptionRequest(BaseModel):
    voice_over_url: str

@router.post("/transcribe/word-level/")
async def transcribe_word_level(request: TranscriptionRequest):
    try:
        audio_path = "audio.mp3"
        async with aiohttp.ClientSession() as session:
            async with session.get(request.voice_over_url) as response:
                if response.status != 200:
                    raise HTTPException(status_code=404, detail="Audio file not found")
                with open(audio_path, "wb") as f:
                    f.write(await response.read())

        start_time = time.time()
        result = model.transcribe(audio_path, word_timestamps=True)
        end_time = time.time()

        word_transcripts = [
            {
                "word": word['word'],
                "start": word['start'],
                "end": word['end']
            }
            for segment in result['segments']
            for word in segment['words']
        ]

        os.remove(audio_path)

        return {
            "word_transcripts": word_transcripts,
            "transcription_time": f"{end_time - start_time:.2f} seconds"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
