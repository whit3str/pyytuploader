# YouTube Uploader (YTU)

A simple and efficient tool for automatically uploading videos to YouTube from a local folder.

## Features

- Automatic upload of multiple video files (.mp4) to YouTube
- Uses the filename as the video title
- Real-time upload progress tracking
- Post-upload processing status monitoring
- Secure OAuth authentication with Google
- Configurable via environment variables for Docker deployment

## Prerequisites

- Python 3.7 or higher
- A Google account with YouTube access
- A Google Cloud Platform project with YouTube API enabled

## Installation

1. Clone or download this repository
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. Create a project in the [Google Cloud Console](https://console.cloud.google.com/)
4. Enable the YouTube Data v3 API
5. Create OAuth credentials (Desktop type)
6. Download the credentials JSON file and rename it to `client_secrets.json`
7. Place this file in the `data` directory

## Configuration

### Environment Variables

The following environment variables can be used to configure the application:

| Variable | Description | Default |
|----------|-------------|---------|
| `YTU_VIDEOS_FOLDER` | Path to folder containing videos to upload | *empty* |
| `YTU_PRIVACY_STATUS` | Privacy setting for uploaded videos (private, unlisted, public) | private |
| `YTU_CHECK_INTERVAL` | Time in minutes between folder scans | 60 |
| `YTU_CLIENT_SECRETS` | Path to the client secrets JSON file | data/client_secrets.json |
| `YTU_VIDEO_CATEGORY` | YouTube category ID | 22 (People & Blogs) |
| `YTU_DESCRIPTION` | Default video description | "Uploaded with YTU" |
| `YTU_TAGS` | Comma-separated list of tags to apply to videos | YTU Upload |

### Manual Configuration

You can also configure the application interactively:

```bash
python youtube_uploader.py --setup
```

## Usage

Run the main script:

```bash
python youtube_uploader.py
```

On first execution, a browser will open asking you to authorize the application to access your YouTube account. Once authorized, a token will be saved locally for future use.

The script will find all .mp4 files in the specified folder and upload them one by one to YouTube, using the filename as the video title.

### Command Line Options

```bash
python youtube_uploader.py --help
```

## Docker Usage

1. Build the Docker image:

```bash
docker build -t youtube-uploader .
```

2. Run using Docker Compose:

```bash
# Edit docker-compose.yaml to set your video path
docker-compose up -d
```

### Docker Configuration

When using Docker, configure the application using environment variables in the `docker-compose.yaml` file.

## Upload Monitoring

During execution, you will see detailed information about:
- Upload progress (percentage)
- YouTube processing status after upload
- URL of the uploaded video

## Troubleshooting

- If you encounter authentication errors, delete the `token.json` file and restart the script
- For "unverified" applications, add your account as a test user in the Google Cloud console
- YouTube can take considerable time to process videos after upload, especially for large files

## Notes

- This script is designed for personal use. For wider distribution, you'll need to complete Google's verification process.
- By default, videos are uploaded as private. Use the `YTU_PRIVACY_STATUS` environment variable to change this.

## License

This project is free to use.

## Next

- Friendlier privacy selector 
- Not uploading duplicates
- Live script with CRON schedule