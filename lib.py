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
import os
import progressbar
# If modifying these scopes, delete the file token.pickle.
SCOPE_PHOTOS = ['https://www.googleapis.com/auth/photoslibrary.appendonly']
SCOPE_DRIVE = ['https://www.googleapis.com/auth/drive.metadata.readonly',
               'https://www.googleapis.com/auth/drive.readonly']
IMAGE_UPLOAD_URL = 'https://photoslibrary.googleapis.com/v1/uploads'
MEDIA_CREATE_URL = 'https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate'
IMAGE_ALBUM_URL = 'https://photoslibrary.googleapis.com/v1/albums'
FILE_BATCH_SIZE = 1

PHOTO_SIZE_LIMIT = 16000000  # 16 MB
MOD = 1000000007


class DriveToPhotos:
    def __init__(self, drive_creds_path, photos_creds_path):
        self.drive_creds = self.get_auth_token(drive_creds_path, SCOPE_DRIVE)
        self.photos_creds = self.get_auth_token(
            photos_creds_path, SCOPE_PHOTOS)
        self.drive_service_v2 = build(
            'drive', 'v2', credentials=self.drive_creds)
        self.drive_service_v3 = build(
            'drive', 'v3', credentials=self.drive_creds)

    def files_in_folder(self, folder_id):
        param = {}
        files = list()
        children = self.drive_service_v2.children().list(
            folderId=folder_id, **param).execute()
        for child in children.get('items', []):
            files.append(child['id'])
            # page_token = children.get('nextPageToken')
            # if not page_token:
            #     break

        return files

    def upload_to_album(self, album_id, file_path):
        # upload bytes and get the media token
        image_file = open(file_path, 'rb')
        image_bytes = image_file.read()
        kind = filetype.guess(image_bytes)
        image_file.close()
        headers = {'Authorization': 'Bearer ' + self.photos_creds.token,
                   'Content-type': 'application/octet-stream'}
        headers['X-Google-Upload-File-Name'] = file_path + kind.extension
        res = requests.post(url=IMAGE_UPLOAD_URL,
                            headers=headers, data=image_bytes)
        upload_token = res.content
        album_request = dict()
        album_request['albumId'] = album_id
        album_request['newMediaItems'] = list()
        item = dict()
        item['description'] = 'Sample Image'
        item['simpleMediaItem'] = dict()
        item['simpleMediaItem']['uploadToken'] = upload_token.decode("utf-8")
        album_request['newMediaItems'].append(item)
        res = requests.post(url=MEDIA_CREATE_URL, json=album_request,
                            headers=headers)

        return res

    def get_auth_token(self, credential_file_path, scope):
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

    # TODO: Improve the compression algorithm, delete files post transfer
    def image_compress(self, input_path, file_name):
        statinfo = os.stat(input_path + file_name)
        output_file_path = ''
        if statinfo.st_size > PHOTO_SIZE_LIMIT:
            image = Image.open(input_path + file_name)
            width, height = image.st_size
            fraction = math.sqrt(PHOTO_SIZE_LIMIT/statinfo.st_size)
            new_width = width*fraction
            new_height = height*fraction
            new_image = image.resize(int(new_width), int(new_height))
            new_image.save('/tmp/' + 'compressed' + file_name)
            output_file_path = '/tmp/' + 'compressed' + file_name

        return output_file_path

    def create_album(self, name):
        d = {}
        d['album'] = {}
        d['album']['title'] = name
        creds = self.photos_creds
        headers = {'Authorization': 'Bearer ' + creds.token,
                   'Content-type': 'application/json'}
        res = requests.post(url=IMAGE_ALBUM_URL, json=d, headers=headers)

        return res.content

    def see_shared_folders(self):
        results = self.drive_service_v3.files() \
            .list(q="sharedWithMe=true and mimeType='application/vnd.google-apps.folder'", pageSize=10,
                  fields="nextPageToken, files(id, name, owners)").execute()
        items = results.get('files', [])

        if not items:
            print('No shared folders found.')

        return items

    def download_file(self, file_id, download_path):
        request = self.drive_service_v3.files().get_media(fileId=file_id)
        fh = open(download_path, "wb")
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

    def download_files(self, folder_id):
        files = self.files_in_folder(folder_id)
        for f in files:
            creds = self.drive_creds
            hed2 = {'Authorization': 'Bearer ' + creds.token,
                    'Content-type': 'application/json'}
            response = requests.get(
                "https://www.googleapis.com/drive/v3/files/" + f + "?fields=*", headers=hed2)

            self.download_file(f)

    def move_files(self, folder_id, album_id):
        print('Moving files in progress')
        files = self.files_in_folder(folder_id)
        current_batch = []
        total_batches = len(files)/FILE_BATCH_SIZE + 1
        current_batch_nums = 0
        with progressbar.ProgressBar(max_value=total_batches) as bar:
            for i, f in enumerate(files):
                if len(current_batch) == FILE_BATCH_SIZE:
                    for f_c in current_batch:
                        res = self.upload_to_album(album_id, f_c)
                        if res.status_code == 200:
                            os.remove(f_c)
                        else:
                            print("Couldn't upload " + f_c)
                    current_batch_nums += 1
                    bar.update(current_batch_nums)
                    current_batch = []

                creds = self.drive_creds
                hed2 = {'Authorization': 'Bearer ' + creds.token,
                        'Content-type': 'application/json'}
                response = requests.get(
                    "https://www.googleapis.com/drive/v3/files/" + f + "?fields=*", headers=hed2)

                download_path = '/tmp/' + f
                self.download_file(f, download_path)
                current_batch.append(download_path)


def main():
    drive_to_photos = DriveToPhotos(
        'credentials_drive.json', 'credentials_photos.json')
    shared_folders = drive_to_photos.see_shared_folders()
    folder_ids = {}
    for i, item in enumerate(shared_folders):
        print(i + 1, '|',  item['name'], ' | ',
              item['owners'][0]['displayName'])
        folder_ids[i+1] = item['id']
    n = input('Enter a folder number:')
    n = int(n)

    album_name = input('Enter an album you want to move the photos to:')
    album_created = drive_to_photos.create_album(album_name)
    album_created = json.loads(album_created)
    drive_to_photos.move_files(folder_ids[n], album_created['id'])


main()
