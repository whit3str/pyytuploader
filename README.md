<p align="center">
  <img src="https://github.com/whit3str/pyytuploader/blob/main/resources/icon.png?raw=true" alt="Logo" width="100"/>
  <h1 align="center">PyYTUploader</h1>
</p>

An automated tool to upload videos to YouTube from a local folder. It's particularly useful for content creators who want to automate their publishing process.

## Features

* Automatic upload of videos to YouTube
* Periodic monitoring of a folder for new videos
* Support for Ganymede metadata (for Twitch VODs)
* Automatic playlist creation by channel
* Discord notifications for successful uploads with video thumbnails
* Resume interrupted uploads
* Thumbnail management

## Installation

### Prerequisites

* Python 3.7 or higher
* A Google account with YouTube API access

### Installation with Docker (recommended)

```bash
docker pull ghcr.io/whit3str/pyytuploader:latest
```

### Docker Configuration

Create a docker-compose.yml file:

```yaml
version: '3'

services:
  pyytuploader:
    image: ghcr.io/whit3str/pyytuploader:latest
    container_name: youtube-uploader
    volumes:
      - ./data:/app/data  # For configuration, tokens, and history
      - /path/to/videos:/app/videos  # Mount your videos directory here
    restart: unless-stopped
    environment:
      - TZ=Europe/Paris  # Set your timezone here
      - YTU_VIDEOS_FOLDER=/app/videos
      - YTU_PRIVACY_STATUS=private  # Options: private, unlisted, public
      - YTU_CHECK_INTERVAL=60  # Minutes between folder scans
      # Discord webhook for notifications
      - YTU_DISCORD_WEBHOOK=
      # Optional environment variables:
      # - YTU_VIDEO_CATEGORY=20  # Gaming category
      - YTU_DESCRIPTION=Uploaded with YTU Automated Uploader
      - YTU_GANYMEDE_MODE=true
      # - YTU_TAGS=auto-upload,ytu,video
      - YTU_AUTO_PLAYLIST=true
```

## Configuration

### Obtaining OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the YouTube Data v3 API
4. Create OAuth 2.0 credentials
5. Download the JSON file and place it in the /app/data/client_secrets.json folder

### Environment Variables

| Variable | Description | Default Value |
|----------|-------------|---------------|
| YTU_VIDEOS_FOLDER | Folder containing videos to upload | '' |
| YTU_PRIVACY_STATUS | Privacy status of videos | 'private' |
| YTU_CHECK_INTERVAL | Check interval (minutes) | 60 |
| YTU_CLIENT_SECRETS | Path to client_secrets.json | 'data/client_secrets.json' |
| YTU_VIDEO_CATEGORY | YouTube category ID | '22' |
| YTU_DESCRIPTION | Default video description | 'Uploaded with YTU' |
| YTU_TAGS | Tags separated by commas | 'YTU Upload' |
| YTU_GANYMEDE_MODE | Enable Ganymede mode for VODs | 'false' |
| YTU_AUTO_PLAYLIST | Automatically add to playlists | 'false' |
| YTU_DISCORD_WEBHOOK | Discord webhook URL for notifications | '' |

### Categories 

| ID | Category |
|----|----------|
| 1 | Film & Animation |
| 2 | Autos & Vehicles |
| 10 | Music |
| 15 | Pets & Animals |
| 17 | Sports |
| 20 | Gaming |
| 22 | People & Blogs |
| 23 | Comedy |
| 24 | Entertainment |
| 25 | News & Politics |
| 26 | Howto & Style |
| 27 | Education |
| 28 | Science & Technology |
| 29 | Nonprofits & Activism |

## Usage

### First Run

On first run, you'll need to authorize the application to access your YouTube account:

```bash
docker-compose up
```

Follow the instructions for OAuth authentication.

### Ganymede Mode

Ganymede mode is designed for Twitch VODs downloaded with [Ganymede](https://github.com/Zibbp/ganymede). It automatically extracts metadata from associated JSON files.

### Discord Notifications

To receive notifications on Discord when a video is successfully uploaded:

1. Create a webhook in your Discord server
2. Add the webhook URL to the YTU_DISCORD_WEBHOOK environment variable

The notifications include:
- Video title
- Channel name
- Privacy status
- Upload timestamp
- Video thumbnail (high quality)
- Link to the uploaded video

## Troubleshooting

### Discord notifications not working

* Check that the webhook URL is correct
* Make sure the webhook has the necessary permissions
* Check Docker logs for errors

### Authentication issues

If you encounter authentication issues:

```bash
docker-compose down
docker volume rm youtube-uploader_data
docker-compose up
```

## License

This project is under the MIT License.

## Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request.