from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-gimp",
    version="0.1.0",
    description="CLI-Anything wrapper for GIMP image editor state",
    packages=find_namespace_packages(),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-gimp=cli_anything_gimp.cli:main",
        ],
    },
)
