import os
import sys
import json
import time
import argparse
import datetime
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
from datetime import timezone, timedelta
from zoneinfo import ZoneInfo

# Configuration
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
TOKEN_FILE = 'data/token.json'
UPLOADS_FILE = 'data/uploads.json'


def is_token_expired(creds):
    """
    Vérifie si le token va expirer dans les 5 prochaines minutes.
    
    Args:
        creds: Credentials object
    
    Returns:
        bool: True si le token expire bientôt, False sinon
    """
    if not creds or not creds.expiry:
        return True
    
    # Ajouter une marge de sécurité de 5 minutes
    buffer_time = datetime.datetime.utcnow() + timedelta(minutes=5)
    return creds.expiry <= buffer_time


def save_credentials(creds):
    """
    Sauvegarde les credentials dans le fichier token.
    
    Args:
        creds: Credentials object
    
    Returns:
        bool: True si la sauvegarde a réussi
    """
    try:
        # Créer le dossier data s'il n'existe pas
        os.makedirs('data', exist_ok=True)
        
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
        
        print(f"Credentials saved to {TOKEN_FILE}")
        return True
        
    except Exception as e:
        print(f"Error saving credentials: {e}")
        return False


def load_credentials():
    """
    Charge les credentials depuis le fichier token.
    
    Returns:
        Credentials: Credentials object ou None si erreur
    """
    if not os.path.exists(TOKEN_FILE):
        return None
        
    try:
        with open(TOKEN_FILE, 'r') as token:
            token_data = json.load(token)
            
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        print(f"✓ Credentials loaded from {TOKEN_FILE}")
        
        # Vérifier la présence du refresh_token
        if not creds.refresh_token:
            print("⚠ WARNING: No refresh_token found in saved credentials!")
            print("⚠ Le token ne pourra pas être rafraîchi automatiquement.")
        
        # Afficher les informations sur l'expiration du token
        if creds.expiry:
            time_until_expiry = creds.expiry - datetime.datetime.utcnow()
            if time_until_expiry.total_seconds() > 0:
                print(f"Token expires in: {time_until_expiry}")
            else:
                print("Token has expired")
        
        return creds
        
    except Exception as e:
        print(f"Error loading credentials: {e}")
        return None


def refresh_credentials(creds):
    """
    Rafraîchit les credentials en utilisant le refresh_token.
    
    Args:
        creds: Credentials object
    
    Returns:
        Credentials: Credentials rafraîchis ou None si erreur
    """
    if not creds or not hasattr(creds, 'refresh_token') or not creds.refresh_token:
        print("="*60)
        print("ERROR: No refresh token available!")
        print("="*60)
        print("Le refresh_token est nécessaire pour renouveler automatiquement l'accès.")
        print("")
        print("SOLUTION:")
        print("1. Supprimez le fichier: data/token.json")
        print("2. Relancez avec: python youtube_uploader.py --reauth")
        print("3. Lors de l'autorisation Google, assurez-vous d'accepter tous les accès")
        print("="*60)
        return None
        
    try:
        print("Refreshing access token...")
        request = Request()
        creds.refresh(request)
        
        # Sauvegarder les nouveaux credentials
        if save_credentials(creds):
            print("✓ Token refreshed successfully!")
            if creds.expiry:
                time_until_expiry = creds.expiry - datetime.datetime.utcnow()
                print(f"✓ New token expires in: {time_until_expiry}")
        else:
            print("Warning: Token refreshed but failed to save to disk")
            
        return creds
        
    except Exception as e:
        print("="*60)
        print(f"ERROR: Token refresh failed!")
        print(f"Error details: {type(e).__name__}: {e}")
        print("="*60)
        print("SOLUTION:")
        print("1. Vérifiez votre connexion internet")
        print("2. Supprimez data/token.json")
        print("3. Relancez avec: python youtube_uploader.py --reauth")
        print("="*60)
        return None


def test_api_connection(youtube):
    """
    Teste la connexion à l'API YouTube pour vérifier que les credentials sont valides.
    
    Args:
        youtube: Service YouTube API
    
    Returns:
        bool: True si la connexion fonctionne
    """
    try:
        # Faire une requête simple pour tester la connexion
        request = youtube.channels().list(
            part="snippet",
            mine=True,
            maxResults=1
        )
        response = request.execute()
        
        if 'items' in response:
            channel_name = "Unknown"
            if response['items']:
                channel_name = response['items'][0]['snippet']['title']
            print(f"API connection test successful. Connected as: {channel_name}")
            return True
        else:
            print("API connection test: No channel data returned")
            return False
            
    except Exception as e:
        print(f"API connection test failed: {e}")
        return False


