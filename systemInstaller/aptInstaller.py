#! /usr/bin/python3
# -*- coding: utf-8 -*-
#
# Cinnamon Installer
#
# Authors: Lester Carballo Pérez <lestcape@gmail.com>
#
# Original version from: Sebastian Heinlein <devel@glatzor.de>
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License as
#  published by the Free Software Foundation; either version 2 of the
#  License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
#  USA


import aptdaemon.client
import aptdaemon.errors
from aptdaemon.enums import *

import apt_pkg, apt

import logging, difflib, gettext, os, pty, re, subprocess, glob
from defer import inline_callbacks
from defer.utils import deferable

# uncomment to use GTK 2.0
#import gi
#gi.require_version('Gtk', '2.0')
#gi.require_version('Vte', '0.0')

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gdk
from gi.repository import Pango
from gi.repository import Vte

__all__ = ("AptConfigFileConflictDialog", "AptCancelButton",
           "AptConfirmDialog",
           "AptProgressDialog", "AptTerminalExpander", "AptStatusIcon",
           "AptRoleIcon", "AptStatusAnimation", "AptRoleLabel",
           "AptStatusLabel", "AptMediumRequiredDialog", "AptMessageDialog",
           "AptErrorDialog", "AptProgressBar", "DiffView",
           "AptTerminal"
           )

_ = lambda msg: gettext.dgettext("aptdaemon", msg)

(COLUMN_ID,
 COLUMN_PACKAGE) = list(range(2))

def configure():
    return True

def findPackageByPath(path):
    '''Return the package that ships the given file.

    Return None if no package ships it.
    '''
    if path is not None:
        # resolve symlinks in directories
        (dir, name) = os.path.split(path)
        resolved_dir = os.path.realpath(dir)
        if os.path.isdir(resolved_dir):
            file = os.path.join(resolved_dir, name)

        if not likely_packaged(path):
            return None

        return get_file_package(path)
    return None

def likely_packaged(file):
    '''Check whether the given file is likely to belong to a package.'''
    pkg_whitelist = ['/bin/', '/boot', '/etc/', '/initrd', '/lib', '/sbin/',
                     '/opt', '/usr/', '/var']  # packages only ship executables in these directories

    whitelist_match = False
    for i in pkg_whitelist:
        if file.startswith(i):
            whitelist_match = True
            break
    return whitelist_match and not file.startswith('/usr/local/') and not \
        file.startswith('/var/lib/')

