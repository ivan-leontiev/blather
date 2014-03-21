#!/usr/bin/env python2

# -- this code is licensed GPLv3
# Copyright 2013 Jezra

import sys
import signal
import gobject
import os.path
import subprocess
import re
import urllib
import functools

from multipartfd import *
from optparse import OptionParser


__config_options = {
    'awake_command': True,
    'bad_cmd1': False,
    'bad_cmd2': False
}

# where are the files?

def set_config(dir="~/.config/blather"):
    global conf_dir, lang_dir, command_file, history_file, lang_file, dic_file

    conf_dir = os.path.expanduser(dir)
    lang_dir = os.path.join(conf_dir, "language")
    # make the lang_dir if it doesn't exist
    if not os.path.exists(lang_dir):
        os.makedirs(lang_dir)
    command_file = os.path.join(conf_dir, "commands.conf")
    # strings_file = os.path.join(conf_dir, "sentences.corpus")
    history_file = os.path.join(conf_dir, "blather.history")
    lang_file = os.path.join(lang_dir, 'lm')
    dic_file = os.path.join(lang_dir, 'dic')
    # sys_l = os.path.join(lang_dir, 'sys.lm')
    # sys_d = os.path.join(lang_dir, 'sys.dic')

set_config()


class Blather:

    def __init__(self, opts):
        # import the recognizer so Gst doesn't clobber our -h

        from Recognizer import Recognizer
        self.ui = None
        # keep track of the opts
        self.opts = opts
        self.__active = False
        ui_continuous_listen = False
        self.continuous_listen = False
        self.read_commands()
        self.recognizer = Recognizer(lang_file, dic_file, opts.microphone)
        self.recognizer.connect('finished', self.recognizer_finished)

        if opts.interface is not None:
            if opts.interface == "q":
                # import the ui from qt
                from QtUI import UI
            elif opts.interface == "g":
                from GtkUI import UI
            else:
                print "no GUI defined"
                sys.exit()

            self.ui = UI(args, opts.continuous)
            self.ui.connect("command", self.process_command)
            # can we load the icon resource?
            icon = self.load_resource("icon.png")
            if icon:
                self.ui.set_icon(icon)

        if self.opts.history:
            self.history = []

    def read_commands(self):
        sysd, comd = parse_config()
        self.commands = comd
        self.sys_commands = sysd

    def log_history(self, text):
        if self.opts.history:
            self.history.append(text)
            if len(self.history) > self.opts.history:
            # pop off the first item
                self.history.pop(0)

            # open and truncate the blather history file
            hfile = open(history_file, "w")
            for line in self.history:
                hfile.write(line + "\n")
            # close the  file
            hfile.close()

    def recognizer_finished(self, recognizer, text):
        t = text.lower()
        # is there a matching command?
        if self.__active:
            if t in self.commands:
                print 'command: ' + t
                subprocess.call('espeak "running the %s command"' % t, shell=True)
                subprocess.call(self.commands[t], shell=True)
                self.log_history(text)
                self.__active = False
                print 'Waiting for awake_command'
            else:
                # if 'bad_cmd2' in self.sys_commands['events']:
                #     subprocess.call(self.sys_commands['events']['bad_cmd2'], shell=True)
                subprocess.call('espeak "Whaat?"', shell=True)
                print 'no matching command: ' + t
            # if there is a UI and we are not continuous listen
            if self.ui:
                if not self.continuous_listen:
                    # stop listening
                    self.recognizer.pause()
                # let the UI know that there is a finish
                self.ui.finished(t)
        else:
            # print t
            if t in self.sys_commands['vcmds']:
                self.__active = True
                subprocess.call(self.sys_commands['vcmds'][t], shell=True)
                # subprocess.call('espeak "Yes!"', shell=True)
                print 'Listening...'
            else:
                # if 'bad_cmd1' in self.sys_commands['events']:
                    # subprocess.call(self.sys_commands['events']['bad_cmd1'], shell=True)
                subprocess.call('espeak "Wrong"', shell=True)
                print 'no matching command: ' + t

    def run(self):
        if self.ui:
            self.ui.run()
        else:
            print 'Waiting for awake_command'
            blather.recognizer.listen()

    def quit(self):
        sys.exit()

    def process_command(self, UI, command):
        print command
        if command == "listen":
            self.recognizer.listen()
        elif command == "stop":
            self.recognizer.pause()
        elif command == "continuous_listen":
            self.continuous_listen = True
            self.recognizer.listen()
        elif command == "continuous_stop":
            self.continuous_listen = False
            self.recognizer.pause()
        elif command == "quit":
            self.quit()

    def load_resource(self, string):
        local_data = os.path.join(os.path.dirname(__file__), 'data')
        paths = ["/usr/share/blather/", "/usr/local/share/blather", local_data]
        for path in paths:
            resource = os.path.join(path, string)
            if os.path.exists(resource):
                return resource
        # if we get this far, no resource was found
        return False


