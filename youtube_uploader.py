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
        print(f"Credentials loaded from {TOKEN_FILE}")
        
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
    if not creds.refresh_token:
        print("No refresh token available. Re-authentication required.")
        return None
        
    try:
        print("Refreshing access token...")
        request = Request()
        creds.refresh(request)
        
        # Sauvegarder les nouveaux credentials
        if save_credentials(creds):
            print("Token refreshed successfully!")
            if creds.expiry:
                time_until_expiry = creds.expiry - datetime.datetime.utcnow()
                print(f"New token expires in: {time_until_expiry}")
        
        return creds
        
    except Exception as e:
        print(f"Error refreshing credentials: {e}")
        print("Token refresh failed. Re-authentication may be required.")
        return None


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
                # Mode interactif
                print("Running interactive authentication...")
                auth_url, _ = flow.authorization_url(
                    prompt='consent',
                    access_type='offline',  # Important pour obtenir un refresh_token
                    include_granted_scopes='true'
                )
                print(f'Please visit this URL to authorize this application: {auth_url}')
                code = input('Enter the authorization code: ')
                flow.fetch_token(code=code)
                creds = flow.credentials
            else:
                print("Authentication token is invalid or expired, and the application is not running in interactive mode.")
                print("Please run with the --reauth flag to re-authenticate.")
                return None
        
        except Exception as e:
            print(f"Error during authentication: {e}")
            return None

        # Sauvegarder les nouveaux credentials
        if not save_credentials(creds):
            print("Warning: Failed to save credentials")

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


# [Le reste du code reste identique...]

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


def delete_token_file():
    """
    Deletes the token file to force re-authentication.
    """
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        print("Token file deleted. Re-authentication will be required.")


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


# [Continuer avec le reste des fonctions existantes...]

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


# [Continuer avec toutes les autres fonctions existantes du fichier original...]

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


# [Ajouter les fonctions manquantes du fichier original...]

def extract_ganymede_metadata(video_path):
    """
    Extracts metadata from Ganymede VOD structure.
    """
    # [Code de la fonction originale...]
    pass

def upload_video(youtube, video_path, options=None, is_ganymede=False):
    """
    Uploads a video to YouTube with the specified options.
    """
    # [Code de la fonction originale...]
    pass

def parse_arguments():
    """
    Parses command line arguments.
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
    """
    # [Code de la fonction originale...]
    pass

def process_video(youtube, video_path, config):
    """
    Processes a single video for upload.
    """
    # [Code de la fonction originale...]
    pass

# [Autres fonctions nécessaires...]

if __name__ == '__main__':
    run_uploader()
