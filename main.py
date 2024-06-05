import time
import whisper
import aiohttp
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

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
        result = model.transcribe(audio_path, word_timestamps=True)

        # End the timer
        end_time = time.time()

        # Calculate the elapsed time
        elapsed_time = end_time - start_time

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
