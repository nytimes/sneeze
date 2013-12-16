from threading import Lock
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound
from datetime import datetime
import pkg_resources
from sneeze.database.models import Base, EXECUTION_STATUSES, add_models


class SessionTransaction(object):
    
    def __init__(self, tissue):
        
        self.tissue = tissue
        self.session = None
    
    def __enter__(self):
        
        self.tissue.access_lock.acquire()
        self.session = self.tissue.make_session()[0]
        return self.session
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        
        self.session.commit()
        self.tissue.last_session = self.session
        self.tissue.access_lock.release()
        return False


# Multiprocess support
# TODO: Less hacky please...
_db_models = {}

def _get_models(base, adders):
    
    global _db_models
    if not _db_models:
        for adder in adders:
            _db_models.update(adder(base))
    return _db_models


class Tissue(object):
    """The Tissue is the core component of Sneeze; it catches everything from
    your nose when you Sneeze.  The Tissue loads the DB models, manages the DB
    connection, and acts as a state machine for the system as a whole.
    
    Primary attributes include a lock used to control access to the database,
    a session factory to generate sessions, a list of active
    :term:`Plugin Manager`\ s, and a dictionary of added db model classes.
    """
    
    def __init__(self, db_config_string, test_cycle_name, test_cycle_description,
                 environment, host, command_line_arguments, start_time=None,
                 test_cycle_id=None, declarative_base=Base, engine=None,
                 session_factory=None, rerun_execution_ids=[]):
        """Initialize a Tissue object.  Creates a ``SQLAlchemy`` `engine
        <http://docs.sqlalchemy.org/en/rel_0_8/core/connections.html#sqlalchemy.engine.Engine>`_
        and `session factory
        <http://docs.sqlalchemy.org/en/latest/orm/session.html#sqlalchemy.orm.session.sessionmaker>`_
        , loads models from the plugin entry point, creates a new or
        establishes relationship to an existing :term:`Test Cycle`, and creates
        an :term:`Execution Batch`.  Also creates the ``access_lock`` for the
        Tissue instance.
        
        :param db_config_string: An `SQLAlchemy formatted
            <http://docs.sqlalchemy.org/en/rel_0_8/core/engines.html#database-urls>`_
            database connection string.
        :type db_config_string: string
        :param test_cycle_name: A shortish string describing the :term:`Test Cycle`.
        :type test_cycle_name: string
        :param test_cycle_description: A longer string describing the :term:`Test Cycle`.
        :type test_cycle_description: string
        :param environment: Will be recorded as part of the :term:`Execution Batch` details.
        :type environment: string
        :param host: Will be recorded as part of the :term:`Execution Batch` details.
        :type host: string
        :param command_line_arguments: Will be recorded as part of the :term:`Execution Batch`
            details.
        :type command_line_arguments: string
        :param start_time: The start time of the :term:`Execution Batch`.  If ``None``, will
            be set to ``now()``.  Defaults to ``None``.
        :type start_time: ``datetime.datetime`` or ``None``.
        :param test_cycle_id: If truey, tests run in this Tissue will be added to
            the :term:`Test Cycle` with the given id.  A falsey value will cause the
            name and description to be used to create a new :term:`Test Cycle`.
            Defaults to ``None``.
        :type test_cycle_id: ``int`` or ``None``
        :param declarative_base: Will be used to derive the models being added.  If not
            provided, a default Base instance will be used.
        :type declarative_base: `SQLAlchemy declarative base
            <http://docs.sqlalchemy.org/en/rel_0_8/orm/extensions/declarative.html>`_
        :param engine: Used to initialize the session factory.  If ``None`` is provided,
            an engine is created using `SQLAlchemy's create_engine
            <http://docs.sqlalchemy.org/en/rel_0_8/core/engines.html#sqlalchemy.create_engine>`_\ .
            Defaults to ``None``.
        :type engine: `SQLAlchemy engine
            <http://docs.sqlalchemy.org/en/rel_0_8/core/connections.html#sqlalchemy.engine.Engine>`_
        :param session_factory: A callable that returns an ``SQLAlchemy Session``
            object for the Tissue configuration.  If ``None``, a factory created
            with `SQLAlchemy's sessionmaker
            <http://docs.sqlalchemy.org/en/latest/orm/session.html#sqlalchemy.orm.session.sessionmaker>`_
            using the connection string provided to ``db_config_string`` is
            created.  Defaults to ``None``.
        :type session_factory: callable or ``None``
        :param rerun_execution_ids: An iterable of execution ids to rerun tests
            from.  The test names from the executions will be added to the list
            of test names to be run.  Defaults to an empty list.
        :type rerun_execution_ids: iterable of ``int``s.
        """
        
        self.access_lock = Lock()
        self.access_lock.acquire()
        if engine is None:
            engine = create_engine(db_config_string)
        else:
            engine = engine
        # To play nice with SQLAlchemy web framework integration, we have to wrap
        # the models in functions that take a declarative base, so we call that function
        # for the core Sneeze models here
        adders = [add_models]
        for ext_add_models in pkg_resources.iter_entry_points(group='nose.plugins.sneeze.plugins.add_models'):
            adders.append(ext_add_models.load())
        self.db_models = _get_models(declarative_base, adders)
        self.plugin_managers = []
        declarative_base.metadata.create_all(engine)
        if session_factory is None:
            self.session_factory = sessionmaker(bind=engine)
        else:
            self.session_factory = session_factory
        session = self.session_factory()
        TestCycle = self.db_models['TestCycle']
        CaseExecution = self.db_models['CaseExecution']
        if rerun_execution_ids and not test_cycle_id and not test_cycle_name:
            case_executions = (session.query(CaseExecution)
                               .filter(CaseExecution.id.in_(rerun_execution_ids))
                               .all())
            if case_executions[0].test_cycles:
                cycle_ids = set(cycle.id for cycle in case_executions[0].test_cycles)
                for case_execution in case_executions[1:]:
                    if case_execution.test_cycles:
                        cycle_ids.intersection_update(cycle.id for cycle in case_execution.test_cycles)
                    else:
                        break
                else:
                    if len(cycle_ids) == 1:
                        test_cycle_id = cycle_ids.pop()
        if test_cycle_id:
            self.test_cycle = session.query(TestCycle).filter(TestCycle.id==test_cycle_id).one()
            self.test_cycle.running_count += 1
            session.commit()
        else:
            self.test_cycle = TestCycle(name=test_cycle_name, description=test_cycle_description,
                                        running_count=1)
            session.add(self.test_cycle)
        self.execution_batch = self.db_models['ExecutionBatch'](environment=environment, host=host,
                                                        arguments=command_line_arguments,
                                                        start_time=start_time if start_time else datetime.now())
        session.add(self.execution_batch)
        session.commit()
        self.last_session = session
        self.case_execution = None
        self.access_lock.release()
    
    def start(self):
        """Called to begin the :term:`Execution Batch` being run in this
        ``Tissue``, enters the batch's :term:`Default Case`.
        """
        
        self.enter_case(self.execution_batch.default_case.id, ['default_case'])
    
    def make_session(self, sync_with_new=True):
        """Wraps the ``SQLAlchemy`` session factory for the ``Tissue``
        instance.
        
        :param sync_with_new: If ``True``, the ``case_execution`` and
            ``test_cycle`` instances of the calling ``Tissue`` instance
            will be updated to the objects from the new session.  Defaults
            to ``True``.
        :type sync_with_new: ``bool``
        
        :returns: A 2-tuple containing the newly created session and a ``dict``
            containing the merge target (ex ``test_cycle`` and
            ``execution_batch``\ ) model instances from the newly created
            session.
        """
        
        session = self.session_factory()
        merge_targets = {'test_cycle' : session.merge(self.test_cycle),
                         'execution_batch' : session.merge(self.execution_batch)}
        if self.case_execution:
            merge_targets['case_execution'] = session.merge(self.case_execution)
        # TODO: Plugin hook to allow extension of session state replication here
        if sync_with_new:
            # TODO: Plugin hook to override sync behavior for session state replication here
            for name, value in merge_targets.iteritems():
                setattr(self, name, value)
            self.last_session.close()
        return session, merge_targets
    
    def session_transaction(self):
        """Returns a context manager that handles grabbing the ``Tissue``\ 's
        lock and committing the session automatically.
        """
        
        return SessionTransaction(self)
    
    def enter_case(self, case, test_address_parts, description=''):
        """Causes the ``Tissue`` to enter a new :term:`Case Execution` for the
        given :term:`Test Case`\ .  Calls :meth:`before_enter_case` and
        :meth:`after_enter_case` plugin hooks.  Also closes out the current
        :term:`Case Execution` if it is an execution of the :term:`Default Case`\ .
        :meth:`enter_case`, unlike :meth:`exit_case`, is called for executions of the
        :term:`Default Case`\ .
        
        :param case: A :term:`Test Case` object.
        :type case: ``TestCase`` DB model object
        :param test_address_parts: Will be recorded as the test address for the
            :term:`Test Execution`.  Primarily useful for ``rerun_execution_ids``\ .
        :type test_address_parts: iterable of ``string``\ s
        :param description: A description of the :term:`Test Case` for this
            :term:`Case Execution`.  Defaults to ``''``.
        :type description: ``string``
        """
        
        for manager in self.plugin_managers:
            if hasattr(manager, 'before_enter_case'):
                manager.before_enter_case(case, description)
        with self.session_transaction() as session:
            # Assumes no nested default case scopes; all default case executions
            # should end PASSED (or PENDING)
            if (self.case_execution and self.execution_batch
                and self.case_execution.case.id == self.execution_batch.default_case.id):
                self.case_execution.end_time = datetime.now()
                self.case_execution.result = 'PASS'
            Case = self.db_models['Case']
            if not isinstance(case, Case):
                try:
                    id_ = int(case)
                except ValueError:
                    id_ = 0
                try:
                    case = session.query(Case).filter(or_(Case.id==id_, Case.label==case)).one()
                except NoResultFound:
                    case = Case(label=case)
            self.case_execution = self.db_models['CaseExecution'](case=case, description=description)
            self.execution_batch.case_executions.append(self.case_execution)
            self.test_cycle.case_executions.append(self.case_execution)
            AddressPart = self.db_models['CaseExecutionAddressPart']
            for part in test_address_parts:
                self.case_execution.address_parts.append(AddressPart(part=part))
        for manager in self.plugin_managers:
            if hasattr(manager, 'after_enter_case'):
                manager.after_enter_case(case, description)
        
    
    def exit_case(self, result):
        """Called after a test has been executed, causes the ``Tissue``
        to exit the current case.  Calls :meth:`before_exit_case` and
        :meth:`after_exit_case` plugin hooks.  Enters the :term:`Default Case`\ .
        Note that :meth:`exit_case`, unlike :meth:`enter_case`, is not called for
        executions of the :term:`Default Case`\ .
        
        :param result: The result of the just completed :term:`Case Execution`\ .
        :type result: ``string``
        """
        
        for manager in self.plugin_managers:
            if hasattr(manager, 'before_exit_case'):
                manager.before_exit_case(result)
        with self.session_transaction():
            self.case_execution.end_time = datetime.now()
            self.case_execution.result = result
        # Very slim potential for activities to occur outside the start/end time
        # of any case execution here; if a thread grabs the lock between
        # the session transaction context and the enter case
        for manager in self.plugin_managers:
            if hasattr(manager, 'after_exit_case'):
                manager.after_exit_case(result)
        self.enter_case(self.execution_batch.default_case.id, ['default_case'])
    
    def exit(self):
        """Called after the :term:`Execution Batch` is completed.  Tears down
        the ``Tissue``.  Closes out the last :term:`Default Case` execution
        and calls the :meth:`exit_test_cycle` plugin hook.
        """
        
        with self.session_transaction():
            self.case_execution.result = 'PASS'
            self.case_execution.end_time = datetime.now()
            self.test_cycle.running_count -= 1
        for manager in self.plugin_managers:
            if hasattr(manager, 'exit_test_cycle'):
                manager.exit_test_cycle()