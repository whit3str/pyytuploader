import os
import pickle
import logging
import time
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s: %(message)s',
    filename='youtube_upload.log'
)

class YouTubeVideoUploader:
    def __init__(self, credentials_path):
        """
        Initialise le client YouTube avec les credentials OAuth.
        
        :param credentials_path: Chemin vers le fichier de credentials OAuth
        """
        self.credentials_path = credentials_path
        self.youtube_service = self._authenticate()

    def _authenticate(self):
        """
        Authentifie l'utilisateur auprès de l'API YouTube avec gestion améliorée des jetons.
        
        :return: Client YouTube authentifié
        """
        creds = None
        token_pickle = 'token.pickle'
        
        # Charger les credentials depuis le fichier token.pickle s'il existe
        if os.path.exists(token_pickle):
            logging.info("Loading credentials from token.pickle")
            with open(token_pickle, 'rb') as token:
                creds = pickle.load(token)
        
        # Si aucun credential valide n'est disponible, demander à l'utilisateur de se connecter
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logging.info("Refreshing expired credentials")
                creds.refresh(Request())
            else:
                logging.info("Getting new credentials")
                try:
                    # Supprimer tout fichier de cache temporaire potentiellement existant
                    for file in ['./.oauthlib_cache.sqlite', './.oath2_cache']:
                        if os.path.exists(file):
                            os.remove(file)
                            logging.info(f"Removed cached OAuth file: {file}")
                    
                    scopes = ['https://www.googleapis.com/auth/youtube.upload']
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path,
                        scopes
                    )
                    
                    # Attendre un moment pour s'assurer que les connexions réseau sont stables
                    time.sleep(1)
                    
                    # Utiliser run_local_server avec plus d'options
                    creds = flow.run_local_server(
                        port=8080,  # Port dynamique pour éviter les conflits
                        open_browser=True,
                        authorization_prompt_message="S'authentifier dans le navigateur qui s'ouvre",
                        success_message="Authentification réussie. Vous pouvez fermer cette fenêtre."
                    )
                except Exception as e:
                    logging.error(f"Authentication process failed: {e}")
                    raise
                
            # Sauvegarder les credentials pour la prochaine exécution
            with open(token_pickle, 'wb') as token:
                pickle.dump(creds, token)
                logging.info("Credentials saved to token.pickle")
                
        try:
            service = build('youtube', 'v3', credentials=creds)
            logging.info("YouTube API service built successfully")
            return service
        except Exception as e:
            logging.error(f"Failed to build service: {e}")
            raise

    def upload_video(self, video_path, title, description, category_id='22', privacy_status='private'):
        """
        Uploade une vidéo sur YouTube.
        
        :param video_path: Chemin complet vers le fichier vidéo
        :param title: Titre de la vidéo
        :param description: Description de la vidéo
        :param category_id: ID de catégorie YouTube (défaut: 22 - People & Blogs)
        :param privacy_status: Statut de confidentialité (private, public, unlisted)
        :return: Détails de la vidéo uploadée
        """
        try:
            if not os.path.exists(video_path):
                logging.error(f"Video file not found: {video_path}")
                raise FileNotFoundError(f"Video file not found: {video_path}")
                
            file_size = os.path.getsize(video_path)
            logging.info(f"Preparing to upload: {video_path} (Size: {file_size/1024/1024:.2f} MB)")

            media = MediaFileUpload(video_path, resumable=True, chunksize=1024*1024)
            
            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'categoryId': category_id
                },
                'status': {
                    'privacyStatus': privacy_status
                }
            }
            
            # Créer la requête d'insertion
            request = self.youtube_service.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            # Effectuer l'upload avec gestion de la progression
            logging.info(f"Starting upload for: {title}")
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logging.info(f"Upload progress: {progress}%")
            
            logging.info(f"Successfully uploaded: {title} (Video ID: {response['id']})")
            return response

        except Exception as e:
            logging.error(f"Upload failed for {video_path}: {e}")
            raise

    def upload_videos_from_directory(self, directory_path, description_template='Vidéo uploadée depuis mon script'):
        """
        Uploade toutes les vidéos d'un répertoire.
        
        :param directory_path: Chemin du répertoire contenant les vidéos
        :param description_template: Modèle de description pour les vidéos
        """
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv']
        
        if not os.path.exists(directory_path):
            logging.error(f"Directory not found: {directory_path}")
            raise FileNotFoundError(f"Directory not found: {directory_path}")
            
        logging.info(f"Starting batch upload from directory: {directory_path}")
        
        videos_found = False
        for filename in os.listdir(directory_path):
            if os.path.splitext(filename)[1].lower() in video_extensions:
                videos_found = True
                video_path = os.path.join(directory_path, filename)
                title = os.path.splitext(filename)[0]
                
                try:
                    self.upload_video(
                        video_path, 
                        title, 
                        description_template
                    )
                except Exception as e:
                    logging.error(f"Skipping {filename} due to error: {e}")
        
        if not videos_found:
            logging.warning(f"No video files found in {directory_path}")
        else:
            logging.info("Batch upload completed")

def main():
    # Chemin vers votre fichier de credentials OAuth
    CREDENTIALS_PATH = 'credentials.json'
    
    # Chemin du dossier contenant les vidéos
    VIDEO_DIRECTORY = './videos'
    
    # Vérifier si le dossier videos existe, sinon le créer
    if not os.path.exists(VIDEO_DIRECTORY):
        os.makedirs(VIDEO_DIRECTORY)
        logging.info(f"Created directory: {VIDEO_DIRECTORY}")
    else:
        logging.info(f"Using existing directory: {VIDEO_DIRECTORY}")
    
    # Vérifier si le fichier credentials existe
    if not os.path.exists(CREDENTIALS_PATH):
        logging.error(f"Credentials file not found: {CREDENTIALS_PATH}")
        print(f"ERROR: Credentials file not found: {CREDENTIALS_PATH}")
        print("Please download your OAuth credentials from Google Cloud Console")
        return
    
    # Si token.pickle existe mais est corrompu, le supprimer
    if os.path.exists('token.pickle'):
        try:
            with open('token.pickle', 'rb') as f:
                pickle.load(f)
        except:
            logging.warning("Corrupt token.pickle file found, removing it")
            os.remove('token.pickle')
        
    try:
        uploader = YouTubeVideoUploader(CREDENTIALS_PATH)
        uploader.upload_videos_from_directory(VIDEO_DIRECTORY)
        print("Upload process completed. Check log file for details.")
    except Exception as e:
        logging.error(f"Script terminated with error: {e}")
        print(f"ERROR: {e}")
        print("Check youtube_upload.log for more details.")

if __name__ == '__main__':
    main()