def get_file_package(file):
    '''Return the package a file belongs to.

    Return None if the file is not shipped by any package.
    '''
    # check if the file is a diversion
    divert = '/usr/bin/dpkg-divert'
    if(not GLib.file_test(divert, GLib.FileTest.EXISTS)):
        divert = '/usr/sbin/dpkg-divert'
    if(GLib.file_test(divert, GLib.FileTest.EXISTS)):
        dpkg = subprocess.Popen([divert, '--list', file],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = dpkg.communicate()[0].decode('UTF-8')
        if dpkg.returncode == 0 and out:
            pkg = out.split()[-1]
            if pkg != 'hardening-wrapper':
                return pkg

    fname = os.path.splitext(os.path.basename(file))[0].lower()

    all_lists = []
    likely_lists = []
    for f in glob.glob('/var/lib/dpkg/info/*.list'):
        p = os.path.splitext(os.path.basename(f))[0].lower().split(':')[0]
        if p in fname or fname in p:
            likely_lists.append(f)
        else:
            all_lists.append(f)

    # first check the likely packages
    match = __fgrep_files(file, likely_lists)
    if not match:
        match = __fgrep_files(file, all_lists)

    if match:
        return os.path.splitext(os.path.basename(match))[0].split(':')[0]

    return None

def __fgrep_files(pattern, file_list):
    '''Call fgrep for a pattern on given file list and return the first
    matching file, or None if no file matches.'''

    match = None
    slice_size = 100
    i = 0

    while not match and i < len(file_list):
        p = subprocess.Popen(['fgrep', '-lxm', '1', '--', pattern] +
                             file_list[i:(i + slice_size)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = p.communicate()[0].decode('UTF-8')
        if p.returncode == 0:
            match = out
        i += slice_size

    return match

def searchUnistalledPackages(pattern):
     cache = apt.Cache(apt.progress.base.OpProgress())
     matchWordsPattern = pattern.split(",")
     unInstalledPackages = []
     for pkgName in cache.keys():
        pkg = cache[pkgName]
        if((not pkg.is_installed) and (isMatching(matchWordsPattern, pkg.name)) and
            (not packageExistArch(pkgName, cache))):
            unInstalledPackages.append(pkg.name)
     return unInstalledPackages

def isMatching(matchWordsPattern, packageName):
    for word in matchWordsPattern:
       if(not (word in packageName)):
           return False
    return True
          

def packageExistArch(pkgName, cache):
    lenght = len(pkgName)
    if pkgName[lenght-5:lenght] == ":i386":
        try:
            pkg = cache[pkgName[0:lenght-5]]
            if pkg.is_installed:
                #print("Installed: " + pkgName)
                return True
        except Exception:
            return False
    return False


''' Report me package that do not exit need apt instead
def searchUnistalledPackages(pattern):
    apt_pkg.init()
    cache = apt_pkg.Cache(progress=None)
    unInstalledPackages = []
    for p in cache.packages:
       if((p.current_state == apt_pkg.CURSTATE_NOT_INSTALLED) and
             (pattern in p.name)):
           if not packageNameInList(p.name, unInstalledPackages):
               unInstalledPackages.append(p)
    return filterDuplicatePackageName(unInstalledPackages, cache, aptC)

def packageNameInList(pkgName, listPackage):
    for p in listPackage:
        if pkgName == p.name:
            return True
    return False

def filterDuplicatePackageName(listPackage, cache, aptC):
    filterUninstPackageList = []
    for p in listPackage:
        duplicate = False
        for d in cache.packages:
            if((p.name == d.name) and
                (d.current_state != apt_pkg.CURSTATE_NOT_INSTALLED)):
                duplicate = True
                break
        if not duplicate:
            filterUninstPackageList.append(p)
    return filterUninstPackageList
'''

class DummyFile(object):
    def write(self, x): pass

class ControlWindow(object):
    def __init__(self, mainApp):
        self.mainApp = mainApp
        self.packageName = None
#att requeridos
        self.debconf = True
        self.show_terminal = True
        self._expanded_size = None
        self._transaction = None
        self.icon_name = None
#att requeridos
        #interface = self.mainApp.interface
        #self.mainWindow = (interface.get_object("Installer"))
        #self.progressBar = interface.get_object("progressbar")
        #self.expander = interface.get_object("terminalExpander")
        #self.labelRole = interface.get_object("roleLabel")
        #self.labelStatus = interface.get_object("statusLabel")
        #self.cancelButton = interface.get_object("cancelButton")
        self._signals = []

        self.mainApp._statusLabel.set_ellipsize(Pango.EllipsizeMode.END)
        self.mainApp._statusLabel.set_max_width_chars(15)
        self._signalsLabelStatus = []

        self.mainApp._cancelButton.set_use_stock(True)
        self.mainApp._cancelButton.set_label(Gtk.STOCK_CANCEL)
        self.mainApp._cancelButton.set_sensitive(True)
        self._signalsCancelButton = []

        self.mainApp._progressBar.set_ellipsize(Pango.EllipsizeMode.END)
        self.mainApp._progressBar.set_text(" ")
        self.mainApp._progressBar.set_pulse_step(0.05)
        self._signalsProgressBar = []

        self.mainApp._terminalExpander.set_sensitive(False)
        self.mainApp._terminalExpander.set_expanded(False)
        if self.show_terminal:
            self.terminal = AptTerminal()
        else:
            self.terminal = None
        self.download_view = AptDownloadsView()
        self.download_scrolled = Gtk.ScrolledWindow()
        self.download_scrolled.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        self.download_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.download_scrolled.add(self.download_view)
        self.mainApp._terminalBox.pack_start(self.download_scrolled, True, True, 0)
        if self.terminal:
            self.mainApp._terminalBox.pack_start(self.terminal, True, True, 0)

        self.mainApp._terminalExpander.connect("notify::expanded", self._on_expanded)
        
        #self.set_title("")
        self.mainApp._progressBar.set_size_request(350, -1)

        self._signalsExpander = []

        self.terminal.hide()
        self.loop = GObject.MainLoop()
        self.ac = aptdaemon.client.AptClient()

    def preformInstall(self, name):
        self.packageName = name
        if self.packageName is not None:
            self.ac.install_packages([self.packageName],
                                     reply_handler=self._simulate_trans,
                                     error_handler=self._on_error)
        self.run()

    def preformUninstall(self, name):
        self.packageName = name
        if self.packageName is not None:
            self.ac.remove_packages([self.packageName],
                                    reply_handler=self._simulate_trans,
                                    error_handler=self._on_error)
            self.run()

    def _setTransaction(self, transaction=None):
        if transaction is not None:
            self.set_transaction(transaction)

    def _on_dialog_delete_event(self, dialog, event):
        self.mainApp._cancelButton.clicked()
        return True


    def _on_expanded(self, expander, param):
        # Make the dialog resizable if the expander is expanded
        # try to restore a previous size
        if not expander.get_expanded():
            self._expanded_size = (self.terminal.get_visible(),
                                   self.mainApp._mainWindow.get_size())
            self.mainApp._mainWindow.set_resizable(False)
        elif self._expanded_size:
            self.mainApp._mainWindow.set_resizable(True)
            term_visible, (stored_width, stored_height) = self._expanded_size
            # Check if the stored size was for the download details or
            # the terminal widget
            if term_visible != self.terminal.get_visible():
                # The stored size was for the download details, so we need
                # get a new size for the terminal widget
                self._resize_to_show_details()
            else:
                self.mainApp._mainWindow.resize(stored_width, stored_height)
        else:
            self.mainApp._mainWindow.set_resizable(True)
            self._resize_to_show_details()

    def _resize_to_show_details(self):
        win_width, win_height = self.mainApp._mainWindow.get_size()
        exp_width = self.mainApp._terminalExpander.get_allocation().width
        exp_height = self.mainApp._terminalExpander.get_allocation().height
        if self.terminal and self.terminal.get_visible():
            terminal_width = self.terminal.get_char_width() * 80
            terminal_height = self.terminal.get_char_height() * 24
            self.mainApp._mainWindow.resize(terminal_width - exp_width ,
                               terminal_height - exp_height )
        else:
            print(win_height)
            self.mainApp._mainWindow.resize(win_width + 100, win_height)

    def _on_status_changed(self, trans, status):
        # Also resize the window if we switch from download details to
        # the terminal window
        print(status)
        #if (status == STATUS_COMMITTING and self.terminal and 
        #        self.terminal.get_visible()):
        #    self._resize_to_show_details()

    @inline_callbacks
    def _run(self, attach, close_on_finished, show_error,
             reply_handler, error_handler):
        try:
            sig = self._transaction.connect("finished", self._on_finished,
                                            close_on_finished, show_error)
            self._signals.append(sig)
            if attach:
                yield self._transaction.sync()
            else:
                if self.debconf:
                    yield self._transaction.set_debconf_frontend("gnome")
                yield self._transaction.run()
            self.mainApp._mainWindow.show_all()
        except Exception as error:
            print(error)
            if error_handler:
                error_handler(error)
            else:
                raise
        else:
            if reply_handler:
                reply_handler()

    def _on_role_changed(self, transaction, role_enum):
        """Show the role of the transaction in the dialog interface"""
        role = get_role_localised_present_from_enum(role_enum)
        self.mainApp._roleLabel.set_markup("<big><b>%s</b></big>" % role)
        icon_name = get_role_icon_name_from_enum(role_enum)
        if icon_name is None:
            icon_name = Gtk.STOCK_MISSING_IMAGE
        if icon_name != self.icon_name:
            self.icon_name = icon_name
        self.mainApp._actionImage.set_from_icon_name(icon_name, Gtk.IconSize.BUTTON)

    def set_transaction(self, transaction):
        """Connect the dialog to the given aptdaemon transaction"""
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals = []
        self._signals.append(
            transaction.connect_after("status-changed",
                                      self._on_status_changed))
        self._signals.append(transaction.connect("role-changed",
                                                 self._on_role_changed))
        self._signals.append(transaction.connect("medium-required",
                                                 self._on_medium_required))
        self._signals.append(transaction.connect("config-file-conflict",
                             self._on_config_file_conflict))
        self._on_role_changed(transaction, transaction.role)
        self.setCancelButtonTransaction(transaction)
        self.setProgressBarTransaction(transaction)
        self.setExpanderTransaction(transaction)
        self.setLabelStatusTransaction(transaction)
        #self.icon.set_transaction(transaction)


        self._transaction = transaction

    def _on_medium_required(self, transaction, medium, drive):
        dialog = AptMediumRequiredDialog(medium, drive, self)
        res = dialog.run()
        dialog.hide()
        if res == Gtk.ResponseType.OK:
            self._transaction.provide_medium(medium)
        else:
            self._transaction.cancel()

    def _on_config_file_conflict(self, transaction, old, new):
        dialog = AptConfigFileConflictDialog(old, new, self)
        res = dialog.run()
        dialog.hide()
        if res == Gtk.ResponseType.YES:
            self._transaction.resolve_config_file_conflict(old, "replace")
        else:
            self._transaction.resolve_config_file_conflict(old, "keep")

    def _on_finished(self, transaction, status, close, show_error):
        if close:
            self.mainApp._mainWindow.hide()
        if status == EXIT_FAILED and show_error:
            err_dia = AptErrorDialog(self._transaction.error, self.mainApp._mainWindow)
            err_dia.run()
            self.loop.quit()
            err_dia.hide()
        else:
            self.loop.quit()
        #self.emit("finished")

#labelStatus
    def setLabelStatusTransaction(self, transaction):
        """Connect the status label to the given aptdaemon transaction"""
        for sig in self._signalsLabelStatus:
            GLib.source_remove(sig)
        self._signalsLabelStatus = []
        self._signalsLabelStatus.append(
            transaction.connect("status-changed", self._on_status_changed_labelStatus))
        self._signalsLabelStatus.append(
            transaction.connect("status-details-changed",
                                self._on_status_details_changed_labelStatus))

    def _on_status_changed_labelStatus(self, transaction, status):
        """Set the status text according to the changed status"""
        self.mainApp._statusLabel.set_markup(get_status_string_from_enum(status))

    def _on_status_details_changed_labelStatus(self, transaction, text):
        """Set the status text to the one reported by apt"""
        self.mainApp._statusLabel.set_markup(text)
#labelStatus
#cancelButton
    def setCancelButtonTransaction(self, transaction):
        """Connect the status label to the given aptdaemon transaction"""
        for sig in self._signalsCancelButton:
            GLib.source_remove(sig)
        self._signalsCancelButton = []
        self._signalsCancelButton.append(
            transaction.connect("finished", self._on_finished_cancelButton))
        self._signalsCancelButton.append(
            transaction.connect("cancellable-changed",
                                self._on_cancellable_changed_cancelButton))
        self.mainApp._cancelButton.connect("clicked", self._on_clicked_cancelButton, transaction)

    def _on_cancellable_changed_cancelButton(self, transaction, cancellable):
        """
        Enable the button if cancel is allowed and disable it in the other case
        """
        self.mainApp._cancelButton.set_sensitive(cancellable)

    def _on_finished_cancelButton(self, transaction, status):
        self.mainApp._cancelButton.set_sensitive(False)

    def _on_clicked_cancelButton(self, button, transaction):
        transaction.cancel()
        self.mainApp._cancelButton.set_sensitive(False)
        self.loop.quit()
#cancelButton
#progressBar
    def setProgressBarTransaction(self, transaction):
        """Connect the progress bar to the given aptdaemon transaction"""
        for sig in self._signalsProgressBar:
            GLib.source_remove(sig)
        self._signalsProgressBar = []
        self._signalsProgressBar.append(
            transaction.connect("finished", self._on_finished_progressBar))
        self._signalsProgressBar.append(
            transaction.connect("progress-changed", self._on_progress_changed_progressBar))
        self._signalsProgressBar.append(transaction.connect("progress-details-changed",
                                                 self._on_progress_details_progressBar))

    def _on_progress_changed_progressBar(self, transaction, progress):
        """
        Update the progress according to the latest progress information
        """
        if progress > 100:
            self.mainApp._progressBar.pulse()
        else:
            self.mainApp._progressBar.set_fraction(progress / 100.0)

    def _on_progress_details_progressBar(self, transaction, items_done, items_total,
                             bytes_done, bytes_total, speed, eta):
        """
        Update the progress bar text according to the latest progress details
        """
        if items_total == 0 and bytes_total == 0:
            self.mainApp._progressBar.set_text(" ")
            return
        if speed != 0:
            self.mainApp._progressBar.set_text(_("Downloaded %sB of %sB at %sB/s") %
                                      (apt_pkg.size_to_str(bytes_done),
                                      apt_pkg.size_to_str(bytes_total),
                                      apt_pkg.size_to_str(speed)))
        else:
            self.mainApp._progressBar.set_text(_("Downloaded %sB of %sB") %
                                      (apt_pkg.size_to_str(bytes_done),
                                      apt_pkg.size_to_str(bytes_total)))

    def _on_finished_progressBar(self, transaction, exit):
        """Set the progress to 100% when the transaction is complete"""
        self.mainApp._progressBar.set_fraction(1)
#progressBar
#expander
    def setExpanderTransaction(self, transaction):
        """Connect the status label to the given aptdaemon transaction"""
        for sig in self._signalsExpander:
            GLib.source_remove(sig)
        self._signalsExpander = []
        self._signalsExpander.append(
            transaction.connect("status-changed", self._on_status_changed_expander))
        self._signalsExpander.append(
            transaction.connect("terminal-attached-changed", self._on_terminal_attached_changed_expander))
        if self.terminal:
            self.terminal.set_transaction(transaction)
        self.download_view.set_transaction(transaction)

    def _on_status_changed_expander(self, trans, status):
        if status in (STATUS_DOWNLOADING, STATUS_DOWNLOADING_REPO):
            self.mainApp._terminalExpander.set_sensitive(True)
            self.download_scrolled.show()
            if self.terminal:
                self.terminal.hide()
        elif status == STATUS_COMMITTING:
            self.download_scrolled.hide()
            if self.terminal:
                self.terminal.show()
                self.mainApp._terminalExpander.set_sensitive(True)
            else:
                self.mainApp._terminalExpander.set_expanded(False)
                self.mainApp._terminalExpander.set_sensitive(False)
        else:
            self.download_scrolled.hide()
            if self.terminal:
                self.terminal.hide()
            self.mainApp._terminalExpander.set_sensitive(False)
            self.mainApp._terminalExpander.set_expanded(False)

    def _on_terminal_attached_changed_expander(self, transaction, attached):
        """Connect the terminal to the pty device"""
        if attached and self.terminal:
            self.mainApp._terminalExpander.set_sensitive(True)
#expander
    def _run_transaction(self, transaction):
        self._setTransaction(transaction)
        self._run(None, close_on_finished=True, show_error=True,
                reply_handler=lambda: True,
                error_handler=self._on_error)

    def _simulate_trans(self, trans):
        trans.simulate(reply_handler=lambda: self._confirm_deps(trans),
                       error_handler=self._on_error)

    def _confirm_deps(self, trans):
        if [pkgs for pkgs in trans.dependencies if pkgs]:
            dia = AptConfirmDialog(trans, parent=self.mainApp._mainWindow)
            res = dia.run()
            dia.hide()
            if res != Gtk.ResponseType.OK:
                self.loop.quit()
                return
        self._run_transaction(trans)

    def _on_error(self, error):
        print("error" + str(error))
        try:
            raise error
        except aptdaemon.errors.NotAuthorizedError:
            # Silently ignore auth failures
            return
        except aptdaemon.errors.TransactionFailed as error:
            errorApt = aptdaemon.errors.TransactionFailed(ERROR_UNKNOWN,
                                                       str(error))
        except Exception as error:
            errorApt = aptdaemon.errors.TransactionFailed(ERROR_UNKNOWN,
                                                       str(error))
        if errorApt:
           dia = AptErrorDialog(errorApt, self.mainApp._mainWindow)
           dia.run()
           self.loop.quit()
           dia.hide()

    def run(self):
        self.loop.run()
    '''
    def preformUpgrade_clicked(self):
        self.ac.upgrade_system(safe_mode=False, 
                               reply_handler=self._simulate_trans,
                               error_handler=self._on_error)
        self.run()

    def preformUpdate(self):
        self.ac.update_cache(reply_handler=self._run_transaction,
                             error_handler=self._on_error)
        self.run()

    def preformInstallFile(self):
        chooser = Gtk.FileChooserDialog(parent=self.mainWindow,
                                        action=Gtk.FileChooserAction.OPEN,
                                        buttons=(Gtk.STOCK_CANCEL,
                                                 Gtk.ResponseType.CANCEL,
                                                 Gtk.STOCK_OPEN,
                                                 Gtk.ResponseType.OK))
        chooser.set_local_only(True)
        chooser.run()
        chooser.hide()
        path = chooser.get_filename()
        self.ac.install_file(path, reply_handler=self._simulate_trans,
                             error_handler=self._on_error)
        self.run()
    '''

class AptStatusIcon(Gtk.Image):
    """
    Provides a Gtk.Image which shows an icon representing the status of a
    aptdaemon transaction
    """
    def __init__(self, transaction=None, size=Gtk.IconSize.DIALOG):
        Gtk.Image.__init__(self)
        # note: icon_size is a property which you can't set with GTK 2, so use
        # a different name
        self._icon_size = size
        self.icon_name = None
        self._signals = []
        self.set_alignment(0, 0)
        if transaction is not None:
            self.set_transaction(transaction)

    def set_transaction(self, transaction):
        """Connect to the given transaction"""
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals = []
        self._signals.append(transaction.connect("status-changed",
                                                 self._on_status_changed))

    def set_icon_size(self, size):
        """Set the icon size to gtk stock icon size value"""
        self._icon_size = size

    def _on_status_changed(self, transaction, status):
        """Set the status icon according to the changed status"""
        icon_name = get_status_icon_name_from_enum(status)
        if icon_name is None:
            icon_name = Gtk.STOCK_MISSING_IMAGE
        if icon_name != self.icon_name:
            self.set_from_icon_name(icon_name, self._icon_size)
            self.icon_name = icon_name


class AptRoleIcon(AptStatusIcon):
    """
    Provides a Gtk.Image which shows an icon representing the role of an
    aptdaemon transaction
    """
    def set_transaction(self, transaction):
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals = []
        self._signals.append(transaction.connect("role-changed",
                                                 self._on_role_changed))
        self._on_role_changed(transaction, transaction.role)

    def _on_role_changed(self, transaction, role_enum):
        """Show an icon representing the role"""
        icon_name = get_role_icon_name_from_enum(role_enum)
        if icon_name is None:
            icon_name = Gtk.STOCK_MISSING_IMAGE
        if icon_name != self.icon_name:
            self.set_from_icon_name(icon_name, self._icon_size)
            self.icon_name = icon_name


class AptStatusAnimation(AptStatusIcon):
    """
    Provides a Gtk.Image which shows an animation representing the
    transaction status
    """
    def __init__(self, transaction=None, size=Gtk.IconSize.DIALOG):
        AptStatusIcon.__init__(self, transaction, size)
        self.animation = []
        self.ticker = 0
        self.frame_counter = 0
        self.iter = 0
        name = get_status_animation_name_from_enum(STATUS_WAITING)
        fallback = get_status_icon_name_from_enum(STATUS_WAITING)
        self.set_animation(name, fallback)

    def set_animation(self, name, fallback=None, size=None):
        """Show and start the animation of the given name and size"""
        if name == self.icon_name:
            return
        if size is not None:
            self._icon_size = size
        self.stop_animation()
        animation = []
        (width, height) = Gtk.icon_size_lookup(self._icon_size)
        theme = Gtk.IconTheme.get_default()
        if name is not None and theme.has_icon(name):
            pixbuf = theme.load_icon(name, width, 0)
            rows = pixbuf.get_height() / height
            cols = pixbuf.get_width() / width
            for r in range(rows):
                for c in range(cols):
                    animation.append(pixbuf.subpixbuf(c * width, r * height,
                                                      width, height))
            if len(animation) > 0:
                self.animation = animation
                self.iter = 0
                self.set_from_pixbuf(self.animation[0])
                self.start_animation()
            else:
                self.set_from_pixbuf(pixbuf)
            self.icon_name = name
        elif fallback is not None and theme.has_icon(fallback):
            self.set_from_icon_name(fallback, self._icon_size)
            self.icon_name = fallback
        else:
            self.set_from_icon_name(Gtk.STOCK_MISSING_IMAGE)

    def start_animation(self):
        """Start the animation"""
        if self.ticker == 0:
            self.ticker = GLib.timeout_add(200, self._advance)

    def stop_animation(self):
        """Stop the animation"""
        if self.ticker != 0:
            GLib.source_remove(self.ticker)
            self.ticker = 0

    def _advance(self):
        """
        Show the next frame of the animation and stop the animation if the
        widget is no longer visible
        """
        if self.get_property("visible") is False:
            self.ticker = 0
            return False
        self.iter = self.iter + 1
        if self.iter >= len(self.animation):
            self.iter = 0
        self.set_from_pixbuf(self.animation[self.iter])
        return True

    def _on_status_changed(self, transaction, status):
        """
        Set the animation according to the changed status
        """
        name = get_status_animation_name_from_enum(status)
        fallback = get_status_icon_name_from_enum(status)
        self.set_animation(name, fallback)


class AptRoleLabel(Gtk.Label):
    """
    Status label for the running aptdaemon transaction
    """
    def __init__(self, transaction=None):
        GtkLabel.__init__(self)
        self.set_alignment(0, 0)
        self.set_ellipsize(Pango.EllipsizeMode.END)
        self.set_max_width_chars(15)
        self._signals = []
        if transaction is not None:
            self.set_transaction(transaction)

    def set_transaction(self, transaction):
        """Connect the status label to the given aptdaemon transaction"""
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals = []
        self._on_role_changed(transaction, transaction.role)
        self._signals.append(transaction.connect("role-changed",
                                                 self._on_role_changed))

    def _on_role_changed(self, transaction, role):
        """Set the role text."""
        self.set_markup(get_role_localised_present_from_enum(role))


class AptStatusLabel(Gtk.Label):
    """
    Status label for the running aptdaemon transaction
    """
    def __init__(self, transaction=None):
        Gtk.Label.__init__(self)
        self.set_alignment(0, 0)
        self.set_ellipsize(Pango.EllipsizeMode.END)
        self.set_max_width_chars(15)
        self._signals = []
        if transaction is not None:
            self.set_transaction(transaction)

    def set_transaction(self, transaction):
        """Connect the status label to the given aptdaemon transaction"""
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals = []
        self._signals.append(
            transaction.connect("status-changed", self._on_status_changed))
        self._signals.append(
            transaction.connect("status-details-changed",
                                self._on_status_details_changed))

    def _on_status_changed(self, transaction, status):
        """Set the status text according to the changed status"""
        self.set_markup(get_status_string_from_enum(status))

    def _on_status_details_changed(self, transaction, text):
        """Set the status text to the one reported by apt"""
        self.set_markup(text)


class AptProgressBar(Gtk.ProgressBar):
    """
    Provides a Gtk.Progress which represents the progress of an aptdaemon
    transactions
    """
    def __init__(self, transaction=None):
        Gtk.ProgressBar.__init__(self)
        self.set_ellipsize(Pango.EllipsizeMode.END)
        self.set_text(" ")
        self.set_pulse_step(0.05)
        self._signals = []
        if transaction is not None:
            self.set_transaction(transaction)

    def set_transaction(self, transaction):
        """Connect the progress bar to the given aptdaemon transaction"""
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals = []
        self._signals.append(
            transaction.connect("finished", self._on_finished))
        self._signals.append(
            transaction.connect("progress-changed", self._on_progress_changed))
        self._signals.append(transaction.connect("progress-details-changed",
                                                 self._on_progress_details))

    def _on_progress_changed(self, transaction, progress):
        """
        Update the progress according to the latest progress information
        """
        if progress > 100:
            self.pulse()
        else:
            self.set_fraction(progress / 100.0)

    def _on_progress_details(self, transaction, items_done, items_total,
                             bytes_done, bytes_total, speed, eta):
        """
        Update the progress bar text according to the latest progress details
        """
        if items_total == 0 and bytes_total == 0:
            self.set_text(" ")
            return
        if speed != 0:
            self.set_text(_("Downloaded %sB of %sB at %sB/s") %
                          (apt_pkg.size_to_str(bytes_done),
                           apt_pkg.size_to_str(bytes_total),
                           apt_pkg.size_to_str(speed)))
        else:
            self.set_text(_("Downloaded %sB of %sB") %
                          (apt_pkg.size_to_str(bytes_done),
                           apt_pkg.size_to_str(bytes_total)))

    def _on_finished(self, transaction, exit):
        """Set the progress to 100% when the transaction is complete"""
        self.set_fraction(1)


class AptDetailsExpander(Gtk.Expander):

    def __init__(self, transaction=None, terminal=True):
        Gtk.Expander.__init__(self, label=_("Details"))
        self.show_terminal = terminal
        self._signals = []
        self.set_sensitive(False)
        self.set_expanded(False)
        if self.show_terminal:
            self.terminal = AptTerminal()
        else:
            self.terminal = None
        self.download_view = AptDownloadsView()
        self.download_scrolled = Gtk.ScrolledWindow()
        self.download_scrolled.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        self.download_scrolled.set_policy(Gtk.PolicyType.NEVER,
                                          Gtk.PolicyType.AUTOMATIC)
        self.download_scrolled.add(self.download_view)
        hbox = Gtk.HBox()
        hbox.pack_start(self.download_scrolled, True, True, 0)
        if self.terminal:
            hbox.pack_start(self.terminal, True, True, 0)
        self.add(hbox)
        if transaction is not None:
            self.set_transaction(transaction)

    def set_transaction(self, transaction):
        """Connect the status label to the given aptdaemon transaction"""
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals.append(
            transaction.connect("status-changed", self._on_status_changed))
        self._signals.append(
            transaction.connect("terminal-attached-changed",
                                self._on_terminal_attached_changed))
        if self.terminal:
            self.terminal.set_transaction(transaction)
        self.download_view.set_transaction(transaction)

    def _on_status_changed(self, trans, status):
        if status in (STATUS_DOWNLOADING, STATUS_DOWNLOADING_REPO):
            self.set_sensitive(True)
            self.download_scrolled.show()
            if self.terminal:
                self.terminal.hide()
        elif status == STATUS_COMMITTING:
            self.download_scrolled.hide()
            if self.terminal:
                self.terminal.show()
                self.set_sensitive(True)
            else:
                self.set_expanded(False)
                self.set_sensitive(False)
        else:
            self.download_scrolled.hide()
            if self.terminal:
                self.terminal.hide()
            self.set_sensitive(False)
            self.set_expanded(False)

    def _on_terminal_attached_changed(self, transaction, attached):
        """Connect the terminal to the pty device"""
        if attached and self.terminal:
            self.set_sensitive(True)


class AptTerminal(Vte.Terminal):

    def __init__(self, transaction=None):
        Vte.Terminal.__init__(self)
        self._signals = []
        self._master, self._slave = pty.openpty()
        self._ttyname = os.ttyname(self._slave)
        self.set_size(80, 24)
        self.set_pty_object(Vte.Pty.new_foreign(self._master))
        if transaction is not None:
            self.set_transaction(transaction)

    def set_transaction(self, transaction):
        """Connect the status label to the given aptdaemon transaction"""
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals.append(
            transaction.connect("terminal-attached-changed",
                                self._on_terminal_attached_changed))
        self._transaction = transaction
        self._transaction.set_terminal(self._ttyname)

    def _on_terminal_attached_changed(self, transaction, attached):
        """Show the terminal"""
        self.set_sensitive(attached)


class AptCancelButton(Gtk.Button):
    """
    Provides a Gtk.Button which allows to cancel a running aptdaemon
    transaction
    """
    def __init__(self, transaction=None):
        Gtk.Button.__init__(self)
        self.set_use_stock(True)
        self.set_label(Gtk.STOCK_CANCEL)
        self.set_sensitive(True)
        self._signals = []
        if transaction is not None:
            self.set_transaction(transaction)

    def set_transaction(self, transaction):
        """Connect the status label to the given aptdaemon transaction"""
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals = []
        self._signals.append(
            transaction.connect("finished", self._on_finished))
        self._signals.append(
            transaction.connect("cancellable-changed",
                                self._on_cancellable_changed))
        self.connect("clicked", self._on_clicked, transaction)

    def _on_cancellable_changed(self, transaction, cancellable):
        """
        Enable the button if cancel is allowed and disable it in the other case
        """
        self.set_sensitive(cancellable)

    def _on_finished(self, transaction, status):
        self.set_sensitive(False)

    def _on_clicked(self, button, transaction):
        transaction.cancel()
        self.set_sensitive(False)


class AptDownloadsView(Gtk.TreeView):

    """A Gtk.TreeView which displays the progress and status of each dowload
    of a transaction.
    """

    COL_TEXT, COL_PROGRESS, COL_URI = list(range(3))

    def __init__(self, transaction=None):
        Gtk.TreeView.__init__(self)
        model = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_INT,
                              GObject.TYPE_STRING)
        self.set_model(model)
        self.props.headers_visible = False
        self.set_rules_hint(True)
        self._download_map = {}
        self._signals = []
        if transaction is not None:
            self.set_transaction(transaction)
        cell_uri = Gtk.CellRendererText()
        cell_uri.props.ellipsize = Pango.EllipsizeMode.END
        column_download = Gtk.TreeViewColumn(_("File"))
        column_download.pack_start(cell_uri, True)
        column_download.add_attribute(cell_uri, "markup", self.COL_TEXT)
        cell_progress = Gtk.CellRendererProgress()
        #TRANSLATORS: header of the progress download column
        column_progress = Gtk.TreeViewColumn(_("%"))
        column_progress.pack_start(cell_progress, True)
        column_progress.set_cell_data_func(cell_progress, self._data_progress,
                                           None)
        self.append_column(column_progress)
        self.append_column(column_download)
        self.set_tooltip_column(self.COL_URI)

    def set_transaction(self, transaction):
        """Connect the download view to the given aptdaemon transaction"""
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals = []
        self._signals.append(transaction.connect("progress-download-changed",
                                                 self._on_download_changed))

    def _on_download_changed(self, transaction, uri, status, desc, full_size,
                             downloaded, message):
        """Callback for a changed download progress."""
        try:
            progress = int(downloaded * 100 / full_size)
        except ZeroDivisionError:
            progress = -1
        if status == DOWNLOAD_DONE:
            progress = 100
        if progress > 100:
            progress = 100
        text = desc[:]
        text += "\n<small>"
        #TRANSLATORS: %s is the full size in Bytes, e.g. 198M
        if status == DOWNLOAD_FETCHING:
            text += (_("Downloaded %sB of %sB") %
                     (apt_pkg.size_to_str(downloaded),
                     apt_pkg.size_to_str(full_size)))
        elif status == DOWNLOAD_DONE:
            if full_size != 0:
                text += _("Downloaded %sB") % apt_pkg.size_to_str(full_size)
            else:
                text += _("Downloaded")
        else:
            text += get_download_status_from_enum(status)
        text += "</small>"
        model = self.get_model()
        try:
            iter = self._download_map[uri]
        except KeyError:
            adj = self.get_vadjustment()
            is_scrolled_down = (adj.get_value() + adj.get_page_size() ==
                                adj.get_upper())
            iter = model.append((text, progress, uri))
            self._download_map[uri] = iter
            if is_scrolled_down:
                # If the treeview was scrolled to the end, do this again
                # after appending a new item
                self.scroll_to_cell(model.get_path(iter), None, False, False,
                                    False)
        else:
            model.set_value(iter, self.COL_TEXT, text)
            model.set_value(iter, self.COL_PROGRESS, progress)

    def _data_progress(self, column, cell, model, iter, data):
        progress = model.get_value(iter, self.COL_PROGRESS)
        if progress == -1:
            cell.props.pulse = progress
        else:
            cell.props.value = progress


class AptProgressDialog(Gtk.Dialog):
    """
    Complete progress dialog for long taking aptdaemon transactions, which
    features a progress bar, cancel button, status icon and label
    """

    __gsignals__ = {"finished": (GObject.SIGNAL_RUN_FIRST,
                                 GObject.TYPE_NONE, ())}

    def __init__(self, transaction=None, parent=None, terminal=True,
                 debconf=True):
        Gtk.Dialog.__init__(self, parent=parent)
        self._expanded_size = None
        self.debconf = debconf
        # Setup the dialog
        self.set_border_width(6)
        self.set_resizable(False)
        self.get_content_area().set_spacing(6)
        # Setup the cancel button
        self.button_cancel = AptCancelButton(transaction)
        self.get_action_area().pack_start(self.button_cancel, False, False, 0)
        # Setup the status icon, label and progressbar
        hbox = Gtk.HBox()
        hbox.set_spacing(12)
        hbox.set_border_width(6)
        self.icon = AptRoleIcon()
        hbox.pack_start(self.icon, False, True, 0)
        vbox = Gtk.VBox()
        vbox.set_spacing(12)
        self.label_role = Gtk.Label()
        self.label_role.set_alignment(0, 0)
        vbox.pack_start(self.label_role, False, True, 0)
        vbox_progress = Gtk.VBox()
        vbox_progress.set_spacing(6)
        self.progress = AptProgressBar()
        vbox_progress.pack_start(self.progress, False, True, 0)
        self.label = AptStatusLabel()
        self.label._on_status_changed(None, STATUS_WAITING)
        vbox_progress.pack_start(self.label, False, True, 0)
        vbox.pack_start(vbox_progress, False, True, 0)
        hbox.pack_start(vbox, True, True, 0)
        self.expander = AptDetailsExpander(terminal=terminal)
        self.expander.connect("notify::expanded", self._on_expanded)
        vbox.pack_start(self.expander, True, True, 0)
        self.get_content_area().pack_start(hbox, True, True, 0)
        self._transaction = None
        self._signals = []
        self.set_title("")
        self.realize()
        self.progress.set_size_request(350, -1)
        functions = Gdk.WMFunction.MOVE | Gdk.WMFunction.RESIZE
        try:
            self.get_window().set_functions(functions)
        except TypeError:
            # workaround for older and broken GTK typelibs
            self.get_window().set_functions(Gdk.WMFunction(functions))
        if transaction is not None:
            self.set_transaction(transaction)
        # catch ESC and behave as if cancel was clicked
        self.connect("delete-event", self._on_dialog_delete_event)

    def _on_dialog_delete_event(self, dialog, event):
        self.button_cancel.clicked()
        return True

    def _on_expanded(self, expander, param):
        # Make the dialog resizable if the expander is expanded
        # try to restore a previous size
        if not expander.get_expanded():
            self._expanded_size = (self.expander.terminal.get_visible(),
                                   self.get_size())
            self.set_resizable(False)
        elif self._expanded_size:
            self.set_resizable(True)
            term_visible, (stored_width, stored_height) = self._expanded_size
            # Check if the stored size was for the download details or
            # the terminal widget
            if term_visible != self.expander.terminal.get_visible():
                # The stored size was for the download details, so we need
                # get a new size for the terminal widget
                self._resize_to_show_details()
            else:
                self.resize(stored_width, stored_height)
        else:
            self.set_resizable(True)
            self._resize_to_show_details()

    def _resize_to_show_details(self):
        """Resize the window to show the expanded details.

        Unfortunately the expander only expands to the preferred size of the
        child widget (e.g showing all 80x24 chars of the Vte terminal) if
        the window is rendered the first time and the terminal is also visible.
        If the expander is expanded afterwards the window won't change its
        size anymore. So we have to do this manually. See LP#840942
        """
        win_width, win_height = self.get_size()
        exp_width = self.expander.get_allocation().width
        exp_height = self.expander.get_allocation().height
        if self.expander.terminal.get_visible():
            terminal_width = self.expander.terminal.get_char_width() * 80
            terminal_height = self.expander.terminal.get_char_height() * 24
            self.resize(terminal_width - exp_width + win_width,
                        terminal_height - exp_height + win_height)
        else:
            self.resize(win_width + 100, win_height + 200)

    def _on_status_changed(self, trans, status):
        # Also resize the window if we switch from download details to
        # the terminal window
        if (status == STATUS_COMMITTING and
                self.expander.terminal.get_visible()):
            self._resize_to_show_details()

    @deferable
    def run(self, attach=False, close_on_finished=True, show_error=True,
            reply_handler=None, error_handler=None):
        """Run the transaction and show the progress in the dialog.

        Keyword arguments:
        attach -- do not start the transaction but instead only monitor
                  an already running one
        close_on_finished -- if the dialog should be closed when the
                  transaction is complete
        show_error -- show a dialog with the error message
        """
        return self._run(attach, close_on_finished, show_error,
                         reply_handler, error_handler)

    @inline_callbacks
    def _run(self, attach, close_on_finished, show_error,
             reply_handler, error_handler):
        try:
            sig = self._transaction.connect("finished", self._on_finished,
                                            close_on_finished, show_error)
            self._signals.append(sig)
            if attach:
                yield self._transaction.sync()
            else:
                if self.debconf:
                    yield self._transaction.set_debconf_frontend("gnome")
                yield self._transaction.run()
            self.show_all()
        except Exception as error:
            if error_handler:
                error_handler(error)
            else:
                raise
        else:
            if reply_handler:
                reply_handler()

    def _on_role_changed(self, transaction, role_enum):
        """Show the role of the transaction in the dialog interface"""
        role = get_role_localised_present_from_enum(role_enum)
        self.set_title(role)
        self.label_role.set_markup("<big><b>%s</b></big>" % role)

    def set_transaction(self, transaction):
        """Connect the dialog to the given aptdaemon transaction"""
        for sig in self._signals:
            GLib.source_remove(sig)
        self._signals = []
        self._signals.append(
            transaction.connect_after("status-changed",
                                      self._on_status_changed))
        self._signals.append(transaction.connect("role-changed",
                                                 self._on_role_changed))
        self._signals.append(transaction.connect("medium-required",
                                                 self._on_medium_required))
        self._signals.append(transaction.connect("config-file-conflict",
                             self._on_config_file_conflict))
        self._on_role_changed(transaction, transaction.role)
        self.progress.set_transaction(transaction)
        self.icon.set_transaction(transaction)
        self.label.set_transaction(transaction)
        self.expander.set_transaction(transaction)
        self._transaction = transaction

    def _on_medium_required(self, transaction, medium, drive):
        dialog = AptMediumRequiredDialog(medium, drive, self)
        res = dialog.run()
        dialog.hide()
        if res == Gtk.ResponseType.OK:
            self._transaction.provide_medium(medium)
        else:
            self._transaction.cancel()

    def _on_config_file_conflict(self, transaction, old, new):
        dialog = AptConfigFileConflictDialog(old, new, self)
        res = dialog.run()
        dialog.hide()
        if res == Gtk.ResponseType.YES:
            self._transaction.resolve_config_file_conflict(old, "replace")
        else:
            self._transaction.resolve_config_file_conflict(old, "keep")

    def _on_finished(self, transaction, status, close, show_error):
        if close:
            self.hide()
        if status == EXIT_FAILED and show_error:
            err_dia = AptErrorDialog(self._transaction.error, self)
            err_dia.run()
            err_dia.hide()
        self.emit("finished")


class _ExpandableDialog(Gtk.Dialog):

    """Dialog with an expander."""

    def __init__(self, parent=None, stock_type=None, expanded_child=None,
                 expander_label=None, title=None, message=None, buttons=None):
        """Return an _AptDaemonDialog instance.

        Keyword arguments:
        parent -- set the dialog transient for the given Gtk.Window
        stock_type -- type of the Dialog, defaults to Gtk.STOCK_DIALOG_QUESTION
        expanded_child -- Widget which should be expanded
        expander_label -- label for the expander
        title -- a news header like title of the dialog
        message -- the message which should be shown in the dialog
        buttons -- tuple containing button text/reponse id pairs, defaults
                   to a close button
        """
        if not buttons:
            buttons = (Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        Gtk.Dialog.__init__(self, parent=parent)
        self.set_title("")
        self.add_buttons(*buttons)
        self.set_resizable(False)
        self.set_border_width(6)
        self.get_content_area().set_spacing(12)
        if not stock_type:
            stock_type = Gtk.STOCK_DIALOG_QUESTION
        icon = Gtk.Image.new_from_stock(stock_type, Gtk.IconSize.DIALOG)
        icon.set_alignment(0, 0)
        hbox_base = Gtk.HBox()
        hbox_base.set_spacing(12)
        hbox_base.set_border_width(6)
        vbox_left = Gtk.VBox()
        vbox_left.set_spacing(12)
        hbox_base.pack_start(icon, False, True, 0)
        hbox_base.pack_start(vbox_left, True, True, 0)
        self.label = Gtk.Label()
        self.label.set_selectable(True)
        self.label.set_alignment(0, 0)
        self.label.set_line_wrap(True)
        vbox_left.pack_start(self.label, False, True, 0)
        self.get_content_area().pack_start(hbox_base, True, True, 0)
        # The expander widget
        self.expander = Gtk.Expander(label=expander_label)
        self.expander.set_spacing(6)
        self.expander.set_use_underline(True)
        self.expander.connect("notify::expanded", self._on_expanded)
        self._expanded_size = None
        vbox_left.pack_start(self.expander, True, True, 0)
        # Set some initial data
        text = ""
        if title:
            text = "<b><big>%s</big></b>" % title
        if message:
            if text:
                text += "\n\n"
            text += message
        self.label.set_markup(text)
        if expanded_child:
            self.expander.add(expanded_child)
        else:
            self.expander.set_sensitive(False)

    def _on_expanded(self, expander, param):
        if expander.get_expanded():
            self.set_resizable(True)
            if self._expanded_size:
                # Workaround a random crash during progress dialog expanding
                # It seems that either the gtk.Window.get_size() method
                # doesn't always return a tuple or that the
                # gtk.Window.set_size() method doesn't correctly handle *
                # arguments correctly, see LP#898851
                try:
                    self.resize(self._expanded_size[0], self._expanded_size[1])
                except (IndexError, TypeError):
                    pass
        else:
            self._expanded_size = self.get_size()
            self.set_resizable(False)


class AptMediumRequiredDialog(Gtk.MessageDialog):

    """Dialog to ask for medium change."""

    def __init__(self, medium, drive, parent=None):
        Gtk.MessageDialog.__init__(self, parent=parent,
                                   type=Gtk.MessageType.INFO)
        #TRANSLATORS: %s represents the name of a CD or DVD
        text = _("CD/DVD '%s' is required") % medium
        #TRANSLATORS: %s is the name of the CD/DVD drive
        desc = _("Please insert the above CD/DVD into the drive '%s' to "
                 "install software packages from it.") % drive
        self.set_markup("<big><b>%s</b></big>\n\n%s" % (text, desc))
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         _("C_ontinue"), Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)


class AptConfirmDialog(Gtk.Dialog):

    """Dialog to confirm the changes that would be required by a
    transaction.
    """

    def __init__(self, trans, cache=None, parent=None):
        """Return an AptConfirmDialog instance.

        Keyword arguments:
        trans -- the transaction of which the dependencies should be shown
        cache -- an optional apt.cache.Cache() instance to provide more details
                 about packages
        parent -- set the dialog transient for the given Gtk.Window
        """
        Gtk.Dialog.__init__(self, parent=parent)
        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        self.add_button(_("C_ontinue"), Gtk.ResponseType.OK)
        self.cache = cache
        self.trans = trans
        if isinstance(parent, Gdk.Window):
            self.realize()
            self.window.set_transient_for(parent)
        else:
            self.set_transient_for(parent)
        self.set_resizable(True)
        self.set_border_width(6)
        self.get_content_area().set_spacing(12)
        icon = Gtk.Image.new_from_stock(Gtk.STOCK_DIALOG_QUESTION,
                                        Gtk.IconSize.DIALOG)
        icon.set_alignment(0, 0)
        hbox_base = Gtk.HBox()
        hbox_base.set_spacing(12)
        hbox_base.set_border_width(6)
        vbox_left = Gtk.VBox()
        vbox_left.set_spacing(12)
        hbox_base.pack_start(icon, False, True, 0)
        hbox_base.pack_start(vbox_left, True, True, 0)
        self.label = Gtk.Label()
        self.label.set_selectable(True)
        self.label.set_alignment(0, 0)
        vbox_left.pack_start(self.label, False, True, 0)
        self.get_content_area().pack_start(hbox_base, True, True, 0)
        self.treestore = Gtk.TreeStore(GObject.TYPE_STRING)
        self.treeview = Gtk.TreeView.new_with_model(self.treestore)
        self.treeview.set_headers_visible(False)
        self.treeview.set_rules_hint(True)
        self.column = Gtk.TreeViewColumn()
        self.treeview.append_column(self.column)
        cell_icon = Gtk.CellRendererPixbuf()
        self.column.pack_start(cell_icon, False)
        self.column.set_cell_data_func(cell_icon, self.render_package_icon,
                                       None)
        cell_desc = Gtk.CellRendererText()
        self.column.pack_start(cell_desc, True)
        self.column.set_cell_data_func(cell_desc, self.render_package_desc,
                                       None)
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.AUTOMATIC,
                                 Gtk.PolicyType.AUTOMATIC)
        self.scrolled.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        self.scrolled.add(self.treeview)
        vbox_left.pack_start(self.scrolled, True, True, 0)
        self.set_default_response(Gtk.ResponseType.CANCEL)

    def _show_changes(self):
        """Show a message and the dependencies in the dialog."""
        self.treestore.clear()
        for index, msg in enumerate([_("Install"),
                                     _("Reinstall"),
                                     _("Remove"),
                                     _("Purge"),
                                     _("Upgrade"),
                                     _("Downgrade"),
                                     _("Skip upgrade")]):
            if self.trans.dependencies[index]:
                piter = self.treestore.append(None, ["<b>%s</b>" % msg])
                for pkg in self.trans.dependencies[index]:
                    for object in self.map_package(pkg):
                        self.treestore.append(piter, [str(object)])
        # If there is only one type of changes (e.g. only installs) expand the
        # tree
        #FIXME: adapt the title and message accordingly
        #FIXME: Should we have different modes? Only show dependencies, only
        #       initial packages or both?
        msg = _("Please take a look at the list of changes below.")
        if len(self.treestore) == 1:
            filtered_store = self.treestore.filter_new(
                Gtk.TreePath.new_first())
            self.treeview.expand_all()
            self.treeview.set_model(filtered_store)
            self.treeview.set_show_expanders(False)
            if self.trans.dependencies[PKGS_INSTALL]:
                title = _("Additional software has to be installed")
            elif self.trans.dependencies[PKGS_REINSTALL]:
                title = _("Additional software has to be re-installed")
            elif self.trans.dependencies[PKGS_REMOVE]:
                title = _("Additional software has to be removed")
            elif self.trans.dependencies[PKGS_PURGE]:
                title = _("Additional software has to be purged")
            elif self.trans.dependencies[PKGS_UPGRADE]:
                title = _("Additional software has to be upgraded")
            elif self.trans.dependencies[PKGS_DOWNGRADE]:
                title = _("Additional software has to be downgraded")
            elif self.trans.dependencies[PKGS_KEEP]:
                title = _("Updates will be skipped")
            if len(filtered_store) < 6:
                self.set_resizable(False)
                self.scrolled.set_policy(Gtk.PolicyType.AUTOMATIC,
                                         Gtk.PolicyType.NEVER)
            else:
                self.treeview.set_size_request(350, 200)
        else:
            title = _("Additional changes are required")
            self.treeview.set_size_request(350, 200)
            self.treeview.collapse_all()
        if self.trans.download:
            msg += "\n"
            msg += (_("%sB will be downloaded in total.") %
                    apt_pkg.size_to_str(self.trans.download))
        if self.trans.space < 0:
            msg += "\n"
            msg += (_("%sB of disk space will be freed.") %
                    apt_pkg.size_to_str(self.trans.space))
        elif self.trans.space > 0:
            msg += "\n"
            msg += (_("%sB more disk space will be used.") %
                    apt_pkg.size_to_str(self.trans.space))
        self.label.set_markup("<b><big>%s</big></b>\n\n%s" % (title, msg))

    def map_package(self, pkg):
        """Map a package to a different object type, e.g. applications
        and return a list of those.

        By default return the package itself inside a list.

        Override this method if you don't want to store package names
        in the treeview.
        """
        return [pkg]

    def render_package_icon(self, column, cell, model, iter, data):
        """Data func for the Gtk.CellRendererPixbuf which shows the package.

        Override this method if you want to show custom icons for
        a package or map it to applications.
        """
        path = model.get_path(iter)
        if path.get_depth() == 0:
            cell.props.visible = False
        else:
            cell.props.visible = True
        cell.props.icon_name = "applications-other"

    def render_package_desc(self, column, cell, model, iter, data):
        """Data func for the Gtk.CellRendererText which shows the package.

        Override this method if you want to show more information about
        a package or map it to applications.
        """
        value = model.get_value(iter, 0)
        if not value:
            return
        try:
            pkg_name, pkg_version = value.split("=")[0:2]
        except ValueError:
            pkg_name = value
            pkg_version = None
        try:
            if pkg_version:
                text = "%s (%s)\n<small>%s</small>" % (
                    pkg_name, pkg_version, self.cache[pkg_name].summary)
            else:
                text = "%s\n<small>%s</small>" % (
                    pkg_name, self.cache[pkg_name].summary)
        except (KeyError, TypeError):
            if pkg_version:
                text = "%s (%s)" % (pkg_name, pkg_version)
            else:
                text = "%s" % pkg_name
        cell.set_property("markup", text)

    def run(self):
        self._show_changes()
        self.show_all()
        return Gtk.Dialog.run(self)


class AptConfigFileConflictDialog(_ExpandableDialog):

    """Dialog to resolve conflicts between local and shipped
    configuration files.
    """

    def __init__(self, from_path, to_path, parent=None):
        self.from_path = from_path
        self.to_path = to_path
        #TRANSLATORS: %s is a file path
        title = _("Replace your changes in '%s' with a later version of "
                  "the configuration file?") % from_path
        msg = _("If you don't know why the file is there already, it is "
                "usually safe to replace it.")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        self.diffview = DiffView()
        self.diffview.set_size_request(-1, 200)
        scrolled.add(self.diffview)
        _ExpandableDialog.__init__(self, parent=parent,
                                   expander_label=_("_Changes"),
                                   expanded_child=scrolled,
                                   title=title, message=msg,
                                   buttons=(_("_Keep"), Gtk.ResponseType.NO,
                                            _("_Replace"),
                                            Gtk.ResponseType.YES))
        self.set_default_response(Gtk.ResponseType.YES)

    def run(self):
        self.show_all()
        self.diffview.show_diff(self.from_path, self.to_path)
        return _ExpandableDialog.run(self)


REGEX_RANGE = "^@@ \-(?P<from_start>[0-9]+)(?:,(?P<from_context>[0-9]+))? " \
              "\+(?P<to_start>[0-9]+)(?:,(?P<to_context>[0-9]+))? @@"


class DiffView(Gtk.TextView):

    """Shows the difference between two files."""

    ELLIPSIS = "[…]\n"

    def __init__(self):
        self.textbuffer = Gtk.TextBuffer()
        Gtk.TextView.__init__(self, buffer=self.textbuffer)
        self.set_property("editable", False)
        self.set_cursor_visible(False)
        tags = self.textbuffer.get_tag_table()
        #FIXME: How to get better colors?
        tag_default = Gtk.TextTag.new("default")
        tag_default.set_properties(font="Mono")
        tags.add(tag_default)
        tag_add = Gtk.TextTag.new("add")
        tag_add.set_properties(font="Mono",
                               background='#8ae234')
        tags.add(tag_add)
        tag_remove = Gtk.TextTag.new("remove")
        tag_remove.set_properties(font="Mono",
                                  background='#ef2929')
        tags.add(tag_remove)
        tag_num = Gtk.TextTag.new("number")
        tag_num.set_properties(font="Mono",
                               background='#eee')
        tags.add(tag_num)

    def show_diff(self, from_path, to_path):
        """Show the difference between two files."""
        #FIXME: Use gio
        try:
            with open(from_path) as fp:
                from_lines = fp.readlines()
            with open(to_path) as fp:
                to_lines = fp.readlines()
        except IOError:
            return

        # helper function to work around current un-introspectability of
        # varargs methods like insert_with_tags_by_name()
        def insert_tagged_text(iter, text, tag):
            #self.textbuffer.insert_with_tags_by_name(iter, text, tag)
            offset = iter.get_offset()
            self.textbuffer.insert(iter, text)
            self.textbuffer.apply_tag_by_name(
                tag, self.textbuffer.get_iter_at_offset(offset), iter)

        line_number = 0
        iter = self.textbuffer.get_start_iter()
        for line in difflib.unified_diff(from_lines, to_lines, lineterm=""):
            if line.startswith("@@"):
                match = re.match(REGEX_RANGE, line)
                if not match:
                    continue
                line_number = int(match.group("from_start"))
                if line_number > 1:
                    insert_tagged_text(iter, self.ELLIPSIS, "default")
            elif line.startswith("---") or line.startswith("+++"):
                continue
            elif line.startswith(" "):
                line_number += 1
                insert_tagged_text(iter, str(line_number), "number")
                insert_tagged_text(iter, line, "default")
            elif line.startswith("-"):
                line_number += 1
                insert_tagged_text(iter, str(line_number), "number")
                insert_tagged_text(iter, line, "remove")
            elif line.startswith("+"):
                spaces = " " * len(str(line_number))
                insert_tagged_text(iter, spaces, "number")
                insert_tagged_text(iter, line, "add")


class _DetailsExpanderMessageDialog(_ExpandableDialog):
    """
    Common base class for Apt*Dialog
    """
    def __init__(self, text, desc, type, details=None, parent=None):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        textview = Gtk.TextView()
        textview.set_wrap_mode(Gtk.WrapMode.WORD)
        buffer = textview.get_buffer()
        scrolled.add(textview)
        #TRANSLATORS: expander label in the error dialog
        _ExpandableDialog.__init__(self, parent=parent,
                                   expander_label=_("_Details"),
                                   expanded_child=scrolled,
                                   title=text, message=desc,
                                   stock_type=type)
        self.show_all()
        if details:
            buffer.insert_at_cursor(details)
        else:
            self.expander.set_visible(False)


class AptErrorDialog(_DetailsExpanderMessageDialog):
    """
    Dialog for aptdaemon errors with details in an expandable text view
    """
    def __init__(self, error=None, parent=None):
        text = get_error_string_from_enum(error.code)
        desc = get_error_description_from_enum(error.code)
        _DetailsExpanderMessageDialog.__init__(
            self, text, desc, Gtk.STOCK_DIALOG_ERROR, error.details, parent)
