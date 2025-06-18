import os
import sys
import json
import time
import argparse
import datetime
import pytz
import glob
import re
import http.client
import httplib2
import random
import requests
import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from datetime import timezone

# Configuration
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
TOKEN_FILE = 'data/token.json'
UPLOADS_FILE = 'data/uploads.json'


def clean_youtube_title(title):
    """
    Nettoie un titre pour le rendre compatible avec l'API YouTube.
    
    Args:
        title (str): Titre original
        
    Returns:
        str: Titre nettoyé et valide pour YouTube
    """
    if not title or not title.strip():
        return "Untitled Video"
    
    # Limiter la longueur du titre (YouTube accepte max 100 caractères)
    title = title[:100]
    
    # Remplacer les caractères problématiques
    title = title.replace("\u0026", "&")
    
    # Supprimer les caractères de contrôle et autres caractères problématiques
    import re
    # Supprimer les caractères de contrôle (0x00-0x1F et 0x7F)
    title = re.sub(r'[\x00-\x1F\x7F]', '', title)
    
    # Remplacer les caractères spéciaux qui peuvent poser problème
    title = re.sub(r'[<>:"\/\\|?*]', '', title)
    
    # S'assurer que le titre n'est pas vide après nettoyage
    if not title.strip():
        return "Untitled Video"
    
    return title.strip()


def send_discord_notification(webhook_url, message):
    """
    Envoie une notification à un webhook Discord.

    Args:
        webhook_url (str): URL du webhook Discord
        message (dict): Message à envoyer (contenu, embeds, etc.)

    Returns:
        bool: True si l'envoi a réussi, False sinon
    """
    if not webhook_url:
        return False

    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(webhook_url, json=message, headers=headers)
        response.raise_for_status()
        print(f"Discord notification sent successfully")
        return True
    except Exception as e:
        print(f"Error sending Discord notification: {e}")
        return False


def get_authenticated_service():
    """
    Authenticates with YouTube API and returns the service object.

    Returns:
        googleapiclient.discovery.Resource: YouTube API service object
    """
    creds = None
    config = get_config()
    client_secrets_file = config['client_secrets']

    # Check if token file exists
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_info(
                json.load(open(TOKEN_FILE)), SCOPES)
        except Exception as e:
            print(f"Error loading credentials: {e}")

    # If there are no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing credentials: {e}")
                creds = None

        # If still no valid credentials, run the flow
        if not creds:
            if not os.path.exists(client_secrets_file):
                print(f"Client secrets file not found: {client_secrets_file}")
                return None

            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secrets_file, SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                print(f"Error during authentication: {e}")
                return None

            # Save the credentials for the next run
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())

    try:
        return build(API_SERVICE_NAME, API_VERSION, credentials=creds)
    except Exception as e:
        print(f"Error building service: {e}")
        return None


def extract_channel_name(video_path):
    """
    Extracts the channel name from the video path.

    Args:
        video_path (str): Path to the video file

    Returns:
        str: Channel name or None if not found
    """
    # Obtenir le chemin absolu
    abs_path = os.path.abspath(video_path)
    # Extraire les composants du chemin
    path_parts = abs_path.split(os.sep)
    # Dans la structure typique, le nom de la chaîne est le premier
    # dossier après le dossier racine des vidéos
    # /app/videos/wipr/... -> 'wipr'
    videos_index = -1
    try:
        videos_index = path_parts.index("videos")
        if len(path_parts) > videos_index + 1:
            return path_parts[videos_index + 1]
    except ValueError:
        pass

    # Méthode alternative si la structure est différente
    # Remonter de 3 niveaux depuis le fichier vidéo
    try:
        parent_dir = os.path.dirname(video_path)  # Dossier contenant la vidéo
        channel_dir = os.path.dirname(parent_dir)  # Dossier de la chaîne
        return os.path.basename(channel_dir)
    except Exception:
        return None


