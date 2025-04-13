import os
import time
import json
import logging
import argparse
import schedule
from datetime import datetime
import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Set up logging
logging.basicConfig(
    filename='upload.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Scopes needed for upload and status verification
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube'
]

# File to store uploaded videos info
UPLOAD_HISTORY_FILE = 'data/upload_history.json'
CONFIG_FILE = 'data/config.json'

# Default configuration
DEFAULT_CONFIG = {
    "videos_folder": "",
    "check_interval": 60,  # minutes
    "privacy_status": "private",
    "video_category": "22",  # People & Blogs
    "tags": ["YTU Upload"],
    "description": "Uploaded with YTU"
}


def load_config():
    """Load configuration from config file or create default if not exists"""
    # Create data directory if it doesn't exist
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

    # Read environment variables first, they take precedence
    env_config = {}

    if 'YTU_VIDEOS_FOLDER' in os.environ:
        env_config['videos_folder'] = os.environ['YTU_VIDEOS_FOLDER']
        logging.info(f"Using videos folder from environment: {env_config['videos_folder']}")

    if 'YTU_PRIVACY_STATUS' in os.environ:
        privacy = os.environ['YTU_PRIVACY_STATUS'].lower()
        if privacy in ['private', 'unlisted', 'public']:
            env_config['privacy_status'] = privacy
            logging.info(f"Using privacy status from environment: {env_config['privacy_status']}")
        else:
            logging.warning(f"Invalid privacy status in environment: {privacy}. Using default.")

    if 'YTU_CHECK_INTERVAL' in os.environ:
        try:
            interval = int(os.environ['YTU_CHECK_INTERVAL'])
            if interval > 0:
                env_config['check_interval'] = interval
                logging.info(f"Using check interval from environment: {env_config['check_interval']} minutes")
            else:
                logging.warning("Invalid check interval in environment (must be > 0). Using default.")
        except ValueError:
            logging.warning(f"Invalid check interval format in environment. Using default.")

    if 'YTU_VIDEO_CATEGORY' in os.environ:
        env_config['video_category'] = os.environ['YTU_VIDEO_CATEGORY']
        logging.info(f"Using video category from environment: {env_config['video_category']}")

    if 'YTU_DESCRIPTION' in os.environ:
        env_config['description'] = os.environ['YTU_DESCRIPTION']
        logging.info(f"Using description from environment")

    if 'YTU_TAGS' in os.environ:
        try:
            tags = os.environ['YTU_TAGS'].split(',')
            env_config['tags'] = [tag.strip() for tag in tags]
            logging.info(f"Using tags from environment: {env_config['tags']}")
        except:
            logging.warning("Error parsing tags from environment. Using default.")

    # Load from config file
    file_config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                file_config.update(json.load(f))
        except json.JSONDecodeError:
            logging.warning(f"Error reading {CONFIG_FILE}, creating new config")
            save_config(file_config)
    else:
        save_config(file_config)

    # Merge configs: env vars override file config, file config overrides defaults
    config = DEFAULT_CONFIG.copy()
    config.update(file_config)
    config.update(env_config)

    return config


def save_config(config):
    """Save configuration to config file"""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    logging.info("Configuration saved")


def authenticate_youtube():
    """Authenticate the application to the YouTube API"""
    print("Authenticating to YouTube API...")
    logging.info("Authenticating to YouTube API")
    creds = None
    token_path = 'data/token.json'
    os.makedirs(os.path.dirname(token_path), exist_ok=True)

    if os.path.exists(token_path):
        print("Reading existing token...")
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            logging.info("Refreshing expired token")
            creds.refresh(Request())
        else:
            print("Creating new authentication token...")
            logging.info("Creating new authentication token")
            client_secrets_path = os.environ.get('YTU_CLIENT_SECRETS', 'data/client_secrets.json')
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
            creds = flow.run_local_server(port=8080)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            print("Token saved")
            logging.info("Token saved")
    print("Authentication successful")
    logging.info("Authentication successful")
    return build('youtube', 'v3', credentials=creds)


