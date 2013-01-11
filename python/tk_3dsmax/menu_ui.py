"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

Menu handling
"""

import tank
import sys
import os
import unicodedata

from tank.platform.qt import QtCore, QtGui, TankQDialog

from .ui.app_menu import Ui_AppMenu
from .ui.context_menu import Ui_ContextMenu

class WorkAreaMenu(TankQDialog):
    """
    Represents the current work area menu
    """
    def __init__(self, parent=None):
        TankQDialog.__init__(self, parent)
        self.ui = Ui_ContextMenu() 
        self.ui.setupUi(self)        
        # no window border pls
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.FramelessWindowHint)
        self._dynamic_widgets = []
        
    def mousePressEvent(self, event):
        # if no other widgets accepts it, it means click is outside any button
        # close dialog
        self.accept()

    def set_work_area_text(self, msg):
        """
        Sets the top text
        """
        self.ui.label.setText(msg)

    def __click_and_close_wrapper(self, callback):
        """
        Closes the dialog, then runs callback
        """
        self.accept()
        callback()

    def add_item(self, label, callback):
        """
        Adds a list item. Returns the created object.
        """
        widget = QtGui.QPushButton(self)
        widget.setText(label)
        self.ui.scroll_area_layout.addWidget(widget)
        self._dynamic_widgets.append(widget)   
        widget.clicked.connect( lambda : self.__click_and_close_wrapper(callback) )   
        return widget  


class AppsMenu(TankQDialog):
    """
    Represents the current apps menu
    """

    def __init__(self, parent=None):
        TankQDialog.__init__(self, parent)
        self.ui = Ui_AppMenu() 
        self.ui.setupUi(self)                
        # no window border pls
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.FramelessWindowHint)
        self.ui.label.setText("Your Current Apps")
        self._dynamic_widgets = []
        
    def mousePressEvent(self, event):
        # if no other widgets accepts it, it means click is outside any button
        # close dialog
        self.accept()

    def __click_and_close_wrapper(self, callback):
        """
        Closes the dialog, then runs callback
        """
        self.accept()
        callback()

    def add_item(self, label, callback):
        """
        Adds a list item. Returns the created object.
        """
        widget = QtGui.QPushButton(self)
        widget.setText(label)
        self.ui.scroll_area_layout.addWidget(widget)
        self._dynamic_widgets.append(widget)
        widget.clicked.connect( lambda : self.__click_and_close_wrapper(callback) )   
        return widget  