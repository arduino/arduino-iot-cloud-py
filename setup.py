import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="aiotcloud",
    version="0.0.1",
    url="https://github.com/bcmi-labs/python-aiotcloud",
    author="Ibrahim Abdelkader",
    author_email="i.abdelkader@arduino.cc",
    description="Arduino IoT cloud Python module",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Topic :: Software Development :: Embedded Systems",
        "Operating System :: Linux",
    ],
    python_requires=">=3.8",
)
