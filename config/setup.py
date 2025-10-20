from setuptools import setup, find_packages

setup(
    name="bugsigdb-analyzer",
    version="0.1.0",
    packages=find_packages(include=['retrieve', 'retrieve.*', 'models', 'models.*', 'utils', 'utils.*']),
    install_requires=[
        "torch>=2.0.0",
        "transformers>=4.35.0",
        "biopython>=1.81",
        "scikit-learn>=1.3.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "sentencepiece>=0.1.99",
        "accelerate>=0.24.0",
        "datasets>=2.14.0",
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=4.9.0",
        "tqdm>=4.65.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
        ],
    },
    python_requires=">=3.8",
) 