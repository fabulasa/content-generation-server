import os
import random
import time
import http.client
import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from pydantic import BaseModel

app = FastAPI()

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

class VideoData(BaseModel):
    file: str
    title: str
    description: str
    keywords: str = ""
    category: str = "22"
    privacyStatus: str = "private"

def get_authenticated_service():
    flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
                                   scope=YOUTUBE_UPLOAD_SCOPE,
                                   message=MISSING_CLIENT_SECRETS_MESSAGE)

    storage = Storage("upload_video.py-oauth2.json")
    credentials = storage.get()

    if credentials is None or credentials.invalid:
        credentials = flow.run_local_server(port=0)

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                 http=credentials.authorize(httplib2.Http()))

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
