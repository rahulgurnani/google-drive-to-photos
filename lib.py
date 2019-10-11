from __future__ import print_function
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image
import math
import requests
import json
import filetype
# If modifying these scopes, delete the file token.pickle.
SCOPE_PHOTOS = ['https://www.googleapis.com/auth/photoslibrary.appendonly']
SCOPE_DRIVE = ['https://www.googleapis.com/auth/drive.metadata.readonly',
               'https://www.googleapis.com/auth/drive.readonly']
IMAGE_UPLOAD_URL = 'https://photoslibrary.googleapis.com/v1/uploads'
MEDIA_CREATE_URL = 'https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate'
PHOTO_SIZE_LIMIT = 16000000  # 16 MB
MOD = 1000000007


def get_headers(token):
    headers = {'Authorization': 'Bearer ' + token,
               'Content-type': 'application/json'}

    return headers


def get_auth_token(credential_file_path, scope):
    creds = None
    store_file = credential_file_path.split('/')[-1] + '.pickle'
    if os.path.exists(store_file):
        with open(store_file, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credential_file_path, scope)
            creds = flow.run_local_server(port=0)
        with open(store_file, 'wb') as token:
            pickle.dump(creds, token)

    return creds


def get_drive_service():
    creds = get_auth_token('credentials_drive.json', SCOPE_DRIVE)
    service = build('drive', 'v3', credentials=creds)

    return service


def get_drive_service2():
    creds = get_auth_token('credentials_drive.json', SCOPE_DRIVE)
    service = build('drive', 'v2', credentials=creds)

    return service


# TODO: Improve the compression algorithm
def image_compress(input_path, file_name):
    statinfo = os.stat(input_path + file_name)
    output_file_path = input_path + file_name
    if statinfo.st_size > PHOTO_SIZE_LIMIT:
        image = Image.open(input_path + file_name)
        width, height = image.st_size
        fraction = math.sqrt(PHOTO_SIZE_LIMIT/statinfo.st_size)
        new_width = width*fraction
        new_height = height*fraction
        new_image = image.resize(int(new_width), int(new_height))
        new_image.save(input_path + 'compressed' + file_name)
        output_file_path = input_path + 'compressed' + file_name

    return output_file_path


def create_album(name):
    f2 = open('album.json', 'r')
    body = f2.read()
    f2.close()
    d = json.loads(body)
    d['album']['title'] = name
    creds = get_auth_token('credentials_photos.json', SCOPE_PHOTOS)
    url = 'https://photoslibrary.googleapis.com/v1/albums'
    hed2 = {'Authorization': 'Bearer ' + creds.token,
            'Content-type': 'application/json'}
    res = requests.post(url=url, json=d, headers=hed2)
    return res.content


def upload_to_album(album_id, file_path):
    # upload bytes and get the media token
    creds = get_auth_token('credentials_photos.json', SCOPE_PHOTOS)
    image_file = open(file_path, 'rb')
    image_bytes = image_file.read()
    kind = filetype.guess(image_bytes)
    image_file.close()
    print(kind.extension)
    headers = get_headers(creds.token)
    headers['Content-type'] = 'application/octet-stream'
    headers['X-Goog-Upload-File-Name'] = file_path + kind.extension
    res = requests.post(url=IMAGE_UPLOAD_URL,
                        headers=headers, data=image_bytes)
    upload_token = res.content
    # create media content
    album_request = dict()
    album_request['albumId'] = album_id
    album_request['newMediaItems'] = list()
    item = dict()
    item['description'] = 'Sample Image'
    item['simpleMediaItem'] = dict()
    item['simpleMediaItem']['uploadToken'] = upload_token.decode("utf-8")
    album_request['newMediaItems'].append(item)
    print(album_request)
    res = requests.post(url=MEDIA_CREATE_URL, json=album_request,
                        headers=headers)

    print(res.content)


def see_shared_folders():
    service = get_drive_service()
    results = service.files().list(q="sharedWithMe=true and mimeType='application/vnd.google-apps.folder'", pageSize=10,
                                   fields="nextPageToken, files(id, name, owners)").execute()
    items = results.get('files', [])

    if not items:
        print('No shared folders found.')
    else:
        for item in items:
            print(item['id'], item['name'], item['owners'][0]['displayName'])
            return item['id']

    return items


def download_file(file_id):
    drive_service = get_drive_service()
    request = drive_service.files().get_media(fileId=file_id)
    fh = open(file_id, "wb")
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(status)
        print("Download")


def files_in_folder(folder_id):
    service = get_drive_service2()
    param = {}
    files = list()
    children = service.children().list(
        folderId=folder_id, **param).execute()
    for child in children.get('items', []):
        print('File Id: %s' % child['id'])
        print(child)
        files.append(child['id'])
        page_token = children.get('nextPageToken')
        if not page_token:
            break

    return files


album_name = 'vof'
album_created = create_album(album_name)
d = json.loads(album_created)

id = see_shared_folders()
files = files_in_folder(id)

for f in files[0:10]:
    download_file(f)
    upload_to_album(d['id'], f)
