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

from common import *

import os
import re
import time
import string

identifier = "(?:[_a-zA-Z][_a-zA-Z0-9]*)"

emptyLine = re.compile("^\s*(#.*)?$", re.U)
singleKeyword = re.compile("\s*(?P<type>[_a-zA-Z]+)\s*(#.*)?", re.U )
assignment = re.compile("\s*(?P<lhs>[^#]*?)\s*=\s*(?P<rhs>.*)", re.U )
identifierRegex = re.compile(identifier)
pathRegex = re.compile('"(?P<path>([^"]|"")*)"', re.U)
pathTimespanRegex = re.compile("%NAME\{(?P<spanNames>"+identifier+"(?:,"+identifier+")*)\}", re.U)
commaSplitter = re.compile("\s*(?P<value>"+identifier+")\s*,?")

def timeLiteralFunc(uid):
    #strTimeSeconds = "(?P<seconds"+uid+">[0-9][0-9]?)"
    #strTimeMinutes = "(?:(?P<minutes"+uid+">[0-9][0-9]?)\s*:\s*)?"+strTimeSeconds
    strTimeMinutes = "(?P<minutes"+uid+">[0-9][0-9]?)"
    strTimeHours   =   "(?:(?P<hours"+uid+">[0-9][0-9]?)\s*:\s*)?"+strTimeMinutes
    strTimeLiteral = "(?P<timeLiteral"+uid+">"+strTimeHours+")"
    return strTimeLiteral
    
timeLiteralRegex = re.compile(timeLiteralFunc(""))
timespanRegex = re.compile("(?P<timespan>"+timeLiteralFunc("1")+"(?:\s*-\s*"+timeLiteralFunc("2")+")?)")

def identifierDefinition(identifierName):
    return identifierName+" must begin with a letter (a-z or A-Z) or" \
        +" an underscore.  They may otherwise contain any combination" \
        +" of alphanumeric characters and underscores."

class WakeSection:
    def __init__(self):
        self.secsAfterState = {
            "rem"   : 0,
            "light" : 0,
            "deep"  : 0,
            "awake" : 0,
            "all"   : 0
            }

class Timespan:
    def __init__(self):
        self.originSourceLine = 0
        self.startSecond = 0
        self.endSecond = -1
    
    def checkValidity(self):
        if ( self.endSecond < 0 ):
            raise Exception("Timespan at line "+str(self.originSourceLine)+" has invalid"+\
                "values in it: {"+str(self.startSecond)+","+str(self.endSecond)+"}.  "+\
                "These should have been caught in the parsing/loading pass, so this "+\
                "is a program bug on at least some level.  That means the config file "+\
                "might be just fine.")
    
    def contains(self, secondOfDay):
        self.checkValidity()
        
        if ( self.endSecond <= self.startSecond ):
            # Wrapping logic.
            if ( secondOfDay < self.endSecond or self.startSecond <= secondOfDay ):
                return True
            else:
                return False
        else:
            # Straightforward non-wrapping logic.
            if ( self.startSecond <= secondOfDay and secondOfDay < self.endSecond ):
                return True
            else:
                return False
        
    def toString(self):
        #self.checkValidity()
        
        def secToLit(second):
            secs  = (second % 60)
            mins  = (second / 60) % 60
            hours = (second / 3600)
            return str(hours)+":"+str(mins) #+":"+str(secs)
        
        return secToLit(self.startSecond) + " - " + secToLit(self.endSecond)

class SpanNameNotFoundError(Exception):
    ''' A nonexistent timespan was referenced. '''
    pass

class SecondHasNoSpanError(Exception):
    ''' There is no timespan that contains the given second. '''
    pass

