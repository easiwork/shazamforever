# Shazam Menu Bar

A macOS menu bar application that continuously listens to and identifies music playing in your environment using the Shazam API.

## Features

- Runs in the menu bar
- Continuous music recognition
- Simple start/stop controls
- Displays song information in notifications

## Requirements

- Python 3.8 or higher
- macOS (tested on macOS 24.3.0)
- PyQt6
- PortAudio (for PyAudio)

## Installation

1. Install PortAudio (required for PyAudio):

```bash
brew install portaudio
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:

```bash
python shazam_menu_bar.py
```

2. Look for the microphone icon in your menu bar
3. Click the icon and select "Start Listening" to begin music recognition
4. The application will check for music every 5 seconds
5. When a song is identified, you'll receive a notification with the song details
6. Select "Stop Listening" to pause recognition
7. Select "Quit" to exit the application

## Notes

- The application records 3 seconds of audio every 5 seconds for recognition
- Make sure your microphone has permission to access audio input
- The application needs to be running to identify songs
- Internet connection is required for song recognition
