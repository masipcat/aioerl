#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

with open("README.md", "r") as f:
    readme = f.read()

with open("requirements.txt", "r") as f:
    requirements = f.readlines()

with open("test-requirements.txt", "r") as f:
    test_requirements = f.readlines()

setup(
    author="Jordi Masip",
    author_email="jordi@masip.cat",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    description="",
    install_requires=requirements,
    license="GNU license",
    long_description=readme,
    long_description_content_type="text/markdown",
    include_package_data=True,
    name="aioerl",
    keywords="",
    packages=find_packages(include=["aioerl"]),
    test_suite="tests",
    tests_require=test_requirements,
    url="https://github.com/masipcat/aioerl",
    version="0.0.20190425.1",
    zip_safe=False,
)
