from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-krita",
    version="0.1.0",
    description="CLI-Anything wrapper for Krita digital painting app state",
    packages=find_namespace_packages(),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-krita=cli_anything_krita.cli:main",
        ],
    },
)
