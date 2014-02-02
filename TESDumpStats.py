# !/usr/bin/python3
#
# BSD License and Copywrite Notice ============================================
#  Copyright (c) 2014, Lojack
#  All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are met:
#
#  * Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
#  * Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
#  * Neither the name of the TESDumpStats nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
#  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
#  ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
#  LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
#  CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
#  SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
#  INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
#  CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
#  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#  POSSIBILITY OF SUCH DAMAGE.
# =============================================================================


"""Everything included into a single source file, so it's easy to copy/paste
   into a directory and run and cleanup afterwards."""


# Imports ---------------------------------------------------------------------
import functools
import traceback
import datetime
import binascii
import argparse
import struct
import time
import zlib
import copy
import sys
import re
import os
import io


# Regex to find valid plugin files
rePlugin = re.compile(r'\.es[mp](.ghost)?$', re.M|re.U|re.I)


# Command line parser
parser = argparse.ArgumentParser(prog='TESDumpStats',
                                  add_help=True)
parser.add_argument('-a', '--a',
                    dest='all',
                    action='store_true',
                    default=False,
                    help='Process all plugins in the Data directory.')
parser.add_argument('-p', '--plugin',
                    dest='plugin',
                    action='store',
                    type=str,
                    default='',
                    help='Process a single specified plugin.')
parser.add_argument('-o', '--output',
                    dest='output',
                    action='store',
                    type=str,
                    default='',
                    help='Specify the output directory for dumped stats.')
parser.add_argument('-s', '--split',
                    dest='split',
                    action='store_true',
                    default=False,
                    help='Create a separate dump file for each plugin.')


class FileReader(io.FileIO):
    """File-object with convenience reading functions."""

    def unpack(self, fmt):
        return struct.unpack(fmt, self.read(struct.calcsize(fmt)))

    def readUByte(self): return struct.unpack('B', self.read(1))[0]
    def readUInt16(self): return struct.unpack('H', self.read(2))[0]
    def readUInt32(self): return struct.unpack('I', self.read(4))[0]
    def readUInt64(self): return struct.unpack('Q', self.read(8))[0]

    def readByte(self): return struct.unpack('b', self.read(1))[0]
    def readInt16(self): return struct.unpack('h', self.read(2))[0]
    def readInt32(self): return struct.unpack('i', self.read(4))[0]
    def readInt64(self): return struct.unpack('q', self.read(8))[0]


def main():
    """Main function, fires everything off."""
    opts, extra = parser.parse_known_args()
    if opts.all:
        # Dump stats for every plugin
        to_dump = [x.lower() for x in os.listdir() if rePlugin.search(x)]
        to_dump.sort()
    elif opts.plugin:
        # Dump specified plugin
        plugin = opts.plugin.lower()
        if plugin.endswith('.ghost'):
            plugin = plugin[-6:]
        to_dump = [x for x in (plugin, plugin+'.ghost')
                   if os.path.exists(x)]
    else:
        # Only dump stats for Skyrim.esm and Update.esm
        to_dump = [x.lower() for x in ('Skyrim.esm', 'Skyrim.esm.ghost',
                                       'Update.esm', 'Update.esm.ghost')
                   if os.path.exists(x)]
    if not to_dump:
        print('Could not find any plugins to dump.  Are you sure TESDumpStats'
              ' is in the Skyrim Data directory?')
        return
    # Check to see if any plugins also have their ghosted version present.
    # We'll dump both if they exist, but something wonky could be up with the
    # user's Data directory.
    dupes = []
    for plugin in to_dump:
        if plugin+'.ghost' in to_dump:
            dupes.append(plugin)
    if dupes:
        print('WARNING:  The following plugins exist in your Data directory as'
              ' both plugins and ghosted plugins.  Something may be wrong!  '
              'The plugins will both be processed however.')
        for dupe in dupes:
            print('  ', dupe)
    # Setup output directory/file
    timestamp = time.strftime('%Y-%m-%d_%H%M.%S')
    outDir = (opts.output if opts.output else
              os.path.join(os.getcwd(),'TESDumpStats'))
    if opts.split:
        outDir = os.path.join(outDir, timestamp)
    try:
        if not os.path.exists(outDir):
            os.makedirs(outDir)
        testFile = os.path.join(outDir,'test.txt')
        with open(testFile,'wb'):
            pass
        os.remove(testFile)
    except Exception as e:
        print('ERROR: Could not setup output path specified:\n\n'
              '       ' + outDir + '\n\n'
              '       ' + str(e) + '\n\n')
        return

    # Start dumping
    print('Beginning dump.  Output directory:', outDir)
    stats = dict()
    for plugin in to_dump:
        s = stats.setdefault(plugin, dict())
        dumpPlugin(plugin, s)
    print('Dump complete.')
    printStats(stats, outDir, opts)


def dumpPlugin(fileName, stats):
    """Gets stats about records, etc from fileName, updates stats dict,
       then prints results to outFile."""
    print(fileName)
    s = dict()
    # Get basic stats on the file
    stats['size'] = size = os.path.getsize(fileName)
    stats['time'] = os.path.getmtime(fileName)
    try:
        with FileReader(fileName, 'rb') as ins:
            # Calculate CRC32
            crc = 0
            while ins.tell() < size:
                crc = binascii.crc32(ins.read(2097152), crc)
            crc = crc & 0xFFFFFFFF
            stats['crc'] = crc
            ins.seek(0)
            # No error checking, just assume everything is properly formed
            s = stats['records'] = dict()
            # Read TES4 record + GRUPs
            while ins.tell() < size:
                dumpGRUPOrRecord(ins, s, size)
    except Exception as e:
        print('ERROR: Unhandled exception\n')
        traceback.print_exc()


