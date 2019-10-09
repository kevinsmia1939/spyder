# -*- coding: utf-8 -*-

# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""Kite completion HTTP client."""

# Standard library imports
import logging
import functools

# Qt imports
from qtpy.QtCore import Slot

# Local imports
from spyder.config.base import running_under_pytest
from spyder.config.manager import CONF
from spyder.utils.programs import run_program
from spyder.api.completion import SpyderCompletionPlugin
from spyder.plugins.completion.kite.client import KiteClient
from spyder.plugins.completion.kite.utils.status import (
    check_if_kite_running, check_if_kite_installed)
from spyder.plugins.completion.kite.utils.install import (
    KiteInstallationThread, FINISHED)
from spyder.plugins.completion.kite.widgets.install import KiteInstallerDialog


logger = logging.getLogger(__name__)


class KiteCompletionPlugin(SpyderCompletionPlugin):
    CONF_SECTION = 'kite'
    CONF_FILE = False

    COMPLETION_CLIENT_NAME = 'kite'

    def __init__(self, parent):
        SpyderCompletionPlugin.__init__(self, parent)
        self.available_languages = []
        self.client = KiteClient(None)
        self.kite_process = None
        self.kite_installation_thread = KiteInstallationThread(self)
        # TODO: Connect thread status to status bar
        self.kite_installer = KiteInstallerDialog(
            parent,
            self.kite_installation_thread)
        self.client.sig_client_started.connect(self.http_client_ready)
        self.client.sig_response_ready.connect(
            functools.partial(self.sig_response_ready.emit,
                              self.COMPLETION_CLIENT_NAME))
        self.kite_installation_thread.sig_installation_status.connect(
            lambda status: self.client.start() if status == FINISHED else None)
        self.main.sig_setup_finished.connect(self.mainwindow_setup_finished)
        self.update_configuration()

    @Slot(list)
    def http_client_ready(self, languages):
        logger.debug('Kite client is available for {0}'.format(languages))
        self.available_languages = languages
        self.sig_plugin_ready.emit(self.COMPLETION_CLIENT_NAME)
        self._kite_onboarding()

    @Slot()
    def mainwindow_setup_finished(self):
        """
        Called when the setup of the main window finished
        to let us do onboarding if necessary
        """
        self._show_installation_dialog()
        self._kite_onboarding()

    def _show_installation_dialog(self):
        """Show installation dialog."""
        kite_installation_enabled = self.get_option('show_installation_dialog')
        installed, path = check_if_kite_installed()
        if (not installed and kite_installation_enabled
                and not running_under_pytest()):
            self.kite_installer.show()
            self.kite_installer.center()

    def send_request(self, language, req_type, req, req_id):
        if self.enabled and language in self.available_languages:
            self.client.sig_perform_request.emit(req_id, req_type, req)
        else:
            self.sig_response_ready.emit(self.COMPLETION_CLIENT_NAME,
                                         req_id, {})

    def start_client(self, language):
        return language in self.available_languages

    def start(self):
        try:
            if not self.enabled:
                return
            installed, path = check_if_kite_installed()
            if not installed:
                return
            logger.debug('Kite was found on the system: {0}'.format(path))
            running = check_if_kite_running()
            if running:
                return
            logger.debug('Starting Kite service...')
            self.kite_process = run_program(path)
        finally:
            # Always start client to support possibly undetected Kite builds
            self.client.start()

    def shutdown(self):
        self.client.stop()
        if self.kite_process is not None:
            self.kite_process.kill()

    def update_configuration(self):
        self.client.enable_code_snippets = CONF.get('lsp-server',
                                                    'code_snippets')
        self.enabled = self.get_option('enable')

    def _kite_onboarding(self):
        """
        Opens the onboarding file, which is retrieved
        from the Kite HTTP endpoint. This skips onboarding if onboarding
        is not possible yet or has already been displayed before.
        :return:
        """
        if not self.enabled:
            return
        if not self.get_option('kite_show_onboarding'):
            return
        if self.main.is_setting_up:
            return
        if not self.available_languages:
            return
        if not self.kite_process:
            installed, _ = check_if_kite_installed()
            if not installed:
                return

        onboarding_file = self.client.get_onboarding_file()
        if onboarding_file is None:
            # fixme: show onboarding notification
            pass
        else:
            self.set_option('kite_show_onboarding', False)
            self.main.open_file(onboarding_file)

    def is_installing(self):
        """Check if an installation is taking place."""
        return self.kite_installation_thread.isRunning()