def load_upload_history():
    """Load the history of uploaded videos"""
    os.makedirs(os.path.dirname(UPLOAD_HISTORY_FILE), exist_ok=True)
    if os.path.exists(UPLOAD_HISTORY_FILE):
        try:
            with open(UPLOAD_HISTORY_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Error reading {UPLOAD_HISTORY_FILE}, creating new history")
            logging.warning(f"Error reading {UPLOAD_HISTORY_FILE}, creating new history")
            return {}
    return {}


def save_upload_history(history):
    """Save the history of uploaded videos"""
    os.makedirs(os.path.dirname(UPLOAD_HISTORY_FILE), exist_ok=True)
    with open(UPLOAD_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def is_already_uploaded(filename, history):
    """Check if a video has already been uploaded"""
    return filename in history


def get_user_uploaded_videos(youtube):
    """Get a list of videos already uploaded by the user"""
    print("Getting list of your YouTube videos...")
    logging.info("Getting list of your YouTube videos")

    videos = {}

    try:
        # First, get the user's channel ID
        channels_response = youtube.channels().list(
            part="contentDetails",
            mine=True
        ).execute()

        if not channels_response.get('items'):
            print("Could not retrieve channel information.")
            logging.warning("Could not retrieve channel information")
            return videos

        # Get the uploads playlist ID
        uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

        # Now get videos from the uploads playlist
        next_page_token = None

        while True:
            # Get playlist items
            playlist_response = youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            # Extract video information
            for item in playlist_response.get('items', []):
                video_id = item['snippet']['resourceId']['videoId']
                title = item['snippet']['title']
                videos[title] = video_id

            # Check if there are more pages
            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token:
                break

    except HttpError as e:
        print(f"Error retrieving videos: {e}")
        logging.error(f"Error retrieving videos: {e}")

    print(f"Found {len(videos)} videos in your YouTube account")
    logging.info(f"Found {len(videos)} videos in your YouTube account")
    return videos


def check_processing_status(youtube, video_id, max_checks=3):
    """Check the processing status of a video but with fewer checks and shorter intervals"""
    print(f"\nChecking initial processing status for video {video_id}...")
    logging.info(f"Checking initial processing status for video {video_id}")

    for i in range(max_checks):
        try:
            response = youtube.videos().list(
                part='status,processingDetails',
                id=video_id
            ).execute()

            if not response['items']:
                print("Video not found")
                logging.warning("Video not found")
                return False

            video_item = response['items'][0]
            upload_status = video_item['status'].get('uploadStatus', 'processing')

            if 'processingDetails' in video_item:
                processing_status = video_item['processingDetails'].get('processingStatus', 'processing')
                processing_progress = video_item['processingDetails'].get('processingProgress', {})

                parts_processed = processing_progress.get('partsProcessed', 0)
                parts_total = processing_progress.get('partsTotal', 1)

                progress_percent = (int(parts_processed) / int(parts_total) * 100) if int(parts_total) > 0 else 0

                print(f"Upload status: {upload_status}")
                print(f"Processing status: {processing_status}")
                print(f"Progress: {progress_percent:.1f}% ({parts_processed}/{parts_total})")
                logging.info(
                    f"Video status: upload={upload_status}, processing={processing_status}, progress={progress_percent:.1f}%")

                # If processing is complete, return success
                if upload_status == 'processed':
                    print("Video fully processed and available!")
                    logging.info("Video fully processed and available")
                    return True

                # If we confirm processing has started, that's good enough
                if upload_status == 'uploaded' and i >= 1:
                    print("Upload confirmed. Processing will continue in the background.")
                    logging.info("Upload confirmed. Processing will continue in the background.")
                    return True
            else:
                print(f"Upload status: {upload_status}")
                logging.info(f"Upload status: {upload_status}")

            # If this is the last check, don't indicate waiting
            if i < max_checks - 1:
                wait_time = 10  # seconds
                print(f"Checking again in {wait_time} seconds...")
                time.sleep(wait_time)

        except HttpError as e:
            print(f"Error checking status: {e.content.decode()}")
            logging.error(f"Error checking status: {e}")
            return False

    print("Moving on to next upload. Processing will continue in the background.")
    logging.info("Moving on to next upload. Processing will continue in the background.")
    # Return True even though processing isn't complete, so we can move on
    return True


def upload_video(youtube, file_path, title, description, category_id, tags, privacy_status='private'):
    """Upload a video to YouTube and track the process"""
    print(f"\nPreparing to upload '{title}'...")
    print(f"Source file: {file_path}")
    logging.info(f"Preparing to upload '{title}' from {file_path}")

    file_size = os.path.getsize(file_path)
    print(f"File size: {file_size / 1024 / 1024:.2f} MB")
    logging.info(f"File size: {file_size / 1024 / 1024:.2f} MB")

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': category_id
        },
        'status': {
            'privacyStatus': privacy_status
        }
    }

    # Create a MediaFileUpload object with progress tracking
    media = MediaFileUpload(file_path, mimetype='video/mp4',
                            chunksize=1024 * 1024, resumable=True)

    # Create the insert request
    request = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )

    print("Starting upload...")
    logging.info("Starting upload...")
    response = None
    last_progress = 0

    # Upload with progress tracking
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                # Calculate progress percentage
                progress = int(status.progress() * 100)
                if progress > last_progress + 5:  # Display every 5%
                    print(f"Upload in progress: {progress}%")
                    logging.info(f"Upload progress: {progress}%")
                    last_progress = progress
        except HttpError as e:
            print(f"An error occurred during upload: {e.content.decode()}")
            logging.error(f"Upload error: {e}")
            return None

    print(f"Upload completed successfully!")
    logging.info("Upload completed successfully")
    video_id = response['id']
    video_url = f"https://youtu.be/{video_id}"
    print(f"Video ID: {video_id}")
    print(f"URL: {video_url}")
    logging.info(f"Video ID: {video_id}, URL: {video_url}")

    # Just check initial processing status to confirm upload was accepted
    check_processing_status(youtube, video_id, max_checks=3)

    return video_id, video_url


