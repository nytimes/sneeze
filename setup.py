from setuptools import setup, find_packages

setup(name='nose-sneeze',
      version='0.0.2',
      author='Silas Ray',
      author_email='silas.ray@nytimes.com',
      license='Apache2.0',
      url='http://sneeze.readthedocs.org/',
      description='A nose plugin for better reporting',
      long_description='A nose plugin that provides a platform to facilitate better result reporting.',
      classifiers=['Development Status :: 4 - Beta',
                   'Intended Audience :: Information Technology',
                   'Topic :: Software Development :: Quality Assurance',
                   'Topic :: Software Development :: Testing'],
      packages=find_packages(),
      install_requires=['SQLAlchemy',
                        'nose-for-sneeze',
                        'passlib'],
      entry_points={'nose.plugins.0.10' : ['sneeze = sneeze.nose_interface:Sneeze']})