def extract_ganymede_metadata(video_path):
    """
    Extracts metadata from Ganymede VOD structure.

    Args:
        video_path (str): Path to the video file

    Returns:
        dict: Metadata including title, description, and thumbnail path
    """
    # Initialize default metadata
    metadata = {
        "title": os.path.basename(video_path),
        "description": "Uploaded with YTU from Ganymede archive",
        "thumbnail_path": None
    }

    # Get directory containing the video
    video_dir = os.path.dirname(video_path)

    # Extract video ID from filename (assuming format like 320223707005-video.mp4)
    video_id_match = re.search(r'(\d+)-video\.mp4$', os.path.basename(video_path))
    if not video_id_match:
        return metadata

    video_id = video_id_match.group(1)

    # Look for the corresponding info.json file
    info_file = os.path.join(video_dir, f"{video_id}-info.json")
    thumbnail_file = os.path.join(video_dir, f"{video_id}-thumbnail.jpg")

    # If info file exists, extract title
    if os.path.exists(info_file):
        try:
            with open(info_file, 'r', encoding='utf-8') as f:
                info_data = json.load(f)

            # Extract title if available and clean it
            if "title" in info_data and info_data["title"]:
                # Nettoyer le titre en utilisant notre nouvelle fonction
                title = clean_youtube_title(info_data["title"])
                metadata["title"] = title
            else:
                # Utiliser un titre par défaut si aucun titre n'est trouvé
                metadata["title"] = f"Stream {video_id}"

            # Extraire et formater la date
            stream_date = ""
            # Vérifier les différents champs possibles pour la date
            date_field = None
            if "created_at" in info_data:
                date_field = "created_at"
            elif "published_at" in info_data:
                date_field = "published_at"
            elif "started_at" in info_data:
                date_field = "started_at"

            if date_field:
                try:
                    # Convertir la date ISO en objet datetime
                    date_obj = datetime.datetime.fromisoformat(info_data[date_field].replace("Z", "+00:00"))
                    # Formater la date en format lisible
                    stream_date = date_obj.strftime("%d/%m/%Y %H:%M")
                except Exception as e:
                    print(f"Error formatting date: {e}")

            # Ajouter les informations à la description
            channel_name = None
            if "user_name" in info_data:
                channel_name = info_data["user_name"]
            elif "channel" in info_data and "name" in info_data["channel"]:
                channel_name = info_data["channel"]["name"]

            if channel_name:
                metadata[
                    "description"] = f"Stream: {info_data.get('title', 'Unknown')}\nChannel: {channel_name}\nDate: {stream_date}\n\nUploaded with YTU from Ganymede archive"
            else:
                metadata[
                    "description"] = f"Stream: {info_data.get('title', 'Unknown')}\nDate: {stream_date}\n\nUploaded with YTU from Ganymede archive"

            # Extraire le nom du jeu
            if "category" in info_data and info_data["category"]:
                metadata["game_name"] = info_data["category"]
            elif "game_name" in info_data and info_data["game_name"]:
                metadata["game_name"] = info_data["game_name"]

        except Exception as e:
            print(f"Error reading Ganymede info file: {e}")

    # Add thumbnail if available
    if os.path.exists(thumbnail_file):
        metadata["thumbnail_path"] = thumbnail_file

    return metadata


