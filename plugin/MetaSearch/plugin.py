# -*- coding: utf-8 -*-
###############################################################################
#
# Copyright (C) 2010 NextGIS (http://nextgis.org),
#                    Alexander Bruy (alexander.bruy@gmail.com),
#                    Maxim Dubinin (sim@gis-lab.info),
#                    Tom Kralidis (tomkralidis@gmail.com)
#
# This source is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# This code is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# A copy of the GNU General Public License is available on the World Wide Web
# at <http://www.gnu.org/copyleft/gpl.html>. You can also obtain it by writing
# to the Free Software Foundation, Inc., 59 Temple Place - Suite 330, Boston,
# MA 02111-1307, USA.
#
###############################################################################

import logging
import os
import webbrowser

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from MetaSearch.cswclientdialog import CSWClientDialog
from MetaSearch.config import StaticContext
from MetaSearch.util import translate

LOGGER = logging.getLogger('MetaSearch')


class MetaSearchPlugin(object):
    """base plugin"""
    def __init__(self, iface):
        """init"""
        self.iface = iface
        self.context = StaticContext()
        self.action_run = None
        self.action_help = None
	self.web_menu = '&MetaSearch'

        LOGGER.debug('Setting up i18n')

        locale_name = str(QLocale.system().name()).split('_')[0]

        LOGGER.debug('Locale name: %s', locale_name)

        # load if exists
        tr_filename = 'MetaSearch_%s.qm' % locale_name
        tr_file = os.path.join(self.context.ppath, 'i18n', tr_filename)

        if os.path.exists(tr_file):
            self.translator = QTranslator()
            result = self.translator.load(tr_file)
            if not result:
                msg = 'Failed to load translation: %s' % tr_file
                LOGGER.error(msg)
                raise RuntimeError(msg)
            QCoreApplication.installTranslator(self.translator)

        LOGGER.debug(translate('Translation loaded: %s' % tr_file))

    def initGui(self):
        """startup"""

        # run
        run_icon = QIcon('%s/%s' % (self.context.ppath,
                                    'images/MetaSearch.png'))
        self.action_run = QAction(run_icon, 'MetaSearch',
                                  self.iface.mainWindow())
        self.action_run.setWhatsThis(translate('MetaSearch plugin'))
        self.action_run.setStatusTip(translate('Search Metadata Catalogues'))
        QObject.connect(self.action_run, SIGNAL('triggered()'), self.run)

        self.iface.addToolBarIcon(self.action_run)
        self.iface.addPluginToWebMenu(self.web_menu, self.action_run)

        # help
        help_icon = QIcon('%s/%s' % (self.context.ppath, 'images/help.png'))
        self.action_help = QAction(help_icon, 'Help', self.iface.mainWindow())
        self.action_help.setWhatsThis(translate('MetaSearch plugin help'))
        self.action_help.setStatusTip(translate('Get Help on MetaSearch'))
        QObject.connect(self.action_help, SIGNAL('triggered()'), self.help)

        self.iface.addPluginToWebMenu(self.web_menu, self.action_help)

    def unload(self):
        """teardown"""
        # remove the plugin menu item and icon
        self.iface.removePluginWebMenu(self.web_menu, self.action_run)
        self.iface.removeToolBarIcon(self.action_run)
        self.iface.removeToolBarIcon(self.action_help)

    def run(self):
        """open MetaSearch"""
	CSWClientDialog(self.iface)

    def help(self):
        """open help in user's default web browser"""
        webbrowser.open(self.context.metadata.get('general', 'homepage'))
