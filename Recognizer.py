# This is part of Blather
# -- this code is licensed GPLv3
# Copyright 2013 Jezra

import pygst
pygst.require('0.10')
import gst
import os.path
import gobject
import urllib2
import json

# define some global variables
this_dir = os.path.dirname(os.path.abspath(__file__))


class Recognizer(gobject.GObject):
    __gsignals__ = {
        'finished_cmd': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING,)),
        'finished_gsr': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING,))
    }

    def __init__(self, language_file, dictionary_file, src=None):
        gobject.GObject.__init__(self)
        self.commands = {}
        self.buffers = []
        if src:
            audio_src = 'alsasrc device="%s"' % (src)
        else:
            audio_src = 'autoaudiosrc'

        # build the pipeline
        # cmd = audio_src + ' ! audioconvert ! audioresample ! vader name=vad ! pocketsphinx name=asr ! appsink sync=false'
        self.pipeline = gst.parse_launch(audio_src +
            # 'udpsrc port=5000'
            # ' ! flacdec'
            ' ! audioconvert'
            ' ! audioresample'
            # ' ! audioamplify amplification=1.2'
            ' ! output-selector name=osel'
            ' osel.src0'
                ' ! queue'
                ' ! vader name=vad0 auto-threshold=true'
                ' ! pocketsphinx name=asr'
                ' ! appsink async=false sync=false'
            ' osel.src1'
                ' ! queue'
                ' ! vader name=vad1 run-length=1200000000'
                ' ! flacenc name=flc'
                ' ! appsink name=app async=false sync=false emit-signals=true'
        )

        asr = self.pipeline.get_by_name('asr')
        asr.connect('result', self.result)
        asr.set_property('lm', language_file)
        asr.set_property('dict', dictionary_file)
        asr.set_property('configured', True)

        self.appsink =  self.pipeline.get_by_name('app')
        self.appsink.connect('new-buffer', self.add_buffer)

        self.vad0 = self.pipeline.get_by_name('vad0')
        self.vad1 = self.pipeline.get_by_name('vad1')
        self.vad1.connect('vader-stop', self.vstop)

        self.osel = self.pipeline.get_by_name('osel')

    def add_buffer(self, sink):
        # print 'appsink'
        buf = sink.emit('pull-buffer')
        self.buffers.append(buf)

    def switch_to(self, padname):
        # print 'switch to %s' % padname
        if padname == 'src1':
            self.pipeline.get_by_name('flc').set_state(gst.STATE_PLAYING)
        else:
            self.pipeline.get_by_name('flc').set_state(gst.STATE_NULL)

        self.osel.set_property('active-pad', self.osel.get_pad(padname))

    def listen(self):
        print 'Waiting for awake_command'
        self.pipeline.set_state(gst.STATE_PLAYING)

    def pause(self):
        self.vad0.set_property('silent', True)
        self.vad1.set_property('silent', True)
        self.pipeline.set_state(gst.STATE_PAUSED)

    def result(self, asr, text, uttid):
        # emit finished
        self.emit("finished_cmd", text)

    def vstart(self, arg, data):
        print "start vader"

    def vstop(self, arg, data):
        # print "stop vader"
        # print self.buffers
        self.pause()
        text = self.to_text()
        print 'You said:', text
        if text:
            self.emit("finished_gsr", text)
        self.buffers = []
        self.switch_to('src0')
        self.listen()

    def to_text(self):
        url = "http://www.google.com/speech-api/v1/recognize?lang=en-us"
        audio = b''.join(b.data for b in self.buffers)

        header = {"Content-Type": "audio/x-flac; rate=8000"}
        req = urllib2.Request(url, audio, header)

        try:
            resp = urllib2.urlopen(req, timeout=30)
            js_data = json.loads(resp.read())
        except urllib2.URLError:
            print '[Warning] Problems with internet connection.'
            return None
        except ValueError:
            print '[Warning] Something went wrong.'
            return None

        if js_data['status'] == 0:
            return js_data['hypotheses'][0]['utterance']
        else:
            return None
        # phrase = json.loads(response)['hypotheses'][0]['utterance']
        # print response