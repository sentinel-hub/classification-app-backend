import os
from setuptools import setup, find_packages


def parse_requirements(file):
    return sorted(set(
        line.partition('#')[0].strip()
        for line in open(os.path.join(os.path.dirname(__file__), file))
    ) - set(''))


def get_version():
    for line in open(os.path.join(os.path.dirname(__file__), 'classification_service', '_version.py')):
        if line.find("__version__") >= 0:
            version = line.split("=")[1].strip()
            version = version.strip('"').strip("'")
    return version


setup(name='classification-service',
      python_requires='>=3.5',
      version=get_version(),
      description='A service which supports Classification App',
      url='https://github.com/sentinel-hub/classification-app-backend.git',
      author='Sinergise EO research team',
      author_email='eoresearch@sinergise.com',
      packages=find_packages(),
      package_data={'data': ['data/input_sources.json']},
      include_package_data=True,
      install_requires=parse_requirements("requirements.txt"),
      extras_require={'DEV': parse_requirements("requirements-dev.txt")},
      zip_safe=False)
