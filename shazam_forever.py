import sys
import asyncio
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                          QWidget, QLabel, QTextEdit, QMessageBox, QComboBox, QHBoxLayout, QProgressBar,
                          QListWidget, QListWidgetItem, QCheckBox)
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont, QPainterPath
from PyQt6.QtCore import QTimer, Qt, QSize, QThread, pyqtSignal, QUrl
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from custom_shazam_api import Shazam
import sounddevice as sd
import numpy as np
import soundfile as sf
import tempfile
import os
import shutil
from datetime import datetime
import json
import requests
from io import BytesIO
import webbrowser
import re
import time
from pydub.utils import which

def check_microphone_permissions():
    """Check if we have permission to access the microphone"""
    try:
        # Try to get device info - this will fail if we don't have permission
        devices = sd.query_devices()
        print(f"Available audio devices: {devices}")
        return True
    except Exception as e:
        print(f"Error checking microphone permissions: {str(e)}")
        if "Permission denied" in str(e) or "access denied" in str(e).lower():
            return False
        raise e

# Configure pydub to use bundled ffmpeg
def get_bundled_ffmpeg_path():
    if getattr(sys, 'frozen', False):
        # Running in a bundle
        bundle_dir = os.path.dirname(sys.executable)
        ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg_binaries', 'ffmpeg')
        ffprobe_path = os.path.join(bundle_dir, 'ffmpeg_binaries', 'ffprobe')
    else:
        # Running in normal Python environment
        ffmpeg_path = which('ffmpeg')
        ffprobe_path = which('ffprobe')
    
    return ffmpeg_path, ffprobe_path

# Set up ffmpeg paths
ffmpeg_path, ffprobe_path = get_bundled_ffmpeg_path()
os.environ['PATH'] = os.path.dirname(ffmpeg_path) + os.pathsep + os.environ['PATH']

class AudioRecorderThread(QThread):
    finished = pyqtSignal(object)  # Signal to emit when recording is done
    error = pyqtSignal(str)  # Signal to emit when an error occurs
    volume = pyqtSignal(float)  # Signal to emit current audio volume
    
    def __init__(self, device, sample_rate, channels, record_seconds):
        super().__init__()
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.record_seconds = record_seconds
        self.is_recording = False
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        
    def run(self):
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                if not check_microphone_permissions():
                    self.error.emit("Microphone permission denied. Please grant microphone access in System Preferences.")
                    return
                
                print(f"Starting recording with device: {self.device}, sample rate: {self.sample_rate}, channels: {self.channels}")
                self.is_recording = True
                
                # Record audio
                recording = sd.rec(
                    int(self.record_seconds * self.sample_rate),
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype=np.float32,
                    device=self.device
                )
                
                # Simple volume monitoring - just emit a fixed value
                # This avoids the callback stream error
                self.volume.emit(0.5)  # Medium volume indicator
                
                sd.wait()  # Wait until recording is finished
                self.is_recording = False
                
                print(f"Recording completed, shape: {recording.shape}")
                
                # Save the recording to a temporary file
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                    sf.write(temp_file.name, recording, self.sample_rate)
                    print(f"Saved recording to: {temp_file.name}")
                    self.finished.emit(temp_file.name)
                return  # Success, exit the retry loop
                    
            except Exception as e:
                retry_count += 1
                error_msg = str(e)
                print(f"Recording error (attempt {retry_count}/{self.max_retries}): {error_msg}")
                
                # Check if it's a permission error
                if "Permission denied" in error_msg or "access denied" in error_msg.lower():
                    self.error.emit("Microphone permission denied. Please grant microphone access in System Preferences.")
                    return
                
                # Check if it's a network-related error
                if any(err in error_msg.lower() for err in ['network', 'connection', 'timeout', 'hardware not running']):
                    if retry_count < self.max_retries:
                        self.error.emit(f"Network microphone error (attempt {retry_count}/{self.max_retries}): {error_msg}. Retrying...")
                        time.sleep(self.retry_delay)  # Wait before retrying
                        continue
                
                # If we've exhausted retries or it's not a network error
                self.error.emit(f"Error during recording: {error_msg}")
                self.is_recording = False
                return
            
    def stop(self):
        self.is_recording = False

