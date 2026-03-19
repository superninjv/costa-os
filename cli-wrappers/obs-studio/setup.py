from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-obs",
    version="0.1.0",
    description="CLI-Anything wrapper for OBS Studio state",
    packages=find_namespace_packages(),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-obs=cli_anything_obs.cli:main",
        ],
    },
)
