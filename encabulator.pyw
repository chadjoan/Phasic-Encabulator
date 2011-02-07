#!/usr/bin/python -d
# -*- coding: utf-8 -*-

'''
    Phasic Encabulator -- Records and responds to sleep data in realtime.
    Copyright (C) 2011  Chad Joan

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
    
    To contact the author, send an email to chadjoan@gmail.com
    
    
    This program will require either the Zeo Raw Data Library or a suitable
    substitute in order to function.  If you use the Zeo Raw Data Library you
    must also agree to the terms and conditions for the Zeo Raw Data Library.
    These terms and conditions can be found at 
    <http://developers.myzeo.com/terms-and-conditions/>.
    
'''

USE_ZEO_RDL = True


# NapTrainer.pyw
# This program will attempt to wake the sleeper whenever they are in light sleep
#   for too long.  This could potentially be used to acquire better polyphasic
#   naps very early in an adaptation and possibly train the user to nap
#   efficiently, though this is all guesswork so far.  This is definitely not
#   recommended for normal sleep!
# You will need to provide a program for this script to run as a way to wake
#   you up.  The default setup calls mplayer and tells it to play the 
#   "alarm.wav" file that should be found in the same directory as this script.

from common import *

import sys
import time
import csv
import subprocess
import os
import os.path
import colorama
#import threading
import platform
import traceback
import io
import re
from sleepconfig import *
from threading import RLock, Thread, Timer
from termcolor import colored
from serial import *
from glob import glob
import TermInput

if ( USE_ZEO_RDL ):
    from ZeoRawData import BaseLink, Parser

def printException():
    print ""
    print colored("Caught an exception!", "red", attrs=['bold'])
    print "This is almost certainly a bug."
    print "The exception's message is as follows:"
    traceback.print_exc()

def scanPorts():
    portList = []
    
    # Helps find USB>Serial converters on linux
    for p in glob('/dev/ttyUSB*'):
        portList.append(p)
    #Linux and Windows
    for i in range(256):
        try:
            ser = Serial(i)
            if ser.isOpen(): 
                #Check that the port is actually valid
                #Otherwise invalid /dev/ttyS* ports may be added
                portList.append(ser.portstr)
            ser.close()
        except SerialException:
            pass

    # This is a strange hack needed to prevent colorama from producing
    #   an assertion exception.  
    # Perhaps the serial library accidentally messes up some stack variables
    #   or io state and the only way to remedy it is to reestablish the stdout
    #   context ASAP.
    # So the idea is to print an empty string that's colored, and be sure
    #   NOT to print a newline or it will very quickly clear the screen.
    # This must be done before returning from this function.  Once we've
    #   returned, it's too late.  
    if platform.system() == 'Windows' :
        print colored('', 'green', 'on_red') ,

    return portList
    

class NullStream(io.IOBase):
    def __init__(self):
        io.IOBase.__init__(self)
        self.closed = False
        
    def close(self):
        ''' nop '''
    
    def flush(self):
        ''' nop '''

    def isatty(self):
        return True
        
    def read(self,n=-1):
        return ""
    
    def readable(self):
        return True
        
    def readinto(self,b):
        return None
    
    def readline(self, limit=-1):
        return ""
    
    def readlines(self, hint=-1):
        return []
    
    def seek(self,offset, whence):
        ''' nop '''
    
    def seekable(self):
        return True
        
    def tell(self):
        return 0
    
    def truncate(self,size=None):
        ''' nop '''
    
    def writable(self):
        return True
        
    def write(self,line):
        ''' nop '''
    
    def writelines(self,lines):
        ''' nop '''

