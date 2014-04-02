.. sneeze documentation master file, created by
   sphinx-quickstart on Mon Dec  2 13:20:47 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Introduction
============

Sneeze is a pluggable plugin for the nose unit testing framework that logs test
activity to a database at test runtime.  It also exposes an interface that
allows extension of the DB model and an API modeled on the nose plugin API to
extend behavior.  Finally, it adds a number of command line options to
nosetests to configure the database to connect to and to rerun tests from
identifiers from the database.  It is intended primarily as a base for
additional plugins.

Installation and Quickstart
===========================

First, install Sneeze (``pip install nose-sneeze``), then run any tests with nose 
using nosetests from the command line as you would normally, but with the 
following command line arguments:

* :option:`--reporting-db-config` An `SQLAlchemy formatted
  <http://docs.sqlalchemy.org/en/rel_0_8/core/engines.html#database-urls>`_
  connection string (you can use an SQLite database without any additional
  setup provided you have a standard Python install)
* :option:`--test-cycle-name` A short identifying string for the
  :term:`Test Cycle` being run
* :option:`--test-cycle-description` A longer description of the
  :term:`Test Cycle` being run

:term:`Test Cycle`\ s are just collections of test results; they are not unique
by name or description, and can contain one or more results for each of any
number of tests.  To report tests in an existing :term:`Test Cycle`, use
:option:`--test-cycle-id` with the :term:`Test Cycle` id from the database of
the :term:`Test Cycle` you wish to add the results of the tests being run to.
Either the :term:`Test Cycle` name/description pair or the id must be provided;
if an id is provided, it will always supersede any other :term:`Test Cycle`
configurations.  The database config can also be stored more permanently by
setting it on an environment variable named ``sneeze_db_config``.

*Be aware that do to nose being in maintenance mode, Sneeze relies on a custom
version of nose, nose-for-sneeze.  It should work fine with normal nose as long
as you don't attempt to use the multiprocess plugin.  Links to relevant fork 
and pull request here:*

* `nose with worker exit hook <https://github.com/silasray/nose>`_
* `pull request <https://github.com/nose-devs/nose/pull/748>`_

Details
=======

.. toctree::
   :maxdepth: 2

   sneeze
   plugin_info
   glossary

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
