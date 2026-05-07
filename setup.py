"""Setup for editable installs and PyInstaller builds."""
from setuptools import find_packages, setup

setup(
    name="alttext",
    version="0.1.0",
    description="BITV-konforme Alt-Text-Generierung mit lokalem Ollama-Vision-Modell.",
    packages=find_packages(exclude=("tests",)),
    python_requires=">=3.11",
    install_requires=[
        "ollama>=0.4.0",
        "Pillow>=10.0.0",
        "PyExifTool>=0.5.6",
        "rich>=13.7.0",
        "typer>=0.12.0",
    ],
    entry_points={
        "console_scripts": [
            "alttext=alttext.cli:app",
        ],
    },
)
