'''The Sneeze class is the plugin for nose.  It provides the core command line options
for controlling Sneeze behavior for a given nosetests execution.  Providing the
:option:`--reporting-db-config` argument to nosetests enables Sneeze (and any of its
enabled plugins) for the given nosetests execution.  The user must also provide either
:option:`--test-cycle-name` and :option:`--test-cycle-description`, or a valid
:option:`--test-cycle-id` for the tests to execute successfully, once Sneeze is enabled.

The plugin starts the Tissue and connects the Sneeze API hooks to the nose plugin API.
It also loads and initializes the plugin managers for any Sneeze plugins being used,
and attaches them to the Tissue.
'''


from nose.plugins import Plugin
from sneeze.database.interface import Tissue
import os, sys, socket, pkg_resources
from nose.exc import SkipTest, DeprecatedTest
from multiprocessing import current_process


class Sneeze(Plugin):
    
    enabled = False
    # Prioritize before SkipTests nose plugin, leave space for Sneeze plugins
    score = 1100
    
    def options(self, parser, env=os.environ):
        
        parser.add_option('--reporting-db-config',
                          action='store',
                          default=env.get('sneeze_db_config', ''),
                          dest='reporting_db_config',
                          metavar='CONFIG_STRING',
                          help='SQLAlchemy formated connection string for reporting database.')
        parser.add_option('--test-cycle-name',
                          action='store',
                          dest='test_cycle_name',
                          metavar='NAME',
                          help='Name of the test cycle being run.')
        parser.add_option('--test-cycle-description',
                          action='store',
                          default='',
                          dest='test_cycle_description',
                          metavar='DESCRIPTION',
                          help='Description for the test cycle being run.')
        parser.add_option('--test-cycle-id',
                          action='store',
                          default=0,
                          dest='test_cycle_id',
                          metavar='CYCLE_ID',
                          type=int,
                          help=('id of test cycle to run tests under.  '
                                'Overrides :option:`--test-cycle-name` and :option:`--test-cycle-description`.'))
        parser.add_option('--rerun-from-case-execution',
                          action='append',
                          dest='case_execution_reruns',
                          metavar='EXECUTION_ID_LIST',
                          type=int,
                          help='Case execution id to base rerun upon.')
        parser.add_option('--pocket-change-host',
                          action='store',
                          default=env.get('pocket_change_host', ''),
                          dest='pocket_change_host',
                          metavar='HOST',
                          help='url of associated pocket change server.')
        parser.add_option('--pocket-change-username',
                          action='store',
                          default=env.get('pocket_change_username', ''),
                          dest='pocket_change_username',
                          metavar='USERNAME',
                          help='username for pocket change user.')
        parser.add_option('--pocket-change-password',
                          action='store',
                          default='',
                          dest='pocket_change_password',
                          metavar='PASSWORD',
                          help='password for pocket change user.')
        parser.add_option('--pocket-change-token',
                          action='store',
                          default=env.get('pocket_change_token', ''),
                          dest='pocket_change_token',
                          metavar='TOKEN',
                          help='token for pocket change user.')
        parser.add_option('--pocket-change-environment-envvar',
                          action='store',
                          default='TEST_ENVIRONMENT',
                          dest='pocket_change_environment_envvar',
                          metavar='ENVIRONMENT_VAR_NAME',
                          help='Name of environment variable to record as the test environment value.')
        for add_options in pkg_resources.iter_entry_points(group='nose.plugins.sneeze.plugins.add_options'):
            add_options.load()(parser, env)
    
    def configure(self, options, noseconfig):
        
        if options.reporting_db_config:
            # nose multiprocess configures plugins twice in each worker (once during unpickling config,
            # once during __runner setting itself up.  It doesn't seem to make any sense that it does
            # that, but it does, so we have to handle it in order to not end up with 2 Tissues (etc)
            # created in each worker and thus ending up with orphaned sneeze plugins that do bad things.
            if not (hasattr(self, 'tissue') and self.tissue):
                environment = os.environ.get(options.pocket_change_environment_envvar,
                                             '[no environment found]')
                try:
                    test_cycle_id = noseconfig.test_cycle_id
                except AttributeError:
                    test_cycle_id = options.test_cycle_id
                    rerun_execution_ids = []
                else:
                    rerun_execution_ids = options.case_execution_reruns
                self.tissue = Tissue(options.reporting_db_config, options.test_cycle_name,
                                     options.test_cycle_description, environment,
                                     socket.gethostbyaddr(socket.gethostname())[0],
                                     ' '.join(sys.argv), test_cycle_id=test_cycle_id,
                                     rerun_execution_ids=rerun_execution_ids)
                noseconfig.test_cycle_id = self.tissue.test_cycle.id
                Sneeze.enabled = True
                for Manager in pkg_resources.iter_entry_points(group='nose.plugins.sneeze.plugins.managers'):
                    Manager = Manager.load()
                    if Manager.enabled(self.tissue, options, noseconfig):
                        self.tissue.plugin_managers.append(Manager(self.tissue, options, noseconfig))
                self.tissue.start()
                for manager in self.tissue.plugin_managers:
                    if hasattr(manager, 'enter_test_cycle'):
                        manager.enter_test_cycle()
                if options.case_execution_reruns:
                    CaseExecution = self.tissue.db_models['CaseExecution']
                    with self.tissue.session_transaction() as session:
                        case_executions = (session.query(CaseExecution)
                                           .filter(CaseExecution.id.in_(options.case_execution_reruns))
                                           .all())
                        noseconfig.testNames = []
                        for case_execution in case_executions:
                            name = '{}:{}'.format(*[p.part for p in case_execution.address_parts[::2]])
                            noseconfig.testNames.append(name)
        else:
            self.tissue = None
            Sneeze.enabled = False
    
    def startTest(self, test):
        
        case_label = '.'.join(test.address()[1:])
        self.tissue.enter_case(case_label, test.address(), test.test.shortDescription())
    
    
    def peekError(self, test, err):
          
        for manager in self.tissue.plugin_managers:
            if hasattr(manager, 'peek_error'):
                manager.peek_error(test, err)
    
    def handleError(self, test, err):
        
        self.peekError(test, err)
    
    def handleFailure(self, test, err):
        
        self.peekError(test, err)
    
    def addError(self, test, err):
        
        if isinstance(err[1], basestring):
            error = err[1]
        else:
            error = err[1].message
        if err[0] in (SkipTest, DeprecatedTest):
            self.exit_state = 'SKIP'
            for manager in self.tissue.plugin_managers:
                if hasattr(manager, 'handle_skip'):
                    manager.handle_skip(error)
        else:
            self.exit_state = 'FAIL'
            for manager in self.tissue.plugin_managers:
                if hasattr(manager, 'handle_fail'):
                    manager.handle_fail(error)

    def addFailure(self, test, err):
        
        self.exit_state = 'FAIL'
        if isinstance(err[1], basestring):
            error = err[1]
        else:
            error = err[1].message
        for manager in self.tissue.plugin_managers:
            if hasattr(manager, 'handle_fail'):
                manager.handle_fail(error)

    def addSuccess(self, test):
        
        self.exit_state = 'PASS'
        for manager in self.tissue.plugin_managers:
            if hasattr(manager, 'handle_pass'):
                manager.handle_pass()
    
    def stopTest(self, test):
        
        self.tissue.exit_case(self.exit_state)
    
    def finalize(self, result):
        
        self.tissue.exit()
    
    def stopWorker(self, config):
        
        self.tissue.exit()