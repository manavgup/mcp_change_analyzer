from setuptools import setup, find_packages

setup(
    name="mcp-change-analyzer",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "fastmcp>=0.1.0",
        "a2a-python>=0.1.0",
        "pydantic>=2.0.0",
        "gitpython>=3.1.30",
        "redis>=4.5.5",
        "fastapi>=0.100.0",
        "uvicorn>=0.22.0",
        "httpx>=0.24.1",
    ],
    extras_require={
        "dev": [
            "pytest>=7.3.1",
            "black>=23.3.0",
            "flake8>=6.0.0",
            "mypy>=1.3.0",
            "isort>=5.12.0",
        ]
    },
    python_requires=">=3.9",
    description="Git Change Analyzer MCP Server with A2A Protocol Support",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/mcp-change-analyzer",
    author="Your Name",
    author_email="your.email@example.com",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
