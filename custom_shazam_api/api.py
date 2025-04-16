from io import BytesIO
import requests
import uuid
import time
import json
import soundfile as sf
import numpy as np

from .algorithm import SignatureGenerator
from .signature_format import DecodedMessage

LANG = 'en-US'
TIME_ZONE = 'America/New_York'
API_URL = 'https://amp.shazam.com/discovery/v5/en/US/iphone/-/tag/%s/%s?sync=true&webv3=true&sampling=true&connected=&shazamapiversion=v3&sharehub=true&hubv5minorversion=v5.1&hidelb=true&video=v3'
HEADERS = {
    "X-Shazam-Platform": "IPHONE",
    "X-Shazam-AppVersion": "14.1.0",
    "Accept": "*/*",
    "Accept-Language": LANG,
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "Shazam/3685 CFNetwork/1197 Darwin/20.0.0"
}


class Shazam:
    def __init__(self, songData: bytes):
        self.songData = songData
        self.MAX_TIME_SECONDS = 8

    def recognizeSong(self) -> dict:
        self.audio = self.normalizateAudioData(self.songData)
        signatureGenerator = self.createSignatureGenerator(self.audio)
        while True:
            signature = signatureGenerator.get_next_signature()
            if not signature:
                break
            
            results = self.sendRecognizeRequest(signature)
            currentOffset = signatureGenerator.samples_processed / 16000
            
            yield currentOffset, results
    
    def sendRecognizeRequest(self, sig: DecodedMessage) -> dict:
        data = {
            'timezone': TIME_ZONE,
            'signature': {
                'uri': sig.encode_to_uri(),
                'samplems':int(sig.number_samples / sig.sample_rate_hz * 1000)
                },
            'timestamp': int(time.time() * 1000),
            'context': {},
            'geolocation': {}
                }
        r = requests.post(
            API_URL % (str(uuid.uuid4()).upper(), str(uuid.uuid4()).upper()), 
            headers=HEADERS,
            json=data
        )
        return r.json()
    
    def normalizateAudioData(self, songData: bytes) -> np.ndarray:
        # Read audio data using soundfile
        with BytesIO(songData) as audio_file:
            audio_data, sample_rate = sf.read(audio_file)
            
            # Convert to mono if stereo
            if len(audio_data.shape) > 1:
                audio_data = np.mean(audio_data, axis=1)
            
            # Resample to 16kHz if needed
            if sample_rate != 16000:
                # Simple linear resampling
                duration = len(audio_data) / sample_rate
                new_length = int(duration * 16000)
                audio_data = np.interp(
                    np.linspace(0, len(audio_data), new_length),
                    np.arange(len(audio_data)),
                    audio_data
                )
            
            # Convert to 16-bit PCM
            audio_data = (audio_data * 32767).astype(np.int16)
            
            return audio_data
    
    def createSignatureGenerator(self, audio: np.ndarray) -> SignatureGenerator:
        signature_generator = SignatureGenerator()
        signature_generator.feed_input(audio.tolist())
        signature_generator.MAX_TIME_SECONDS = self.MAX_TIME_SECONDS
        if len(audio) > 12 * 3 * 16000:  # If longer than 36 seconds
            signature_generator.samples_processed += 16000 * (int(len(audio) / (16 * 16000)) - 6)
        return signature_generator 