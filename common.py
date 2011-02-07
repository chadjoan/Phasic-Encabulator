# -*- coding: utf-8 -*-

# Data type constants.
DATA_RAW    = 0
DATA_HGRAM  = 1
DATA_SGRAM  = 2
DATA_EVENTS = 3

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

# Table mapping Zeo's string constants for sleep-states onto height values.
SLEEP_STATE_TO_HEIGHT =  {  'Undefined' : 0,
                            'Deep'      : 1,
                            'Light'     : 2,
                            'REM'       : 3,
                            'Awake'     : 4}