def scan_and_upload(config):
    """Scan the videos folder and upload new videos"""
    print(f"\n===== Starting scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====")
    logging.info(f"Starting scan for new videos in {config['videos_folder']}")

    folder_path = config['videos_folder']

    # Check if folder exists
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        print(f"Error: Folder {folder_path} does not exist or is not a directory")
        logging.error(f"Folder {folder_path} does not exist or is not a directory")
        return

    try:
        youtube = authenticate_youtube()

        # Load upload history
        upload_history = load_upload_history()

        # Get list of videos already on YouTube
        existing_videos = get_user_uploaded_videos(youtube)

        # Find all mp4 files in the folder and subfolders
        video_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.endswith('.mp4'):
                    # Chemin complet du fichier
                    full_path = os.path.join(root, file)
                    # Chemin relatif par rapport au dossier de base
                    rel_path = os.path.relpath(full_path, folder_path)
                    video_files.append(rel_path)

        print(f"Number of .mp4 files found: {len(video_files)}")
        logging.info(f"Number of .mp4 files found: {len(video_files)}")

        if not video_files:
            print("No new videos to upload")
            logging.info("No new videos to upload")
            return

        # Counter for uploaded videos
        uploaded_count = 0
        skipped_count = 0

        for i, rel_filename in enumerate(video_files, 1):
            print(f"\n[{i}/{len(video_files)}] Processing {rel_filename}")
            file_path = os.path.join(folder_path, rel_filename)
            title = os.path.splitext(os.path.basename(rel_filename))[0]

            # Check if video has already been uploaded - use rel_filename as key
            if is_already_uploaded(rel_filename, upload_history):
                print(f"Video '{title}' has already been uploaded (found in history). Skipping...")
                logging.info(f"Skipping '{title}' - found in upload history")
                skipped_count += 1
                continue

            # Check if a video with the same title exists on YouTube
            if title in existing_videos:
                print(f"Video with title '{title}' already exists on YouTube. Skipping...")
                logging.info(f"Skipping '{title}' - already exists on YouTube")
                # Add to history to avoid checking online next time
                upload_history[rel_filename] = {
                    "title": title,
                    "video_id": existing_videos[title],
                    "upload_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "url": f"https://youtu.be/{existing_videos[title]}"
                }
                skipped_count += 1
                continue

            start_time = time.time()
            result = upload_video(
                youtube,
                file_path,
                title,
                config['description'],
                config['video_category'],
                config['tags'],
                config['privacy_status']
            )

            if result:
                video_id, video_url = result
                elapsed_time = time.time() - start_time

                print(f"Total upload and verification time: {elapsed_time:.2f} seconds")
                print(f"Video '{title}' uploaded to: {video_url}")
                logging.info(f"Video '{title}' uploaded successfully in {elapsed_time:.2f} seconds")

                # Add to history - use rel_filename as key
                upload_history[rel_filename] = {
                    "title": title,
                    "video_id": video_id,
                    "upload_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "url": video_url
                }
                uploaded_count += 1

                # Save history after each successful upload
                save_upload_history(upload_history)

                # Wait a bit between uploads to avoid API overload
                if i < len(video_files):
                    wait_time = 5  # seconds
                    print(f"Waiting {wait_time} seconds before next upload...")
                    time.sleep(wait_time)

        print(f"\n=== Upload Summary ===")
        print(f"Total videos processed: {len(video_files)}")
        print(f"Videos uploaded: {uploaded_count}")
        print(f"Videos skipped (already uploaded): {skipped_count}")
        logging.info(f"Scan completed. Total: {len(video_files)}, Uploaded: {uploaded_count}, Skipped: {skipped_count}")

    except Exception as e:
        print(f"An error occurred during scan: {str(e)}")
        logging.error(f"Error during scan: {str(e)}")


