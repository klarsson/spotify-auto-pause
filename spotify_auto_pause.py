#! /usr/bin/env python3
"""
Pause spotify if another media player starts playing, and resume when it stops.
"""
import logging
import dbus.exceptions
import signal
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from dbus import Interface, SessionBus
from argparse import ArgumentParser

STATUS_PAUSED = 'Paused'
STATUS_PLAYING = 'Playing'
STATUS_STOPPED = 'Stopped'

MEDIA_PLAYER_PATH = '/org/mpris/MediaPlayer2'
DBUS_PATH = '/org/freedesktop/DBus'
DBUS_INTERFACE_NAME = 'org.freedesktop.DBus'
PLAYER_INTERFACE_NAME = 'org.mpris.MediaPlayer2.Player'
PROPERTIES_INTERFACE_NAME = 'org.freedesktop.DBus.Properties'
SPOTIFY_NAME = 'org.mpris.MediaPlayer2.spotify'

spotify_player = None
spotify_properties = None
is_spotify_running = False
was_playing = False
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


def on_properties_changed(interface_name, changed_properties, invalidated_properties, **call_args):
    if not is_spotify_running:
        log.debug("Nothing to do, spotify is not running.")
        return

    sender = call_args.get('sender')
    playback_status = changed_properties.get('PlaybackStatus')

    log.debug(
        "Properties changed.",
        {'interface_name': interface_name, 'sender': sender, 'playback_status': playback_status}
    )

    if (playback_status == STATUS_PLAYING or playback_status == STATUS_PAUSED) and not is_spotify(sender):
        play_pause_spotify(playback_status)


def is_spotify(sender):
    sender_object = bus.get_object(sender, MEDIA_PLAYER_PATH)
    identity = sender_object.Get('org.mpris.MediaPlayer2', 'Identity', dbus_interface=PROPERTIES_INTERFACE_NAME)

    return identity == 'Spotify'


def play_pause_spotify(playback_status):
    global was_playing

    if playback_status == STATUS_PLAYING:
        log.info("Pausing spotify.")
        was_playing = spotify_properties.Get(PLAYER_INTERFACE_NAME, 'PlaybackStatus') == STATUS_PLAYING
        spotify_player.Pause()
    elif was_playing and (playback_status == STATUS_PAUSED or playback_status == STATUS_STOPPED):
        log.info("Resuming playing.")
        spotify_player.Play()


def setup_spotify_interfaces():
    global spotify_player, spotify_properties, is_spotify_running

    try:
        spotify_object = bus.get_object(SPOTIFY_NAME, MEDIA_PLAYER_PATH)
        spotify_player = Interface(spotify_object, dbus_interface=PLAYER_INTERFACE_NAME)
        spotify_properties = Interface(spotify_object, dbus_interface=PROPERTIES_INTERFACE_NAME)
        is_spotify_running = True
    except dbus.exceptions.DBusException as e:
        log.info("Spotify not running.", e)


def on_name_owner_changed(name, old_owner, new_owner):
    if name == SPOTIFY_NAME:
        log.info("Spotify started.")
        setup_spotify_interfaces()


def on_name_lost(name):
    global spotify_player, spotify_properties, is_spotify_running

    if name == SPOTIFY_NAME:
        log.info("Spotify exited.")
        spotify_player = None
        spotify_properties = None
        is_spotify_running = False


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('-v', '--verbose', help="Verbose output, use twice for very verbose.", action='count')
    args = parser.parse_args()

    logging.basicConfig(
        level=[logging.WARNING, logging.INFO, logging.DEBUG][max(args.verbose or 0, 2)],
        format='%(levelname)s::%(message)s: %(args)s'
    )

    DBusGMainLoop(set_as_default=True)
    loop = GLib.MainLoop()
    signal.signal(signal.SIGTERM, lambda signal_number, stack_frame: loop.quit())

    bus = SessionBus()
    media_player_bus_object = bus.get_object(None, MEDIA_PLAYER_PATH)
    media_player_property_interface = Interface(media_player_bus_object, dbus_interface=PROPERTIES_INTERFACE_NAME)
    media_player_property_interface.connect_to_signal(
        'PropertiesChanged',
        on_properties_changed,
        sender_keyword='sender'
    )

    dbus_bus_object = bus.get_object('org.freedesktop.DBus', DBUS_PATH)
    dbus_interface = Interface(dbus_bus_object, dbus_interface=DBUS_INTERFACE_NAME)
    dbus_interface.connect_to_signal('NameOwnerChanged', on_name_owner_changed)
    dbus_interface.connect_to_signal('NameLost', on_name_lost)

    setup_spotify_interfaces()

    log.debug('starting')
    loop.run()
