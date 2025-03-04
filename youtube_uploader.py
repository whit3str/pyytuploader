import os
import logging
from google_auth_oauthlib.flow import InstalledAppFlow
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
        Authentifie l'utilisateur auprès de l'API YouTube.
        
        :return: Client YouTube authentifié
        """
        try:
            scopes = ['https://www.googleapis.com/auth/youtube.upload']
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_path, 
                scopes
            )
            credentials = flow.run_local_server(port=0)
            return build('youtube', 'v3', credentials=credentials)
        except Exception as e:
            logging.error(f"Authentication failed: {e}")
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
            file_size = os.path.getsize(video_path)
            logging.info(f"Preparing to upload: {video_path} (Size: {file_size/1024/1024:.2f} MB)")

            media = MediaFileUpload(video_path, resumable=True)
            
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
            
            request = self.youtube_service.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = request.execute()
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
        
        logging.info(f"Starting batch upload from directory: {directory_path}")
        
        for filename in os.listdir(directory_path):
            if os.path.splitext(filename)[1].lower() in video_extensions:
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

        logging.info("Batch upload completed")

def main():
    # Chemin vers votre fichier de credentials OAuth
    CREDENTIALS_PATH = 'credentials.json'
    
    # Chemin du dossier contenant les vidéos
    VIDEO_DIRECTORY = './videos'  # Assurez-vous que ce dossier existe
    
    try:
        uploader = YouTubeVideoUploader(CREDENTIALS_PATH)
        uploader.upload_videos_from_directory(VIDEO_DIRECTORY)
    except Exception as e:
        logging.error(f"Script terminated with error: {e}")

if __name__ == '__main__':
    main()