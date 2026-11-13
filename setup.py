# Compatibility for pre-PEP621 setuptools. pyproject.toml remains canonical.
from setuptools import setup, find_packages
setup(name='labs-meet-companion',version='0.1.0',description='Review-first Google Meet companion for Lathar Labs',python_requires='>=3.10',packages=find_packages(),package_data={'labs_meet':['static/*','public/*','fixtures/*']},extras_require={'google':['google-auth>=2.40,<3','requests>=2.32,<3']},entry_points={'console_scripts':['labs-meet=labs_meet.cli:main']})
