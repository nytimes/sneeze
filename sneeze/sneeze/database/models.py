from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.ext.associationproxy import association_proxy
from datetime import datetime
from sqlalchemy import event
from passlib.hash import bcrypt, sha256_crypt
from datetime import timedelta

Base = declarative_base()


class ReverseMappingTuple(tuple):
    
    def __getitem__(self, key):
        
        try:
            return tuple.__getitem__(self, key)
        except TypeError:
            try:
                return self.index(key)
            except ValueError:
                raise KeyError('Mapping contains no value %s.' % key)
    
    def __getattr__(self, key):
        
        try:
            return self[key]
        except KeyError, e:
            raise AttributeError(e.msg)


EXECUTION_STATUSES = ReverseMappingTuple(('RUNNING', 'COMPLETE', 'ZOMBIE'))


def encryption_rounds(timestamp):
    
    # minimum 5001 rounds to avoid passlib.hash.sha256_crypt magic behavior at 5000 rounds
    rounds = int((float(timestamp.month + timestamp.second) / float(timestamp.day + timestamp.minute)) * 455091)
    while rounds > 65536:
        rounds = rounds >> 1
    if timestamp.microsecond > 1000:
        rounds += timestamp.microsecond / 1000
    else:
        rounds += timestamp.microsecond
    return rounds


