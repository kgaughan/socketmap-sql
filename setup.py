#!/usr/bin/env python3

from setuptools import setup


setup(
    name='socketmap-sql',
    version='0.1.0',
    description='A socketmap script for SQL databases',
    long_description=open('README').read(),
    url='https://github.com/kgaughan/socketmap-sql/',
    author='Keith Gaughan',
    author_email='k@stereochro.me',
    license='MIT',
    scripts=['socketmap-sql'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Communications :: Email :: Mail Transport Agents',
        'Topic :: Database',
    ],
)
