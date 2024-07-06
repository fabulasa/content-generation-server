from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from utils.auth import get_authenticated_service
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import time
import random
import httplib2
import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GoogleRequest





YOUTUBE_API_SERVICE_NAME = "youtube"
MAX_RETRIES = 10
TOKENS_DIR = "tokens"


router = APIRouter()

class VideoData(BaseModel):
    file: str
    title: str
    description: str
    keywords: str = ""
    category: str = "22"
    privacyStatus: str = "public"
    channelId: str

@router.post("/uploadToYouTube")
async def upload_to_youtube(video_data: VideoData):
    try:
        youtube = get_authenticated_service(video_data.channelId)
        response = initialize_upload(youtube, video_data)
        return {"id": response['id']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Constants
CLIENT_SECRETS_FILE = "client_secrets.json"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
SCOPES = [YOUTUBE_UPLOAD_SCOPE]
MAX_RETRIES = 10
TOKENS_DIR = "tokens"



def get_authenticated_service(channel_id: str):
    token_file = os.path.join(TOKENS_DIR, f"{channel_id}.json")
    credentials = None

    # Load credentials from file if available
    if os.path.exists(token_file):
        credentials = Credentials.from_authorized_user_file(token_file, SCOPES)

    # If no valid credentials are available, prompt the user to log in
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleRequest())
        else:
            # Start the OAuth flow to get new credentials
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(token_file, 'w') as token:
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
            if e.resp.status in [500, 502, 503, 504]:
                error = f"A retriable HTTP error {e.resp.status} occurred:\n{e.content}"
            else:
                raise HTTPException(status_code=e.resp.status, detail=e.content)
        except (httplib2.HttpLib2Error, IOError) as e:
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
