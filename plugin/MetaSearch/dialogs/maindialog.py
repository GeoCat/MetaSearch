# -*- coding: utf-8 -*-
###############################################################################
#
# CSW Client
# ---------------------------------------------------------
# QGIS Catalogue Service client.
#
# Copyright (C) 2010 NextGIS (http://nextgis.org),
#                    Alexander Bruy (alexander.bruy@gmail.com),
#                    Maxim Dubinin (sim@gis-lab.info)
#
# Copyright (C) 2014 Tom Kralidis (tomkralidis@gmail.com)
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

import os.path

from PyQt4.QtCore import QSettings, Qt
from PyQt4.QtGui import (QApplication, QColor, QCursor, QDialog, QInputDialog,
                         QMessageBox, QTreeWidgetItem, QWidget)

from qgis.core import (QgsApplication, QgsGeometry, QgsPoint,
                       QgsProviderRegistry)
from qgis.gui import QgsRubberBand

from owslib.csw import CatalogueServiceWeb as csw
from owslib.fes import BBox, PropertyIsLike
from owslib.ows import ExceptionReport
from owslib.wcs import WebCoverageService
from owslib.wfs import WebFeatureService
from owslib.wms import WebMapService

from MetaSearch.dialogs.manageconnectionsdialog import ManageConnectionsDialog
from MetaSearch.dialogs.newconnectiondialog import NewConnectionDialog
from MetaSearch.dialogs.responsedialog import ResponseDialog
from MetaSearch.util import (get_connections_from_file, highlight_xml,
                             render_template, StaticContext)
from MetaSearch.ui.maindialog import Ui_MetaSearchDialog


