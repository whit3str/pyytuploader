# YouTube Uploader (YTU)

A simple and efficient tool for automatically uploading videos to YouTube from a local folder.

## Features

- Automatic upload of multiple video files (.mp4) to YouTube
- Uses the filename as the video title
- Real-time upload progress tracking
- Post-upload processing status monitoring
- Secure OAuth authentication with Google

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
7. Place this file in the project directory

## Configuration

1. Modify the `folder_path` variable in the `main()` function of the `main.py` file to point to your videos folder
2. Optionally customize the description, category, and tags in the `main()` function

## Usage

Run the main script:

```bash
python main.py
```

On first execution, a browser will open asking you to authorize the application to access your YouTube account. Once authorized, a token will be saved locally for future use.

The script will find all .mp4 files in the specified folder and upload them one by one to YouTube, using the filename as the video title.

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
- By default, videos are uploaded as public. Modify `'privacyStatus': 'public'` in the `upload_video()` function to change this behavior.

## License

This project is free to use.

## Next

- Friendlier privacy selector 
- Docker Image
- Not uploading duplicates
- Live script with CRON schedule