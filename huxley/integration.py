"""
Integrate with unittest.
"""

# Copyright (c) 2013 contributors; see AUTHORS.
# Licensed under the Apache License, Version 2.0
# https://www.apache.org/licenses/LICENSE-2.0

import unittest

from huxley.main import dispatch
from huxley.constant import modes, states, LOCAL_WEBDRIVER_URL, REMOTE_WEBDRIVER_URL, \
    DEFAULT_BROWSER
from huxley import util, exc


def run_huxleyfile(huxleyfile, data_dir, browser=None, local=None, remote=None):
    """
    Call this to read a Huxleyfile and run all of its tests.
    """
    case = HuxleyTestCase

    browser = browser or DEFAULT_BROWSER
    local = local or LOCAL_WEBDRIVER_URL
    remote = remote or REMOTE_WEBDRIVER_URL

    options = {'browser': browser, 'local': local, 'remote': remote}

    tests = util.make_tests([huxleyfile], modes.PLAYBACK, data_dir, **options)
    for key, test in tests.items():
        case.tests.append(run_nose(case, key, test, test.settings.browser, local, remote))
    return case


def run_nose(self, name, test, browser, local, remote): # pylint: disable=R0913
    """
    Run a test for Nose.
    """
    try:
        driver = util.get_driver(browser, local, remote)
        result = dispatch(driver, modes.PLAYBACK, {name: test, })[name]
        if result == states.FAIL:
            self.fail()
        elif result == states.ERROR:
            raise exc.TestError() # todo
    finally:
        driver.quit()


class HuxleyTestCase(unittest.TestCase): # pylint: disable=R0904
    """
    unittest case.
    """
    tests = []
