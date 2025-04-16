# Shazam Forever

### This is vibe-coded. Not a single line in this repo was written by a human being. A human is writing some footnotes to this readme though lol

A desktop application that continuously listens to and identifies music playing in your environment using the Shazam API.

## Features

- Continuous music recognition
- Beautiful UI with album art display [^lol]
- Song history tracking
- Daily song history in markdown format
- Caching system for recent recordings
- Network microphone support with automatic reconnection
- Spotify integration for identified songs

## Requirements

- Python 3.8 or higher
- PyQt6
- PortAudio (for sounddevice) [^I'm pretty sure ffmpeg is necessary because i had to brew install that as well at some point but i don't think the ai caught that move]

## Installation

1. Install PortAudio (required for sounddevice): [^actually I'm not sure this is necessary...]

```bash
brew install portaudio
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

3. Install the custom ShazamAPI package (with English locale): [^this is because the ShazamAPI i guess is hardcoded as russian in the original repo]

```bash
cd custom_shazam_api
pip install -e . [^i dont think i did this...]
cd ..
```

## Usage

1. Run the application:

```bash
python shazam_forever.py
```

2. Select your audio input device from the dropdown
3. Click "Start Listening" to begin music recognition
4. The application will check for music every 30 seconds
5. When a song is identified, it will display the song details and album art
6. Click "Stop Listening" to pause recognition
7. Click "View Today's History" to see your identified songs in markdown format
8. Click "Quit" to exit the application

## Song History

- The application keeps track of the last 10 identified songs in the UI
- A daily markdown file is created at `~/.shazam_history/YYYY-MM-DD.md`
- Each song entry includes a clickable link to Spotify
- History files are organized by date for easy browsing

## Notes

- The application records 5 seconds of audio for recognition
- Make sure your microphone has permission to access audio input
- The application needs to be running to identify songs
- Internet connection is required for song recognition
- Network microphones are supported with automatic reconnection [^this is a lie, i think]
