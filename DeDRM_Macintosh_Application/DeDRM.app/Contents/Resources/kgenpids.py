#!/usr/bin/env python

from __future__ import with_statement
import sys
import os, csv
import binascii
import zlib
import re
from struct import pack, unpack, unpack_from

class DrmException(Exception):
    pass

global kindleDatabase
global charMap1
global charMap2
global charMap3
global charMap4

if sys.platform.startswith('win'):
    from k4pcutils import openKindleInfo, CryptUnprotectData, GetUserName, GetVolumeSerialNumber, charMap2
if sys.platform.startswith('darwin'):
    from k4mutils import openKindleInfo, CryptUnprotectData, GetUserName, GetVolumeSerialNumber, charMap2

charMap1 = "n5Pr6St7Uv8Wx9YzAb0Cd1Ef2Gh3Jk4M"
charMap3 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
charMap4 = "ABCDEFGHIJKLMNPQRSTUVWXYZ123456789"

# crypto digestroutines
import hashlib

def MD5(message):
    ctx = hashlib.md5()
    ctx.update(message)
    return ctx.digest()

def SHA1(message):
    ctx = hashlib.sha1()
    ctx.update(message)
    return ctx.digest()


# Encode the bytes in data with the characters in map
def encode(data, map):
    result = ""
    for char in data:
        value = ord(char)
        Q = (value ^ 0x80) // len(map)
        R = value % len(map)
        result += map[Q]
        result += map[R]
    return result
  
# Hash the bytes in data and then encode the digest with the characters in map
def encodeHash(data,map):
    return encode(MD5(data),map)

# Decode the string in data with the characters in map. Returns the decoded bytes
def decode(data,map):
    result = ""
    for i in range (0,len(data)-1,2):
        high = map.find(data[i])
        low = map.find(data[i+1])
        if (high == -1) or (low == -1) :
            break
        value = (((high * len(map)) ^ 0x80) & 0xFF) + low
        result += pack("B",value)
    return result


# Parse the Kindle.info file and return the records as a list of key-values
def parseKindleInfo(kInfoFile):
    DB = {}
    infoReader = openKindleInfo(kInfoFile)
    infoReader.read(1)
    data = infoReader.read()
    if sys.platform.startswith('win'):
        items = data.split('{')
    else :
        items = data.split('[')
    for item in items:
        splito = item.split(':')
        DB[splito[0]] =splito[1]
    return DB

# Get a record from the Kindle.info file for the key "hashedKey" (already hashed and encoded). Return the decoded and decrypted record
def getKindleInfoValueForHash(hashedKey):
    global kindleDatabase
    global charMap1
    global charMap2
    encryptedValue = decode(kindleDatabase[hashedKey],charMap2)
    if sys.platform.startswith('win'):
        return CryptUnprotectData(encryptedValue,"")
    else:
        cleartext = CryptUnprotectData(encryptedValue)
        return decode(cleartext, charMap1)
 
#  Get a record from the Kindle.info file for the string in "key" (plaintext). Return the decoded and decrypted record
def getKindleInfoValueForKey(key):
    global charMap2
    return getKindleInfoValueForHash(encodeHash(key,charMap2))

# Find if the original string for a hashed/encoded string is known. If so return the original string othwise return an empty string.
def findNameForHash(hash):
    global charMap2
    names = ["kindle.account.tokens","kindle.cookie.item","eulaVersionAccepted","login_date","kindle.token.item","login","kindle.key.item","kindle.name.info","kindle.device.info", "MazamaRandomNumber"]
    result = ""
    for name in names:
        if hash == encodeHash(name, charMap2):
           result = name
           break
    return result
    
# Print all the records from the kindle.info file (option -i)
def printKindleInfo():
    for record in kindleDatabase:
        name = findNameForHash(record)
        if name != "" :
            print (name)
            print ("--------------------------")
        else :
            print ("Unknown Record")
        print getKindleInfoValueForHash(record)
        print "\n"

#
# PID generation routines
#
  
# Returns two bit at offset from a bit field
def getTwoBitsFromBitField(bitField,offset):
    byteNumber = offset // 4
    bitPosition = 6 - 2*(offset % 4)
    return ord(bitField[byteNumber]) >> bitPosition & 3

# Returns the six bits at offset from a bit field
def getSixBitsFromBitField(bitField,offset):
     offset *= 3
     value = (getTwoBitsFromBitField(bitField,offset) <<4) + (getTwoBitsFromBitField(bitField,offset+1) << 2) +getTwoBitsFromBitField(bitField,offset+2)
     return value
     
# 8 bits to six bits encoding from hash to generate PID string
def encodePID(hash):
    global charMap3
    PID = ""
    for position in range (0,8):
        PID += charMap3[getSixBitsFromBitField(hash,position)]
    return PID

# Encryption table used to generate the device PID
def generatePidEncryptionTable() :
    table = []
    for counter1 in range (0,0x100):
        value = counter1
        for counter2 in range (0,8):
            if (value & 1 == 0) :
                value = value >> 1
            else :
                value = value >> 1
                value = value ^ 0xEDB88320
        table.append(value)
    return table