def setup_schedule(config):
    """Schedule the scan_and_upload function to run at regular intervals"""
    interval_minutes = config['check_interval']

    # Schedule the job to run every X minutes
    schedule.every(interval_minutes).minutes.do(scan_and_upload, config)

    print(f"Scheduler set up to scan for videos every {interval_minutes} minutes")
    logging.info(f"Scheduler set up to scan for videos every {interval_minutes} minutes")


def interactive_setup():
    """Set up the configuration interactively"""
    print("=== YouTube Uploader (YTU) Setup ===")

    config = load_config()

    # Get videos folder
    folder_path = input(f"Enter the path to your videos folder [{config['videos_folder'] or 'not set'}]: ").strip()
    if folder_path:
        # Remove quotes if the user included them
        if (folder_path.startswith('"') and folder_path.endswith('"')) or \
                (folder_path.startswith("'") and folder_path.endswith("'")):
            folder_path = folder_path[1:-1]

        if not os.path.exists(folder_path):
            print(f"Warning: The path '{folder_path}' does not exist.")
            create = input("Do you want to create this directory? (y/n): ").strip().lower()
            if create == 'y':
                os.makedirs(folder_path, exist_ok=True)
                print(f"Directory '{folder_path}' created.")
            else:
                print("Please specify a valid path.")
                return None

        if not os.path.isdir(folder_path):
            print(f"Error: '{folder_path}' is not a directory.")
            return None

        config['videos_folder'] = folder_path

    # Get check interval
    interval = input(f"Enter scan interval in minutes [{config['check_interval']}]: ").strip()
    if interval:
        try:
            interval = int(interval)
            if interval < 1:
                print("Interval must be at least 1 minute.")
                interval = max(1, config['check_interval'])
            config['check_interval'] = interval
        except ValueError:
            print(f"Invalid interval. Using default: {config['check_interval']} minutes")

    # Privacy options
    print("\nSelect privacy setting for your videos:")
    print("1. Private (only you can view) [DEFAULT]")
    print("2. Unlisted (anyone with the link can view)")
    print("3. Public (anyone can search and view)")

    privacy_options = {
        '': 'private',
        '1': 'private',
        '2': 'unlisted',
        '3': 'public'
    }

    privacy = input(f"Enter your choice (1-3) [{config['privacy_status']}]: ").strip()
    if privacy in privacy_options:
        config['privacy_status'] = privacy_options[privacy]

    # Save configuration
    save_config(config)
    print("Configuration saved.")

    return config


def main():
    """Main function to run the uploader"""
    parser = argparse.ArgumentParser(description="YouTube Uploader - Automatically upload videos to YouTube")
    parser.add_argument("-s", "--setup", action="store_true", help="Run interactive setup")
    parser.add_argument("-r", "--run-once", action="store_true", help="Run once and exit (don't start scheduler)")
    parser.add_argument("-i", "--interval", type=int, help="Set scan interval in minutes")
    parser.add_argument("-f", "--folder", help="Set videos folder path")
    args = parser.parse_args()

    try:
        # Load configuration
        config = load_config()

        # Interactive setup if requested or if folder path is not set
        if args.setup or not config['videos_folder']:
            config = interactive_setup()
            if not config:
                return

        # Override configuration with command line arguments if provided
        if args.interval:
            config['check_interval'] = max(1, args.interval)
            save_config(config)

        if args.folder:
            folder_path = args.folder
            if (folder_path.startswith('"') and folder_path.endswith('"')) or \
                    (folder_path.startswith("'") and folder_path.endswith("'")):
                folder_path = folder_path[1:-1]

            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                config['videos_folder'] = folder_path
                save_config(config)
            else:
                print(f"Error: Folder '{folder_path}' does not exist or is not a directory")
                return

        print("\n=== YouTube Uploader (YTU) ===")
        print(f"Videos folder: {config['videos_folder']}")
        print(f"Scan interval: {config['check_interval']} minutes")
        print(f"Privacy setting: {config['privacy_status']}")

        # Run once if requested
        if args.run_once:
            print("\nRunning single scan...")
            scan_and_upload(config)
            return

        # Start continuous operation
        print("\nStarting continuous operation")
        print("Press Ctrl+C to exit")

        # Set up scheduler
        setup_schedule(config)

        # Run initial scan
        print("\nRunning initial scan...")
        scan_and_upload(config)

        # Keep the script running
        while True:
            schedule.run_pending()
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nExiting YouTube Uploader")
        logging.info("YouTube Uploader stopped by user")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        logging.error(f"Error in main execution: {str(e)}")


if __name__ == '__main__':
    main()