class OutputSection:
    def __init__(self):
        
        # There's no way to represent this right now
        self.filePaths = {
            DATA_RAW    : None,
            DATA_HGRAM  : None,
            DATA_SGRAM  : None,
            DATA_EVENTS : None
        }
        
        self.srcLines = {
            DATA_RAW    : None,
            DATA_HGRAM  : None,
            DATA_SGRAM  : None,
            DATA_EVENTS : None
        }
        
    # If timespanTable is passed a value of None, then this will not try to
    #   look up any %NAME elements and instead do syntax-checking only.
    def calculatePath(self, dataType, timeStruct, timespanTable):
        
        path = self.filePaths[dataType]
        if path == None:
            path = dataTypeConstToString(dataType) + ".csv"
        
        secondOfDay = \
              (timeStruct.tm_hour * 3600) \
            + (timeStruct.tm_min * 60) \
            + (timeStruct.tm_sec)
        
        pos = 0
        while True:
            match = pathTimespanRegex.search(path,pos)
            if match == None:
                break
            
            spanNames = match.groupdict()["spanNames"]
            spanNameToUse = None

            for spanMatch in commaSplitter.finditer(spanNames):
                pname = spanMatch.groupdict()["value"]
                if ( timespanTable != None and pname in timespanTable ):
                    tspans = timespanTable[pname]
                    for tspan in tspans:
                        if tspan.contains(secondOfDay):
                            spanNameToUse = pname
                            break
                    
                    if spanNameToUse != None:
                        break

                elif (timespanTable != None):
                    raise SpanNameNotFoundError("config.cfg, "+str(self.srcLines[dataType])+
                        ": Span name "+pname+" given in %NAME{} was not found in the timespan tables.")
                #if
            #for
            
            if ( timespanTable != None and spanNameToUse == None ):
                raise SecondHasNoSpanError("Span corresponding to the second of day "+
                    str(currentSecond)+" was not found.")
            #    spanNameToUse = "error_no_span_for_second_"+str(currentSecond)
            
            if ( spanNameToUse != None ):
                path = path[:match.start()] + spanNameToUse + path[match.end():]

            pos = match.start() + 1
        #while

        path = string.replace(path,'""','"')
        #path = string.replace(path,'%%','%')
        path = time.strftime(path,timeStruct)
        path = os.path.abspath(path)
        return path
        
