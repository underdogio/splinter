# -*- coding: utf-8 -*-

# Copyright 2014 splinter authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

from __future__ import with_statement

from flask.testing import FlaskClient, make_test_environ_builder
from splinter.cookie_manager import CookieManagerAPI
from splinter.request_handler.status_code import StatusCode
from werkzeug.test import ClientRedirectError, EnvironBuilder

from .lxmldriver import LxmlDriver


class SplinterFlaskClient(FlaskClient):
    """FlaskClient with redirect support"""

    def open(self, *args, **kwargs):
        # https://github.com/mitsuhiko/flask/blob/0.10.1/flask/testing.py#L96-L108
        kwargs.setdefault('environ_overrides', {}) \
            ['flask._preserve_context'] = self.preserve_context

        as_tuple = kwargs.pop('as_tuple', False)
        buffered = kwargs.pop('buffered', False)
        follow_redirects = kwargs.pop('follow_redirects', False)
        builder = make_test_environ_builder(self.application, *args, **kwargs)
        args = [builder]
        kwargs = dict(
            as_tuple=as_tuple,
            buffered=buffered,
            follow_redirects=follow_redirects,
        )

        # https://github.com/mitsuhiko/werkzeug/blob/0.10.4/werkzeug/test.py#L701-L769
        as_tuple = kwargs.pop('as_tuple', False)
        buffered = kwargs.pop('buffered', False)
        follow_redirects = kwargs.pop('follow_redirects', False)
        environ = None
        if not kwargs and len(args) == 1:
            if isinstance(args[0], EnvironBuilder):
                environ = args[0].get_environ()
            elif isinstance(args[0], dict):
                environ = args[0]
        if environ is None:
            builder = EnvironBuilder(*args, **kwargs)
            try:
                environ = builder.get_environ()
            finally:
                builder.close()

        response = self.run_wsgi_app(environ, buffered=buffered)

        # handle redirects
        redirect_chain = []
        while 1:
            status_code = int(response[1].split(None, 1)[0])
            if status_code not in (301, 302, 303, 305, 307) \
               or not follow_redirects:
                break
            new_location = response[2]['location']

            method = 'GET'
            if status_code == 307:
                method = environ['REQUEST_METHOD']

            new_redirect_entry = (new_location, status_code)
            if new_redirect_entry in redirect_chain:
                raise ClientRedirectError('loop detected')
            redirect_chain.append(new_redirect_entry)
            environ, response, _ = self.resolve_redirect(response, new_location,
                                                      environ,
                                                      buffered=buffered)

        if self.response_wrapper is not None:
            response = self.response_wrapper(*response)
        # Modified code here
        if as_tuple:
            return environ, response, redirect_chain
        return response


class CookieManager(CookieManagerAPI):

    def __init__(self, browser_cookies):
        self._cookies = browser_cookies

    def add(self, cookies):
        if isinstance(cookies, list):
            for cookie in cookies:
                for key, value in cookie.items():
                    self._cookies.set_cookie('localhost', key, value)
                return
        for key, value in cookies.items():
            self._cookies.set_cookie('localhost', key, value)

    def delete(self, *cookies):
        if cookies:
            for cookie in cookies:
                try:
                    self._cookies.delete_cookie('localhost', cookie)
                except KeyError:
                    pass
        else:
            self._cookies.cookie_jar.clear()

    def all(self, verbose=False):
        cookies = {}
        for cookie in self._cookies.cookie_jar:
            cookies[cookie.name] = cookie.value
        return cookies

    def __getitem__(self, item):
        cookies = dict([(c.name, c) for c in self._cookies.cookie_jar])
        return cookies[item].value

    def __eq__(self, other_object):
        if isinstance(other_object, dict):
            cookies_dict = dict([(c.name, c.value)
                                 for c in self._cookies.cookie_jar])
            return cookies_dict == other_object


class FlaskClient(LxmlDriver):

    driver_name = "flask"

    def __init__(self, app, user_agent=None, wait_time=2):
        app.config['TESTING'] = True
        # https://github.com/mitsuhiko/flask/blob/0.10.1/flask/app.py#L812-L815
        self._browser = SplinterFlaskClient(app, app.response_class, use_cookies=True)
        self._cookie_manager = CookieManager(self._browser)
        super(FlaskClient, self).__init__(wait_time=wait_time)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def _handle_redirect_chain(self):
        if self._redirect_chain:
            for redirect_url, redirect_code in self._redirect_chain:
                self._last_urls.append(redirect_url)
            self._url = self._last_urls[-1]

    def _post_load(self):
        self._forms = {}
        try:
            del self._html
        except AttributeError:
            pass
        self.status_code = StatusCode(self._response.status_code, '')

    def _do_method(self, method, url, data=None):
        self._url = url
        func_method = getattr(self._browser, method.lower())
        _, self._response, self._redirect_chain = func_method(url, as_tuple=True, data=data, follow_redirects=True)
        self._handle_redirect_chain()
        self._last_urls.append(url)
        self._post_load()

    def submit_data(self, form):
        return super(FlaskClient, self).submit(form).data

    @property
    def html(self):
        return self._response.get_data(as_text=True)