def get_local_timestamp():
    """
    Obtient le timestamp local en tenant compte du fuseau horaire défini.
    Utilise zoneinfo (Python 3.9+) - module standard, pas de dépendance externe.
    
    Returns:
        str: timestamp ISO avec timezone correcte
    """
    # Récupérer le fuseau horaire depuis la variable d'environnement
    tz_name = os.environ.get('TZ', 'Europe/Paris')
    
    try:
        # Créer l'objet timezone
        local_tz = ZoneInfo(tz_name)
    except Exception:
        # Fallback sur Europe/Paris si la timezone n'est pas reconnue
        local_tz = ZoneInfo('Europe/Paris')
    
    # Obtenir l'heure UTC actuelle avec timezone
    utc_now = datetime.datetime.utcnow().replace(tzinfo=ZoneInfo('UTC'))
    
    # Convertir vers le fuseau horaire local
    local_time = utc_now.astimezone(local_tz)
    
    # Retourner le timestamp ISO
    return local_time.isoformat()


def get_channel_display_name(video_path, fallback_channel_name):
    """
    Récupère le display_name de la chaîne depuis les métadonnées Ganymede.
    
    Args:
        video_path (str): Chemin vers le fichier vidéo
        fallback_channel_name (str): Nom de chaîne de fallback (depuis le dossier)
    
    Returns:
        str: Display name de la chaîne ou fallback
    """
    try:
        # Extraire l'ID vidéo depuis le nom de fichier
        video_id_match = re.search(r'(\d+)-video\.mp4$', os.path.basename(video_path))
        if not video_id_match:
            return fallback_channel_name
        video_id = video_id_match.group(1)
        info_file = os.path.join(os.path.dirname(video_path), f"{video_id}-info.json")
        if os.path.exists(info_file):
            with open(info_file, 'r', encoding='utf-8') as f:
                info_data = json.load(f)
            # Priorité au display_name
            if "channel" in info_data and "display_name" in info_data["channel"]:
                return info_data["channel"]["display_name"]
            elif "user_name" in info_data:
                return info_data["user_name"]
    except Exception as e:
        print(f"Error extracting channel display_name: {e}")
    return fallback_channel_name

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
    # Supprimer les caractères de contrôle (0x00-0x1F et 0x7F)
    title = re.sub(r'[\x00-\x1F\x7F]', '', title)
    # Supprimer certains caractères spéciaux
    title = re.sub(r'[:"/\\|?*]', '', title)
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


def is_running_in_docker():
    """
    Détecte si l'application tourne dans un conteneur Docker.
    
    Returns:
        bool: True si dans Docker, False sinon
    """
    # Vérifier si le fichier /.dockerenv existe (créé par Docker)
    if os.path.exists('/.dockerenv'):
        return True
    
    # Vérifier si on est dans un cgroup Docker
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read()
    except:
        pass
    
    # Vérifier les variables d'environnement Docker
    return os.environ.get('DOCKER_CONTAINER', '').lower() == 'true'


def delete_token_file():
    """
    Deletes the token file to force re-authentication.
    """
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        print("Token file deleted. Re-authentication will be required.")


