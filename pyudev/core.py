# -*- coding: utf-8 -*-
# Copyright (C) 2010, 2011 Sebastian Wiesner <lunaryorn@googlemail.com>

# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by the
# Free Software Foundation; either version 2.1 of the License, or (at your
# option) any later version.

# This library is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License
# for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, write to the Free Software Foundation,
# Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA


"""
    pyudev.core
    ===========

    Core types and functions of :mod:`pyudev`.

    .. moduleauthor::  Sebastian Wiesner  <lunaryorn@googlemail.com>
"""


from __future__ import (print_function, division, unicode_literals,
                        absolute_import)

try:
    from subprocess import check_output
except ImportError:
    from pyudev._compat import check_output

from pyudev.device import Device
from pyudev._libudev import libudev
from pyudev._util import (ensure_unicode_string, ensure_byte_string,
                          udev_list_iterate, property_value_to_bytes)


__all__ = ['udev_version', 'Context', 'Enumerator']


def udev_version():
    """
    Get the version of the underlying udev library.

    udev doesn't use a standard major-minor versioning scheme, but instead
    labels releases with a single consecutive number.  Consequently, the
    version number returned by this function is a single integer, and not a
    tuple (like for instance the interpreter version in
    :data:`sys.version_info`).

    As libudev itself does not provide a function to query the version number,
    this function calls the ``udevadm`` utilitiy, so be prepared to catch
    :exc:`~exceptions.EnvironmentError` and
    :exc:`~subprocess.CalledProcessError` if you call this function.

    Return the version number as single integer.  Raise
    :exc:`~exceptions.ValueError`, if the version number retrieved from udev
    could not be converted to an integer.  Raise
    :exc:`~exceptions.EnvironmentError`, if ``udevadm`` was not found, or could
    not be executed.  Raise :exc:`subprocess.CalledProcessError`, if
    ``udevadm`` returned a non-zero exit code.  On Python 2.7 or newer, the
    ``output`` attribute of this exception is correctly set.

    .. versionadded:: 0.8
    """
    output = ensure_unicode_string(check_output(['udevadm', '--version']))
    return int(output.strip())


class Context(object):
    """
    The udev context.

    This is *the* central object to access udev.  An instance of this class
    must be created before anything else can be done.  It holds the udev
    configuration and provides the interface to list devices (see
    :meth:`list_devices`).

    Instances of this class can directly be given as ``udev *`` to functions
    wrapped through :mod:`ctypes`.
    """

    def __init__(self):
        """
        Create a new context.
        """
        self._as_parameter_ = libudev.udev_new()

    def __del__(self):
        libudev.udev_unref(self)

    @property
    def sys_path(self):
        """
        The ``sysfs`` mount point defaulting to ``/sys'`` as unicode string.

        The mount point can be overwritten using the environment variable
        :envvar:`SYSFS_PATH`.  Use this for testing purposes.
        """
        return ensure_unicode_string(libudev.udev_get_sys_path(self))

    @property
    def device_path(self):
        """
        The device directory path defaulting to ``/dev`` as unicode string.

        This can be overridden in the udev configuration.
        """
        return ensure_unicode_string(libudev.udev_get_dev_path(self))

    @property
    def run_path(self):
        """
        The run runtime directory path defaulting to ``/run`` as unicode
        string.

        .. udevversion:: 167

        .. versionadded:: 0.10
        """
        return ensure_unicode_string(libudev.udev_get_run_path(self))

    @property
    def log_priority(self):
        """
        The logging priority of the interal logging facitility of udev as
        integer with a standard :mod:`syslog` priority.  Assign to this
        property to change the logging priority.

        UDev uses the standard :mod:`syslog` priorities.  Constants for these
        priorities are defined in the :mod:`syslog` module in the standard
        library:

        >>> import syslog
        >>> context = pyudev.Context()
        >>> context.log_priority = syslog.LOG_DEBUG

        .. versionadded:: 0.9
        """
        return libudev.udev_get_log_priority(self)

    @log_priority.setter
    def log_priority(self, value):
        libudev.udev_set_log_priority(self, value)

    def list_devices(self, **kwargs):
        """
        List all available devices.

        The arguments of this method are the same as for
        :meth:`Enumerator.match()`.  In fact, the arguments are simply passed
        straight to method :meth:`~Enumerator.match()`.

        This function creates and returns an :class:`Enumerator` object,
        that can be used to filter the list of devices, and eventually
        retrieve :class:`Device` objects representing matching devices.

        .. versionchanged:: 0.8
           Accept keyword arguments now for easy matching
        """
        return Enumerator(self).match(**kwargs)