# A better way to do this would be to create a polling interface for grabbing
#   data events.  This way the calling code could determine when events fire,
#   rather than having the events fired at arbitrary times by the thread
#   scheduler.
class ToughLink(BaseLink.BaseLink):
    
    def __init__(self, port):
        #colorama.init()
        BaseLink.BaseLink.__init__(self,port)
        self.connected = False
        self.disconnectEvents = []
        self.ioLock = None
    
    
    def run(self):
        
        #self.connected = True
        # HACK: wait a second or so for disconnect events to raise.
        #   Ideally we'd know from the BaseLink itself when we are no longer
        #   in danger of exceptions caused by a false-start, but this will
        #   have to do for now.
        def _setConnectFlag( context ):
            context.connected = True
    
        timer = Timer(0.5, _setConnectFlag, [self])
        timer.start()
        try:
            BaseLink.BaseLink.run(self)
        
        except SerialException as e:
            if ( self.ioLock != None ): self.ioLock.acquire()
            print "SerialException: "
            traceback.print_exc()
            self.connected = False
            timer.cancel()
            if ( self.ioLock != None ): self.ioLock.release()
            
        except OSError as e:
            if ( self.ioLock != None ): self.ioLock.acquire()
            print "OSError: "
            traceback.print_exc()
            self.connected = False
            timer.cancel()
            if ( self.ioLock != None ): self.ioLock.release()
        
        except Exception:
            if ( self.ioLock != None ): self.ioLock.acquire()
            printException()
            self.connected = False
            timer.cancel()
            if ( self.ioLock != None ): self.ioLock.release()
        
        if ( self.ser != None ):
            self.ser.close()
    

def getHeader(dataType):
    if dataType == DATA_RAW:
        header = ["Time Stamp","Version","SQI","Impedance","Bad Signal (Y/N)","Voltage (uV)"]
    elif dataType == DATA_SGRAM:
        header = ["Time Stamp","Version","SQI","Impedance","Bad Signal (Y/N)",
                                   "2-4 Hz","4-8 Hz","8-13 Hz","11-14 Hz","13-18 Hz","18-21 Hz","30-50 Hz"]
    elif dataType == DATA_HGRAM:
        header = ["Time Stamp","Version","SQI","Impedance","Bad Signal (Y/N)","State (0-4)","State (named)"]
    elif dataType == DATA_EVENTS:
        header = ["Time Stamp","Version","Event"]
    else:
        errUnknownSleepType()
    
    return header

class StreamCache:
    def __init__(self):
        self.fstreams = {
            DATA_RAW    : None,
            DATA_HGRAM  : None,
            DATA_SGRAM  : None,
            DATA_EVENTS : None,
        }

