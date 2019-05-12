import os
from setuptools import setup, find_packages


version = '0.2.1'
README = os.path.join(os.path.dirname(__file__), 'README.md')
long_description = open(README).read()
setup(
    name='moneriote',
    version=version,
    description='Python scripts to maintain Monero open-nodes DNS records',
    long_description=long_description,
    long_description_content_type='text/markdown',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: WTFPL',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
        'Programming Language :: Python'
    ],
    keywords='monero',
    author='',
    author_email='',
    url='',
    install_requires=[
        'requests',
        'click',
        'python-dateutil'
    ],
    entry_points='''
    [console_scripts]
    moneriote=moneriote.main:cli
    ''',
    setup_requires=['setuptools>=38.6.0'],
    download_url=
        '',
    packages=find_packages(),
    include_package_data=True,
)
