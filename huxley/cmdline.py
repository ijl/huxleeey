# Copyright (c) 2013 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Command-line interface to the app.
"""

import ConfigParser
import glob
import json
import os
import sys

import plac
from selenium import webdriver

from huxley.consts import modes, exits, \
    REMOTE_WEBDRIVER_URL, DEFAULT_WEBDRIVER
from huxley import util
from huxley.main import dispatch
from huxley.version import __version__
from huxley import errors


class TestRun(object): # check this name...
    """
    Object to be passed into dispatch... containing all information 
    run a test, minus mode, since it's effectively global.
    """

    def __init__(self, settings, recorded_run=None):
        self.settings = settings
        self.recorded_run = recorded_run

    def __repr__(self):
        return "%s: %r, %r" % (
            self.__class__.__name__, 
            self.settings, 
            self.recorded_run
        )


class Settings(object): # pylint: disable=R0903,R0902
    """
    Hold validated settings for a specific test run.
    """

    def __init__(self, 
            name, url, mode, path,
            sleepfactor, screensize, postdata,
            diffcolor, save_diff
        ): # pylint: disable=R0913
        self.name = name
        self.url = url
        self.mode = mode
        self.path = path
        self.sleepfactor = sleepfactor
        self.screensize = screensize
        self.postdata = postdata
        self.diffcolor = diffcolor
        self.save_diff = save_diff

    def navigate(self):
        """
        Return data in form expected by :func:`huxley.run.navigate`.
        """
        return (self.url, self.postdata)

    def __repr__(self):
        return '%s: %r' % (self.__class__.__name__, self.__dict__)

DRIVERS = {
    'firefox': webdriver.Firefox,
    'chrome': webdriver.Chrome,
    'ie': webdriver.Ie,
    'opera': webdriver.Opera
}

CAPABILITIES = {
    'firefox': webdriver.DesiredCapabilities.FIREFOX,
    'chrome': webdriver.DesiredCapabilities.CHROME,
    'ie': webdriver.DesiredCapabilities.INTERNETEXPLORER,
    'opera': webdriver.DesiredCapabilities.OPERA
}



DEFAULT_SLEEPFACTOR = 1.0
DEFAULT_SCREENSIZE = '1024x768'
DEFAULT_BROWSER = 'firefox'
DEFAULT_DIFFCOLOR = '0,255,0'


DEFAULTS = {
    'screensize': DEFAULT_SCREENSIZE,
    # etc.
}

def _postdata(arg):
    """
    Given CLI input `arg`, resolve postdata.
    """
    if arg:
        if arg == '-':
            return sys.stdin.read()
        else:
            with open(arg, 'r') as f:
                data = json.loads(f.read())
            return data
    return None

@plac.annotations(
    names = plac.Annotation(
        'Test case name(s) to use, comma-separated',
    ),
    postdata = plac.Annotation(
        'File for POST data or - for stdin'
    ),

    testfile = plac.Annotation(
        'Test file(s) to use',
        'option', 'f', str,
        metavar='GLOB'
    ),
    record = plac.Annotation(
        'Record a new test',
        'flag', 'r'
    ),
    rerecord = plac.Annotation(
        'Re-run the test but take new screenshots',
        'flag', 'rr' 
    ),
    # playback_only = plac.Annotation(
    #     'Don\'t write new screenshots',
    #     'flag', 'p'
    # ),

    local = plac.Annotation(
        'Local WebDriver URL to use',
        'option', 'l',
        metavar=DEFAULT_WEBDRIVER
    ),
    remote = plac.Annotation(
        'Remote WebDriver to use',
        'option', 'w',
        metavar=DEFAULT_WEBDRIVER
    ),

    sleepfactor = plac.Annotation(
        'Sleep interval multiplier',
        'option', 's', float,
        metavar=DEFAULT_SLEEPFACTOR
    ),

    browser = plac.Annotation(
        'Browser to use, either firefox, chrome, phantomjs, ie, or opera',
        'option', 'b', str,
        metavar=DEFAULT_BROWSER,
    ),
    screensize = plac.Annotation(
        'Width and height for screen (i.e. 1024x768)',
        'option', 'z',
        metavar=DEFAULT_SCREENSIZE
    ),
    diffcolor = plac.Annotation(
        'Diff color for errors in RGB (i.e. 0,255,0)',
        'option', 'd', str,
        metavar=DEFAULT_DIFFCOLOR
    ),

    save_diff = plac.Annotation(
        'Save information about failures as last.png and diff.png',
        'flag', 'e'
    ),

    # autorerecord = plac.Annotation(
    #     'Playback test and automatically rerecord if it fails',
    #     'flag', 'a' # todo
    # ),

    version = plac.Annotation(
        'Get the current version',
        'flag', 'version'
    )

    # todo: verbose?
)


def initialize(
        names=None,
        testfile='Huxleyfile',
        record=False,
        rerecord=False,
        local=None,
        remote=None,
        postdata=None,
        sleepfactor=None,
        browser=None,
        screensize=None,
        diffcolor=None,
        save_diff=False,
        version=False
    ): # pylint: disable=R0913
        # autorerecord=False,
        # playback_only=False,
    """
    Given arguments from the `plac` argument parser, this must:
        1. construct a settings object
        2. create new directories, or handle overwriting existing data
        3. hand off settings to the dispatcher
    """

    if version:
        print 'Huxley ' + __version__
        return exits.OK

    cwd = os.getcwd()

    names = names.split(',') if names else None

    test_files = []
    for pattern in testfile.split(','):
        for name in glob.glob(pattern):
            test_files.append(os.path.join(cwd, name))
    if len(test_files) == 0:
        print 'No Huxleyfile found'
        return exits.ERROR

    # mode
    if record and rerecord:
        print 'Cannot specify both -r and -rr'
        return exits.ARGUMENT_ERROR
    if record:
        mode = modes.RECORD
    elif rerecord:
        mode = modes.RERECORD
    else:
        mode = modes.PLAYBACK

    # driver
    try:
        if local and not remote:
            driver_url = local
        else:
            driver_url = remote or REMOTE_WEBDRIVER_URL
        try:
            driver = webdriver.Remote(driver_url, CAPABILITIES[(browser or DEFAULT_BROWSER)])
            screensize = tuple(int(x) for x in (screensize or DEFAULT_SCREENSIZE).split('x'))
        except KeyError:
            print 'Invalid browser %r; valid browsers are %r.' % (browser, DRIVERS.keys())
            return exits.ARGUMENT_ERROR

        # others
        postdata = _postdata(postdata)
        diffcolor = tuple(int(x) for x in (diffcolor or DEFAULT_DIFFCOLOR).split(','))

        tests = {}

        for file_name in test_files:

            config = ConfigParser.SafeConfigParser(
                defaults=DEFAULTS,
                allow_no_value=True
            )
            config.read([file_name])

            for testname in config.sections():

                if names and (testname not in names):
                    continue
                if testname in tests:
                    print 'Duplicate test name %s' % testname
                    return exits.ERROR

                test_config = dict(config.items(testname))
                url = config.get(testname, 'url')

                default_filename = os.path.join(
                    os.path.dirname(file_name),
                    testname + '.huxley'
                )
                filename = test_config.get(
                    'filename',
                    default_filename
                )
                if not os.path.isabs(filename):
                    filename = os.path.join(cwd, filename)

                if os.path.exists(filename):
                    if mode == modes.RECORD: # todo weirdness with rerecord
                        if os.path.getsize(filename) > 0:
                            if not util.prompt(
                                '%s already exists--clear existing '
                                'screenshots and overwrite test? [Y/n] ' \
                                    % testname, 
                                ('Y', 'y')
                                ):
                                return exits.ERROR
                            for each in os.listdir(filename):
                                if each.split('.')[-1] in ('png', 'json'):
                                    os.remove(os.path.join(filename, each))
                else:
                    if mode == modes.RECORD:
                        try:
                            os.makedirs(filename)
                        except Exception as exc:
                            print str(exc)
                            raise
                    else:
                        print '%s does not exist' % filename
                        return exits.ERROR

                # load recorded runs if appropriate
                if mode != modes.RECORD:
                    try:
                        recorded_run = util.read_recorded_run(filename)
                    except errors.RecorcedRunEmpty:
                        print 'Recorded run for %s is empty--please rerecord' % \
                            (testname, )
                        return exits.RECORDED_RUN_ERROR
                    except errors.RecordedRunDoesNotExist:
                        print 'Recorded run for %s does not exist' % \
                            (testname, )
                        return exits.RECORDED_RUN_ERROR
                else:
                    recorded_run = None

                sleepfactor = sleepfactor or float(test_config.get(
                    'sleepfactor',
                    1.0
                ))
                screensize = screensize or test_config.get(
                    'screensize',
                    '1024x768'
                )

                settings = Settings(
                    name=testname,
                    url=url,
                    mode=mode,
                    path=filename,
                    sleepfactor=sleepfactor,
                    screensize=screensize,
                    postdata=postdata or test_config.get('postdata'),
                    diffcolor=diffcolor,
                    save_diff=save_diff
                )

                tests[testname] = TestRun(settings, recorded_run)
                # print tests[testname]

        # run the tests
        try:
            logs = dispatch(driver, mode, tests)
        except Exception as exc: # pylint: disable=W0703
            print str(exc)
            return exits.ERROR
        return exits.OK
    finally:
        try:
            driver.quit()
        except UnboundLocalError:
            pass

def main():
    """
    Defined as the `huxley` command in setup.py.

    Runs the argument parser and passes settings to 
    :func:`huxley.main.dispatcher`.
    """
    sys.exit(plac.call(initialize))
