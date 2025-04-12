from setuptools import setup, find_packages

setup(
    name="shazam-forever",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "PyQt6>=6.9.0",
        "requests>=2.32.2",
        "sounddevice>=0.4.6",
        "numpy>=1.26.3",
        "soundfile>=0.12.1",
    ],
    entry_points={
        "console_scripts": [
            "shazam-forever=shazam_forever:main",
        ],
    },
    author="Easi Work",
    author_email="todo@easi.work",
    description="A desktop application for continuous music recognition using Shazam API",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/easiwork/shazam-forever",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
) 