def formatSize(size):
    suffix = 'B'
    if size > 1024*10:
        size /= 1024
        suffix = 'KB'
    if size > 1024*10:
        size /= 1024
        suffix = 'MB'
    if size > 1024*10:
        size /= 1024
        suffix = 'GB'
    return '%i %s' % (int(size), suffix)


def printRecordStats(stats, outFile):
    for Type in sorted(stats):
        print('', Type, file=outFile)
        recStats = stats[Type]
        count = recStats['count']
        print('  Count:', count, file=outFile)
        sizes = recStats['sizes']
        minsize = min(sizes)
        maxsize = max(sizes)
        compressed = recStats.get('compressed', 0)
        if compressed == count:
            print('  All compressed', file=outFile)
        elif compressed > 0:
            print('  Compressed: %i / %i' % (compressed, count), file=outFile)
        else:
            print('  None compressed', file=outFile)
        if minsize == maxsize:
            print('  Size:', maxsize, file=outFile)
        else:
            print('  Min Size:', minsize, file=outFile)
            print('  Max Size:', maxsize, file=outFile)
        # Subrecords
        print('  Subrecords:', file=outFile)
        for subtype in recStats:
            if subtype in ('count','sizes','compressed'):
                continue
            subStats = recStats[subtype]
            subCounts = subStats['counts']
            if len(subCounts) == count:
                # At least 1 per record
                print('  ', subtype, '- Required', file=outFile)
            else:
                print('  ', subtype, '- %i / %i records' % (len(subCounts), count), file=outFile)
            maxcount = max(subCounts)
            mincount = min(subCounts)
            if maxcount == mincount:
                print('    Count:', maxcount, file=outFile)
            else:
                print('    Min Count:', mincount, file=outFile)
                print('    Max Count:', maxcount, file=outFile)
            sizes = subStats['sizes']
            maxsize = max(sizes)
            minsize = min(sizes)
            if maxsize == minsize:
                print('    Size:', maxsize, file=outFile)
            else:
                print('    Min Size:', minsize, file=outFile)
                print('    Max Size:', maxsize, file=outFile)
        print('', file=outFile)


def printStats(stats, outDir, opts):
    outName = os.path.join(outDir, time.strftime('%Y-%m-%d_%H%M.%S_dump.txt'))
    if not opts.split:
        # Make sure combined output file is empty
        if os.path.exists(outName):
            os.remove(outName)
        mode = 'a+'
    else:
        mode = 'w'
    for plugin in stats:
        if opts.split:
            outName = os.path.join(outDir, plugin+'.txt')
        with open(outName, mode) as outFile:
            print(plugin, file=outFile)
            pstats = stats[plugin]
            print(' File size:', formatSize(pstats['size']), file=outFile)
            print(' File Date:', datetime.datetime.fromtimestamp(pstats['time']), file=outFile)
            print(' File CRC: 0x%X' % pstats['crc'], file=outFile)
            printRecordStats(pstats['records'], outFile)


def dumpGRUPOrRecord(ins, stats, end):
    pos = ins.tell()
    if pos+24 > end:
        ins.seek(end)
        return
    grup = ins.read(4)
    if grup == b'GRUP':
        # It's a GRUP
        size = ins.readUInt32() - 24
        label = ins.read(4)
        Type = ins.readInt32()
        stamp = ins.readUInt16()
        unk1 = ins.readUInt16()
        version = ins.readUInt16()
        unk2 = ins.readUInt16()
        pos = ins.tell()
        if pos+size > end:
            ins.seek(end)
            return
        # Data
        while ins.tell() < pos+size:
            dumpGRUPOrRecord(ins, stats, pos+size)
    else:
        Type = grup.decode('ascii')
        dataSize = ins.readUInt32()
        flags = ins.readUInt32()
        id = ins.readUInt32()
        revision = ins.readUInt32()
        version = ins.readUInt16()
        unk = ins.readUInt16()
        if not flags & 0x20: # Not deleted
            # Data
            s = stats.setdefault(Type, dict())
            num = s.get('count', 0)
            s['count'] = num + 1
            data = ins.read(dataSize)
            if flags & 0x00040000:
                # Data is compressed
                uncompSize = struct.unpack('I', data[:4])
                data = zlib.decompress(data[4:])
                num = s.get('compressed', 0)
                s['compressed'] = num + 1
            s.setdefault('sizes',[]).append(len(data))
            dumpSubRecords(data, s)
        # Ensure we're at the end of the record
        ins.seek(pos+dataSize+24)


def dumpSubRecords(data, stats):
    size = len(data)
    pos = 0
    counts = dict()
    while pos < size - 6:
        subType = data[pos:pos+4].decode('ascii')
        pos += 4
        if subType == 'XXXX':
            subSize = struct.unpack('I', data[pos:pos+4])[0]
            pos += 4
            subType = data[pos:pos+4].decode('ascii')
            pos += 4
            pos += 2 # datasize
        else:
            subSize = struct.unpack('H', data[pos:pos+2])[0]
            pos += 2
        if pos+subSize > size:
            break
        pos += subSize
        s = stats.setdefault(subType, dict())
        num = counts.get(subType,0)
        counts[subType] = num + 1
        s.setdefault('sizes',[]).append(subSize)
    for subType in counts:
        stats[subType].setdefault('counts',[]).append(counts[subType])

if __name__=='__main__':
    main()
