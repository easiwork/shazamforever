from setuptools import setup, find_packages

setup(
    name="custom-shazam-api",
    version="0.0.1",
    packages=find_packages(),
    install_requires=[
        "numpy",
        "pydub",
        "requests",
    ],
    author="Your Name",
    author_email="your.email@example.com",
    description="A modified version of ShazamAPI that defaults to English locale",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/custom-shazam-api",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
) 