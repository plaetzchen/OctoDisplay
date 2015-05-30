#!/usr/bin/python
# -*- coding: utf-8 -*-
          
import urwid
import psutil
import getopt
import sys
import requests
import Queue
import threading
import time
import logging
import signal

logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)-4s %(threadName)s %(message)s", 
    datefmt="%H:%M:%S",
    filename='octodisplay.log',
)

class OctoDisplayWindow:
    """The class that holds all UI elements and updates them"""
    palette = [
        ('banner', 'white', 'dark green'),
        ('streak', 'white', 'dark green'),
        ('bg', 'black', 'black'),
        ('pg normal',    'white',      'white'),
        ('pg complete',  'white',      'dark green', 'standout'),
        ('temp', 'dark green', 'black', 'bold'),
        ('time', 'dark green', 'black', 'bold')]
    pbar = None
    txt = None
    loop = None
        
    def __init__(self, msg_queue):
        self.setupUI()
        self.msg_queue = msg_queue
        self.check_messages(self.loop, None)
    
    def setupUI(self):
        self.txt = urwid.Text(('banner', u" OctoPrint "), align='center')
        map1 = urwid.AttrMap(self.txt, 'streak')
        fill = urwid.Filler(map1,'top')
        map2 = urwid.AttrMap(fill, 'bg')
        self.timetxt = urwid.Text(('time', u"00:00:00h left"), align='center')
        timefill = urwid.Filler(self.timetxt,'middle')
        timemap = urwid.AttrMap(timefill, 'bg')
        self.pbar = urwid.ProgressBar('pg normal', 'pg complete')
        self.pbar.set_completion(0)
        pbarfill = urwid.Filler(self.pbar,'top')
        map3 = urwid.AttrMap(pbarfill, 'bg')
        self.temptxt = urwid.Text(('temp', u"Extruder: ?°C / ?°C\nBed: ?°C / ?°C"), align='center')
        tempfill = urwid.Filler(self.temptxt, 'middle')
        map4 = urwid.AttrMap(tempfill, 'bg')
        self.loop = urwid.MainLoop(urwid.Pile([map2,timemap,map3,map4]), self.palette, unhandled_input=self.exit_on_q)
        
    def update_progress(self,progress):
        self.pbar.set_completion(progress)
    
    def update_time_left(self, time_left, job_name):
        self.timetxt.set_text(('time', u"{0}\n{1}h left".format(job_name,time_left)))
        
    def update_cpu(self):
        self.txt.set_text("Octoprint CPU: {0}%".format(psutil.cpu_percent()))
        
    def update_temp_txt(self,temps):
        temp_string = u"Extruder: {0}°C / {1}°C \nBed: {2}°C / {3}°C".format(temps["tool"]["actual"],temps["tool"]["target"],temps["bed"]["actual"],temps["bed"]["target"])
        logging.info(temp_string)
        self.temptxt.set_text(('temp', temp_string))
           
    def exit_on_q(self, key):        
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
            
    def check_messages(self, loop, *_args):
        """update cpu and percent if needed"""
        loop.set_alarm_in(
            sec=0.5,
            callback=self.check_messages,
            )
        try:
            msg = self.msg_queue.get_nowait()
        except Queue.Empty:
            return
        if "cpu" in msg:
            self.update_cpu()
        if "progress" in msg:
            self.update_progress(msg["progress"]["completion"])
            self.update_time_left(msg["progress"]["time_left"],msg["progress"]["job_name"])
        if "temps" in msg:
            self.update_temp_txt(msg["temps"])
            
