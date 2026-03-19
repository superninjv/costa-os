from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-vesktop",
    version="0.1.0",
    description="CLI-Anything wrapper for Vesktop (Discord) state",
    packages=find_namespace_packages(),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-vesktop=cli_anything_vesktop.cli:main",
        ],
    },
)