# Seed value used to generate the device PID
def generatePidSeed(table,dsn) :
    value = 0
    for counter in range (0,4) :
       index = (ord(dsn[counter]) ^ value) &0xFF
       value = (value >> 8) ^ table[index]
    return value

# Generate the device PID
def generateDevicePID(table,dsn,nbRoll):
    global charMap4
    seed = generatePidSeed(table,dsn)
    pidAscii = ""
    pid = [(seed >>24) &0xFF,(seed >> 16) &0xff,(seed >> 8) &0xFF,(seed) & 0xFF,(seed>>24) & 0xFF,(seed >> 16) &0xff,(seed >> 8) &0xFF,(seed) & 0xFF]
    index = 0
    for counter in range (0,nbRoll):
        pid[index] = pid[index] ^ ord(dsn[counter])
        index = (index+1) %8
    for counter in range (0,8):
        index = ((((pid[counter] >>5) & 3) ^ pid[counter]) & 0x1f) + (pid[counter] >> 7)
        pidAscii += charMap4[index]
    return pidAscii

def crc32(s):
  return (~binascii.crc32(s,-1))&0xFFFFFFFF 

# convert from 8 digit PID to 10 digit PID with checksum
def checksumPid(s):
    global charMap4
    crc = crc32(s)
    crc = crc ^ (crc >> 16)
    res = s
    l = len(charMap4)
    for i in (0,1):
        b = crc & 0xff
        pos = (b // l) ^ (b % l)
        res += charMap4[pos%l]
        crc >>= 8
    return res


# old kindle serial number to fixed pid
def pidFromSerial(s, l):
    global charMap4
    crc = crc32(s)
    arr1 = [0]*l
    for i in xrange(len(s)):
        arr1[i%l] ^= ord(s[i])
    crc_bytes = [crc >> 24 & 0xff, crc >> 16 & 0xff, crc >> 8 & 0xff, crc & 0xff]
    for i in xrange(l):
        arr1[i] ^= crc_bytes[i&3]
    pid = ""
    for i in xrange(l):
        b = arr1[i] & 0xff
        pid+=charMap4[(b >> 7) + ((b >> 5 & 3) ^ (b & 0x1f))]
    return pid


# Parse the EXTH header records and use the Kindle serial number to calculate the book pid.
def getKindlePid(pidlst, rec209, token, serialnum):

    if rec209 != None:
        # Compute book PID
        pidHash = SHA1(serialnum+rec209+token)
        bookPID = encodePID(pidHash)
        bookPID = checksumPid(bookPID)
        pidlst.append(bookPID)

    # compute fixed pid for old pre 2.5 firmware update pid as well
    bookPID = pidFromSerial(serialnum, 7) + "*"
    bookPID = checksumPid(bookPID)
    pidlst.append(bookPID)

    return pidlst


# Parse the EXTH header records and parse the Kindleinfo
# file to calculate the book pid.

def getK4Pids(pidlst, rec209, token, kInfoFile=None):
    global kindleDatabase
    global charMap1
    kindleDatabase = None
    try:
        kindleDatabase = parseKindleInfo(kInfoFile)
    except Exception, message:
        print(message)
        pass
    
    if kindleDatabase == None :
        return pidlst

    # Get the Mazama Random number
    MazamaRandomNumber = getKindleInfoValueForKey("MazamaRandomNumber")

    # Get the HDD serial
    encodedSystemVolumeSerialNumber = encodeHash(GetVolumeSerialNumber(),charMap1)

    # Get the current user name
    encodedUsername = encodeHash(GetUserName(),charMap1)

    # concat, hash and encode to calculate the DSN
    DSN = encode(SHA1(MazamaRandomNumber+encodedSystemVolumeSerialNumber+encodedUsername),charMap1)
       
    # Compute the device PID (for which I can tell, is used for nothing).
    table =  generatePidEncryptionTable()
    devicePID = generateDevicePID(table,DSN,4)
    devicePID = checksumPid(devicePID)
    pidlst.append(devicePID)

    # Compute book PID
    if rec209 == None:
        print "\nNo EXTH record type 209 - Perhaps not a K4 file?"
        return pidlst

    # Get the kindle account token
    kindleAccountToken = getKindleInfoValueForKey("kindle.account.tokens")

    # book pid
    pidHash = SHA1(DSN+kindleAccountToken+rec209+token)
    bookPID = encodePID(pidHash)
    bookPID = checksumPid(bookPID)
    pidlst.append(bookPID)

    # variant 1
    pidHash = SHA1(kindleAccountToken+rec209+token)
    bookPID = encodePID(pidHash)
    bookPID = checksumPid(bookPID)
    pidlst.append(bookPID)

    # variant 2
    pidHash = SHA1(DSN+rec209+token)
    bookPID = encodePID(pidHash)
    bookPID = checksumPid(bookPID)
    pidlst.append(bookPID)

    return pidlst

def getPidList(md1, md2, k4, pids, serials, kInfoFiles):
    pidlst = []
    if k4:
        pidlst = getK4Pids(pidlst, md1, md2)
    for infoFile in kInfoFiles:
        pidlst = getK4Pids(pidlst, md1, md2, infoFile)
    for serialnum in serials:
        pidlst = getKindlePid(pidlst, md1, md2, serialnum)
    for pid in pids:
        pidlst.append(pid)
    return pidlst