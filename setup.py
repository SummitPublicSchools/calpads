from setuptools import setup, find_packages

with open("README.md", "r") as readme:
    long_description = readme.read()

with open("LICENSE", "r") as li:
    lic = li.read()

setup(
    name="calpads",
    version="0.0.0",
    author="Yusuph Mkangara",
    author_email="yusuph.mka@outlook.com",
    description="Python Web API wrapper for CDE's CALPADS with a focus on data extraction",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license=lic,
    url="https://github.com/yo-my-bard/calpads",
    packages=find_packages(include=["calpads"]),
    install_requires=[
    "beautifulsoup4>=4.8.0, <5.0.0" #Might not need 4.8.0 exactly, but for now
    ]
)
