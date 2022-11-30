# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.
"""
A 3ds Max (2017+) engine for Toolkit based mostly on pymxs and also uses MaxPlus for certain features
on older Max releases.
"""
from __future__ import print_function
import os
import time
import math
import sgtk

import pymxs

# MaxPlus will be deprecated in a future release of Max, so tolerate the failure to import it.
# The code in the engine that uses MaxPlus is for versions 2019 and below, which do ship
# with MaxPlus, so we're in no danger of getting an error when MaxPlus eventually
# goes away.
try:
    import MaxPlus
except ImportError:
    pass


class MaxEngine(sgtk.platform.Engine):
    """
    The main Toolkit engine for 3ds Max
    """

    @property
    def host_info(self):
        """
        :returns: A dictionary with information about the application hosting this engine.

        The returned dictionary is of the following form on success:
        Note that the version field refers to the release year.

            {
                "name": "3ds Max",
                "version": "2018",
            }

        The returned dictionary is of following form on an error preventing
        the version identification.

            {
                "name": "3ds Max",
                "version: "unknown"
            }

        References:
        http://docs.autodesk.com/3DSMAX/16/ENU/3ds-Max-Python-API-Documentation/index.html
        """
        host_info = {"name": "3ds Max", "version": "unknown"}

        try:
            host_info["version"] = str(
                self._max_version_to_year(self._get_max_version())
            )
        except:
            # Fallback to initialized values above
            pass

        return host_info

    def __init__(self, *args, **kwargs):
        """
        Engine Constructor
        """

        # Add instance variables before calling our base class
        # __init__() because the initialization may need those
        # variables.
        self._parent_to_max = True
        self._dock_widgets = []

        self._max_version = None

        # proceed about your business
        sgtk.platform.Engine.__init__(self, *args, **kwargs)

    ##########################################################################################
    # properties

    @property
    def context_change_allowed(self):
        """
        Tells the core API that context changes are allowed by this engine.
        """
        return True

    ##########################################################################################
    # init

    def pre_app_init(self):
        """
        Called before all apps have initialized
        """
        from sgtk.platform.qt import QtCore, QtGui

        self.log_debug("%s: Initializing..." % self)

        if self._get_max_version() > MaxEngine.MAXIMUM_SUPPORTED_VERSION:
            # Untested max version

            highest_supported_version = self._max_version_to_year(
                MaxEngine.MAXIMUM_SUPPORTED_VERSION
            )

            msg = (
                "SG Pipeline Toolkit!\n\n"
                "The SG Pipeline Toolkit has not yet been fully tested with 3ds Max versions greater than %s. "
                "You can continue to use the Toolkit but you may experience bugs or instability. "
                "Please report any issues you see via %s."
                % (
                    highest_supported_version,
                    sgtk.support_url,
                )
            )

            # Display warning dialog
            max_year = self._max_version_to_year(self._get_max_version())
            max_next_year = highest_supported_version + 1
            if max_year >= self.get_setting(
                "compatibility_dialog_min_version", max_next_year
            ):
                QtGui.QMessageBox.warning(
                    None, "SG Warning", "Warning - {0}".format(msg)
                )
            # and log the warning
            self.log_warning(msg)

        self._safe_dialog = []

        # Add image formats since max doesn't add the correct paths by default and jpeg won't be readable
        maxpath = QtCore.QCoreApplication.applicationDirPath()
        pluginsPath = os.path.join(maxpath, "plugins")
        QtCore.QCoreApplication.addLibraryPath(pluginsPath)

        # Window focus objects are used to enable proper keyboard handling by the window instead of 3dsMax's accelerators
        engine = self

        class DialogEvents(QtCore.QObject):
            def eventFilter(self, obj, event):
                if event.type() == QtCore.QEvent.WindowActivate:
                    pymxs.runtime.enableAccelerators = False
                elif event.type() == QtCore.QEvent.WindowDeactivate:
                    pymxs.runtime.enableAccelerators = True
                # Remove from tracked dialogs
                if event.type() == QtCore.QEvent.Close:
                    if obj in engine._safe_dialog:
                        engine._safe_dialog.remove(obj)

                return False

        self.dialogEvents = DialogEvents()

        # set up a qt style sheet
        # note! - try to be smart about this and only run
        # the style setup once per session - it looks like
        # 3dsmax slows down if this is executed every engine restart.
        #
        # If we're in pre-Qt Max (before 2018) then we'll need to apply the
        # stylesheet to the QApplication. That's not safe in 2019.3+, as it's
        # possible that we'll get back a QCoreApplication from Max, which won't
        # carry references to a stylesheet. In that case, we apply our styling
        # to the dialog parent, which will be the top-level Max window.
        if self._max_version_to_year(self._get_max_version()) < 2018:
            parent_widget = sgtk.platform.qt.QtCore.QCoreApplication.instance()
        else:
            parent_widget = self._get_dialog_parent()

        curr_stylesheet = parent_widget.styleSheet()

        if "toolkit 3dsmax style extension" not in curr_stylesheet:
            # If we're in pre-2017 Max then we need to handle our own styling. Otherwise
            # we just inherit from Max.
            if self._max_version_to_year(self._get_max_version()) < 2017:
                self._initialize_dark_look_and_feel()

            curr_stylesheet += "\n\n /* toolkit 3dsmax style extension */ \n\n"
            curr_stylesheet += (
                "\n\n QDialog#TankDialog > QWidget { background-color: #343434; }\n\n"
            )
            parent_widget.setStyleSheet(curr_stylesheet)

        # This needs to be present for apps as it will be used in
        # show_dialog when perforce asks for login info very early on.
        self.tk_3dsmax = self.import_module("tk_3dsmax")

        # The "qss_watcher" setting causes us to monitor the engine's
        # style.qss file and re-apply it on the fly when it changes
        # on disk. This is very useful for development work,
        if self.get_setting("qss_watcher", False):
            self._qss_watcher = QtCore.QFileSystemWatcher(
                [
                    os.path.join(
                        self.disk_location,
                        sgtk.platform.constants.BUNDLE_STYLESHEET_FILE,
                    )
                ]
            )

            self._qss_watcher.fileChanged.connect(self.reload_qss)

    def _add_shotgun_menu(self):
        """
        Add Shotgun menu to the main menu bar.
        """
        self.log_debug("Adding the SG menu to the main menu bar.")
        self._menu_generator.create_menu()
        self.tk_3dsmax.MaxScript.enable_menu()

    def _remove_shotgun_menu(self):
        """
        Remove Shotgun menu from the main menu bar.
        """
        self.log_debug("Removing the SG menu from the main menu bar.")
        self._menu_generator.destroy_menu()

    def _on_menus_loaded(self):
        """
        Called when receiving postLoadingMenus from 3dsMax.

        :param code: Notification code received
        """
        self._add_shotgun_menu()

    def post_app_init(self):
        """
        Called when all apps have initialized
        """
        # Make sure this gets executed from the main thread because pymxs can't be used
        # from a background thread.
        self.execute_in_main_thread(self._post_app_init)

    def _post_app_init(self):
        """
        Called from the main thread when all apps have initialized
        """
        # set up menu handler
        self._menu_generator = self.tk_3dsmax.MenuGenerator(self)
        self._add_shotgun_menu()

        # Register a callback for the postLoadingMenus event.
        python_code = "\n".join(
            [
                "import sgtk",
                "engine = sgtk.platform.current_engine()",
                "engine._on_menus_loaded()",
            ]
        )
        # Unfortunately we can't pass in a Python function as a callback,
        # so we're passing in piece of MaxScript instead.
        pymxs.runtime.callbacks.addScript(
            pymxs.runtime.Name("postLoadingMenus"),
            'python.execute "{0}"'.format(python_code),
            id=pymxs.runtime.Name("sg_tk_on_menus_loaded"),
        )

        # Run a series of app instance commands at startup.
        self._run_app_instance_commands()

        # if a file was specified, load it now
        file_to_open = os.environ.get("SGTK_FILE_TO_OPEN")
        if file_to_open:
            try:
                pymxs.runtime.loadMaxFile(file_to_open)
            except Exception:
                self.logger.exception(
                    "Couldn't not open the requested file: {}".format(file_to_open)
                )

    def post_context_change(self, old_context, new_context):
        """
        Handles necessary processing after a context change has been completed
        successfully.

        :param old_context: The previous context.
        :param new_context: The current, new context.
        """
        # Replacing the menu will cause the old one to be removed
        # and the new one put into its place.
        self._add_shotgun_menu()

    def _run_app_instance_commands(self):
        """
        Runs the series of app instance commands listed in the 'run_at_startup' setting
        of the environment configuration yaml file.
        """

        # Build a dictionary mapping app instance names to dictionaries of commands they registered with the engine.
        app_instance_commands = {}
        for (command_name, value) in self.commands.items():
            app_instance = value["properties"].get("app")
            if app_instance:
                # Add entry 'command name: command function' to the command dictionary of this app instance.
                command_dict = app_instance_commands.setdefault(
                    app_instance.instance_name, {}
                )
                command_dict[command_name] = value["callback"]

        # Run the series of app instance commands listed in the 'run_at_startup' setting.
        for app_setting_dict in self.get_setting("run_at_startup", []):
            app_instance_name = app_setting_dict["app_instance"]
            # Menu name of the command to run or '' to run all commands of the given app instance.
            setting_command_name = app_setting_dict["name"]

            # Retrieve the command dictionary of the given app instance.
            command_dict = app_instance_commands.get(app_instance_name)

            if command_dict is None:
                self.log_warning(
                    "%s configuration setting 'run_at_startup' requests app '%s' that is not installed."
                    % (self.name, app_instance_name)
                )
            else:
                if not setting_command_name:
                    # Run all commands of the given app instance.
                    for (command_name, command_function) in command_dict.items():
                        self.log_debug(
                            "%s startup running app '%s' command '%s'."
                            % (self.name, app_instance_name, command_name)
                        )
                        command_function()
                else:
                    # Run the command whose name is listed in the 'run_at_startup' setting.
                    command_function = command_dict.get(setting_command_name)
                    if command_function:
                        self.log_debug(
                            "%s startup running app '%s' command '%s'."
                            % (self.name, app_instance_name, setting_command_name)
                        )
                        command_function()
                    else:
                        known_commands = ", ".join(
                            "'%s'" % name for name in command_dict
                        )
                        self.log_warning(
                            "%s configuration setting 'run_at_startup' requests app '%s' unknown command '%s'. "
                            "Known commands: %s"
                            % (
                                self.name,
                                app_instance_name,
                                setting_command_name,
                                known_commands,
                            )
                        )

    def destroy_engine(self):
        """
        Called when the engine is shutting down
        """
        self.log_debug("%s: Destroying..." % self)

        pymxs.runtime.callbacks.removeScripts(
            pymxs.runtime.Name("postLoadingMenus"),
            id=pymxs.runtime.Name("sg_tk_on_menus_loaded"),
        )
        self._remove_shotgun_menu()

    def update_shotgun_menu(self):
        """
        Rebuild the shotgun menu displayed in the main menu bar
        """
        self._remove_shotgun_menu()
        self._add_shotgun_menu()

    ##########################################################################################
    # logging
    # Should only call logging function from the main thread, although output to listener is
    # supposed to be thread-safe.
    # Note From the max team: Python scripts run in MAXScript are not thread-safe.
    #                         Python commands are always executed in the main 3ds Max thread.
    #                         You should not attempt to spawn separate threads in your scripts
    #                         (for example, by using the Python threading module).
    def _emit_log_message(self, handler, record):
        """
        Emits a log message.
        """
        msg_str = handler.format(record)
        self.async_execute_in_main_thread(self._print_output, msg_str)

    def _print_output(self, msg):
        """
        Print the specified message to the maxscript listener
        :param msg: The message string to print
        """
        print(msg)

    ##########################################################################################
    # Engine

    def _get_dialog_parent(self):
        """
        Get the QWidget parent for all dialogs created through :meth:`show_dialog` :meth:`show_modal`.

        :return: QT Parent window (:class:`PySide.QtGui.QWidget`)
        """
        # Older versions of Max make use of special logic in _create_dialog
        # to handle window parenting. If we can, though, we should go with
        # the more standard approach to getting the main window.
        if self._max_version_to_year(self._get_max_version()) > 2020:
            # getMAXHWND returned a float instead of a long, which was completely
            # unusable with PySide in 2017 to 2020, but starting 2021
            # we can start using it properly.
            # This logic was taken from
            # https://help.autodesk.com/view/3DSMAX/2020/ENU/?guid=__developer_creating_python_uis_html
            import shiboken2
            from sgtk.platform.qt import QtGui

            widget = QtGui.QWidget.find(pymxs.runtime.windows.getMAXHWND())
            return shiboken2.wrapInstance(
                shiboken2.getCppPointer(widget)[0], QtGui.QMainWindow
            )
        elif self._max_version_to_year(self._get_max_version()) > 2017:
            #
            return MaxPlus.GetQMaxMainWindow()
        else:
            return super(MaxEngine, self)._get_dialog_parent()

    def show_panel(self, panel_id, title, bundle, widget_class, *args, **kwargs):
        """
        Docks an app widget in a 3dsmax panel.

        :param panel_id: Unique identifier for the panel, as obtained by register_panel().
        :param title: The title of the panel
        :param bundle: The app, engine or framework object that is associated with this window
        :param widget_class: The class of the UI to be constructed. This must derive from QWidget.

        Additional parameters specified will be passed through to the widget_class constructor.

        :returns: the created widget_class instance
        """
        from sgtk.platform.qt import QtCore, QtGui

        self.log_debug("Begin showing panel %s" % panel_id)

        if self._max_version_to_year(self._get_max_version()) <= 2017:
            # Qt docking is supported in version 2018 and later.
            self.log_warning(
                "Panel functionality not implemented. Falling back to showing "
                "panel '%s' in a modeless dialog" % panel_id
            )
            return super(MaxEngine, self).show_panel(
                panel_id, title, bundle, widget_class, *args, **kwargs
            )

        dock_widget_id = "sgtk_dock_widget_" + panel_id

        main_window = self._get_dialog_parent()
        # Check if the dock widget wrapper already exists.
        dock_widget = main_window.findChild(QtGui.QDockWidget, dock_widget_id)

        if dock_widget is None:
            # The dock widget wrapper cannot be found in the main window's
            # children list so that means it has not been created yet, so create it.
            widget_instance = widget_class(*args, **kwargs)
            widget_instance.setParent(self._get_dialog_parent())
            widget_instance.setObjectName(panel_id)

            class DockWidget(QtGui.QDockWidget):
                """
                Widget used for docking app panels that ensures the widget is closed when the dock is closed
                """

                closed = QtCore.Signal(QtCore.QObject)

                def closeEvent(self, event):
                    widget = self.widget()
                    if widget:
                        widget.close()
                    self.setParent(None)
                    self.closed.emit(self)

            dock_widget = DockWidget(title, parent=main_window)
            dock_widget.setObjectName(dock_widget_id)
            dock_widget.setWidget(widget_instance)
            # Add a callback to remove the dock_widget from the list of open panels and delete it
            dock_widget.closed.connect(self._remove_dock_widget)
            self.log_debug("Created new dock widget %s" % dock_widget_id)

            # Disable 3dsMax accelerators, in order for QTextEdit and QLineEdit
            # widgets to work properly.
            widget_instance.setProperty("NoMaxAccelerators", True)

            # Remember the dock widget, so we can delete it later.
            self._dock_widgets.append(dock_widget)
        else:
            # The dock widget wrapper already exists, so just get the
            # shotgun panel from it.
            widget_instance = dock_widget.widget()
            self.log_debug("Found existing dock widget %s" % dock_widget_id)

        # apply external stylesheet
        self._apply_external_stylesheet(bundle, widget_instance)

        if not main_window.restoreDockWidget(dock_widget):
            # The dock widget cannot be restored from the main window's state,
            # so dock it to the right dock area and make it float by default.
            main_window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock_widget)
            dock_widget.setFloating(True)

        dock_widget.show()
        return widget_instance

    def _remove_dock_widget(self, dock_widget):
        """
        Removes a docked widget (panel) opened by the engine
        """
        self._get_dialog_parent().removeDockWidget(dock_widget)
        self._dock_widgets.remove(dock_widget)
        dock_widget.deleteLater()

    def close_windows(self):
        """
        Closes the various windows (dialogs, panels, etc.) opened by the engine.
        """

        # Make a copy of the list of Tank dialogs that have been created by the engine and
        # are still opened since the original list will be updated when each dialog is closed.
        opened_dialog_list = self.created_qt_dialogs[:]

        # Loop through the list of opened Tank dialogs.
        for dialog in opened_dialog_list:
            dialog_window_title = dialog.windowTitle()
            try:
                # Close the dialog and let its close callback remove it from the original dialog list.
                self.log_debug("Closing dialog %s." % dialog_window_title)
                dialog.close()
            except Exception as exception:
                self.log_error(
                    "Cannot close dialog %s: %s" % (dialog_window_title, exception)
                )

        # Close all dock widgets previously added.
        for dock_widget in self._dock_widgets[:]:
            dock_widget.close()

    def _create_dialog(self, title, bundle, widget, parent):
        """
        Parent function override to install event filtering in order to allow proper events to
        reach window dialogs (such as keyboard events).
        """
        dialog = sgtk.platform.Engine._create_dialog(
            self, title, bundle, widget, parent
        )

        # Attaching the dialog to Max is a matter of whether this is a new
        # enough version of 3ds Max. Anything short of 2016 SP1 is going to
        # fail here with an AttributeError, so we can just catch that and
        # continue on without the new-style parenting.
        if (
            self._parent_to_max
            and self._max_version_to_year(self._get_max_version()) <= 2019
        ):
            previous_parent = dialog.parent()
            try:
                self.log_debug("Attempting to attach dialog to 3ds Max...")
                dialog.setParent(None)
                # widget must be parentless when calling MaxPlus.AttachQWidgetToMax
                # Accessing MaxPlus here is safe because we're inside a
                # a branch of code that can only be executed on Max 2019 and lower.
                MaxPlus.AttachQWidgetToMax(dialog)
                self.log_debug("AttachQWidgetToMax successful.")
            except AttributeError:
                dialog.setParent(previous_parent)
                self.log_debug(
                    "AttachQWidgetToMax not available in this version of 3ds Max."
                )

        dialog.installEventFilter(self.dialogEvents)

        # Add to tracked dialogs (will be removed in eventFilter)
        self._safe_dialog.append(dialog)

        # Apply the engine-level stylesheet.
        self._apply_external_styleshet(self, dialog)

        return dialog

    def reload_qss(self):
        """
        Causes the style.qss file that comes with the tk-rv engine to
        be re-applied to all dialogs that the engine has previously
        launched.
        """
        self.log_warning("Reloading engine QSS...")
        for dialog in self.created_qt_dialogs:
            self._apply_external_styleshet(self, dialog)
            dialog.update()

    def show_modal(self, title, bundle, widget_class, *args, **kwargs):
        from sgtk.platform.qt import QtGui

        if not self.has_ui:
            self.log_error(
                "Sorry, this environment does not support UI display! Cannot show "
                "the requested window '%s'." % title
            )
            return None

        status = QtGui.QDialog.DialogCode.Rejected

        try:
            # Disable 'Shotgun' background menu while modals are there.
            self.tk_3dsmax.MaxScript.disable_menu()

            # create the dialog:
            try:
                self._parent_to_max = False
                dialog, widget = self._create_dialog_with_widget(
                    title, bundle, widget_class, *args, **kwargs
                )
            finally:
                self._parent_to_max = True

            # finally launch it, modal state
            status = dialog.exec_()
        except Exception:
            import traceback

            tb = traceback.format_exc()
            self.log_error("Exception in modal window: %s" % tb)
        finally:
            # Re-enable 'Shotgun' background menu after modal has been closed
            self.tk_3dsmax.MaxScript.enable_menu()

        # lastly, return the instantiated widget
        return (status, widget)

    def safe_dialog_exec(self, func):
        """
        If running a command from a dialog also creates a 3ds max window, this function tries to
        ensure that the dialog will stay alive and that the max modal window becomes visible
        and unobstructed.

        :param callable script: Function to execute
        """

        # Merge operation can cause max dialogs to pop up, and closing the window results in a crash.
        # So keep alive and hide all of our qt windows while this type of operations are occuring.
        from sgtk.platform.qt import QtGui

        toggled = []

        for dialog in self._safe_dialog:
            needs_toggling = dialog.isVisible()

            if needs_toggling:
                self.log_debug("Toggling dialog off: %r" % dialog)
                toggled.append(dialog)
                dialog.hide()
                dialog.lower()
                QtGui.QApplication.processEvents()
            else:
                self.log_debug("Dialog is already hidden: %r" % dialog)

        try:
            func()
        finally:
            for dialog in toggled:
                # Restore the window after the operation is completed
                self.log_debug("Toggling dialog on: %r" % dialog)
                dialog.show()
                dialog.activateWindow()  # for Windows
                dialog.raise_()  # for MacOS

    ##########################################################################################
    # MaxPlus SDK Patching

    # Version Id for 3dsmax 2016 Taken from Max Sdk (not currently available in maxplus)
    MAX_RELEASE_R18 = 18000

    # Latest supported max version
    MAXIMUM_SUPPORTED_VERSION = 25000

    def _max_version_to_year(self, version):
        """
        Get the max year from the max release version.
        Note that while 17000 is 2015, 17900 would be 2016 alpha
        """
        year = 2000 + (math.ceil(version / 1000.0) - 2)
        return year

    def _get_max_version(self):
        """
        Returns Version integer of max release number.
        """
        if self._max_version is None:
            # Make sure this gets executed from the main thread because pymxs can't be used
            # from a background thread.
            self._max_version = self.execute_in_main_thread(
                lambda: pymxs.runtime.maxVersion()[0]
            )
        # 3dsMax Version returns a number which contains max version, sdk version, etc...
        return self._max_version
