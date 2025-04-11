import os
import time
import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Scopes nécessaires pour l'upload et la vérification du statut
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube'
]


def authenticate_youtube():
    """Authentifie l'application à l'API YouTube"""
    print("Authentification à l'API YouTube...")
    creds = None
    if os.path.exists('token.json'):
        print("Lecture du token existant...")
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Rafraîchissement du token expiré...")
            creds.refresh(Request())
        else:
            print("Création d'un nouveau token d'authentification...")
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=8080)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            print("Token sauvegardé")
    print("Authentification réussie")
    return build('youtube', 'v3', credentials=creds)


def check_processing_status(youtube, video_id, max_checks=15):
    """Vérifie périodiquement le statut de traitement d'une vidéo"""
    print(f"\nSurveillance du statut de traitement pour la vidéo {video_id}...")

    for i in range(max_checks):
        try:
            response = youtube.videos().list(
                part='status,processingDetails',
                id=video_id
            ).execute()

            if not response['items']:
                print("Vidéo non trouvée")
                return False

            video_item = response['items'][0]
            upload_status = video_item['status'].get('uploadStatus', 'processing')

            if 'processingDetails' in video_item:
                processing_status = video_item['processingDetails'].get('processingStatus', 'processing')
                processing_progress = video_item['processingDetails'].get('processingProgress', {})

                parts_processed = processing_progress.get('partsProcessed', 0)
                parts_total = processing_progress.get('partsTotal', 1)

                progress_percent = (int(parts_processed) / int(parts_total) * 100) if int(parts_total) > 0 else 0

                print(f"Statut d'upload: {upload_status}")
                print(f"Statut de traitement: {processing_status}")
                print(f"Progression: {progress_percent:.1f}% ({parts_processed}/{parts_total})")

                if upload_status == 'processed':
                    print("Vidéo complètement traitée et disponible!")
                    return True
            else:
                print(f"Statut d'upload: {upload_status}")

            # Si c'est la dernière vérification, ne pas indiquer d'attente
            if i < max_checks - 1:
                wait_time = 30  # secondes
                print(f"Nouvelle vérification dans {wait_time} secondes...")
                time.sleep(wait_time)

        except HttpError as e:
            print(f"Erreur lors de la vérification du statut: {e.content.decode()}")
            return False

    print("Délai maximum de vérification atteint. Le traitement peut continuer en arrière-plan.")
    return False


def upload_video(youtube, file_path, title, description, category_id, tags):
    """Upload une vidéo sur YouTube et suit le processus"""
    print(f"\nPréparation à l'upload de '{title}'...")
    print(f"Fichier source: {file_path}")

    file_size = os.path.getsize(file_path)
    print(f"Taille du fichier: {file_size / 1024 / 1024:.2f} MB")

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': category_id
        },
        'status': {
            'privacyStatus': 'private'
        }
    }

    # Créer un objet MediaFileUpload avec suivi de progression
    media = MediaFileUpload(file_path, mimetype='video/mp4',
                            chunksize=1024 * 1024, resumable=True)

    # Créer la requête d'insertion
    request = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )

    print("Démarrage de l'upload...")
    response = None
    last_progress = 0

    # Upload avec suivi de progression
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                # Calcul du pourcentage de progression
                progress = int(status.progress() * 100)
                if progress > last_progress + 5:  # Afficher tous les 5%
                    print(f"Upload en cours: {progress}%")
                    last_progress = progress
        except HttpError as e:
            print(f"Une erreur est survenue pendant l'upload: {e.content.decode()}")
            return None

    print(f"Upload terminé avec succès!")
    video_id = response['id']
    video_url = f"https://youtu.be/{video_id}"
    print(f"Video ID: {video_id}")
    print(f"URL: {video_url}")

    # Vérifier le statut du traitement de la vidéo
    check_processing_status(youtube, video_id)

    return video_url


def main():
    try:
        print("=== YouTube Uploader ===")
        youtube = authenticate_youtube()

        folder_path = 'C:/Users/nlesage/Videos'
        print(f"Recherche de vidéos dans: {folder_path}")

        video_files = [f for f in os.listdir(folder_path) if f.endswith('.mp4')]
        print(f"Nombre de fichiers .mp4 trouvés: {len(video_files)}")

        for i, filename in enumerate(video_files, 1):
            print(f"\n[{i}/{len(video_files)}] Traitement de {filename}")
            file_path = os.path.join(folder_path, filename)
            title = os.path.splitext(filename)[0]

            start_time = time.time()
            video_url = upload_video(youtube, file_path, title, 'Uploaded with YTU', '22', ['tag1', 'tag2'])
            elapsed_time = time.time() - start_time

            if video_url:
                print(f"Temps total d'upload et vérification: {elapsed_time:.2f} secondes")
                print(f"Vidéo '{title}' uploadée à: {video_url}")
                print("Note: Le traitement sur YouTube peut continuer en arrière-plan")

                # Attendre un peu entre chaque upload pour éviter de surcharger l'API
                if i < len(video_files):
                    wait_time = 5  # secondes
                    print(f"Attente de {wait_time} secondes avant le prochain upload...")
                    time.sleep(wait_time)

    except Exception as e:
        print(f"Une erreur est survenue: {str(e)}")


if __name__ == '__main__':
    main()