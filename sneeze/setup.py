from setuptools import setup, find_packages

setup(name='sneeze',
      version='0.0.0',
      packages=find_packages(),
      install_requires=['SQLAlchemy',
                        'nose >= 1.2',
                        'passlib'],
      entry_points={'nose.plugins.0.10' : ['sneeze = sneeze.nose_interface:Sneeze']})