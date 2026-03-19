from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-mpv",
    version="0.1.0",
    description="CLI-Anything wrapper for MPV media player playback and property state",
    packages=find_namespace_packages(),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-mpv=cli_anything_mpv.cli:main",
        ],
    },
)
