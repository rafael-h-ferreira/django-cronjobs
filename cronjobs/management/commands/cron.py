import atexit
import logging
import os
import sys
import imp
import tempfile
from importlib import import_module

from django.conf import settings
from django.core.management.base import BaseCommand

import cronjobs


log = logging.getLogger('cron')

LOCK = getattr(settings, 'CRONJOB_LOCK_PREFIX', 'lock')
DEBUG = getattr(settings, 'DEBUG', False)

class Command(BaseCommand):
    help = 'Run a script, often a cronjob'
    args = '[name args...]'

    def add_arguments(self, parser):
        parser.add_argument('argz', nargs='+')

    def handle(self, *args, **opts):
        # Load up all the cron scripts.
        for app in settings.INSTALLED_APPS:
            try:
                app_path = import_module(app).__path__
            except AttributeError:
                continue

            try:
                imp.find_module('cron', app_path)
            except ImportError as e:
                continue

            import_module('%s.cron' % app)

        registered = cronjobs.registered

        if not args and not opts['argz']:
            log.error("Cron called but doesn't know what to do.")
            if DEBUG:
                sys.stdout.write('Try one of these:\n%s\n' % '\n'.join(sorted(registered)))
            sys.exit(1)

        argz = opts['argz']

        script, args = argz[0], argz[1:]
        if script not in registered:
            log.error("Cron called with unrecognized command: %s %s" %
                      (script, args))
            if DEBUG:
                sys.stdout.write('Unrecognized name: %s\n' % script)
            sys.exit(1)

        # Acquire lock if needed.
        if script in cronjobs.registered_lock:
            filename = os.path.join(tempfile.gettempdir(),
                                    'django_cron.%s.%s' % (LOCK, script))
            try:
                fd = os.open(filename, os.O_CREAT|os.O_EXCL)

                def register():
                    os.close(fd)
                    os.remove(filename)

                atexit.register(register)
            except OSError:
                msg = ("Script run multiple times. If this isn't true, delete "
                       "`%s`." % filename)
                log.error(msg)
                sys.stderr.write(msg + "\n")
                sys.exit(1)

        log.info("Beginning job: %s %s" % (script, args))
        try:
            registered[script](*args)
        except Exception as e:
            log.error('Task %s raised exception %s' % (script, e))
        log.info("Ending job: %s %s" % (script, args))
