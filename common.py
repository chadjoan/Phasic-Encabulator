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

# Data type constants.
DATA_RAW    = 0
DATA_HGRAM  = 1
DATA_SGRAM  = 2
DATA_EVENTS = 3

# Don't store more than this many epochs in sleep history memory.
# This matters only for regular expression matching.
MAX_HISTORY_LEN = 30000 # Lil' more than 10 days worth ;)


def errUknownSleepType():
    raise Exception("Unknown type of sleep data: "+str(dtype))

def dataTypeConstToString(dtype):
    if   dtype == DATA_RAW:    return "raw"
    elif dtype == DATA_HGRAM:  return "hypnogram"
    elif dtype == DATA_SGRAM:  return "spectrogram"
    elif dtype == DATA_EVENTS: return "events"
    
    errUnknownSleepType()
    
# The Zeo will send these string constants at us.
SLEEP_STATE_UNDEFINED = 'Undefined'
SLEEP_STATE_DEEP      = 'Deep'
SLEEP_STATE_LIGHT     = 'Light'
SLEEP_STATE_REM       = 'REM'
SLEEP_STATE_AWAKE     = 'Awake'
SLEEP_STATE_NOT_GIVEN = 'Not Given' # Indicates the absence of a string from Zeo

# Table mapping Zeo's string constants for sleep-states onto height values.
SLEEP_STATE_TO_HEIGHT =  {  'Undefined' : 0,
                            'Deep'      : 1,
                            'Light'     : 2,
                            'REM'       : 3,
                            'Awake'     : 4,
                            'Not Given' : 0}