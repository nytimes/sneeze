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


class Tissue(object):
    
    def __init__(self, db_config_string, test_cycle_name, test_cycle_description,
                 environment, host, command_line_arguments, start_time=None,
                 test_cycle_id=None, declarative_base=Base, engine=None,
                 session_factory=None, rerun_execution_ids=[]):
        
        self.access_lock = Lock()
        self.access_lock.acquire()
        if engine is None:
            engine = create_engine(db_config_string)
        else:
            engine = engine
        # To play nice with SQLAlchemy web framework integration, we have to wrap
        # the models in functions that take a declarative base, so we call that function
        # here for the core Sneeze models here
        self.db_models = add_models(declarative_base)
        for ext_add_models in pkg_resources.iter_entry_points(group='nose.plugins.sneeze.plugins.add_models'):
            self.db_models.update(ext_add_models.load()(declarative_base))
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
        
        self.enter_case(self.execution_batch.default_case.id, ['default_case'])
    
    def make_session(self, sync_with_new=True):
        
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
        
        return SessionTransaction(self)
    
    def enter_case(self, case, test_address_parts, description=''):
        
        for manager in self.plugin_managers:
            if hasattr(manager, 'before_enter_case'):
                manager.before_enter_case(case, description)
        with self.session_transaction() as session:
            # Assumes no nested default case scopes; all default case executions
            # should end PASSED (or PENDING)
            if (self.case_execution and self.execution_batch
                and self.case_execution.case.id == self.execution_batch.default_case.id):
                self.case_execution.result = 'PASS'
            Case = self.db_models['Case']
            if not isinstance(case, Case):
                try:
                    case = session.query(Case).filter(or_(Case.id==case, Case.label==case)).one()
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
        
        with self.session_transaction():
            self.case_execution.result = 'PASS'
            self.case_execution.end_time = datetime.now()
            self.test_cycle.running_count -= 1
        for manager in self.plugin_managers:
            if hasattr(manager, 'exit_test_cycle'):
                manager.exit_test_cycle()