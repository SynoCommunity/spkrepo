# -*- coding: utf-8 -*-
from setuptools import setup, find_packages


tests_require = ['Flask-Testing',
                 'factory-boy', 'Faker',
                 'lxml', 'urltools', 'mock', 
                 'coveralls']

install_requires = ['Flask',
                    'Flask-SQLAlchemy',
                    'Flask-Security', 'passlib', 
                    'Flask-Babelex',
                    'Flask-WTF', 'Flask-Mail', 'configparser', 'email_validator',
                    'Flask-Principal',
                    'Flask-Admin', 'SQLAlchemy',  # ValueError: too many values to unpack (until flask-admin is fixed)
                    'Pillow', 
                    'Flask-RESTful',
                    'Flask-Login',
                    'Flask-Caching', 'redis',
                    'python-gnupg', 'requests', 'click', 
                    'Flask-Migrate', 'alembic>=0.7.0',
                    'Flask-Script', 'Text-Unidecode', 'ipaddress',
                    'Flask-DebugToolbar']

dev_requires = ['sphinx', 'sphinx-rtd-theme']


setup(
    name='spkrepo',
    version='0.1',
    license='MIT',
    url='https://github.com/Diaoul/spkrepo',
    description='Synology Package Repository',
    long_description=open('README.md').read(),
    author='Antoine Bertin',
    author_email='diaoulael@gmail.com',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Flask',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
        'Topic :: System :: Archiving :: Packaging'
    ],
    install_requires=install_requires,
    test_suite='spkrepo.tests.suite',
    tests_require=tests_require,
    extras_require={'tests': tests_require,
                    'dev': tests_require + dev_requires}
)