class MetaSearchDialog(QDialog, Ui_MetaSearchDialog):
    """main dialogue"""
    def __init__(self, iface):
        """init window"""

        QDialog.__init__(self)
        self.setupUi(self)

        self.iface = iface
        self.map = iface.mapCanvas()
        self.settings = QSettings()
        self.catalog = None
        self.catalog_url = None
        self.context = StaticContext()

        self.rubber_band = QgsRubberBand(self.map, True)  # True = a polygon
        self.rubber_band.setColor(QColor(255, 0, 0, 75))
        self.rubber_band.setWidth(5)

        # form inputs
        self.startfrom = 0
        self.maxrecords = 10
        self.constraints = []

        # Servers tab
        self.cmbConnections.activated.connect(self.save_connection)
        self.btnServerInfo.clicked.connect(self.connection_info)
        self.btnAddDefault.clicked.connect(self.add_default_connections)
        self.btnCapabilities.clicked.connect(self.show_response)

        # server management buttons
        self.btnNew.clicked.connect(self.add_connection)
        self.btnEdit.clicked.connect(self.edit_connection)
        self.btnDelete.clicked.connect(self.delete_connection)
        self.btnLoad.clicked.connect(self.load_connections)
        self.btnSave.clicked.connect(save_connections)

        # Search tab
        self.treeRecords.itemSelectionChanged.connect(self.record_clicked)
        self.treeRecords.itemDoubleClicked.connect(self.show_metadata)
        self.btnSearch.clicked.connect(self.search)
        self.leKeywords.returnPressed.connect(self.search)
        self.btnCanvasBbox.clicked.connect(self.set_bbox_from_map)
        self.btnGlobalBbox.clicked.connect(self.set_bbox_global)

        # navigation buttons
        self.btnFirst.clicked.connect(self.navigate)
        self.btnPrev.clicked.connect(self.navigate)
        self.btnNext.clicked.connect(self.navigate)
        self.btnLast.clicked.connect(self.navigate)

        self.btnAddToWms.clicked.connect(self.add_to_ows)
        self.btnAddToWfs.clicked.connect(self.add_to_ows)
        self.btnAddToWcs.clicked.connect(self.add_to_ows)
        self.btnShowXml.clicked.connect(self.show_response)

        self.manageGui()

    def manageGui(self):
        """open window"""

        self.tabWidget.setCurrentIndex(0)
        self.populate_connection_list()
        self.btnCapabilities.setEnabled(False)
        self.spnRecords.setValue(
            self.settings.value('/CSWClient/returnRecords', 10, int))

        key = '/CSWClient/%s' % self.cmbConnections.currentText()
        self.catalog_url = self.settings.value('%s/url' % key)

        self.set_bbox_global()

        self.reset_buttons()

    # Servers tab

    def populate_connection_list(self):
        """populate select box with connections"""

        self.settings.beginGroup('/CSWClient/')
        self.cmbConnections.clear()
        self.cmbConnections.addItems(self.settings.childGroups())
        self.settings.endGroup()

        self.set_connection_list_position()

        if self.cmbConnections.count() == 0:
            # no connections - disable various buttons
            state_disabled = False
            self.btnSave.setEnabled(state_disabled)
        else:
            # connections - enable various buttons
            state_disabled = True

        self.btnServerInfo.setEnabled(state_disabled)
        self.btnEdit.setEnabled(state_disabled)
        self.btnDelete.setEnabled(state_disabled)
        self.tabWidget.setTabEnabled(1, state_disabled)

    def set_connection_list_position(self):
        """set the current index to the selected connection"""
        to_select = self.settings.value('/CSWClient/selected')
        conn_count = self.cmbConnections.count()

        # does to_select exist in cmbConnections?
        exists = False
        for i in range(conn_count):
            if self.cmbConnections.itemText(i) == to_select:
                self.cmbConnections.setCurrentIndex(i)
                exists = True
                break

        # If we couldn't find the stored item, but there are some, default
        # to the last item (this makes some sense when deleting items as it
        # allows the user to repeatidly click on delete to remove a whole
        # lot of items)
        if not exists and conn_count > 0:
            # If to_select is null, then the selected connection wasn't found
            # by QSettings, which probably means that this is the first time
            # the user has used CSWClient, so default to the first in the list
            # of connetions. Otherwise default to the last.
            if not to_select:
                current_index = 0
            else:
                current_index = conn_count - 1

            self.cmbConnections.setCurrentIndex(current_index)

    def save_connection(self):
        """save connection"""

        current_text = self.cmbConnections.currentText()

        self.settings.setValue('/CSWClient/selected', current_text)
        key = '/CSWClient/%s' % current_text
        self.catalog_url = self.settings.value('%s/url' % key)

        # clear server metadata
        self.textMetadata.clear()

    def connection_info(self):
        """show connection info"""

        current_text = self.cmbConnections.currentText()
        key = '/CSWClient/%s' % current_text
        self.catalog_url = self.settings.value('%s/url' % key)

        # connect to the server
        try:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            self.catalog = csw(self.catalog_url)
            QApplication.restoreOverrideCursor()
        except ExceptionReport, err:
            QApplication.restoreOverrideCursor()
            msg = self.tr('Error connecting to service %s: %s' %
                          current_text, err)
            QMessageBox.warning(self, self.tr('Connection error'), msg)
            return

        if self.catalog:  # display service metadata
            self.btnCapabilities.setEnabled(True)
            metadata = render_template('en', self.context,
                                       self.catalog,
                                       'service_metadata.html')
            style = QgsApplication.reportStyleSheet()
            self.textMetadata.clear()
            self.textMetadata.document().setDefaultStyleSheet(style)
            self.textMetadata.setHtml(metadata)

    def add_connection(self):
        """add new service"""

        conn_new = NewConnectionDialog()
        conn_new.setWindowTitle(self.tr('New Catalogue service'))
        if conn_new.exec_() == QDialog.Accepted:  # add to service list
            self.populate_connection_list()

    def edit_connection(self):
        """modify existing connection"""

        current_text = self.cmbConnections.currentText()

        url = self.settings.value('/CSWClient/%s/url' % current_text)

        conn_edit = NewConnectionDialog(current_text)
        conn_edit.setWindowTitle(self.tr('Edit Catalogue service'))
        conn_edit.leName.setText(current_text)
        conn_edit.leURL.setText(url)
        if conn_edit.exec_() == QDialog.Accepted:  # update service list
            self.populate_connection_list()

    def delete_connection(self):
        """delete connection"""

        current_text = self.cmbConnections.currentText()

        key = '/CSWClient/%s' % current_text

        msg = self.tr('Remove service %s?' % current_text)

        result = QMessageBox.information(self, self.tr('Confirm delete'), msg,
                                         QMessageBox.Ok | QMessageBox.Cancel)
        if result == QMessageBox.Ok:  # remove service from list
            self.settings.remove(key)
            self.cmbConnections.removeItem(self.cmbConnections.currentIndex())
            self.set_connection_list_position()

    def load_connections(self):
        """load services from list"""

        ManageConnectionsDialog(1).exec_()
        self.populate_connection_list()

    def add_default_connections(self):
        """add default connections"""

        filename = os.path.join(self.context.ppath,
                                'resources', 'connections-default.xml')
        doc = get_connections_from_file(self, filename)
        if doc is None:
            return

        self.settings.beginGroup('/CSWClient/')
        keys = self.settings.childGroups()
        self.settings.endGroup()

        for server in doc.findall('csw'):
            name = server.attrib.get('name')
            # check for duplicates
            if name in keys:
                msg = self.tr('%s exists.  Overwrite?' % name)
                res = QMessageBox.warning(self,
                                          self.tr('Loading connections'), msg,
                                          QMessageBox.Yes | QMessageBox.No)
                if res != QMessageBox.Yes:
                    continue

            # no dups detected or overwrite is allowed
            key = '/CSWClient/%s' % name
            self.settings.setValue('%s/url' % key, server.attrib.get('url'))

        self.populate_connection_list()
        QMessageBox.information(self, self.tr('Catalogue services'),
                                self.tr('Default connections added'))

    # Search tab

    def set_bbox_from_map(self):
        """set bounding box from map extent"""

        extent = self.map.extent()
        self.leNorth.setText(str(extent.yMaximum()))
        self.leSouth.setText(str(extent.yMinimum()))
        self.leWest.setText(str(extent.xMinimum()))
        self.leEast.setText(str(extent.xMaximum()))

    def set_bbox_global(self):
        """set global bounding box"""
        self.leNorth.setText('90')
        self.leSouth.setText('-90')
        self.leWest.setText('-180')
        self.leEast.setText('180')

    def search(self):
        """execute search"""

        self.catalog = None
        self.constraints = []

        # clear all fields and disable buttons
        self.lblResults.clear()
        self.treeRecords.clear()
        self.textAbstract.clear()

        self.reset_buttons()

        # save some settings
        self.settings.setValue('/CSWClient/returnRecords',
                               self.spnRecords.cleanText())

        # start position and number of records to return
        self.startfrom = 0
        self.maxrecords = self.spnRecords.value()

        # bbox
        minx = self.leWest.text()
        miny = self.leSouth.text()
        maxx = self.leEast.text()
        maxy = self.leNorth.text()
        bbox = [minx, miny, maxx, maxy]

        # only apply spatial filter if bbox is not global
        # even for a global bbox, if a spatial filter is applied, then
        # the CSW server will skip records without a bbox
        if bbox != ['-180', '-90', '180', '90']:
            self.constraints.append(BBox(bbox))

        # keywords
        if self.leKeywords.text():
            # TODO: handle multiple word searches
            keywords = self.leKeywords.text()
            self.constraints.append(PropertyIsLike('csw:AnyText', keywords))

        if len(self.constraints) > 1:  # exclusive search (a && b)
            self.constraints = [self.constraints]

        # build request
        try:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            self.catalog = csw(self.catalog_url)
        except ExceptionReport, err:
            QApplication.restoreOverrideCursor()
            msg = self.tr('Error connecting to service %s: %s' %
                          self.catalog_url, err)
            QMessageBox.warning(self, self.tr('Search error'), msg)
            return

        # TODO: allow users to select resources types
        # to find ('service', 'dataset', etc.)
        try:
            self.catalog.getrecords2(constraints=self.constraints,
                                     maxrecords=self.maxrecords, esn='full')
        except ExceptionReport, err:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, self.tr('Search error'),
                                self.tr('Search error: %s' % err))
            return
        except Exception, err:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, self.tr('Connection error'),
                                self.tr('Connection error: %s' % err))
            return

        QApplication.restoreOverrideCursor()

        if not self.catalog.results:
            QMessageBox.information(self, self.tr('Search'),
                                    self.tr('No results.'))
            return

        if self.catalog.results['matches'] == 0:
            QMessageBox.information(self, self.tr('Search'),
                                    self.tr('0 search results'))
            self.lblResults.setText(self.tr('0 results'))
            return

        self.display_results()

    def display_results(self):
        """display search results"""

        self.treeRecords.clear()

        position = self.catalog.results['returned'] + self.startfrom

        msg = self.tr('Showing %d - %d of %d results' %
                     (self.startfrom + 1, position,
                      self.catalog.results['matches']))

        self.lblResults.setText(msg)

        for rec in self.catalog.records:
            item = QTreeWidgetItem(self.treeRecords)
            if self.catalog.records[rec].type:
                item.setText(0, self.catalog.records[rec].type)
            else:
                item.setText(0, 'unknown')
            if self.catalog.records[rec].title:
                item.setText(1, self.catalog.records[rec].title)
            if self.catalog.records[rec].identifier:
                set_item_data(item, 'identifier',
                              self.catalog.records[rec].identifier)

        self.btnShowXml.setEnabled(True)

        if self.catalog.results["matches"] < self.maxrecords:
            disabled = False
        else:
            disabled = True

        self.btnFirst.setEnabled(disabled)
        self.btnPrev.setEnabled(disabled)
        self.btnNext.setEnabled(disabled)
        self.btnLast.setEnabled(disabled)

    def record_clicked(self):
        """record clicked signal"""

        # disable only service buttons
        self.reset_buttons(True, False, False)

        if not self.treeRecords.selectedItems():
            return

        item = self.treeRecords.currentItem()
        if not item:
            return

        identifier = get_item_data(item, 'identifier')
        record = self.catalog.records[identifier]

        if record.abstract:
            self.textAbstract.setText(record.abstract.strip())
        else:
            self.textAbstract.setText(self.tr('No abstract'))

        # if the record has a bbox, show a footprint on the map
        if record.bbox is not None:
            points = bbox_to_polygon(record.bbox)
            self.rubber_band.setToGeometry(QgsGeometry.fromPolygon(points),
                                           None)

        # figure out if the data is interactive and can be operated on
        self.find_services(record, item)

    def find_services(self, record, item):
        """scan record for WMS/WMTS|WFS|WCS endpoints"""

        links = record.uris + record.references

        service_list = []
        for link in links:

            if 'scheme' in link:
                link_type = link['scheme']
            elif 'protocol' in link:
                link_type = link['protocol']
            else:
                link_type = None

            if link_type is not None:
                link_type = link_type.upper()

            if all([link_type is not None,
                    link_type in ['OGC:WMS', 'OGC:WMTS',
                                  'OGC:WFS', 'OGC:WCS']]):
                if link_type in ['OGC:WMS', 'OGC:WMTS']:
                    service_list.append(link['url'])
                    self.btnAddToWms.setEnabled(True)
                else:
                    service_list.append('')
                if link_type == 'OGC:WFS':
                    service_list.append(link['url'])
                    self.btnAddToWfs.setEnabled(True)
                else:
                    service_list.append('')
                if link_type == 'OGC:WCS':
                    service_list.append(link['url'])
                    self.btnAddToWcs.setEnabled(True)
                else:
                    service_list.append('')

            set_item_data(item, 'link', ','.join(service_list))

    def navigate(self):
        """manage navigation / paging"""

        caller = self.sender().objectName()

        if caller == 'btnFirst':
            self.startfrom = 0
        elif caller == 'btnLast':
            self.startfrom = self.catalog.results['matches'] - self.maxrecords
        elif caller == 'btnNext':
            self.startfrom += self.maxrecords
            if self.startfrom >= self.catalog.results["matches"]:
                msg = self.tr('End of results. Go to start?')
                res = QMessageBox.information(self, self.tr('Navigation'),
                                              msg,
                                              (QMessageBox.Ok |
                                               QMessageBox.Cancel))
                if res == QMessageBox.Ok:
                    self.startfrom = 0
                else:
                    return
        elif caller == "btnPrev":
            self.startfrom -= self.maxrecords
            if self.startfrom <= 0:
                msg = self.tr('Start of results. Go to end?')
                res = QMessageBox.information(self, self.tr('Navigation'),
                                              msg,
                                              (QMessageBox.Ok |
                                               QMessageBox.Cancel))
            if res == QMessageBox.Ok:
                self.startfrom = (self.catalog.results['matches'] -
                                  self.maxrecords)
            else:
                return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        self.catalog.getrecords2(constraints=self.constraints,
                                 maxrecords=self.maxrecords,
                                 startposition=self.startfrom, esn='full')

        QApplication.restoreOverrideCursor()

        self.display_results()

    def add_to_ows(self):
        """add to OWS provider connection list"""

        item = self.treeRecords.currentItem()

        if not item:
            return

        item_data = get_item_data(item, 'link').split(',')

        caller = self.sender().objectName()

        # stype = human name,/Qgis/connections-%s,providername
        if caller == 'btnAddToWms':
            stype = ['OGC:WMS/OGC:WMTS', 'wms', 'wms']
            data_url = item_data[0]
        elif caller == 'btnAddToWfs':
            stype = ['OGC:WFS', 'wfs', 'WFS']
            data_url = item_data[1]
        elif caller == 'btnAddToWcs':
            stype = ['OGC:WCS', 'wcs', 'wcs']
            data_url = item_data[2]

        # test if URL is valid WMS server
        try:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

            service_type = stype[0]
            if service_type == 'OGC:WMS':
                WebMapService(data_url)
            elif service_type == 'OGC:WFS':
                WebFeatureService(data_url)
            elif service_type == 'OGC:WCS':
                WebCoverageService(data_url)
        except Exception, err:
            QApplication.restoreOverrideCursor()
            msg = self.tr('Error connecting to %s: %s' % (stype[0], err))
            QMessageBox.warning(self, self.tr('Connection error'), msg)
            return

        QApplication.restoreOverrideCursor()

        inputmsg = self.tr('Enter name for %s' % stype[0])
        sname, valid = QInputDialog.getText(self, inputmsg,
                                            self.tr('Server name'))

        # store connection
        if valid and sname:
            # check if there is a connection with same name
            self.settings.beginGroup('/Qgis/connections-%s' % stype[1])
            keys = self.settings.childGroups()
            self.settings.endGroup()
        else:
            return

        # check for duplicates
        if sname in keys:
            msg = self.tr('Connection %s exists. Overwrite?' % sname)
            res = QMessageBox.warning(self, self.tr('Saving server'), msg,
                                      QMessageBox.Yes | QMessageBox.No)
            if res != QMessageBox.Yes:
                return

        # no dups detected or overwrite is allowed
        self.settings.beginGroup('/Qgis/connections-%s' % stype[1])
        self.settings.setValue('/%s/url' % sname, data_url)
        self.settings.endGroup()

        # open provider window
        ows_provider = QgsProviderRegistry.instance().selectWidget(stype[2],
                                                                   self)
        ows_provider.setModal(False)
        ows_provider.show()

        conn_tab = ows_provider.findChild(QWidget, 'tabServers')
        conn_cmb = conn_tab.findChild(QWidget, 'cmbConnections')
        index = conn_cmb.findText('/Qgis/connections-%s/%s' % (stype[1],
                                                               sname))
        if index >= 0:
            connectionsCombo.setCurrentIndex(index)
        ows_provider.on_btnConnect_clicked()

    def show_metadata(self):
        """show record metadata"""

        if not self.treeRecords.selectedItems():
            return

        item = self.treeRecords.currentItem()
        if not item:
            return

        identifier = get_item_data(item, 'identifier')

        try:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            cat = csw(self.catalog_url)
        except ExceptionReport, err:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, self.tr('Connection error'),
                                self.tr('Error connecting to service: %s' %
                                        err))
            return

        try:
            cat.getrecordbyid([self.catalog.records[identifier].identifier])
        except ExceptionReport, err:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, self.tr('GetRecords error'),
                                self.tr('Error getting response: %s' % err))
            return

        QApplication.restoreOverrideCursor()

        record = cat.records[identifier]

        crd = ResponseDialog()
        metadata = render_template('en', self.context,
                                   record, 'record_metadata_dc.html')

        style = QgsApplication.reportStyleSheet()
        crd.textXml.document().setDefaultStyleSheet(style)
        crd.textXml.setHtml(metadata)
        crd.exec_()

    def show_response(self):
        """show response"""

        crd = ResponseDialog()
        html = highlight_xml(self.context, self.catalog.response)
        style = QgsApplication.reportStyleSheet()
        crd.textXml.clear()
        crd.textXml.document().setDefaultStyleSheet(style)
        crd.textXml.setHtml(html)
        crd.exec_()

    def reset_buttons(self, services=True, xml=True, navigation=True):
        """Convenience function to disable WMS/WMTS|WFS|WCS buttons"""

        if services:
            self.btnAddToWms.setEnabled(False)
            self.btnAddToWfs.setEnabled(False)
            self.btnAddToWcs.setEnabled(False)

        if xml:
            self.btnShowXml.setEnabled(False)

        if navigation:
            self.btnFirst.setEnabled(False)
            self.btnPrev.setEnabled(False)
            self.btnNext.setEnabled(False)
            self.btnLast.setEnabled(False)

    def reject(self):
        """back out of dialogue"""

        QDialog.reject(self)
        self.map.scene().removeItem(self.rubber_band)


def save_connections():
    """save servers to list"""

    ManageConnectionsDialog(0).exec_()


def get_item_data(item, field):
    """return identifier for a QTreeWidgetItem"""

    return item.data(_get_field_value(field), 32)


def set_item_data(item, field, value):
    """set identifier for a QTreeWidgetItem"""

    item.setData(_get_field_value(field), 32, value)


def _get_field_value(field):
    """convenience function to return field value integer"""

    value = 0

    if field == 'identifier':
        value = 0
    if field == 'link':
        value = 1

    return value


def bbox_to_polygon(bbox):
    """converts OWSLib bbox object to list of QgsPoint objects"""

    minx = float(bbox.minx)
    miny = float(bbox.miny)
    maxx = float(bbox.maxx)
    maxy = float(bbox.maxy)

    return [[
        QgsPoint(minx, miny),
        QgsPoint(minx, maxy),
        QgsPoint(maxx, maxy),
        QgsPoint(maxx, miny)
    ]]