class Enumerator(object):
    """
    Enumerate all available devices.

    To retrieve devices, simply iterate over an instance of this class.
    This operation yields :class:`Device` objects representing the available
    devices.

    Before iteration the device list can be filtered by subsystem or by
    property values using :meth:`match_subsystem` and
    :meth:`match_property`.  Multiple subsystem (property) filters are
    combined using a logical OR, filters of different types are combined
    using a logical AND.  The following filter for instance::

        devices.match_subsystem('block').match_property(
            'ID_TYPE', 'disk').match_property('DEVTYPE', 'disk')

    means the following::

        subsystem == 'block' and (ID_TYPE == 'disk' or DEVTYPE == 'disk')

    Once added, a filter cannot be removed anymore.  Create a new object
    instead.

    Instances of this class can directly be given as given ``udev_enumerate *``
    to functions wrapped through :mod:`ctypes`.
    """

    def __init__(self, context):
        """
        Create a new enumerator with the given ``context`` (a
        :class:`Context` instance).

        While you can create objects of this class directly, this is not
        recommended.  Call :method:`Context.list_devices()` instead.
        """
        if not isinstance(context, Context):
            raise TypeError('Invalid context object')
        self.context = context
        self._as_parameter_ = libudev.udev_enumerate_new(context)

    def __del__(self):
        libudev.udev_enumerate_unref(self)

    def match(self, **kwargs):
        """
        Include devices according to the rules defined by the keyword
        arguments.  These keyword arguments are interpreted as follows:

        - The value for the keyword argument ``subsystem`` is forwarded to
          :meth:`match_subsystem()`.
        - The value for the keyword argument ``sys_name`` is forwared to
          :meth:`match_sys_name()`.
        - The value for the keyword argument ``tag`` is forwared to
          :meth:`match_tag()`.
        - The value for the keyword argument ``parent`` is forwared to
          :meth:`match_parent()`.
        - All other keyword arguments are forwareded one by one to
          :meth:`match_property()`.  The keyword argument itself is interpreted
          as property name, the value of the keyword argument as the property
          value.

        All keyword arguments are optional, calling this method without no
        arguments at all is simply a noop.

        Return the instance again.

        .. versionadded:: 0.8

        .. versionchanged:: 0.13
           Added ``parent`` keyword
        """
        subsystem = kwargs.pop('subsystem', None)
        if subsystem is not None:
            self.match_subsystem(subsystem)
        sys_name = kwargs.pop('sys_name', None)
        if sys_name is not None:
            self.match_sys_name(sys_name)
        tag = kwargs.pop('tag', None)
        if tag is not None:
            self.match_tag(tag)
        parent = kwargs.pop('parent', None)
        if parent is not None:
            self.match_parent(parent)
        for property, value in kwargs.iteritems():
            self.match_property(property, value)
        return self

    def match_subsystem(self, subsystem):
        """
        Include all devices, which are part of the given ``subsystem``.

        ``subsystem`` is either a unicode string or a byte string,
        containing the name of the subsystem.

        Return the instance again.
        """
        libudev.udev_enumerate_add_match_subsystem(
            self, ensure_byte_string(subsystem))
        return self

    def match_sys_name(self, sys_name):
        """
        Include all devices with the given name.

        ``sys_name`` is a byte or unicode string containing the device name.

        Return the instance again.

        .. versionadded:: 0.8
        """
        libudev.udev_enumerate_add_match_sysname(
            self, ensure_byte_string(sys_name))
        return self

    def match_property(self, property, value):
        """
        Include all devices, whose ``property`` has the given ``value``.

        ``property`` is either a unicode string or a byte string, containing
        the name of the property to match.  ``value`` is a property value,
        being one of the following types:

        - :func:`int`
        - :func:`bool`
        - A byte string
        - Anything convertable to a unicode string (including a unicode string
          itself)

        Return the instance again.
        """
        libudev.udev_enumerate_add_match_property(
            self, ensure_byte_string(property), property_value_to_bytes(value))
        return self

    def match_attribute(self, attribute, value):
        """
        Include all devices, whose ``attribute`` has the given ``value``.

        ``attribute`` is either a unicode string or a byte string, containing
        the name of a sys attribute to match.  ``value`` is an attribute value,
        being one of the following types:

        - :func:`int`,
        - :func:`bool`
        - A byte string
        - Anything convertable to a unicode string (including a unicode string
          itself)

        Return the instance again.
        """
        libudev.udev_enumerate_add_match_sysattr(
            self, ensure_byte_string(attribute),
            property_value_to_bytes(value))
        return self

    def match_tag(self, tag):
        """
        Include all devices, which have the given ``tag`` attached.

        ``tag`` is a byte or unicode string containing the tag name.

        Return the instance again.

        .. udevversion:: 154

        .. versionadded:: 0.6
        """
        libudev.udev_enumerate_add_match_tag(self, ensure_byte_string(tag))
        return self

    def match_is_initialized(self):
        """
        Include only devices, which are initialized.

        Initialized devices have properly set device node permissions and
        context, and are (in case of network devices) fully renamed.

        Currently this will not affect devices which do not have device nodes
        and are not network interfaces.

        Return the instance again.

        .. seealso:: :attr:`Device.is_initialized`

        .. udevversion:: 165

        .. versionadded:: 0.8
        """
        libudev.udev_enumerate_add_match_is_initialized(self)
        return self

    def match_parent(self, parent):
        """
        Include all devices on the subtree of the given ``parent`` device.

        The ``parent`` device itself is also included.

        ``parent`` is a :class:`~pyudev.Device`.

        Return the instance again.

        .. udevversion:: 172

        .. versionadded:: 0.13
        """
        libudev.udev_enumerate_add_match_parent(self, parent)
        return self

    def __iter__(self):
        """
        Iterate over all matching devices.

        Yield :class:`Device` objects.
        """
        libudev.udev_enumerate_scan_devices(self)
        entry = libudev.udev_enumerate_get_list_entry(self)
        for name, _ in udev_list_iterate(entry):
            yield Device.from_sys_path(self.context, name)
