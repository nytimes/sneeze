Glossary
========

.. glossary::
   :sorted:
   
   Test Case
      A particular set of operations and validations defined by a nose test.
      Test Cases have a label and id.  Stored in the ``test_case`` table,
      represented by the ``Case`` model.
   
   Case Execution
      The record of a specific run of a :term:`Test Case`.  The execution
      has a description, start time, end time, result, and a reference to the
      :term:`Test Case` that it is for.  Linked through the
      ``test_cycle_test_case_execution`` table to one or more
      :term:`Test Cycle`\ s.  Case Executions also have meta information
      attached to them through :term:`Execution Batch`\ s.  Stored in the
      ``test_case_execution`` table, represented by the ``CaseExecution``
      model.
   
   Test Cycle
      A collection of :term:`Case Execution`\ s with a name, label, and id.
      Stored in the ``test_cycle`` table, represented by the ``TestCycle``
      model.
   
   Execution Batch
      A collection of meta information about a set of tests run together in a
      single execution process.  Provides data on batch start and end time,
      execution host, environment, and nosetests command line options.  Stored
      in the ``execution_batch`` table, represented by the ``ExecutionBatch``
      model.
   
   Plugin Manager
      An object registered via the `managers <plugin_info.html#managers>`_
      entrypoint that implements Sneeze plugin runtime behaviors via the
      `plugin API <plugin_info.html#api>`_.

   Default Case
      Each :term:`Execution Batch` has a default :term:`Test Case` associated
      with it.  This case is used to generate :term:`Case Execution` records
      that act as the current :term:`Test Case` while the executor is outside
      of a test scope.  This is primarily provided so that plugins have
      an entity to associate data to (such as log messages) when a test is not
      currently executing.