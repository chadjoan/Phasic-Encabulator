# -*- coding: utf-8 -*-
# cross-platform non-blocking console IO

import sys
import threading
import platform

if ( platform.system() == 'Windows'):
    import msvcrt
else:
    import tty, termios, select

class TermInput ( threading.Thread ):

    def __init__(self):
        self._eventQueue = []
        self._done = threading.Event()
        self._done.clear()
        self.deamon = True
        threading.Thread.__init__ ( self )
    
    # Returns the least recent character or control code entered on sys.stdin
    #   (this is the same as the order in which the user enters them).
    # If the there are no new characters since the last call to popChar(),
    #   then 0 (the null character) will be returned.
    def popChar(self):
        if len(self._eventQueue) > 0:
            return self._eventQueue.pop(0)
        else:
            return '\0'

    # Used to push a character into the character queue.  This is mostly for
    #  internal use, but can be called as a way to emulate input being placed
    #  on sys.stdin.
    def pushChar(self,ch):
        self._eventQueue.append(ch)

    # Execute this to start looping.
    def run ( self ):
        
        self._done.clear()
        
        if ( platform.system() == 'Windows'):
            while not self._done.isSet():
                # We use kbhit() to see if anything has been entered yet.
                # This is important, because if we don't then we will block
                #   on getch() and be unable to tell when _done.isSet().
                if msvcrt.kbhit(): 
                    self.pushChar(msvcrt.getch())
        else:
            ''' we're not on Windows, so we try the Unix-like approach '''
            
            fd = sys.stdin.fileno( )
            old_settings = termios.tcgetattr(sys.stdin)
            try:
                tty.setcbreak(fd)
                
                while not self._done.isSet():
                    # We use _isData() to see if anything has been entered yet.
                    # This is important, because if we don't then we will block
                    #   on stdin.read() and be unable to tell when _done.isSet().
                    if _isData():
                        self.pushChar(sys.stdin.read(1))
                    
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    # Kill yourself.
    def kill(self):
        self._done.set() # I'm done for!


# Used to find out if there is data to read on stdin on linux/unix/etc.
def _isData():
    return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])