def add_models(Base_=Base):

    class Case(Base_):
        
        __tablename__ = 'testCase'
        
        id = Column(Integer, primary_key=True)
        label = Column(String(200))
        
        def __init__(self, label=''):
            
            self.label = label
    
    
    class TestCycleCaseExecution(Base_):
        
        __tablename__ = 'testCycleTestCaseExecution'
        
        test_cycle_id = Column(Integer, ForeignKey('testCycle.id'), primary_key=True)
        case_execution_id = Column(Integer, ForeignKey('testCaseExecution.id'), primary_key=True)
        include_in_reporting = Column(Boolean)
        test_cycle = relationship('TestCycle', backref='case_execution_associations')
        case_execution = relationship('CaseExecution', backref='test_cycle_associations')
        
        def __init__(self, test_cycle=None, case_execution=None, include_in_reporting=True):
            
            if test_cycle is not None:
                try:
                    test_cycle.case_execution_associations.append(self)
                except:
                    self.test_cycle_id = test_cycle
            if case_execution is not None:
                try:
                    case_execution.test_cycle_associations.append(self)
                except:
                    self.case_execution_id = case_execution
            self.include_in_reporting = include_in_reporting
        
        @staticmethod
        def _link_creator(target):
            
            return TestCycleCaseExecution(**{{TestCycle : 'test_cycle',
                                              CaseExecution : 'case_execution'}[type(target)] : target})
    
    
    class CaseExecution(Base_):
        
        __tablename__ = 'testCaseExecution'
        
        id = Column(Integer, primary_key=True)
        description = Column(String(300))
        result = Column(Enum('PENDING', 'PASS', 'FAIL', 'SKIP'))
        execution_batch_id = Column(Integer, ForeignKey('executionBatch.id'))
        execution_batch = relationship('ExecutionBatch', backref='case_executions')
        case_id = Column(Integer, ForeignKey('testCase.id'))
        case = relationship(Case, backref='case_executions')
        start_time = Column(DateTime)
        end_time = Column(DateTime, nullable=True)
        test_cycles = association_proxy('test_cycle_associations', 'test_cycle',
                                        creator=TestCycleCaseExecution._link_creator)
        
        def __init__(self, case=None, execution_batch=None, test_cycle=None,
                     description='', result='PENDING', start_time=None):
            
            if case is not None:
                try:
                    case.case_executions.append(self)
                except:
                    self.case_id = case
            if execution_batch is not None:
                try:
                    execution_batch.case_executions.append(self)
                except:
                    self.execution_batch_id = execution_batch
            if test_cycle is not None:
                try:
                    test_cycle.case_executions.append(self)
                except Exception:
                    self.test_run_id = test_cycle
            self.description = description
            self.result = result
            self.start_time = start_time if start_time else datetime.now()
            self.end_time = None
        
        @property
        def status(self):
            
            return EXECUTION_STATUSES[self.status_id]
        
        @property
        def status_id(self):
            
            if not self.end_time:
                return EXECUTION_STATUSES.RUNNING
            elif self.result == 'PENDING':
                return EXECUTION_STATUSES.ZOMBIE
            else:
                return EXECUTION_STATUSES.COMPLETE
    
    class CaseExecutionAddressPart(Base_):
        
        __tablename__ = 'testCaseExecutionAddressPart'
        
        id = Column(Integer, primary_key=True)
        part = Column(String(200))
        case_execution_id = Column(Integer, ForeignKey('testCaseExecution.id'))
        case_execution = relationship(CaseExecution, backref='address_parts')
    
    class ExecutionBatch(Base_):
        
        __tablename__ = 'executionBatch'
        
        id = Column(Integer, primary_key=True)
        environment = Column(String(2000))
        host = Column(String(150))
        start_time = Column(DateTime)
        end_time = Column(DateTime, nullable=True)
        arguments = Column(String(2000))
        default_case_id = Column(Integer, ForeignKey('testCase.id'))
        default_case = relationship(Case)
        
        def __init__(self, environment, host, arguments='', start_time=None, default_case=None):
            
            self.environment = environment
            self.host = host
            self.arguments = arguments
            self.start_time = start_time if start_time else datetime.now()
            self.end_time = None
            self.default_case = default_case if default_case else Case()
        
        @property
        def status(self):
            
            return EXECUTION_STATUSES[self.status_id]
        
        @property
        def status_id(self):
            
            if not self.end_time:
                return EXECUTION_STATUSES.RUNNING
            elif self.result == 'PENDING':
                return EXECUTION_STATUSES.ZOMBIE
            else:
                return EXECUTION_STATUSES.COMPLETE
    
    
    def _update_default_case_label(mapper, connection, target):
        
        if not target.default_case.label:
            case = target.default_case
            table = case.__table__
            case_label = 'Out of case scope :%d:' % target.id
            statement = table.update().where(table.c.id==case.id).values(label=case_label)
            connection.execute(statement)
    
    event.listen(ExecutionBatch, 'after_insert', _update_default_case_label)
    
    
    class TestCycle(Base_):
        
        __tablename__ = 'testCycle'
        
        id = Column(Integer, primary_key=True)
        name = Column(String(100))
        description = Column(String(300))
        case_executions = association_proxy('case_execution_associations', 'case_execution',
                                            creator=TestCycleCaseExecution._link_creator)
        running_count = Column(Integer)
    
    
    class UserToken(Base_):
        
        __tablename__ = 'userToken'
        
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey('user.id'))
        user = relationship('User', backref='tokens')
        _create_time = Column(DateTime)
        create_micros = Column(Integer)
        value = Column(String(44))
        remaining_uses = Column(Integer, nullable=True)
        expires = Column(DateTime, nullable=True)
        revoked = Column(Boolean)
        
        @property
        def create_time(self):
            
            if not self._create_time.microsecond:
                return self._create_time + timedelta(microseconds=self.create_micros)
            else:
                return self._create_time
        
        @create_time.setter
        def create_time(self, time):
            
            self._create_time = time
            self.create_micros = time.microsecond
        
        @property
        def expired(self):
            
            return self.expires is not None and self.expires < datetime.now()
        
        @property
        def active(self):
            
            return bool(not self.revoked
                        and not self.expired
                        and (self.remaining_uses is None or self.remaining_uses))
        
        def use(self):
            
            active = self.active
            if self.remaining_uses is None:
                return active
            elif self.remaining_uses > 0:
                self.remaining_uses -= 1
                return active
            else:
                return False
        
        def revoke(self):
            
            self.revoked = True
        
        def verify(self, salt, value=None):
            
            if value is None:
                value = self.user.name
            crypt = '$5${}${}${}'.format('rounds=' + str(encryption_rounds(self.create_time)),
                                         salt,
                                         self.value)
            return sha256_crypt.verify(value, crypt)
    
    
    class User(Base_):
        
        __tablename__ = 'user'
        
        id = Column(Integer, primary_key=True)
        name = Column(String(75))
        password_crypt = Column(String(80), nullable=True)
        
        @property
        def password(self):
            
            raise AttributeError('password is a set-only convenience attribute.')
        
        @password.setter
        def password(self, passw):
            
            self.password_crypt = bcrypt.encrypt(passw)
        
        def verify_password(self, passw):
            
            return bcrypt.verify(passw, self.password_crypt)
        
        def get_new_token(self, salt, expires=None, max_uses=None):
            
            now = datetime.now()
            if expires:
                try:
                    # if expires is a duration (basically a timedelta) instead
                    # of a datetime, set expires to now plus delta
                    expires = now + expires
                except TypeError:
                    pass
            crypt = sha256_crypt.encrypt(self.name,
                                         rounds=encryption_rounds(now),
                                         salt=salt)
            value = crypt.split('$', 4)[4]
            token = UserToken(value=value, create_time=now, expires=expires,
                              revoked=False, remaining_uses=max_uses)
            self.tokens.append(token)
            return token
            
    
    
    return {'Case' : Case, 'TestCycle' : TestCycle,
            'CaseExecution' : CaseExecution, 'ExecutionBatch' : ExecutionBatch,
            'CaseExecutionAddressPart' : CaseExecutionAddressPart,
            'User' : User, 'UserToken' : UserToken}