def get_authenticated_service(interactive=False):
    """
    Authenticates with YouTube API and returns the service object.
    Améliore la gestion du rafraîchissement automatique des tokens.

    Args:
        interactive (bool): Whether to run in interactive mode for authentication.

    Returns:
        googleapiclient.discovery.Resource: YouTube API service object
    """
    config = get_config()
    client_secrets_file = config['client_secrets']
    
    # Charger les credentials existants
    creds = load_credentials()
    
    # Vérifier la validité des credentials
    if creds:
        if creds.valid:
            print("Using existing valid credentials")
        elif creds.expired and creds.refresh_token:
            print("Credentials expired, attempting to refresh...")
            creds = refresh_credentials(creds)
            
            # Si le rafraîchissement échoue, supprimer le token
            if not creds:
                print("Refresh failed, deleting token file...")
                delete_token_file()
        elif is_token_expired(creds) and creds.refresh_token:
            print("Credentials expiring soon, proactively refreshing...")
            creds = refresh_credentials(creds)
        else:
            print("Credentials invalid and no refresh token available")
            creds = None
    
    # Si aucun credential valide, faire l'authentification
    if not creds:
        if not os.path.exists(client_secrets_file):
            print(f"Client secrets file not found: {client_secrets_file}")
            return None

        try:
            print("Starting OAuth2 flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secrets_file, SCOPES)

            if interactive:
                # Détecter l'environnement
                in_docker = is_running_in_docker()
                
                print("="*60)
                print("Running interactive authentication...")
                if in_docker:
                    print("🐳 Docker environment detected - Using OOB flow")
                print("="*60)
                
                # Priorité à la méthode OOB (compatible Docker)
                use_oob = in_docker or os.environ.get('YTU_USE_OOB', '').lower() == 'true'
                
                if use_oob:
                    # Méthode OOB (Out-of-Band) - Compatible Docker
                    print("\n📋 Méthode manuelle (compatible Docker)")
                    print("="*60)
                    
                    flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
                    auth_url, _ = flow.authorization_url(
                        prompt='consent',
                        access_type='offline'
                    )
                    
                    print("\n1. Visitez cette URL dans votre navigateur:")
                    print(f"   {auth_url}")
                    print("\n2. Autorisez l'application")
                    print("3. Copiez le code d'autorisation affiché")
                    print("="*60 + "\n")
                    
                    code = input('Entrez le code d\'autorisation: ').strip()
                    flow.fetch_token(code=code)
                    creds = flow.credentials
                    
                else:
                    # Méthode serveur local (pour environnement desktop)
                    print("\n🖥️  Méthode serveur local (desktop)")
                    print("Un navigateur va s'ouvrir automatiquement.")
                    print("="*60 + "\n")
                    
                    try:
                        creds = flow.run_local_server(
                            port=0,
                            prompt='consent',
                            authorization_prompt_message='Please visit this URL: {url}',
                            success_message='✓ Authentication successful! You can close this window.',
                            open_browser=True
                        )
                    except Exception as e:
                        print(f"\n⚠ Erreur avec le serveur local: {e}")
                        print("\nRetour à la méthode manuelle...\n")
                        
                        # Fallback sur OOB
                        flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
                        auth_url, _ = flow.authorization_url(
                            prompt='consent',
                            access_type='offline'
                        )
                        print(f'Visitez cette URL: {auth_url}\n')
                        code = input('Entrez le code d\'autorisation: ').strip()
                        flow.fetch_token(code=code)
                        creds = flow.credentials
                
                # Vérifier que le refresh_token a bien été obtenu
                print("\n" + "="*60)
                if creds.refresh_token:
                    print("✓ SUCCESS: Refresh token obtained!")
                    print("✓ L'authentification automatique est maintenant configurée.")
                else:
                    print("⚠ WARNING: No refresh token received!")
                    print("⚠ Cela peut arriver si vous aviez déjà autorisé cette app.")
                    print("\nSOLUTION:")
                    print("1. Allez sur: https://myaccount.google.com/permissions")
                    print("2. Révoquez l'accès pour votre application YouTube Uploader")
                    print("3. Relancez: python youtube_uploader.py --reauth")
                print("="*60 + "\n")
            else:
                print("Authentication token is invalid or expired, and the application is not running in interactive mode.")
                print("Please run with the --reauth flag to re-authenticate.")
                return None
        
        except Exception as e:
            print(f"Error during authentication: {e}")
            return None

        # Vérifier que le refresh_token existe avant de sauvegarder
        if not creds.refresh_token:
            print("\n" + "="*60)
            print("⚠ CRITICAL WARNING: No refresh_token obtained!")
            print("="*60)
            print("L'authentification ne sera pas persistante.")
            print("Vous devrez vous réauthentifier à chaque fois.")
            print("\nPour corriger:")
            print("1. Révoquezl'accès: https://myaccount.google.com/permissions")
            print("2. Relancez: python youtube_uploader.py --reauth")
            print("="*60 + "\n")
        
        # Sauvegarder les nouveaux credentials
        if not save_credentials(creds):
            print("Warning: Failed to save credentials")
        elif creds.refresh_token:
            print("✓ Credentials saved with refresh_token")

    # Créer le service YouTube
    try:
        service = build(API_SERVICE_NAME, API_VERSION, credentials=creds)
        print("YouTube API service created successfully")
        return service
        
    except Exception as e:
        print(f"Error building YouTube service: {e}")
        
        # En cas d'erreur, essayer de rafraîchir une dernière fois
        if creds and creds.refresh_token:
            print("Attempting final token refresh...")
            refreshed_creds = refresh_credentials(creds)
            if refreshed_creds:
                try:
                    service = build(API_SERVICE_NAME, API_VERSION, credentials=refreshed_creds)
                    print("YouTube API service created after refresh")
                    return service
                except Exception as e2:
                    print(f"Service creation failed after refresh: {e2}")
        
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
            elif "channel" in info_data:
                # Priorité au display_name, fallback sur name si display_name n'existe pas
                if "display_name" in info_data["channel"]:
                    channel_name = info_data["channel"]["display_name"]
                elif "name" in info_data["channel"]:
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
    parser.add_argument('--reauth', action='store_true', help='Force re-authentication by deleting the token file')
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

    # Si on est en mode Ganymede, utiliser le display_name des métadonnées
    if config['ganymede_mode']:
        channel_name = get_channel_display_name(video_path, channel_name)

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

        # Add to channel playlist if auto_playlist enabled AND Ganymede mode is active
        if config['auto_playlist'] and channel_name and config['ganymede_mode']:
            add_to_channel_playlist(youtube, video_id, channel_name)
        elif config['auto_playlist'] and channel_name and not config['ganymede_mode']:
            print("Ajout à la playlist désactivé (Ganymede Mode inactif)")

        # Send Discord notification if webhook URL is configured
        webhook_url = config.get('discord_webhook')
        if webhook_url:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

            message = {
                "embeds": [
                    {
                        "title": video_title,
                        "description": f"Nouvelle vidéo mise en ligne avec succès !",
                        "url": video_url,
                        "color": 5814783,
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
                        "timestamp": get_local_timestamp(),
                        "image": {
                            "url": thumbnail_url
                        }
                    }
                ]
            }

            send_discord_notification(webhook_url, message)


def run_uploader():
    """
    Main function to run the uploader with improved token management.
    """
    config = get_config()
    args = parse_arguments()

    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)

    # Re-authentication mode
    if args.reauth:
        delete_token_file()
        print("Running setup to re-authenticate...")
        youtube = get_authenticated_service(interactive=True)
        if youtube and test_api_connection(youtube):
            print("Re-authentication successful!")
        else:
            print("Re-authentication failed.")
        return

    # Setup mode
    if args.setup:
        print("Running setup...")
        youtube = get_authenticated_service(interactive=True)
        if youtube and test_api_connection(youtube):
            print("Authentication successful!")
        else:
            print("Setup failed.")
        return

    # Run once mode
    if args.run_once:
        youtube = get_authenticated_service(interactive=True)
        if not youtube:
            print("Authentication failed.")
            return

        if not test_api_connection(youtube):
            print("API connection test failed.")
            return

        videos = scan_for_videos(config)
        print(f"Found {len(videos)} videos to upload.")

        for video_path in videos:
            process_video(youtube, video_path, config)

        return

    # Scheduler mode avec gestion améliorée des tokens
    print(f"Starting YouTube Uploader scheduler...")
    print(f"Videos folder: {config['videos_folder']}")
    print(f"Check interval: {config['check_interval']} minutes")
    print(f"Ganymede mode: {'Enabled' if config['ganymede_mode'] else 'Disabled'}")
    print(f"Auto-playlist: {'Enabled' if config['auto_playlist'] else 'Disabled'}")
    print(f"Discord notifications: {'Enabled' if config['discord_webhook'] else 'Disabled'}")

    youtube = None
    last_auth_check = datetime.datetime.utcnow()
    auth_check_interval = timedelta(minutes=30)  # Vérifier l'auth toutes les 30 minutes

    while True:
        try:
            current_time = datetime.datetime.utcnow()
            
            # Vérifier périodiquement si une ré-authentification est nécessaire
            if not youtube or (current_time - last_auth_check) >= auth_check_interval:
                print("Checking authentication status...")
                youtube = get_authenticated_service(interactive=False)
                last_auth_check = current_time
                
                if not youtube:
                    print("Authentication failed. Retrying in 5 minutes...")
                    time.sleep(300)
                    continue
                    
                if not test_api_connection(youtube):
                    print("API connection test failed. Retrying in 5 minutes...")
                    youtube = None
                    time.sleep(300)
                    continue

            videos = scan_for_videos(config)
            if videos:
                print(f"Found {len(videos)} videos to upload.")

                for video_path in videos:
                    # Avant chaque upload, vérifier si le service est toujours valide
                    if not test_api_connection(youtube):
                        print("API connection lost, re-authenticating...")
                        youtube = get_authenticated_service(interactive=False)
                        if not youtube:
                            print("Re-authentication failed, skipping this upload cycle")
                            break
                    
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
            youtube = None  # Force re-authentication on next cycle
            time.sleep(300)


if __name__ == '__main__':
    run_uploader()