class SleepConfig:

    def __init__(self, configFileName):
        
        self.debugMode = False
        
        self.currentLine = ""
        self.currentLineNumber = 0
        self.nErrors = 0
        
        self.wakeTables = []
        self.timespanTable = {}
        self.outputTables = []
        
        self.fileName = configFileName
        self.fileStream = open(configFileName,"r")
        self._parseConfig()

    def debug(self,msg):
        if self.debugMode:
            print msg
    
    def err(self,msg):
        self.nErrors = self.nErrors + 1
        print self.fileName+", "+str(self.currentLineNumber)+": "+msg
    
    def _atSectionEnd(self):
        
        match = singleKeyword.match(self.currentLine)
        if match != None and match.groupdict()["type"] == "end":
            return True
        
        return False
    
    def _parseWakeSection(self):
        self.debug("_parseWakeSection()")
        wakeTable = WakeSection()
        
        while self._nextline():
            
            if ( self._atSectionEnd() ):
                break
        
        self.wakeTables.append(wakeTable)
        
        ''' do nothing for now.'''
        
    # Parse a time literal and return the second of the day that it represents.
    def _parseTimeLiteral(self, literal):
        self.debug("_parseTimeLiteral("+literal+")")
        match = timeLiteralRegex.match(literal)
        if match == None:
            self.err("Not a valid time of day: "+literal)
        
        minutes = int(match.groupdict()["minutes"])
        
        hoursStr = match.groupdict()["hours"]
        if (hoursStr != None):
            hours = int(hoursStr)
        else:
            hours = 0
        
        if minutes > 59:
            self.err("Invalid time of day has more minutes than there are in an hour: "+literal)
        
        # This doesn't work because the strptime format string doesn't allow
        #   the hours to be omitted.
        #timeStruct = time.strptime(literal,"%H:%M")
        #second = \
        #      (timeStruct.tm_hour * 3600) \
        #    + (timeStruct.tm_min * 60)
        
        second = (minutes * 60) + (hours * 3600)
        
        if second == 86400:
            # 24:00 equals 0:00
            second = 0
        elif second > 86400:
            # quantities that are too large.
            self.err(literal+" is a time that doesn't exist in the 24 hour day.")
        
        return second
    
    def _parseTimespan(self, text):
        self.debug("_parseTimespan("+text+")")
        match = timespanRegex.match(text)
        if match == None:
            self.err("Not a valid timespan: "+text)
            return None
        
        lit1 = match.groupdict()["timeLiteral1"]
        lit2 = match.groupdict()["timeLiteral2"]
        
        span = Timespan()
        span.originSourceLine = self.currentLineNumber
        span.startSecond = self._parseTimeLiteral(lit1)
        if ( lit2 != None ):
            span.endSecond = self._parseTimeLiteral(lit2)
        else:
            span.endSecond = -1 # Let the next one handle it.
        
        return span
    
    def _parseTimespanSection(self):
        self.debug("_parseTimespanSection()")
        def writeSpan(name, curSpan, nextSpan):
            
            if ( curSpan == None ):
                return
            
            if ( nextSpan != None and
                 curSpan.endSecond == -1 ):
                curSpan.endSecond = nextSpan.startSecond

            if ( name in self.timespanTable ):
                self.timespanTable[name].append( curSpan )
            else:
                self.timespanTable[name] = [curSpan]
        #-----------

        firstSpan = None
        curSpan = None
        curName = ""
        nextSpan = None
        nextName = ""
        
        while self._nextline():
            
            if ( self._atSectionEnd() ):
                break
            
            match = assignment.match(self.currentLine)
            if match == None:
                self.err("Unexpected line in config file: \n"+self.currentLine)
                continue
            
            lhs = match.groupdict()["lhs"]
            rhs = match.groupdict()["rhs"]
            
            match = identifierRegex.match(lhs)
            if match == None:
                self.err("Not a valid timespan name: "+lhs+"\n"
                    + identifierDefinition("Timespan names"))
                continue
            
            #if ( lhs in self.timespanTable ):
            #    self.err("A timespan named "+lhs+" already exists.")
            
            nextSpan = self._parseTimespan(rhs)
            nextName = lhs
            #fillSpanDefault(span,lastSpanParsed)
            writeSpan(curName, curSpan, nextSpan)
            
            curSpan = nextSpan
            curName = nextName
            if firstSpan == None:
                firstSpan = curSpan
        #-----------
        
        #fillSpanDefault(span,firstSpanParsed)
        writeSpan(curName, curSpan, firstSpan)
    
    def _parseOutputSection(self):
        self.debug("_parseOutputSection")
        outputSec = OutputSection()
        
        while self._nextline():
            
            if ( self._atSectionEnd() ):
                break
            
            match = assignment.match(self.currentLine)
            if match == None:
                self.err("Unexpected line in config file: \n"+self.currentLine)
                continue
            
            lhs = match.groupdict()["lhs"]
            rhs = match.groupdict()["rhs"]
            
            match = pathRegex.match(rhs)
            if match == None:
                self.err("Invalid path given: "+rhs)
                continue
            
            fullPath = match.groupdict()["path"]
            dataType = None
            if   lhs == "raw":         dataType = DATA_RAW
            elif lhs == "hypnogram":   dataType = DATA_HGRAM
            elif lhs == "spectrogram": dataType = DATA_SGRAM
            elif lhs == "events":      dataType = DATA_EVENTS
            else:
                self.err("Invalid entry in output section: "+lhs)
                continue
            
            if ( outputSec.filePaths[dataType] != None ):
                self.err("Entry is defined more than once: "+lhs)
                continue
            
            outputSec.filePaths[dataType] = fullPath
            outputSec.srcLines[dataType] = self.currentLineNumber
            
            leftovers = rhs[match.end():]
            match = emptyLine.match(leftovers)
            if match == None:
                self.err("Unexpected text after path: "+leftovers)
            
            # Make it calculate the path to ensure that the path was entered
            #   correctly.  Otherwise the program is going to behave like
            #   everything is fine until the user starts recording 5 minutes
            #   later and finds out that the config file is b0rked.
            outputSec.calculatePath(dataType, time.localtime(), None)
        
        self.outputTables.append(outputSec)
    
    def _parseConfig(self):
        self.debug("_parseConfig()")
        while self._nextline():

            match = singleKeyword.match(self.currentLine)
            if match == None:
                self.err("Unexpected line in config file: \n"+self.currentLine)
                continue
            
            sectionType = match.groupdict()["type"]
            if   sectionType == "wake_after":
                self._parseWakeSection()
            elif sectionType == "timespan_names":
                self._parseTimespanSection()
            elif sectionType == "output":
                self._parseOutputSection()
            else:
                self.err("Invalid section type: "+sectionType)
    
    def _nextline(self):
        result = False
        while True:
            self.currentLine = self.fileStream.readline()
            self.currentLineNumber += 1
            
            if len(self.currentLine) > 0 and self.currentLine[-1] == '\n':
                self.debug("_nextline(): "+self.currentLine[:-1])
            else:
                self.debug("_nextline(): "+self.currentLine)
            
            if ( len(self.currentLine) == 0 ):
                break # End of File
            else:
                # Skip empty lines.  None of the config grammar uses them.
                match = emptyLine.match(self.currentLine)
                if match == None:
                    if self.currentLine[-1] == '\n':
                        self.currentLine = self.currentLine[:-1]
                    result = True
                    break
                
        return result
        
    def printConfig(self):
        for table in self.wakeTables:
            print "wake_table"
            print "end"
        
        if ( len(self.timespanTable) > 0 ):
            print "timespan_names"
            for tname, tspans in self.timespanTable.iteritems():
                for tspan in tspans:
                    print "\t"+tname+" = "+tspan.toString()
            print "end"
        
        for table in self.outputTables:
            print "output"
            for dtype, path in table.filePaths.iteritems():
                if path != None:
                    print '\t'+dataTypeConstToString(dtype)+' = "'+path+'"'
            print "end"