def upload_video(youtube, video_path, options=None, is_ganymede=False):
    """
    Uploads a video to YouTube with the specified options.

    Args:
        youtube: YouTube API service object
        video_path (str): Path to the video file
        options (dict, optional): Upload options
        is_ganymede (bool, optional): Whether to use Ganymede metadata

    Returns:
        dict: Upload result information
    """
    if not options:
        options = {}

    # If Ganymede mode is enabled, extract metadata
    if is_ganymede:
        ganymede_metadata = extract_ganymede_metadata(video_path)

        # Use Ganymede title if not explicitly provided
        if "title" not in options:
            options["title"] = ganymede_metadata["title"]

        # Use Ganymede description if not explicitly provided
        if "description" not in options:
            options["description"] = ganymede_metadata["description"]

        # Use Ganymede thumbnail if available and not explicitly provided
        if "thumbnail_path" not in options and ganymede_metadata.get("thumbnail_path"):
            options["thumbnail_path"] = ganymede_metadata["thumbnail_path"]

        # Use game name if available
        if "game_name" in ganymede_metadata:
            options["game_name"] = ganymede_metadata["game_name"]

    # Vérifier et nettoyer le titre pour s'assurer qu'il est valide
    if "title" in options:
        options["title"] = clean_youtube_title(options["title"])
    else:
        # Utiliser le nom du fichier comme titre par défaut
        default_title = os.path.splitext(os.path.basename(video_path))[0]
        options["title"] = clean_youtube_title(default_title)

    # Prepare the request body
    body = {
        'snippet': {
            'title': options.get('title', 'Untitled Video'),
            'description': options.get('description', 'Uploaded with YTU'),
            'tags': options.get('tags', ['YTU']),
            'categoryId': options.get('categoryId', '22')
        },
        'status': {
            'privacyStatus': options.get('privacyStatus', 'private'),
            'selfDeclaredMadeForKids': False
        }
    }

    # Si nous sommes en mode Ganymede et que nous avons un jeu dans les métadonnées
    if is_ganymede and 'game_name' in options:
        # Définir la catégorie comme "Gaming" (ID 20)
        body['snippet']['categoryId'] = '20'

    # Vérification finale du titre avant upload
    if not body['snippet']['title'] or len(body['snippet']['title'].strip()) == 0:
        body['snippet']['title'] = f"Video {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        print(f"Warning: Empty title detected, using default title: {body['snippet']['title']}")

    # Prepare the media file
    media = MediaFileUpload(video_path,
                            chunksize=10 * 1024 * 1024,
                            resumable=True,
                            mimetype='video/mp4')

    # Create the upload request
    upload_request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )

    # Execute the upload
    video_id = None
    response = None

    print(f"Uploading {video_path}...")

    try:
        status, response = upload_request.next_chunk()
        last_progress = -1  # Pour suivre le dernier pourcentage affiché

        while response is None:
            status, response = upload_request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                # N'afficher que si le pourcentage a changé d'au moins 5%
                if progress >= last_progress + 5 or progress == 100:
                    print(f"Upload progress: {progress}%")
                    last_progress = progress

        video_id = response['id']
        print(f"Upload complete! Video ID: {video_id}")

        # Set thumbnail if provided
        thumbnail_path = options.get('thumbnail_path')
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path)
                ).execute()
                print(f"Thumbnail set for video {video_id}")
            except HttpError as e:
                print(f"Error setting thumbnail: {e}")

        return {
            'success': True,
            'video_id': video_id,
            'title': body['snippet']['title']
        }

    except HttpError as e:
        print(f"An HTTP error occurred: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    except Exception as e:
        print(f"An error occurred: {e}")
        return {
            'success': False,
            'error': str(e)
        }
def find_playlist_by_name(youtube, playlist_name):
    """
    Recherche une playlist par son nom et retourne son ID.

    Args:
        youtube: Service YouTube API
        playlist_name (str): Nom de la playlist à rechercher

    Returns:
        str: ID de la playlist ou None si non trouvée
    """
    try:
        request = youtube.playlists().list(
            part="snippet,id",
            mine=True,
            maxResults=50
        )
        response = request.execute()

        for item in response.get("items", []):
            if item["snippet"]["title"].lower() == playlist_name.lower():
                return item["id"]

        # Si la playlist n'est pas trouvée dans les 50 premiers résultats
        # et qu'il y a un nextPageToken, continuer la recherche
        next_page_token = response.get("nextPageToken")
        while next_page_token:
            request = youtube.playlists().list(
                part="snippet,id",
                mine=True,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()

            for item in response.get("items", []):
                if item["snippet"]["title"].lower() == playlist_name.lower():
                    return item["id"]

            next_page_token = response.get("nextPageToken")

        return None
    except Exception as e:
        print(f"Error finding playlist: {e}")
        return None


def create_playlist(youtube, playlist_name):
    """
    Crée une nouvelle playlist et retourne son ID.

    Args:
        youtube: Service YouTube API
        playlist_name (str): Nom de la nouvelle playlist

    Returns:
        str: ID de la playlist créée ou None en cas d'erreur
    """
    try:
        request = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": playlist_name,
                    "description": f"Vidéos de la chaîne {playlist_name}"
                },
                "status": {
                    "privacyStatus": "private"
                }
            }
        )
        response = request.execute()
        print(f"Playlist '{playlist_name}' créée avec succès")
        return response.get("id")
    except Exception as e:
        print(f"Error creating playlist: {e}")
        return None


def add_video_to_playlist(youtube, playlist_id, video_id):
    """
    Ajoute une vidéo à une playlist.

    Args:
        youtube: Service YouTube API
        playlist_id (str): ID de la playlist
        video_id (str): ID de la vidéo à ajouter

    Returns:
        dict: Réponse de l'API ou None en cas d'erreur
    """
    try:
        request = youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id
                    }
                }
            }
        )
        return request.execute()
    except Exception as e:
        print(f"Error adding video to playlist: {e}")
        return None


def add_to_channel_playlist(youtube, video_id, channel_name):
    """
    Ajoute une vidéo à une playlist correspondant au nom de la chaîne.
    Si la playlist n'existe pas, elle est créée.

    Args:
        youtube: Service YouTube API
        video_id: ID de la vidéo YouTube
        channel_name: Nom de la chaîne extrait du chemin
    """
    # Rechercher si une playlist avec ce nom existe déjà
    playlist_id = find_playlist_by_name(youtube, channel_name)

    # Si aucune playlist n'existe, en créer une nouvelle
    if not playlist_id:
        playlist_id = create_playlist(youtube, channel_name)

    # Ajouter la vidéo à la playlist
    if playlist_id:
        result = add_video_to_playlist(youtube, playlist_id, video_id)
        if result:
            print(f"Vidéo ajoutée à la playlist '{channel_name}'")
        else:
            print(f"Échec de l'ajout à la playlist '{channel_name}'")
    else:
        print(f"Impossible de créer ou trouver une playlist pour '{channel_name}'")


