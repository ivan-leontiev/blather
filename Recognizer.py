# This is part of Blather
# -- this code is licensed GPLv3
# Copyright 2013 Jezra

import pygst
pygst.require('0.10')
import gst
import os.path
import time
import gobject

# define some global variables
this_dir = os.path.dirname(os.path.abspath(__file__))


def init_pipeline(pipeline, lf, df, result):
    # get the Auto Speech Recognition piece
    asr = pipeline.get_by_name('asr')
    asr.connect('result', result)
    asr.set_property('lm', lf)
    asr.set_property('dict', df)
    asr.set_property('configured', True)


class Recognizer(gobject.GObject):
    __gsignals__ = {
        'finished': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING, gobject.TYPE_BOOLEAN))
    }

    def __init__(self, lang_file, dic_file, sys_l, sys_d, src=None):
        gobject.GObject.__init__(self)
        self.__active = False
        # self.commands = {}
        if src:
            # audio_src = 'alsasrc slave-method=3'
            audio_src = 'alsasrc device="%s"' % (src)
        else:
            audio_src = 'alsasrc device="default"'

        # build the pipeline
        cmd = audio_src + ' ! audioconvert ! audioresample ! vader name=vad ! pocketsphinx name=asr ! appsink sync=false'
        gst.debug_set_default_threshold(gst.LEVEL_DEBUG)

        self.sys_pipeline = gst.parse_launch(cmd)

        init_pipeline(self.sys_pipeline, sys_l, sys_d, self.result)

        # get the Voice Activity DEtectoR

        self.sys_vad = self.sys_pipeline.get_by_name('vad')
        self.sys_vad.set_property('auto-threshold', True)

        self.pipeline = gst.parse_launch(cmd)
        init_pipeline(self.pipeline, lang_file, dic_file, self.result)

        self.vad = self.pipeline.get_by_name('vad')
        self.vad.set_property('auto-threshold', True)

    def suspend(self):
        self.vad.set_property('silent', True)
        # self.pipeline.set_state(gst.STATE_READY)
        self.listen()

    def listen(self):
        self.__active = False
        print 'Waiting for awake_command'
        self.sys_pipeline.set_state(gst.STATE_PLAYING)

    def activate_listen(self):
        self.__active = True
        self.sys_vad.set_property('silent', True)
        self.sys_pipeline.set_state(gst.STATE_NULL)
        self.pipeline.set_state(gst.STATE_PLAYING)

    def pause(self):
        self.vad.set_property('silent', True)
        self.sys_pipeline.set_state(gst.STATE_NULL)
        self.pipeline.set_state(gst.STATE_NULL)

    def result(self, asr, text, uttid):
        # emit finished
        self.emit("finished", text, self.__active)
