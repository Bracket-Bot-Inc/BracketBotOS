import os
import sys

from setuptools import setup, find_packages

setup(
    name="bbos",
    version="0.0.1",
    packages=find_packages(),
    description="BracketBot OS",
    url="https://github.com/BracketBotInc/BracketBotOS",
    author="Raghava Uppuluri",
    install_requires=[
        "sshkeyboard",
        "posix_ipc",
        "numpy",
        "taichi",
        "pillow",
    ],
)
