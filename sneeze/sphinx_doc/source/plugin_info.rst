Plugins
=======

The behavior of Sneeze can be modified and extended by implementing plugins.

Entrypoints
-----------

The Sneeze plugin API utilizes 3 distutils entrypoints to add functionality to
the system.  They share a root ``nose.plugins.sneeze.plugins``\ .

add_options
^^^^^^^^^^^

``nose.plugins.sneeze.plugins.add_options`` allows a plugin to add new command
line arguments to nosetests.  It should point at a callable that expects an
options parser and an environment string; return values are ignored.

managers
^^^^^^^^

``nose.plugins.sneeze.plugins.managers`` allows a plugin to define a 
:term:`Plugin Manager` to execute the behavior of the plugin during test exection.
It should point to a class that utilizes the Sneeze plugin API.


add_models
^^^^^^^^^^

``nose.plugins.sneeze.plugins.add_models`` allows a plugin to extend the DB
schema by adding new models to the ORM. It should point to a callable that
expects a `SQLAlchemy declarative base object
<http://docs.sqlalchemy.org/en/rel_0_8/orm/extensions/declarative.html>`_.
It should return a dictionary containing key value pairs where the key is a
string of the model name and the value is the model itself for all "public"
models implemented.

API
---

The Sneeze API generally assumes that :term:`Plugin Manager`\ s will use the
:doc:`Tissue <tissue>` instance from initialization to retrieve any needed state, so the
calls generally avoid passing any information as arguments that could be
obtained through the :doc:`Tissue <tissue>`. 

.. function:: enter_test_cycle()

   Called once, after the :doc:`Tissue <tissue>` has been initialized, before any
   :term:`Case Execution`\ s are started.

.. function:: before_enter_case()
   
   Called before entering each case.  Note that this is called when entering
   a :term:`Default Case` as well.

.. function:: after_case(case, description)
   
   Called after a case has been entered, but before it is run.  Receives a
   :term:`Case <Test Case>` object for ``case`` and a *string* ``description``.

.. function peek_error(test, err)
   
   Called from the ``nose`` API calls ``handleError`` and ``handleFailure``,
   allows your plugin to capture the error output from a failed test for later
   use.  Recieves the current ``nose`` test object as ``test`` and the error
   object as ``err``.

.. function:: handle_pass()
   
   Called from ``nose`` API ``addSuccess()``, when a test has passed.

.. function:: handle_fail(error)
   
   Called from ``nose`` API ``addFailure()`` and ``addError()`` in cases where
   the test errored (generally, raised an uncaught exception).  Receives a
   *string* as ``error``.

.. function:: handle_skip(error)
   
   Called from ``nose`` API ``addError()`` in cases where the test was skipped
   or is deprecated, receives a *string* as ``error`` containing any message
   from the skip or deprecation exception.

.. function:: before_exit_case(result)
   
   Called before a :term:`Case Execution` result is recorded, after it has
   completed and :func:handle_fail\ or :func:handle_pass have been called.
   Receives a *string* as ``result``.  Note that this is not called for
   :term:`Case Execution`\ s of the :term:`Default Case`.

.. function:: after_exit_case(result)
   
   Called after the result has been recorded for a :term:`Case Execution`,
   but before entering an execution of the :term:`Default Case`.  Note that
   this is not called for :term:`Case Execution`\ s of the
   :term:`Default Case`.

.. function:: exit_test_cycle()
   
   Called when the :doc:`Tissue <tissue>` exits, after all tests in the executor have been
   completed and recorded.