class ShazamApp(QMainWindow):
    def __init__(self):
        super().__init__()
        print("Initializing ShazamApp...")
        self.setWindowTitle("Shazam Music Recognition")
        self.setGeometry(100, 100, 500, 600)  # Increased size to accommodate history
        
        # Setup audio recording parameters
        self.SAMPLE_RATE = 44100
        self.CHANNELS = 1
        self.RECORD_SECONDS = 5  # Increased from 3 to 5 seconds
        self.input_device = None
        self.input_devices = []
        self.recorder_thread = None
        
        # Setup cache directory
        self.cache_dir = os.path.join(os.path.expanduser("~"), ".shazam_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.max_cache_size = 3  # Keep last 3 recordings
        
        # Setup song history
        self.song_history = []
        self.max_history_size = 10
        
        # Setup daily history file
        self.daily_history_dir = os.path.join(os.path.expanduser("~"), ".shazam_history")
        os.makedirs(self.daily_history_dir, exist_ok=True)
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.daily_history_file = os.path.join(self.daily_history_dir, f"{self.current_date}.md")
        
        # Setup logging
        self.logging_enabled = True  # Enable logging by default for debugging
        
        # Setup UI first
        self.setup_ui()
        
        # Load today's history if it exists
        self.load_daily_history()
        
        # Check microphone permissions at startup
        if not check_microphone_permissions():
            QMessageBox.warning(self, "Microphone Access Required",
                              "Shazam Forever needs access to your microphone to identify songs.\n\n"
                              "Please grant microphone access in System Preferences > Security & Privacy > Privacy > Microphone")
        
        # Track last identified song to prevent duplicates
        self.last_song = None
        self.last_song_time = None
        
        # Setup network manager for downloading images
        self.network_manager = QNetworkAccessManager()
        
        self.is_listening = False
        
        # Initialize audio devices after UI setup
        self.refresh_devices()
        
        print("ShazamApp initialized successfully")
        
    def setup_ui(self):
        print("Setting up UI...")
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create status label
        self.status_label = QLabel("Status: Not Listening")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.status_label)
        
        # Create volume indicator
        volume_layout = QHBoxLayout()
        volume_label = QLabel("Volume:")
        self.volume_bar = QProgressBar()
        self.volume_bar.setRange(0, 100)
        self.volume_bar.setValue(0)
        volume_layout.addWidget(volume_label)
        volume_layout.addWidget(self.volume_bar)
        layout.addLayout(volume_layout)
        
        # Create device selection area
        device_layout = QHBoxLayout()
        
        # Add refresh button
        refresh_button = QPushButton("🔄")
        refresh_button.setFixedSize(30, 30)
        refresh_button.clicked.connect(self.refresh_devices)
        refresh_button.setToolTip("Refresh device list")
        device_layout.addWidget(refresh_button)
        
        # Create device dropdown
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.device_changed)
        device_layout.addWidget(self.device_combo)
        
        layout.addLayout(device_layout)
        
        # Create song info area
        self.song_info_label = QLabel("No song identified yet")
        self.song_info_label.setStyleSheet("font-size: 12px;")
        self.song_info_label.setWordWrap(True)
        self.song_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.song_info_label)
        
        # Create album art label
        self.album_art_label = QLabel()
        self.album_art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_art_label.setMinimumHeight(150)
        self.album_art_label.setMaximumHeight(150)
        layout.addWidget(self.album_art_label)
        
        # Create history section
        history_label = QLabel("Recently Identified Songs:")
        history_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        layout.addWidget(history_label)
        
        # Create history list
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(150)
        self.history_list.itemClicked.connect(self.show_history_item)
        layout.addWidget(self.history_list)
        
        # Create view history button
        view_history_button = QPushButton("View Today's History")
        view_history_button.clicked.connect(self.view_daily_history)
        layout.addWidget(view_history_button)
        
        # Create log toggle
        log_toggle_layout = QHBoxLayout()
        self.log_toggle = QCheckBox("Enable Logs")
        self.log_toggle.setChecked(False)  # Logs disabled by default
        self.log_toggle.stateChanged.connect(self.toggle_logging)
        log_toggle_layout.addWidget(self.log_toggle)
        layout.addLayout(log_toggle_layout)
        
        # Create log area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(100)
        self.log_area.setVisible(False)  # Hidden by default
        layout.addWidget(self.log_area)
        
        # Create toggle button
        self.toggle_button = QPushButton("Start Listening")
        self.toggle_button.setStyleSheet("font-size: 14px; padding: 10px;")
        self.toggle_button.clicked.connect(self.toggle_listening)
        layout.addWidget(self.toggle_button)
        
        # Create quit button
        quit_button = QPushButton("Quit")
        quit_button.setStyleSheet("font-size: 14px; padding: 10px;")
        quit_button.clicked.connect(QApplication.quit)
        layout.addWidget(quit_button)
        
        print("UI setup complete. Window should be visible.")
        
    def refresh_devices(self):
        try:
            if not check_microphone_permissions():
                QMessageBox.warning(self, "Microphone Access Required",
                                  "Shazam Forever needs access to your microphone to identify songs.\n\n"
                                  "Please grant microphone access in System Preferences > Security & Privacy > Privacy > Microphone")
                return
            
            # Get all devices
            devices = sd.query_devices()
            print(f"Found audio devices: {devices}")
            
            # Store current selection if any
            current_device_name = self.device_combo.currentText() if self.device_combo.count() > 0 else None
            
            # Clear the combo box
            self.device_combo.clear()
            self.input_devices = []
            
            # Add input devices to the combo box
            for device in devices:
                if device['max_input_channels'] > 0:
                    self.input_devices.append(device)
                    device_name = f"{device['name']} ({device['index']})"
                    self.device_combo.addItem(device_name)
                    print(f"Added input device: {device_name}")
            
            if self.input_devices:
                # Try to restore previous selection
                if current_device_name:
                    index = self.device_combo.findText(current_device_name)
                    if index >= 0:
                        self.device_combo.setCurrentIndex(index)
                    else:
                        self.device_combo.setCurrentIndex(0)
                else:
                    self.device_combo.setCurrentIndex(0)
                
                self.device_changed()  # Update the selected device
                self.log_message("Audio devices refreshed successfully")
            else:
                self.log_message("No input devices found!")
                self.input_device = None
                QMessageBox.warning(self, "No Devices", 
                                  "No audio input devices were found. Please connect a microphone.")
                
        except Exception as e:
            error_msg = str(e)
            print(f"Error refreshing devices: {error_msg}")
            if "Permission denied" in error_msg or "access denied" in error_msg.lower():
                QMessageBox.warning(self, "Microphone Access Required",
                                  "Shazam Forever needs access to your microphone to identify songs.\n\n"
                                  "Please grant microphone access in System Preferences > Security & Privacy > Privacy > Microphone")
            else:
                self.log_message(f"Error refreshing devices: {error_msg}")
                QMessageBox.critical(self, "Device Error", 
                                   f"Failed to refresh audio devices: {error_msg}")
    
    def device_changed(self):
        if self.is_listening:
            self.stop_listening()
        
        if self.device_combo.count() > 0 and self.input_devices:
            selected_index = self.device_combo.currentIndex()
            if 0 <= selected_index < len(self.input_devices):
                device = self.input_devices[selected_index]
                self.input_device = device['index']
                self.log_message(f"Selected audio device: {device['name']}")
                self.toggle_button.setEnabled(True)
            else:
                self.input_device = None
                self.toggle_button.setEnabled(False)
        else:
            self.input_device = None
            self.toggle_button.setEnabled(False)
        
    def toggle_logging(self, state):
        """Toggle logging on/off"""
        self.logging_enabled = state == Qt.CheckState.Checked.value
        self.log_area.setVisible(self.logging_enabled)
        if self.logging_enabled:
            self.log_message("Logging enabled")
        else:
            self.log_message("Logging disabled")
            
    def log_message(self, message):
        """Log a message if logging is enabled"""
        if self.logging_enabled:
            self.log_area.append(message)
        print(message)  # Always print to console
        
    def toggle_listening(self):
        if not self.is_listening:
            if self.input_device is None:
                QMessageBox.warning(self, "Audio Error", 
                                  "Cannot start listening: No audio input device available")
                return
            self.start_listening()
        else:
            self.stop_listening()
            
    def start_listening(self):
        self.log_message("Starting to listen...")
        self.is_listening = True
        self.toggle_button.setText("Stop Listening")
        self.status_label.setText("Status: Listening")
        
        # Start recording immediately
        self.record_and_identify()
        
        # Then set up the timer for subsequent recordings
        self.timer = QTimer()
        self.timer.timeout.connect(self.record_and_identify)
        self.timer.start(30000)  # Check every 30 seconds
        self.log_message("Now listening for music...")
        
    def stop_listening(self):
        self.log_message("Stopping listening...")
        self.is_listening = False
        self.toggle_button.setText("Start Listening")
        self.status_label.setText("Status: Not Listening")
        if hasattr(self, 'timer'):
            self.timer.stop()
        if self.recorder_thread and self.recorder_thread.isRunning():
            self.recorder_thread.stop()  # Use the stop method instead of terminate
            self.recorder_thread.wait()
        self.volume_bar.setValue(0)
        self.log_message("Stopped listening for music.")
            
    def check_microphone_availability(self):
        """Check if the selected microphone is still available"""
        try:
            # Get all devices
            devices = sd.query_devices()
            
            # Check if our device is still in the list
            device_found = False
            for device in devices:
                if device['index'] == self.input_device:
                    device_found = True
                    break
            
            if not device_found:
                self.log_message("Selected microphone is no longer available")
                self.status_label.setText("Status: Microphone Disconnected")
                self.stop_listening()
                QMessageBox.warning(self, "Microphone Error", 
                                  "The selected microphone is no longer available. Please select a different device.")
                self.refresh_devices()
                return False
                
            return True
        except Exception as e:
            self.log_message(f"Error checking microphone: {str(e)}")
            return False
            
    def record_and_identify(self):
        if not self.is_listening:
            return
            
        # Check if microphone is still available
        if not self.check_microphone_availability():
            return
            
        self.log_message("Recording audio sample...")
        print(f"Starting recording with device: {self.input_device}")
        
        # Create and start the recorder thread
        self.recorder_thread = AudioRecorderThread(
            self.input_device,
            self.SAMPLE_RATE,
            self.CHANNELS,
            self.RECORD_SECONDS
        )
        self.recorder_thread.finished.connect(self.process_recording)
        self.recorder_thread.error.connect(self.handle_recording_error)
        self.recorder_thread.volume.connect(self.update_volume)
        self.recorder_thread.start()
        
    def process_recording(self, temp_file_path):
        try:
            # Read the file as bytes for Shazam
            with open(temp_file_path, 'rb') as audio_file:
                audio_bytes = audio_file.read()
            
            # Cache the recording
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            cache_file = os.path.join(self.cache_dir, f"recording_{timestamp}.wav")
            shutil.copy2(temp_file_path, cache_file)
            
            # Clean up old cache files
            cache_files = sorted([f for f in os.listdir(self.cache_dir) if f.startswith("recording_")])
            while len(cache_files) > self.max_cache_size:
                os.remove(os.path.join(self.cache_dir, cache_files.pop(0)))
            
            # Analyze the audio
            self.log_message("Analyzing audio with Shazam API...")
            self.status_label.setText("Status: Analyzing with Shazam...")
            
            # Create Shazam instance and analyze
            shazam = Shazam(audio_bytes)
            recognize_generator = shazam.recognizeSong()
            
            try:
                result = next(recognize_generator)
                
                # Log the raw Shazam API response if logging is enabled
                if self.logging_enabled and result:
                    self.log_message("Shazam API Response:")
                    self.log_message(json.dumps(result, indent=2))
                
                # Check if we have a valid result with track information
                if result and isinstance(result, tuple) and len(result) > 1:
                    response_data = result[1]
                    if 'track' in response_data:
                        track = response_data['track']
                        title = track.get('title', 'Unknown Title')
                        artist = track.get('subtitle', 'Unknown Artist')
                        
                        # Get additional metadata
                        # Try to get genre in English, fall back to primary if not available
                        genre = track.get('genres', {}).get('primary', 'Unknown Genre')
                        
                        # Check if we have a localized version of the genre
                        if 'genres' in track and 'localized' in track['genres']:
                            # Try to get English genre first
                            if 'en' in track['genres']['localized']:
                                genre = track['genres']['localized']['en']
                            # Fall back to primary if no English version
                            elif track['genres'].get('primary'):
                                genre = track['genres']['primary']
                        
                        album = track.get('sections', [{}])[0].get('metapages', [{}])[1].get('caption', 'Unknown Album')
                        
                        # Get image URLs
                        cover_art_url = track.get('images', {}).get('coverart', '')
                        background_url = track.get('images', {}).get('background', '')
                        
                        # Get Spotify URI if available
                        spotify_uri = None
                        if 'hub' in track and 'providers' in track['hub']:
                            for provider in track['hub']['providers']:
                                if provider.get('type') == 'SPOTIFY':
                                    for action in provider.get('actions', []):
                                        if action.get('name') == 'hub:spotify:searchdeeplink':
                                            spotify_uri = action.get('uri', '')
                                            break
                        
                        # Create a nice blurb
                        blurb = f"<b>{title}</b> by <b>{artist}</b><br>"
                        blurb += f"Genre: {genre}<br>"
                        blurb += f"Album: {album}"
                        
                        # Update UI with song info
                        self.song_info_label.setText(blurb)
                        self.status_label.setText(f"Found: {title} by {artist}")
                        
                        # Download and display album art
                        if cover_art_url:
                            self.download_and_display_image(cover_art_url)
                        else:
                            # Set a default image or clear the label
                            self.album_art_label.setText("No album art available")
                        
                        # Check if this is a new song or a repeat
                        current_time = datetime.now()
                        is_new_song = True
                        
                        # Always log the song with timestamp
                        self.log_message(f"Found song: {title} by {artist} at {current_time.strftime('%H:%M:%S')}")
                        
                        # Check if this song is already in the history
                        if self.last_song and self.last_song.get('title') == title and self.last_song.get('artist') == artist:
                            # Same song as before, don't add to history
                            is_new_song = False
                        else:
                            # New song, update last song info
                            self.last_song = {'title': title, 'artist': artist}
                            self.last_song_time = current_time
                        
                        # Add to history if it's a new song
                        if is_new_song:
                            self.add_to_history(title, artist, genre, album, cover_art_url, timestamp, spotify_uri)
                        
                        # Save metadata to cache
                        metadata_file = os.path.join(self.cache_dir, f"recording_{timestamp}_metadata.json")
                        with open(metadata_file, 'w') as f:
                            json.dump({
                                'title': title,
                                'artist': artist,
                                'genre': genre,
                                'album': album,
                                'cover_art_url': cover_art_url,
                                'background_url': background_url,
                                'spotify_uri': spotify_uri,
                                'timestamp': timestamp
                            }, f)
                    else:
                        # No song identified, but don't log it
                        self.status_label.setText("Status: No song identified")
                        self.song_info_label.setText("No song identified in this sample")
                        self.album_art_label.setText("No album art available")
                else:
                    # No song identified, but don't log it
                    self.status_label.setText("Status: No song identified")
                    self.song_info_label.setText("No song identified in this sample")
                    self.album_art_label.setText("No album art available")
            except StopIteration:
                # No song identified, but don't log it
                self.status_label.setText("Status: No song identified")
                self.song_info_label.setText("No song identified in this sample")
                self.album_art_label.setText("No album art available")
                
        except Exception as e:
            self.log_message(f"Error during analysis: {str(e)}")
            self.status_label.setText("Status: Analysis Error")
        finally:
            # Clean up the temporary file
            try:
                os.unlink(temp_file_path)
            except:
                pass
                
    def download_and_display_image(self, url):
        """Download and display an image from a URL using requests library"""
        if not url:
            self.album_art_label.setText("No album art available")
            return
            
        try:
            # Use requests library for more reliable downloads
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                # Load the image data
                image_data = BytesIO(response.content)
                pixmap = QPixmap()
                pixmap.loadFromData(image_data.getvalue())
                
                # Scale the image to fit the label while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    self.album_art_label.width(), 
                    self.album_art_label.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                # Create a rounded version of the pixmap
                rounded_pixmap = self.create_rounded_pixmap(scaled_pixmap, 10)  # 10px radius
                
                self.album_art_label.setPixmap(rounded_pixmap)
            else:
                self.log_message(f"Error downloading image: HTTP {response.status_code}")
                self.album_art_label.setText("Failed to load album art")
        except Exception as e:
            self.log_message(f"Error downloading image: {str(e)}")
            self.album_art_label.setText("Failed to load album art")
            
    def create_rounded_pixmap(self, pixmap, radius):
        """Create a pixmap with rounded corners"""
        # Create a transparent pixmap with the same size
        rounded_pixmap = QPixmap(pixmap.size())
        rounded_pixmap.fill(Qt.GlobalColor.transparent)
        
        # Create a painter to draw on the rounded pixmap
        painter = QPainter(rounded_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Create a path for the rounded rectangle
        path = QPainterPath()
        path.addRoundedRect(0, 0, pixmap.width(), pixmap.height(), radius, radius)
        
        # Set the clip path to the rounded rectangle
        painter.setClipPath(path)
        
        # Draw the original pixmap
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        
        return rounded_pixmap

    def handle_recording_error(self, error_message):
        """Handle recording errors, with special handling for network-related issues"""
        self.log_message(f"Error during recording: {error_message}")
        
        # Check if it's a network-related error
        if any(err in error_message.lower() for err in ['network', 'connection', 'timeout', 'hardware not running']):
            # For network errors, just update the status and continue
            self.status_label.setText("Status: Network Microphone Error - Retrying...")
            # Don't stop listening for network errors, let the retry mechanism handle it
            return
            
        # For other errors, show a warning and stop listening
        self.status_label.setText("Status: Recording Error")
        self.stop_listening()
        QMessageBox.warning(self, "Recording Error", 
                          f"An error occurred while recording: {error_message}")

    def update_volume(self, volume):
        # Convert volume to a 0-100 scale for the progress bar
        # Handle NaN values
        if np.isnan(volume):
            volume_percent = 0
        else:
            volume_percent = min(100, int(volume * 1000))
        self.volume_bar.setValue(volume_percent)

    def add_to_history(self, title, artist, genre, album, cover_art_url, timestamp, spotify_uri=None):
        """Add a song to the history list"""
        # Create a song entry
        song_entry = {
            'title': title,
            'artist': artist,
            'genre': genre,
            'album': album,
            'cover_art_url': cover_art_url,
            'timestamp': timestamp,
            'spotify_uri': spotify_uri
        }
        
        # Add to history list (newest first)
        self.song_history.insert(0, song_entry)
        
        # Limit history size
        if len(self.song_history) > self.max_history_size:
            self.song_history.pop()
        
        # Update the history list widget
        self.update_history_list()
        
        # Save to daily history file
        self.save_daily_history()
        
    def update_history_list(self):
        """Update the history list widget with current history"""
        self.history_list.clear()
        
        for song in self.song_history:
            # Format the timestamp
            try:
                dt = datetime.strptime(song['timestamp'], "%Y%m%d_%H%M%S")
                # Include date in the timestamp display
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                time_str = "Unknown time"
                
            # Create the display text with timestamp
            display_text = f"{song['title']} by {song['artist']} ({time_str})"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, song)  # Store the full song data
            self.history_list.addItem(item)
            
    def show_history_item(self, item):
        """Display the selected history item and open Spotify if available"""
        song = item.data(Qt.ItemDataRole.UserRole)
        
        # Update the song info
        blurb = f"<b>{song['title']}</b> by <b>{song['artist']}</b><br>"
        blurb += f"Genre: {song['genre']}<br>"
        blurb += f"Album: {song['album']}"
        
        self.song_info_label.setText(blurb)
        self.status_label.setText(f"History: {song['title']} by {song['artist']}")
        
        # Download and display album art if available
        if song['cover_art_url']:
            self.download_and_display_image(song['cover_art_url'])
        else:
            self.album_art_label.setText("No album art available")
            
        # Open Spotify if URI is available
        if song.get('spotify_uri'):
            self.open_spotify(song['spotify_uri'])
            
    def open_spotify(self, uri):
        """Open the Spotify URI in the native Spotify application"""
        try:
            # Use the URI directly to open the native Spotify application
            if uri:
                # The URI is already in the format spotify:track:123456
                # This will open the native Spotify application
                webbrowser.open(uri)
                self.log_message(f"Opening Spotify: {uri}")
            else:
                self.log_message("No Spotify URI available")
        except Exception as e:
            self.log_message(f"Error opening Spotify: {str(e)}")
            QMessageBox.warning(self, "Spotify Error", 
                              f"Failed to open Spotify: {str(e)}")

    def load_daily_history(self):
        """Load today's song history from the markdown file"""
        # Update current date and file path
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.daily_history_file = os.path.join(self.daily_history_dir, f"{self.current_date}.md")
        
        if os.path.exists(self.daily_history_file):
            try:
                with open(self.daily_history_file, 'r') as f:
                    content = f.read()
                
                # Parse the markdown content
                songs = []
                for line in content.split('\n'):
                    if line.startswith('- '):
                        # Extract song info from the line
                        # Format: - [Song Title by Artist](uri) at [YYYY-MM-DD HH:MM] or [Unknown time]
                        match = re.match(r'- \[(.*?) by (.*?)\]\((.*?)\) at \[(.*?)\]', line)
                        if match:
                            title, artist, uri, time_str = match.groups()
                            
                            # Handle timestamp
                            if time_str == "Unknown time":
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            else:
                                try:
                                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                                    timestamp = dt.strftime("%Y%m%d_%H%M%S")
                                except ValueError:
                                    # If parsing fails, use current time
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            
                            # Create a song entry
                            song_entry = {
                                'title': title,
                                'artist': artist,
                                'genre': 'Unknown Genre',  # We don't store genre in the markdown
                                'album': 'Unknown Album',  # We don't store album in the markdown
                                'cover_art_url': '',  # We don't store cover art URL in the markdown
                                'timestamp': timestamp,
                                'spotify_uri': uri if 'spotify:' in uri else None  # Only store actual Spotify URIs
                            }
                            songs.append(song_entry)
                
                # Add to history
                self.song_history = songs
                self.update_history_list()  # Update the UI immediately
                self.log_message(f"Loaded {len(songs)} songs from today's history")
            except Exception as e:
                self.log_message(f"Error loading daily history: {str(e)}")
                self.song_history = []
        else:
            self.log_message("No history file for today")
            self.song_history = []
            self.update_history_list()  # Update the UI even if no history
            
    def save_daily_history(self):
        """Save today's song history to the markdown file"""
        try:
            # Always use current date when saving
            current_date = datetime.now().strftime("%Y-%m-%d")
            if current_date != self.current_date:
                # Date has changed, update the file path and reload history
                self.current_date = current_date
                self.daily_history_file = os.path.join(self.daily_history_dir, f"{self.current_date}.md")
                self.log_message(f"New day detected, creating new history file: {self.daily_history_file}")
                # Load any existing history for the new day
                self.load_daily_history()
            
            # Create the markdown content
            content = f"# Scrobbles for {self.current_date}\n\n"
            
            # Add each song to the markdown
            for song in self.song_history:
                # Format the timestamp
                try:
                    dt = datetime.strptime(song['timestamp'], "%Y%m%d_%H%M%S")
                    # Include date in the timestamp display
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    time_str = "Unknown time"
                
                # Get the Spotify URI or use a default search link
                uri = song.get('spotify_uri', '')
                if not uri:
                    # Create a Spotify search URL if no direct URI is available
                    search_query = f"{song['title']} {song['artist']}".replace(' ', '+')
                    uri = f"https://open.spotify.com/search/{search_query}"
                
                # Add the song to the markdown with a clickable link
                content += f"- [{song['title']} by {song['artist']}]({uri}) at [{time_str}]\n"
            
            # Write to the file
            with open(self.daily_history_file, 'w') as f:
                f.write(content)
            
            self.log_message(f"Saved {len(self.song_history)} songs to today's history")
        except Exception as e:
            self.log_message(f"Error saving daily history: {str(e)}")
            QMessageBox.warning(self, "History Error", 
                              f"Failed to save history: {str(e)}")

    def view_daily_history(self):
        """Open today's history file in the default text editor"""
        try:
            if os.path.exists(self.daily_history_file):
                # Open the file with the default application
                if sys.platform == 'darwin':  # macOS
                    os.system(f"open {self.daily_history_file}")
                elif sys.platform == 'win32':  # Windows
                    os.startfile(self.daily_history_file)
                else:  # Linux and others
                    os.system(f"xdg-open {self.daily_history_file}")
                self.log_message(f"Opened today's history file: {self.daily_history_file}")
            else:
                QMessageBox.information(self, "No History", 
                                      "No history file exists for today yet.")
        except Exception as e:
            self.log_message(f"Error opening history file: {str(e)}")
            QMessageBox.warning(self, "Error", 
                              f"Failed to open history file: {str(e)}")

def main():
    app = QApplication(sys.argv)
    window = ShazamApp()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 