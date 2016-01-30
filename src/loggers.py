# -*- coding: utf-8 -*-

#   Copyright (c) 2010-2015, MIT Probabilistic Computing Project
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from __future__ import print_function

import logging
import matplotlib.pyplot as plt
import re
import sys
import traceback

class BqlLogger(object):
  '''A logger object for BQL.

     The idea of having a custom one is to make it easy to adapt to other
     loggers, like python's builtin one (see LoggingLogger below) or for
     testing, or to set preferences (see DebugLogger, QuietLogger,
     SilentLogger below).

     Loggers should implement functions with the signatures of this base class.
     They are welcome to inherit from it.  Do not depend on return values from
     any of these methods.
  '''
  def info(self, msg_format, *values):
    '''For progress and other informative messages.'''
    if len(values) > 0:
      msg_format = msg_format % values
    print(msg_format)
  def warn(self, msg_format, *values):
    '''For warnings or non-fatal errors.'''
    if len(values) > 0:
      msg_format = msg_format % values
    print(msg_format, file=sys.stderr)
  def plot(self, _suggested_name, figure):
    '''For plotting.

    Name : str
      A filename fragment or window title, not intended to be part of the
      figure, not intended to be a fully qualified path, but of course if
      you know more about the particular logger handling your case, then
      use as you will.
    Figure : a matplotlib object
      on which .show or .savefig might be called.
    '''
    if (hasattr(figure, 'show')):
      figure.show()
    else:
      print(repr(figure))
  def result(self, msg_format, *values):
    '''For formatted text results. In unix, this would be stdout.'''
    if len(values) > 0:
      msg_format = msg_format % values
    print(msg_format)
  def debug(self, _msg_format, *_values):
    '''For debugging information.'''
    pass
  def exception(self, msg_format, *values):
    '''For fatal or fatal-if-uncaught errors.'''
    self.warn('ERROR: ' + msg_format, *values)
    exc_type, exc_value, exc_traceback = sys.exc_info()
    if exc_type:
      lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
      self.warn('\n'.join(lines))
  @classmethod
  def format_escape(str):
    str = re.sub(r"%([^\(])", r"%%\1", str)
    str = re.sub(r"%$", r"%%", str)  # There was a % at the end?
    return str

class DebugLogger(BqlLogger):
  def debug(self, msg_format, *values):
    self.warn('DEBUG: ' + msg_format % values)
    exc_type, exc_value, exc_traceback = sys.exc_info()
    if exc_type:
      lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
      self.warn('\n'.join(lines))

class QuietLogger(BqlLogger):
  def info(self, _msg_format, *_values):
    pass
  def warn(self, _msg_format, *_values):
    pass

class SilentLogger(QuietLogger):
  def plot(self, _suggested_name, _figure):
    pass
  def result(self, _msg, *_values):
    pass
  def debug(self, _msg, *_values):
    pass
  def exception(self, _msg, *_values):
    pass

class LoggingLogger(BqlLogger):
  def info(self, msg_format, *values):
    logging.info(msg_format, *values)
  def warn(self, msg_format, *values):
    logging.warning(msg_format, *values, file=sys.stderr)
  def plot(self, suggested_name, figure):
    figure.savefig(suggested_name + ".png")
  def debug(self, *args, **kwargs):
    logging.debug(*args, **kwargs)
  def exception(self, *args, **kwargs):
    logging.exception(*args, **kwargs)

class CaptureLogger(BqlLogger):
  """Produces no output, but captures call details in .calls"""
  def __init__(self):
    self.calls = []
  def info(self, msg_format, *values):
    self.calls.append(('info', msg_format, values))
  def warn(self, msg_format, *values):
    self.calls.append(('warn', msg_format, values))
  def plot(self, suggested_name, figure):
    self.calls.append(('plot', suggested_name, figure))
  def debug(self, *args, **kwargs):
    self.calls.append(('debug', args, kwargs))
  def exception(self, *args, **kwargs):
    self.calls.append(('exception', args, kwargs, sys.exc_info()))
  def __call__(self, *args, **kwargs):
    self.calls.append(('call', args, kwargs))
  def __getattr__(self, name):
    def _capture(*args, **kwargs):
      self.calls.append((name, args, kwargs))
    return _capture

PROBCOMP_URL = 'https://projects.csail.mit.edu/probcomp/bayesdb/save_sessions.cgi'
import requests
import time
import threading
from version import __version__

class CallHomeStatusLogger(BqlLogger):
    # We will start a small thread for each call home so as to avoid
    # network latency impacting notebook responsiveness.
    def __init__(self, url=PROBCOMP_URL, post=None):
        if post is None:
            post = requests.post
        self._post = post
        self._url = url
    def info(self, json_msg, *unused_values):
        self._send(json_msg)
    def warn(self, json_msg, *unused_values):
        self._send(json_msg)
    def _send(self, json_string):
        data = {'session_json': json_string,
                'User-Agent': 'bdbcontrib %s' % (__version__,)
               }
        t = threading.Thread(target=self._post,
                             args=(self._url,),
                             kwargs={'data': data})
        t.start()
        # I don't care if it finishes. We tried.

import json
def query_info_to_json(session_id, logtype, query, bindings,
                       start_time, error, end_time):
  session = {'entries': [[session_id, logtype, query + json.dumps(bindings),
                          start_time, error, end_time]],
             'fields': ['session_id', 'type', 'data',
                        'start_time', 'error', 'end_time'],
             'version': __version__,
  }
  return json.dumps(session)

import traceback
from contextlib import contextmanager
@contextmanager
def logged_query(query_string=None, bindings=(), name=None, logger=None):
  if query_string is None:
    query_string = ""
  if logger is None:
    logger = CallHomeStatusLogger()

  if name is None:
    yield  # Do no logging without a name to log by.
  else:
    start_time = time.time()
    try:
      yield
      logger.info(query_info_to_json(
          name, 'logged_query', query_string, bindings,
          start_time, None, time.time()))
    except:
      logger.warn(query_info_to_json(
          name, 'logged_query', query_string, bindings,
          start_time, traceback.format_exc(), time.time()))
      raise
