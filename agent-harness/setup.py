"""Setup configuration for the WPS CLI."""

from setuptools import setup, find_namespace_packages

with open("cli_anything/wps/README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="wps",
    version="1.0.0",
    author="Quantatirsk",
    author_email="quant@example.com",
    description="CLI harness for WPS API PDF conversion service",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Quantatirsk/wps-api",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    package_dir={"": "."},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0.0",
        "requests>=2.28.0",
        "rich>=13.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "wps=cli_anything.wps.wps_cli:cli",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