class ZeoToCSV:
    
    
    def __init__(self, config, parent=None):
        self.sleepConfig = config
        
        # Each element is a 4-pair table of dataType->stream pairs.  The paths are
        #   paths that have already been filled in with date/name information.
        # The elements in this array are parallel to the elements in the
        #   self.sleepConfig.outputTables array.
        self.outputs = []
        
        self.updateConfig()
        
        
        '''
        #fileNames = {
        #    DATA_RAW    : 'raw_samples.csv',
        #    DATA_HGRAM  : 'hypnogram.csv',
        #    DATA_SGRAM  : 'spectrogram.csv',
        #    DATA_EVENTS : 'events.csv',
        #}
        
        samplesFileName = 'raw_samples.csv'
        sgramFileName = 'spectrogram.csv'
        hgramFileName = 'hypnogram.csv'
        eventsFileName = 'events.csv'
        
        self.hypToHeight = {'Undefined' : 0,
                            'Deep'      : 1,
                            'Light'     : 2,
                            'REM'       : 3,
                            'Awake'     : 4}
        
        # Only create headers when the files are being created for the first time.
        # After that, all new data should be appended to the existing files.
        samplesNeedHeader = False
        sgramNeedHeader = False
        hgramNeedHeader = False
        eventsNeedHeader = False
        
        if not os.path.isfile(samplesFileName):
            samplesNeedHeader = True
        
        if not os.path.isfile(sgramFileName):
            sgramNeedHeader = True
        
        if not os.path.isfile(hgramFileName):
            hgramNeedHeader = True
    
        if not os.path.isfile(eventsFileName):
            eventsNeedHeader = True
        
        self.fileStreams = {
            DATA_RAW    : open(samplesFileName, 'a+b'),
            DATA_HGRAM  : open(hgramFileName, 'a+b'),
            DATA_SGRAM  : open(sgramFileName, 'a+b'),
            DATA_EVENTS : open(eventsFileName, 'a+b'),
        }
        
        self.rawSamples = csv.writer(self.fileStreams[DATA_RAW], delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        self.spectrogram = csv.writer(self.fileStreams[DATA_SGRAM], delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        self.hypnogram = csv.writer(self.fileStreams[DATA_HGRAM], delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        self.eventsOut = csv.writer(self.fileStreams[DATA_EVENTS], delimiter=',',
                                quotechar='"', quoting=csv.QUOTE_MINIMAL)
        
        if samplesNeedHeader:
            self.rawSamples.writerow(["Time Stamp","Version","SQI","Impedance","Bad Signal (Y/N)","Voltage (uV)"])
        
        if sgramNeedHeader:
            self.spectrogram.writerow(["Time Stamp","Version","SQI","Impedance","Bad Signal (Y/N)",
                                    "2-4 Hz","4-8 Hz","8-13 Hz","11-14 Hz","13-18 Hz","18-21 Hz","30-50 Hz"])
        
        if hgramNeedHeader:
            self.hypnogram.writerow(["Time Stamp","Version","SQI","Impedance","Bad Signal (Y/N)","State (0-4)","State (named)"])
        
        if eventsNeedHeader:
            self.eventsOut.writerow(["Time Stamp","Version","Event"])
        '''
    
    def displaySleepState(self, stage, timeStamp, badSignal):
        if badSignal:
            sigStr = colored( "(Bad Signal)", "red", attrs=['bold'] )
        else:
            sigStr =          "            "
        
        match = re.search("[0-9]{2}:[0-9]{2}:[0-9]{2}",timeStamp)
        timeStr = match.group()
        
        if   stage == SLEEP_STATE_UNDEFINED:
            sleepBar =          "        "
            sleepStr = "Undefined  "
        elif stage == SLEEP_STATE_DEEP:
            sleepBar = colored( "##      ", "blue", attrs=['bold'] )
            sleepStr = "Deep ..... "
        elif stage == SLEEP_STATE_LIGHT:
            sleepBar = colored( "####    ", "cyan", attrs=['bold'] )
            sleepStr = "Light .... "
        elif stage == SLEEP_STATE_REM:
            sleepBar = colored( "######  ", "green", attrs=['bold'] )
            sleepStr = "REM ...... "
        elif stage == SLEEP_STATE_AWAKE:
            sleepBar = colored( "########", "white", attrs=['bold'] )
            sleepStr = "Awake .... "
            
            #print         "           Undefined  "+colored(sigStr, "red",  attrs=['bold'] )
            #print colored("##",                "blue",  attrs=['bold'] ) +\
            #                "         Deep ..... "+colored(sigStr, "red",  attrs=['bold'] )
            #print colored("####",              "cyan",  attrs=['bold'] ) +\
            #                   "      Light .... "+colored(sigStr, "red",  attrs=['bold'] )
            #print colored("######",   "green", attrs=['bold'] ) +\
            #                    "     REM ...... "+colored(sigStr, "red",  attrs=['bold'] )
            #print colored("########", "white", attrs=['bold'] ) +\
            #                      "   Awake .... "+colored(sigStr, "red",  attrs=['bold'] )
        
        # Those dots are kinda awkward if there's nothing to align with.
        if not badSignal:
            sleepStr = sleepStr.replace("."," ")
        
        print timeStr + " " + sleepBar + "  " + sleepStr + "  " + sigStr
        
        return
    
    def updateConfig(self):
        
        if len(self.outputs) != len(self.sleepConfig.outputTables):
            
            for streamCache in self.outputs:
                for dtype, stream in streamCache.fstreams.iteritems():
                    if stream != None:
                        stream.close()
            
            self.outputs = []
            
            for table in self.sleepConfig.outputTables:
                self.outputs.append(StreamCache())
    
    def updateSlice(self, slice):
        #print "updateSlice"
        
        self.updateConfig()
        self._recordData(slice)
        
    def _recordData(self, slice):
        #print "_recordData"
        
        timestamp = slice['ZeoTimestamp']
        ver = slice['Version']
                                        
        if not slice['SQI'] == None:
            sqi = str(slice['SQI'])
        else:
            sqi = '--'
                                        
        if not slice['Impedance'] == None:
            imp = str(int(slice['Impedance']))
        else:
            imp = '--'

        if slice['BadSignal']:
            badSignal = True
        else:
            badSignal = False
            
        if badSignal:
            badSignalYN = 'Y'
        else:
            badSignalYN = 'N'

        if not slice['Waveform'] == []:
            #self.rawSamples.writerow([timestamp,ver,sqi,imp,badSignal] + slice['Waveform'])
            self._outputRow(DATA_RAW, [timestamp,ver,sqi,imp,badSignalYN] + slice['Waveform'])

        if len(slice['FrequencyBins'].values()) == 7:
            f = slice['FrequencyBins']
            bins = [f['2-4'],f['4-8'],f['8-13'],f['11-14'],f['13-18'],f['18-21'],f['30-50']]
            #self.spectrogram.writerow([timestamp,ver,sqi,imp,badSignal] + bins)
            self._outputRow(DATA_SGRAM, [timestamp,ver,sqi,imp,badSignalYN] + bins)

        if not slice['SleepStage'] == None:
            stage = slice['SleepStage']
            #self.hypnogram.writerow([timestamp,ver,sqi,imp,badSignal] +
            #                         [self.hypToHeight[stage],str(stage)])
            self._outputRow(DATA_HGRAM, [timestamp,ver,sqi,imp,badSignalYN] +
                                        [SLEEP_STATE_TO_HEIGHT[stage],str(stage)])
            
            self.displaySleepState(stage, timestamp, badSignal)
        
        #for dataType, stream in self.outputs.iteritems():
        #    stream.flush()
    
    def updateEvent(self, timestamp, version, event):
        self.updateConfig()
        self._outputRow(DATA_EVENTS, [timestamp,version,event])

        #self.eventsOut.writerow([timestamp,version,event])
    
    # Row must be an array.
    def _outputRow(self, dataType, row):
        #print "self._outputRow"
        index = 0
        for table in self.outputs:
            self._outputRowOnDestIndex(dataType, index, row)
            index += 1
        
    def _outputRowOnDestIndex(self, dataType, index, row):
        #print "self._outputRowOnDestIndex"
        
        # Calculate the timestamp first since it is needed in some filepaths.
        timeStruct = None
        timestamp = row[0] # row[0] should always be the timestamp given by Zeo.
        try:
            timeStruct = time.strptime(timestamp, "%m/%d/%Y %H:%M:%S")
        except Exception:
            print ""
            print "Bad timestamp value given: "+colored(timestamp, 'red', attrs=['bold'])
            timeStruct = time.localtime()
            print "Using system time instead: "+colored(time.strftime("%m/%d/%Y %H:%M:%S"), 'green', attrs=['bold'])
        
        # Open or switch files as needed.
        destination = self.outputs[index]
        fstream = destination.fstreams[dataType]
        
        oldPath = ""
        newPath = ""
        
        if ( fstream != None ):
            oldPath = fstream.name
        
        table = self.sleepConfig.outputTables[index]
        try:
            newPath = table.calculatePath(dataType, timeStruct, self.sleepConfig.timespanTable)
        except SpanNameNotFoundError as e:
            traceback.print_exc()
        except SecondHasNoSpanError:
            ''' nop '''

        # Streams are opened and closed lazily. This allows them to easily and
        #   efficiently stay in sync with the config file, assuming updateConfig()
        #   is called everytime a row is written.  
        
        try:
            needHeader = False # Set to true for new files.
            if ( oldPath != newPath ):
                if ( fstream != None ):
                    fstream.close()
                
                newDir = os.path.dirname(newPath)
                if not os.path.isdir(newDir):
                    os.makedirs(newDir)
                
                if not os.path.isfile(newPath):
                    needHeader = True
                
                (dummy,ext) = os.path.splitext(newPath)
                #if   ext == "zip":
                #    fstream = zipfile.ZipFile(newPath, 'a+b')
                if ext == "gz":
                    fstream = gzip.GzipFile(newPath, 'ab')
                else:
                    fstream = open(newPath, 'ab')
                
                destination.fstreams[dataType] = fstream
            
            # destination.fstreams[dataType] now contains the correct stream.
            # The only thing left is to write out the row:
            fstream = destination.fstreams[dataType]
            writer = csv.writer(fstream, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            
            if needHeader:
                writer.writerow(getHeader(dataType))
            
            writer.writerow(row)
            
            del writer
            fstream.flush()
        except Exception as e:
            print ""
            print "Could not write data with timestamp "+colored(timestamp, 'yellow', attrs=['bold'])
            print "The destination file was "+colored(newPath, 'yellow', attrs=['bold'])
            print "The following exception was given:"
            traceback.print_exc()
        
        return

class NapTrainer:
    def __init__(self, parent=None):
        self.alarmProcess = None
        self.lightCount = 0
        
    
    def updateSlice(self, slice):
        
        # TODO: integrate this stuff.
        return
        
        timestamp = slice['ZeoTimestamp']

        if not slice['BadSignal'] and not slice['SleepStage'] == None:
            stage = slice['SleepStage']
            print "Sleep stage: "+ stage
            #if stage == 'Awake':
            if stage == 'Light':
                self.lightCount = self.lightCount + 1
            else:
                self.lightCount = 0
        
        currentHour = time.localtime().tm_hour
        
        # This is about 2 minutes of light sleep.
        #if self.lightCount >= 1:
        #if self.lightCount >= 4:
        if self.lightCount >= (2 * leewayByHour[currentHour]):
            #subprocess.call(["mplayer","alarm.wav"])
            self.alarmProcess = subprocess.Popen(["mplayer","alarm.wav"])
            self.lightCount = 0
    
    def updateEvent(self, timestamp, version, event):
        """Stub: not needed."""

class PhasicEncabulator:
    def __init__(self):
        self.trainer = None
        self.output = None
        self.link = None
        self.ioLock = RLock()
    
        self.linkWasConnected = False
        self.defaultPort = ""
        self.oldPorts = []
        
        self.config = None
        
    def printOptions(self):
        print ""
        print "---------------------------"
        print ""
        print "Below are the available hotkeys."
        print "They are case insensitive."
        print "  space ........ Turn off any running alarms."
        print "  ctrl-C or Q .. Quit."
        print "  W ............ Print disclaimer."
        print "  L ............ Print license (the full GPL v3 text)."
        print "  O ............ Print available options/hotkeys (this text)."
        
    def printDisclaimer(self):
        self.ioLock.acquire()
        print ""
        print "----------------------------------"
        print "  Disclaimer sections of the GPL"
        print "----------------------------------"
        print ""
        
        #TODO: some way to grab these from the file itself?
        print "  15. Disclaimer of Warranty."
        print ""
        print "  THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY"
        print "APPLICABLE LAW.  EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT"
        print 'HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY'
        print "OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO,"
        print "THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR"
        print "PURPOSE.  THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM"
        print "IS WITH YOU.  SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF"
        print "ALL NECESSARY SERVICING, REPAIR OR CORRECTION."
        print ""
        print "  16. Limitation of Liability."
        print ""
        print "  IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING"
        print "WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS"
        print "THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY"
        print "GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE"
        print "USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF"
        print "DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD"
        print "PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS),"
        print "EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF"
        print "SUCH DAMAGES."
        print ""
        print "  17. Interpretation of Sections 15 and 16."
        print ""
        print "  If the disclaimer of warranty and limitation of liability provided"
        print "above cannot be given local legal effect according to their terms,"
        print "reviewing courts shall apply local law that most closely approximates"
        print "an absolute waiver of all civil liability in connection with the"
        print "Program, unless a warranty or assumption of liability accompanies a"
        print "copy of the Program in return for a fee."
        
        self.ioLock.release()
        
    def printLicense(self):
        
        self.ioLock.acquire()
        print ""
        print "---------------------------"
        print ""
        
        licStream = open("license.txt","rt")
        while ( True ):
            line = licStream.readline()
            if len(line) == 0: break;
            sys.stdout.write(line)
            #print line
        
        licStream.close()
        
        if ( USE_ZEO_RDL ):
            print ""
            print "This program will require either the Zeo Raw Data Library or a suitable"
            print "substitute in order to function.  If you use the Zeo Raw Data Library you"
            print "must also agree to the terms and conditions for the Zeo Raw Data Library."
            print "These terms and conditions can be found at "
            print "<http://developers.myzeo.com/terms-and-conditions/>."
        
        self.ioLock.release()
        
    def attachSerial(self,portStr):
        print "------------------------------------------------"
        print "Attempting to connect on port " + \
            colored( portStr, 'green', attrs=['bold'] )
        # Initialize
        self.trainer = NapTrainer()
        self.output = ZeoToCSV(self.config)
        self.link = ToughLink(portStr)
        self.link.ioLock = self.ioLock
        parser1 = Parser.Parser()
        parser2 = Parser.Parser()
        # Add callbacks
        self.link.addCallback(parser1.update)
        parser1.addEventCallback(self.trainer.updateEvent)
        parser1.addSliceCallback(self.trainer.updateSlice)
        self.link.addCallback(parser2.update)
        parser2.addEventCallback(self.output.updateEvent)
        parser2.addSliceCallback(self.output.updateSlice)
        # Start Link 
        self.link.start()
        
        timeoutBegin = time.time()
        while not self.link.connected:
            ''' spin until it connects '''
            ''' otherwise we would revisit this connection
                code over and over and hang '''
            
            currentPorts = scanPorts()
            if ( currentPorts.count(portStr) == 0 ):
                print "Port "+colored(portStr, 'green', attrs=['bold'])+\
                    " no longer available."
                print "Aborting connection attempt."
                print ""
                # We say we're aborting, but if they plug the cable back in
                #   we'll just try again.
                return
            
            # Give up after some time.  This will just cause the calling code
            #   to attempt the connection again, which is necessary because
            #   if the link fails to connect then it won't retry by itself.
            if ( time.time() > timeoutBegin + 5.0 ):
                print "Connection attempt timed out."
                print ""
                return

        self.defaultPort = portStr
        print "... done."
        print ""
        return
        
    def onDisconnect(self):
        if self.link != None and not self.link.connected:
            print "Zeo disconnected from port "+colored(self.link.ser.portstr, "green", attrs=['bold'])
        else:
            print "Zeo disconnected"
        
        print ""
        time.sleep(0.3) # Wait briefly for the OS to update its device nodes.
        print "Current serial port status:"
        self.printPorts()
        print ""
        
    def printPorts(self):
        defaultFound = False
        ports = scanPorts()
        for port in ports:
            print port
            if port == self.defaultPort:
                defaultFound = True
        
        if not defaultFound:
            print colored(self.defaultPort, "green", attrs=['bold']) + \
                  colored(" (disconnected)", "red", attrs=['bold'])
    
    # Always call this before run().
    def startup(self):
        
        print ""
        print "Phasic Encabulator  Copyright (C) 2011  Chad Joan"
        print "This program comes with ABSOLUTELY NO WARRANTY; for details hit "+colored("w", 'green')+"."
        print "This is free software, and you are welcome to redistribute it"
        print "under certain conditions; hit "+colored("l", 'green')+" for details."
        print ""
        
        # Places to look for the config file.  It will scan the list from 
        #   left to right and pick the first one it finds.
        if ( platform.system() == 'Windows'):
            configPaths = ['phasic-encabulator.conf']
        else:
            configPaths = ['phasic-encabulator.conf','/etc/phasic-encabulator.conf']

        chosenPath = None
        
        for possibility in configPaths:
            if os.path.isfile(possibility):
                chosenPath = possibility
        
        if chosenPath != None:
            print "Parsing config file "+colored(chosenPath, 'green', attrs=['bold'])
            self.config = SleepConfig(chosenPath)
            #self.config.printConfig()
            print "Config file parsed successfully."
            print ""
        else:
            print colored("Config file not found!", 'red', attrs=['bold'])
        
    
    def run(self):
        
        print "-------------------------"
        
        # Find ports.
        # TODO: offer a command line option for selecting ports.
        portStr = None
        ports = scanPorts()
        if len(ports) > 0 :
            print "Found the following ports:"
            for port in ports:
                print port
            print ""
            print "Using port "+colored(ports[0], "green", attrs=['bold'])
            print ""
            portStr = ports[0]
            self.defaultPort = portStr
        else:
            print colored('No serial ports found.', 'yellow', attrs=['bold'])
            print "This probably means the Zeo isn't plugged in."
            print "Tasks will wait until the Zeo is plugged in before starting."
            print ""
            #sys.exit("No serial ports found.")
        
        # This must be empty for it to connect to ports present at startup.
        self.oldPorts = []
        
        print "Hit "+colored("ctrl-C","green")+\
              " or "+colored("q","green")+" at any time to stop."
        print "Hit space bar to cancel any playing alarms."
        print ""

        inputThread = TermInput.TermInput()
        inputThread.start()

        try:
            while 1:
                try:
                    self.ioLock.acquire()
                    if self.linkWasConnected and (self.link == None or not self.link.connected):
                        self.linkWasConnected = False
                        self.onDisconnect()
                    elif not self.linkWasConnected and (self.link != None and self.link.connected):
                        self.linkWasConnected = True
                        #onConnect()
                    
                    if self.link == None or not self.link.connected:
                        ports = scanPorts()
                        for port in ports:
                            #if port == self.defaultPort:
                            #    self.attachSerial(port)
                            if self.oldPorts.count(port) == 0:
                                # New port that wasn't there before.
                                self.attachSerial(port)
                                break
                        
                        self.oldPorts = ports
                    # TODO: this if-branch is for attempting to connect
                    #   whenever a new serial device is found.  However, it
                    #   currently only does this when there were no devices to
                    #   begin with.
                    #elif len(ports) == 0 :
                    #    ports = scanPorts()
                    #    if len(ports) > 0 :
                    #        self.attachSerial(ports[0])
                
                    ch = inputThread.popChar()
                    if ch == ' ':
                        if self.trainer != None and self.trainer.alarmProcess != None :
                            print "\nSending kill signal to alarm."
                            self.trainer.alarmProcess.kill() # silence the alarm.
                        else:
                            print "\nNo alarm to kill."
                    elif ch == 'q' or ch == 'Q':
                        print "---------------------------"
                        print "Q command given.  Quitting."
                        break # quit
                    elif ch == 'w' or ch == 'W':
                        self.printDisclaimer()
                        self.printOptions()
                    elif ch == 'l' or ch == 'L':
                        self.printLicense()
                        self.printOptions()
                    elif ch == 'o' or ch == 'O':
                        self.printOptions()
                    elif ch == '\x03': # ctrl-c
                        break # quit
                    elif ch == '\x0A':
                        print ""
                except SerialException:
                    ''' keep going.'''
                finally:
                    self.ioLock.release()
            # /while 1:
        except KeyboardInterrupt:
            print "-------------------------"
            print "Caught ctrl-C.  Quitting."
        finally:
            inputThread.kill()
        
        print ""
        
if __name__ == '__main__':
    colorama.init()
    #print colored('Hello, World!', 'green', 'on_red')
    
    '''
    fileStream = open("config.cfg")
    while True:
        line = fileStream.readline()
        if len(line) == 0:
            print "EOF"
            break
        elif line != None:
            print line
        else:
            print "line == None"
            break
    
    sys.exit()
    '''
    
    encabulator = PhasicEncabulator()
    encabulator.startup()
    
    retryDelay = 0.5
    while True:
        try:
            encabulator.run()
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            printException()
            print ""
            print "Restarting in "+str(retryDelay)+" seconds..."
            print ""
            
            # Avoid spamming the user's terminal by progressively decreasing
            #   the frequency of bug reports.  This is probably the best we
            #   can do without knowing what the actual problem is.
            # Hopefully this way people will be able to find the original error
            #   message without having an infinite scrollback buffer.
            time.sleep(retryDelay)
            retryDelay *= 4
            if ( retryDelay > 60.0 ):
                retryDelay = 60.0
    
    sys.exit()

