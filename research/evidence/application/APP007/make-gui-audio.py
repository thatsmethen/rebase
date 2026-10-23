from pathlib import Path
import hashlib,json,math,wave
root=Path(__file__).resolve().parent/'synthetic-media'
root.mkdir(exist_ok=True)
frames=1058400
period=b''.join(int(round(math.sin(2*math.pi*i/100)*524287)).to_bytes(3,'little',signed=True)+int(round(math.cos(2*math.pi*i/100)*262143)).to_bytes(3,'little',signed=True) for i in range(100))
records=[]
for name,count,invert in [('Synthetic LoFi Format.wav',frames,False),('Synthetic Replacement.wav',frames,True),('Wrong Frame Count.wav',frames-1,False)]:
    data=(period*((count+99)//100))[:count*6]
    if invert:
        data=b''.join((-int.from_bytes(data[i:i+3],'little',signed=True)).to_bytes(3,'little',signed=True) for i in range(0,len(data),3))
    path=root/name
    with wave.open(str(path),'wb') as f:
        f.setparams((2,3,44100,count,'NONE','not compressed'));f.writeframes(data)
    raw=path.read_bytes()
    records.append({'path':str(path.relative_to(root.parent)),'frames':count,'sampleRate':44100,'channels':2,'bitsPerSample':24,'bytesPerFrame':6,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
(root/'manifest.json').write_text(json.dumps({'kind':'self-authored synthetic PCM controls, not original Cubase media or runtime evidence','files':records},indent=2)+'\n')
