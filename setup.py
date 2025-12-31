"""
Legacy setup.py - kept for backward compatibility.

This project uses pyproject.toml (PEP 518/621) as the primary source for package metadata.
Modern tools (pip, build, etc.) will automatically use pyproject.toml when available.

This setup.py is maintained for:
- Backward compatibility with older tools
- Fallback support if pyproject.toml is not available
- Tools that haven't migrated to pyproject.toml yet

For new installations, use: pip install -e .
This will automatically use pyproject.toml.
"""

from setuptools import setup, find_packages

# Read the README file
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
# Filter out PyTorch CPU-specific versions and pip options that aren't valid in install_requires
requirements = []
with open("config/requirements.txt", "r", encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Skip pip-specific options
        if line.startswith("--extra-index-url") or line.startswith("--index-url"):
            continue
        # Convert PyTorch CPU versions to standard versions
        if "+cpu" in line:
            line = line.replace("+cpu", "")
        requirements.append(line)

setup(
    name="bioanalyzer-backend",
    version="1.0.0",
    author="BioAnalyzer Team",
    author_email="team@bioanalyzer.org",
    description="A specialized AI-powered tool for analyzing scientific papers for BugSigDB curation readiness",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-repo/bioanalyzer-backend",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.5.0",
        ],
        "cli": [
            "click>=8.0.1",
            "rich>=13.0.0",
            "tabulate>=0.9.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "bioanalyzer=cli:main",
            "bioanalyzer-cli=cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.md", "*.txt", "*.yml", "*.yaml"],
    },
    keywords="bioinformatics, microbiome, bugsigdb, curation, ai, analysis",
    project_urls={
        "Bug Reports": "https://github.com/your-repo/bioanalyzer-backend/issues",
        "Source": "https://github.com/your-repo/bioanalyzer-backend",
        "Documentation": "https://github.com/your-repo/bioanalyzer-backend/docs",
    },
)
