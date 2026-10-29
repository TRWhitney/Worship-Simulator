"""Extract requested original-client functions for offline comparison tools."""
import json
import re
import struct


def source_from_asar(path):
    with path.open('rb') as stream:
        header=stream.read(16)
        if len(header)!=16:raise ValueError('Invalid ASAR header')
        words=struct.unpack('<4I',header)
        if not 0<words[3]<=words[1]<=8*1024*1024:raise ValueError('Unsupported ASAR header size')
        node=json.loads(stream.read(words[3]))
        for part in 'distBuild/static/game/N.js'.split('/'):node=node['files'][part]
        if not 0<node['size']<=64*1024*1024:raise ValueError('Unsupported client bundle size')
        stream.seek(8+words[1]+int(node['offset']))
        data=stream.read(node['size'])
        if len(data)!=node['size']:raise ValueError('Truncated client bundle')
        return data.decode()


def function(source, name):
    match=re.search(r'(\w+)\.'+re.escape(name)+r'=function\(',source)
    if match is None:raise ValueError('Client function is missing: '+name)
    end=source.index('},'+match[1]+'.',match.end())+1
    return match[1],source[match.start():end]+';'
