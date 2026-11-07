#!/usr/bin/env python3
"""Create deterministic original synthetic audio for the networkless renderer fixture."""
import math
import struct
import sys
import wave
from pathlib import Path

def main():
    target=Path(sys.argv[1])
    target.parent.mkdir(parents=True,exist_ok=True)
    rate,seconds=48000,8
    with wave.open(str(target),"wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(rate)
        chunk_frames=4096
        for first in range(0,rate*seconds,chunk_frames):
            count=min(chunk_frames,rate*seconds-first)
            chunk=bytearray(count*4)
            for offset in range(count):
                index=first+offset
                t=index/rate
                envelope=min(1.0,t*3.0,(seconds-t)*3.0)
                signal=(math.sin(2*math.pi*220*t)+.45*math.sin(2*math.pi*330*t)+.2*math.sin(2*math.pi*440*t))
                value=max(-30000,min(30000,int(9000*envelope*signal/1.65)))
                struct.pack_into("<hh",chunk,offset*4,value,value)
            output.writeframesraw(chunk)
    print(str(target))
if __name__=="__main__":
    main()
