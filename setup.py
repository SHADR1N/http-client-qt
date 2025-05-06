import codecs
import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
path_readme = os.path.join(here, "README.md")

if os.path.exists(path_readme):
    with codecs.open(path_readme, encoding="utf-8") as fh:
        long_description = "\n" + fh.read()
else:
    long_description = ""

setup(
    name='qt-request-client',
    version='1.0.1',
    author='SHADRIN',
    author_email='none@gmail.com',
    license='MIT',
    packages=find_packages(),
    description='QtRequestClient',
    url='https://github.com/SHADR1N/http-client-qt.git',
    long_description_content_type='text/markdown',
    long_description=long_description,
    install_requires=[]
)
