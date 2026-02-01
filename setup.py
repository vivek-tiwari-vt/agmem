#!/usr/bin/env python3
"""Setup script for agmem."""

from setuptools import setup, find_packages
import os

# Read README
readme_path = os.path.join(os.path.dirname(__file__), "README.md")
if os.path.exists(readme_path):
    with open(readme_path, "r", encoding="utf-8") as f:
        long_description = f.read()
else:
    long_description = "agmem - Agentic Memory Version Control System"

setup(
    name="agmem",
    version="0.1.4",
    description="Agentic Memory Version Control System - Git for AI agent memories",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="agmem Team",
    author_email="team@agmem.dev",
    url="https://github.com/vivek-tiwari-vt/agmem",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        # Core dependencies - using only standard library for now
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "agmem=memvcs.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Version Control",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    keywords="ai agent memory version-control git vcs llm",
    project_urls={
        "Bug Reports": "https://github.com/vivek-tiwari-vt/agmem/issues",
        "Source": "https://github.com/vivek-tiwari-vt/agmem",
        "Documentation": "https://github.com/vivek-tiwari-vt/agmem#readme",
    },
)