def is_already_uploaded(video_path):
    """
    Checks if a video has already been uploaded.

    Args:
        video_path (str): Path to the video file

    Returns:
        bool: True if already uploaded, False otherwise
    """
    if not os.path.exists(UPLOADS_FILE):
        return False

    try:
        with open(UPLOADS_FILE, 'r') as f:
            uploads = json.load(f)

        return video_path in uploads
    except Exception as e:
        print(f"Error checking upload status: {e}")
        return False


def record_upload(video_path, video_id):
    """
    Records a successful upload.

    Args:
        video_path (str): Path to the video file
        video_id (str): YouTube video ID
    """
    uploads = {}

    # Load existing uploads if file exists
    if os.path.exists(UPLOADS_FILE):
        try:
            with open(UPLOADS_FILE, 'r') as f:
                uploads = json.load(f)
        except Exception as e:
            print(f"Error loading uploads file: {e}")

    # Add the new upload
    uploads[video_path] = {
        'video_id': video_id,
        'upload_time': datetime.datetime.now().isoformat()
    }

    # Save the updated uploads
    try:
        with open(UPLOADS_FILE, 'w') as f:
            json.dump(uploads, f, indent=2)
    except Exception as e:
        print(f"Error saving uploads file: {e}")


def parse_arguments():
    """
    Parses command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='YouTube Uploader')
    parser.add_argument('-s', '--setup', action='store_true', help='Run interactive setup')
    parser.add_argument('-r', '--run-once', action='store_true', help='Run once and exit (don\'t start scheduler)')
    parser.add_argument('-i', '--interval', type=int, help='Set scan interval in minutes')
    parser.add_argument('-f', '--folder', type=str, help='Set videos folder path')
    parser.add_argument('-g', '--ganymede', action='store_true', help='Enable Ganymede mode for VOD metadata')
    parser.add_argument('-p', '--auto-playlist', action='store_true', help='Auto-add videos to channel playlists')
    return parser.parse_args()


def get_config():
    """
    Gets the application configuration from environment variables and command line arguments.

    Returns:
        dict: Application configuration
    """
    config = {
        'videos_folder': os.environ.get('YTU_VIDEOS_FOLDER', ''),
        'privacy_status': os.environ.get('YTU_PRIVACY_STATUS', 'private'),
        'check_interval': int(os.environ.get('YTU_CHECK_INTERVAL', '60')),
        'client_secrets': os.environ.get('YTU_CLIENT_SECRETS', 'data/client_secrets.json'),
        'video_category': os.environ.get('YTU_VIDEO_CATEGORY', '22'),
        'description': os.environ.get('YTU_DESCRIPTION', 'Uploaded with YTU'),
        'tags': os.environ.get('YTU_TAGS', 'YTU Upload').split(','),
        'ganymede_mode': os.environ.get('YTU_GANYMEDE_MODE', 'false').lower() == 'true',
        'auto_playlist': os.environ.get('YTU_AUTO_PLAYLIST', 'false').lower() == 'true',
        'discord_webhook': os.environ.get('YTU_DISCORD_WEBHOOK', '')
    }

    # Override with command line arguments if provided
    args = parse_arguments()
    if args.interval:
        config['check_interval'] = args.interval
    if args.folder:
        config['videos_folder'] = args.folder
    if args.ganymede:
        config['ganymede_mode'] = True
    if args.auto_playlist:
        config['auto_playlist'] = True

    return config


def scan_for_videos(config):
    """
    Scans the configured folder for videos to upload.

    Args:
        config (dict): Application configuration

    Returns:
        list: List of video paths to upload
    """
    videos_folder = config['videos_folder']
    if not os.path.exists(videos_folder):
        print(f"Videos folder not found: {videos_folder}")
        return []

    videos_to_upload = []

    # If in Ganymede mode, look specifically for *-video.mp4 files
    if config['ganymede_mode']:
        for root, dirs, files in os.walk(videos_folder):
            # Exclure le dossier 'temp'
            if 'temp' in dirs:
                dirs.remove('temp')
            for file in files:
                if file.endswith('-video.mp4'):
                    videos_to_upload.append(os.path.join(root, file))
    else:
        # Standard mode - look for all .mp4 files
        for root, dirs, files in os.walk(videos_folder):
            # Exclure le dossier 'temp'
            if 'temp' in dirs:
                dirs.remove('temp')
            for file in files:
                if file.endswith('.mp4'):
                    videos_to_upload.append(os.path.join(root, file))

    return videos_to_upload

def process_video(youtube, video_path, config):
    """
    Processes a single video for upload.

    Args:
        youtube: YouTube API service object
        video_path (str): Path to the video file
        config (dict): Application configuration
    """
    # Check if already uploaded
    if is_already_uploaded(video_path):
        print(f"Skipping already uploaded video: {video_path}")
        return

    # Extract channel name for playlist
    channel_name = extract_channel_name(video_path)
    if channel_name:
        print(f"Detected channel: {channel_name}")

    # Prepare upload options
    options = {
        "categoryId": config['video_category'],
        "privacyStatus": config['privacy_status'],
        "tags": config['tags'],
    }

    # If not in Ganymede mode, use filename as title and default description
    if not config['ganymede_mode']:
        options["title"] = os.path.splitext(os.path.basename(video_path))[0]
        options["description"] = config['description']

    # Upload the video
    result = upload_video(youtube, video_path, options, is_ganymede=config['ganymede_mode'])

    # Record the upload
    if result and result.get('success'):
        video_id = result.get('video_id')
        video_title = result.get('title')
        record_upload(video_path, video_id)

        # Add to channel playlist if auto_playlist enabled AND Ganymede mode is active (nouveau comportement)
        if config['auto_playlist'] and channel_name and config['ganymede_mode']:
            add_to_channel_playlist(youtube, video_id, channel_name)
        elif config['auto_playlist'] and channel_name and not config['ganymede_mode']:
            print("Ajout à la playlist désactivé (Ganymede Mode inactif)")

        # Send Discord notification if webhook URL is configured
        webhook_url = config.get('discord_webhook')
        if webhook_url:
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            # URL de la miniature YouTube
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

            # Message avec un embed contenant la miniature
            message = {
                "embeds": [
                    {
                        "title": video_title,
                        "description": f"Nouvelle vidéo mise en ligne avec succès !",
                        "url": video_url,
                        "color": 5814783,  # Couleur bleu YouTube
                        "fields": [
                            {
                                "name": "Chaîne",
                                "value": channel_name if channel_name else "Non spécifiée",
                                "inline": True
                            },
                            {
                                "name": "Statut",
                                "value": options["privacyStatus"],
                                "inline": True
                            }
                        ],
                        "footer": {
                            "text": "Uploaded with PyYTUploader"
                        },
                        "timestamp": datetime.datetime.now(pytz.timezone(os.environ.get('TZ', 'Europe/Paris'))).isoformat(),
                        # Ajout de la miniature YouTube
                        "image": {
                            "url": thumbnail_url
                        }
                    }
                ]
            }

            send_discord_notification(webhook_url, message)


def run_uploader():
    """
    Main function to run the uploader.
    """
    config = get_config()
    args = parse_arguments()

    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)

    # Setup mode
    if args.setup:
        print("Running setup...")
        youtube = get_authenticated_service()
        if youtube:
            print("Authentication successful!")
        else:
            print("Setup failed.")
        return

    # Run once mode
    if args.run_once:
        youtube = get_authenticated_service()
        if not youtube:
            print("Authentication failed.")
            return

        videos = scan_for_videos(config)
        print(f"Found {len(videos)} videos to upload.")

        for video_path in videos:
            process_video(youtube, video_path, config)

        return

    # Scheduler mode
    print(f"Starting YouTube Uploader scheduler...")
    print(f"Videos folder: {config['videos_folder']}")
    print(f"Check interval: {config['check_interval']} minutes")
    print(f"Ganymede mode: {'Enabled' if config['ganymede_mode'] else 'Disabled'}")
    print(f"Auto-playlist: {'Enabled' if config['auto_playlist'] else 'Disabled'}")
    print(f"Discord notifications: {'Enabled' if config['discord_webhook'] else 'Disabled'}")

    while True:
        try:
            youtube = get_authenticated_service()
            if not youtube:
                print("Authentication failed. Retrying in 5 minutes...")
                time.sleep(300)
                continue

            videos = scan_for_videos(config)
            if videos:
                print(f"Found {len(videos)} videos to upload.")

                for video_path in videos:
                    process_video(youtube, video_path, config)
            else:
                print("No videos found to upload.")

            # Wait for the next check
            print(f"Next check in {config['check_interval']} minutes...")
            time.sleep(config['check_interval'] * 60)

        except KeyboardInterrupt:
            print("Uploader stopped by user.")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            print("Retrying in 5 minutes...")
            time.sleep(300)


if __name__ == '__main__':
    run_uploader()