def parse_config():
    sdict = {}
    ndict = {}
    sdict['vcmds'] = {}
    sdict['events'] = {}

    with open(command_file, 'r') as config:
        for line in config:
            line = line.strip()

            if not len(line) or line[0] == '#':
                continue

            if line[0] == ':':
                key, value = line[1:].split('=', 1)
                key, value = key.strip(), value.strip()

                if key not in __config_options:
                    continue

                if __config_options[key]:
                    # system voice command
                    k, v = value.split(':', 1)
                    sdict['vcmds'][k.strip()] = v.strip()
                else:
                    sdict['events'][key] = value
            else:
                key, value = line.split(":", 1)
                ndict[key.strip()] = value.strip()

    return (sdict, ndict)


def update_voice_commands():
    cmds = {}
    sd, nd = parse_config()
    cmds.update(nd)
    cmds.update(sd['vcmds'])
    if 'vcmds' not in sd:
        print 'You need to specify awake_command'

    load_lm('\n'.join(cmds))


def load_lm(content):
    lmhost = 'www.speech.cs.cmu.edu'
    lmselector = '/cgi-bin/tools/lmtool/run'
    fields = [('formtype', 'simple')]
    sfile = [('corpus', content)]

    _, headers, _, _ = post_multipart(lmhost, lmselector, fields, sfile)
    page = urllib.urlopen(headers['Location']).read()

    bn_rgx = re.compile(r'<b>(\d+)</b>')
    match = bn_rgx.search(page)
    cid = match.group(1)

    # if syst:
    urllib.urlretrieve(headers['Location'] + cid + '.lm', lang_file)
    urllib.urlretrieve(headers['Location'] + cid + '.dic', dic_file)
    # else:
    #     urllib.urlretrieve(headers['Location'] + cid + '.lm', lang_file)
    #     urllib.urlretrieve(headers['Location'] + cid + '.dic', dic_file)


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-d", "--config-dir", type="string", dest="config",
                      action='store',
                      help="path to config dir")
    parser.add_option("-i", "--interface", type="string", dest="interface",
                      action='store',
                      help="Interface to use (if any). 'q' for Qt, 'g' for GTK")
    parser.add_option("-c", "--continuous",
                      action="store_true", dest="continuous", default=False,
                      help="starts interface with 'continuous' listen enabled")
    parser.add_option("-H", "--history", type="int",
                      action="store", dest="history",
                      help="number of commands to store in history file")
    parser.add_option("-m", "--microphone", type="string",
                      action="store", dest="microphone", default=None,
                      help="Audio input device to use (if other than system default)")
    parser.add_option("-u", "--update",
                      action="store_true", dest="update", default=False,
                      help="Update list of voice commands")

    (options, args) = parser.parse_args()

    if options.config is not None:
        set_config(options.config)

    if options.update:
        update_voice_commands()
        exit(0)

    if not functools.reduce(bool.__and__, map(os.path.exists,
                                              [lang_file, dic_file])):
        print 'You should call with --update firstly'
        exit(1)

    # make our blather object
    blather = Blather(options)

    # init gobject threads
    gobject.threads_init()

    # we want a main loop
    main_loop = gobject.MainLoop()

    # handle sigint
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # run the blather
    blather.run()

    # start the main loop
    try:
        main_loop.run()
    except:
        print "time to quit"
        main_loop.quit()
        sys.exit()
