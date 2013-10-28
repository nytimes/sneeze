from nose.plugins import Plugin
from sneeze.database.interface import Tissue
import os, sys, socket, pkg_resources
from nose.exc import SkipTest, DeprecatedTest


class Sneeze(Plugin):
    
    enabled = False
    # Prioritize before SkipTests nose plugin, leave space for Sneeze plugins
    score = 1100
    
    def options(self, parser, env=os.environ):
        
        parser.add_option('--reporting-db-config',
                          action='store',
                          default=env.get('sneeze_db_config', ''),
                          dest='reporting_db_config',
                          help='SQLAlchemy formated connection string for reporting database.')
        parser.add_option('--test-cycle-name',
                          action='store',
                          dest='test_cycle_name',
                          help='Name of the test cycle being run.')
        parser.add_option('--test-cycle-description',
                          action='store',
                          default='',
                          dest='test_cycle_description',
                          help='Description for the test cycle being run.')
        parser.add_option('--test-cycle-id',
                          action='store',
                          default=0,
                          dest='test_cycle_id',
                          type=int,
                          help=('id of test cycle to run tests under.  '
                                'Overrides --test-cycle-name and --test-cycle-description.'))
        parser.add_option('--rerun-from-case-execution',
                          action='append',
                          dest='case_execution_reruns',
                          type=int,
                          help='Case execution id to base rerun upon.')
        parser.add_option('--pocket-change-host',
                          action='store',
                          default=env.get('pocket_change_host', ''),
                          dest='pocket_change_host',
                          help='url of associated pocket change server.')
        parser.add_option('--pocket-change-username',
                          action='store',
                          default=env.get('pocket_change_username', ''),
                          dest='pocket_change_username',
                          help='username for pocket change user.')
        parser.add_option('--pocket-change-password',
                          action='store',
                          default='',
                          dest='pocket_change_password',
                          help='password for pocket change user.')
        parser.add_option('--pocket-change-token',
                          action='store',
                          default=env.get('pocket_change_token', ''),
                          dest='pocket_change_token',
                          help='token for pocket change user.')
        parser.add_option('--pocket-change-environment-envvar',
                          action='store',
                          default='TEST_ENVIRONMENT',
                          dest='pocket_change_environment_envvar',
                          help='Name of environment variable to record as .')
        for add_options in pkg_resources.iter_entry_points(group='nose.plugins.sneeze.plugins.add_options'):
            add_options.load()(parser, env)
    
    def configure(self, options, noseconfig):
        
        if options.reporting_db_config:
            environment = os.environ.get(options.pocket_change_environment_envvar,
                                         '[no environment found]')
            self.tissue = Tissue(options.reporting_db_config, options.test_cycle_name,
                                 options.test_cycle_description, environment,
                                 socket.gethostbyaddr(socket.gethostname())[0],
                                 ' '.join(sys.argv), test_cycle_id=options.test_cycle_id,
                                 rerun_execution_ids=options.case_execution_reruns)
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
    
    def startTest(self, test):
        
        case_label = '.'.join(test.address()[1:])
        self.tissue.enter_case(case_label, test.address(), test.test.shortDescription())
    
    def formatError(self, test, err):
        
        for manager in self.tissue.plugin_managers:
            if hasattr(manager, 'peek_error'):
                manager.peek_error(test, err)
        return err
    
    def formatFailure(self, test, err):
        
        for manager in self.tissue.plugin_managers:
            if hasattr(manager, 'peek_error'):
                manager.peek_error(test, err)
        return err
    
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