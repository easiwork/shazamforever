# Custom ShazamAPI

A modified version of the ShazamAPI Python package that defaults to English locale (en-US) instead of Russian.

## Changes

- Changed default language from 'ru' to 'en-US'
- Changed timezone from 'Europe/Moscow' to 'America/New_York'
- Updated API URL to use English locale

## Installation

```bash
pip install -e .
```

## Usage

Same as the original ShazamAPI package, but with English responses by default.

```python
from custom_shazam_api import Shazam

# Use as normal
shazam = Shazam(audio_bytes)
recognize_generator = shazam.recognizeSong()
```

## License

MIT