class OctoDisplayNetworkManager:
    """This class communicates with the OctoPrint server and gets the data to display"""
    
    def __init__(self,server,api_key):
        self.server = server
        self.api_key = api_key
        
    def get_job_data(self):
        r = requests.get("http://{0}/api/job?apikey={1}".format(self.server,self.api_key))
        json = r.json()
        if "progress" in json:
            progress = json ["progress"]
            if "completion" in progress:
                completion = progress["completion"]
                if progress["printTimeLeft"] != None:
                    time_left = string_from_seconds(progress["printTimeLeft"])
                else:
                    time_left = "00:00:00"
                job_name = json["job"]["file"]["name"]
                return_dict = {"completion" : int(completion), "time_left" : time_left, "job_name": job_name}
                logging.info("Got progress {0}".format(return_dict))
                return return_dict
            else:
                logger.warn("Could not read progress from response")
        else:
            logger.warn("Could not read progress from response")
            
    def get_temp_data(self):
        r = requests.get("http://{0}/api/printer?history=false&apikey={1}".format(self.server,self.api_key))
        json = r.json()
        if "temperature" in json:
            temperature = json ["temperature"]
            temps = temperature["temps"]
            first_tool_actual = temps["tool0"]["actual"]
            first_tool_target = temps["tool0"]["target"]
            bed_actual = temps["bed"]["actual"]
            bed_target = temps["bed"]["target"]
            return_dict = {"tool": {"actual" : "{0}".format(first_tool_actual), "target": "{0}".format(first_tool_target)},"bed" : {"actual" : "{0}".format(bed_actual), "target": "{0}".format(bed_target)} }
            logging.info("Got temps {0}".format(return_dict))
            return return_dict
        else:
            logger.warn("Could not get temps")        

def update_progress(stop_event, msg_queue, network_manager):
    """Update the progress from Octoprint every 10 seconds"""
    logging.info('start')
    msg_queue.put({"progress" : network_manager.get_job_data()})
    while not stop_event.wait(timeout=10.0):
        msg_queue.put({"progress" : network_manager.get_job_data()})
    logging.info('stop')
    
def update_temps(stop_event, msg_queue, network_manager):
    """Update the temps from Octoprint every 10 seconds"""
    logging.info('start')
    msg_queue.put({"temps" : network_manager.get_temp_data()})
    while not stop_event.wait(timeout=10.0):
        msg_queue.put({"temps" : network_manager.get_temp_data()})
    logging.info('stop')
    
def update_cpu(stop_event, msg_queue):
    """Update the CPU usage percentage once a second"""
    logging.info('start')
    msg_queue.put({"cpu": True})
    while not stop_event.wait(timeout=1.0):
        msg_queue.put({"cpu": True})
    logging.info('stop')
    
def string_from_seconds(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%d:%02d:%02d" % (h, m, s)
        
__doc__ = "Not yet available"


def main():
    # parse command line options
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help"])
    except getopt.error, msg:
        print msg
        print "for help use --help"
        sys.exit(2)
    # process options
    for o, a in opts:
        if o in ("-h", "--help"):
            print __doc__
            sys.exit(0)
    # process arguments
    if len(args) < 2:
        print "Need host and API key for showing info, use --help for info"
        sys.exit(0)
    for arg in args:
        logging.info(arg)
    
    stop_ev = threading.Event()
    message_q = Queue.Queue()
    network = OctoDisplayNetworkManager(args[0],args[1])

    threading.Thread(
        target=update_progress, args=[stop_ev, message_q, network],
        name='update_progress',
    ).start()
    
    threading.Thread(
        target=update_temps, args=[stop_ev, message_q, network],
        name='update_temps',
    ).start()
    
    threading.Thread(
        target=update_cpu, args=[stop_ev, message_q],
        name='update_cpu',
    ).start()

    logging.info('start')
    try:
        OctoDisplayWindow(message_q).loop.run()
    except KeyboardInterrupt:
        logging.info("ctrl+c pressed closing threads")
        stop_ev.set()
        for th in threading.enumerate():
            if th != threading.current_thread():
                th.join()
                
    logging.info('stop')

    # after interface exits, signal threads to exit, wait for them
    logging.info('stopping threads')

    stop_ev.set()
    for th in threading.enumerate():
        if th != threading.current_thread():
            th.join()
    

if __name__ == "__main__":
    main()
    
