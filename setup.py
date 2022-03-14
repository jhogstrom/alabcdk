from os import path
from setuptools import find_packages, setup


here = path.abspath(path.dirname(__file__))

# Get the long description from the relevant file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

with open(path.join(here, "requirements.txt")) as f:
    deps = [l.strip() for l in f.readlines() if l.strip() != ""]

setup(name='aws',
    version='1.0.14',
    description='Useful CDK constructs',
    url='https://github.com/aditrologistics/awscdk.git',
    author='Jesper Högström',
    author_email='jesper.hogstrom@aditrologistics.com',
    # license='MIT',
    packages=find_packages(),
    # zip_safe=False
    long_description_content_type="text/markdown",
    long_description=long_description,
    install_requires=deps,
    package_data={'': ['preinstalled*.txt']},
    include_package_data=True,
)