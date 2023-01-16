# -*- coding: utf-8 -*-
"""
Created on Wed Dec 11 14:02:07 2019
@author: Dan-L
"""

#find fasta repeats
#reverse complelment taken into account (SAM already changes it to reverse comp)
#single letter repeats are removed (i.e. GGGG)
#lowercase seqs will not be considered


import re
import regex
import itertools
import pandas as pd
#from collections import Counter
#from Bio.Seq import Seq
import time
from Bio import SeqIO
import argparse
from datetime import datetime
import copy

parser = argparse.ArgumentParser()
parser.add_argument("SsrReferenceFile", help = "The modified reference file (FASTA)")
parser.add_argument("SamFiles", help = "Text document with the SAM file names separated by newlines")
parser.add_argument("OutputFile", help = "Output file name (\".ssr\") extension will be added")
parser.add_argument("-M","--MinorAlleleHet", help = "The minimum percentage of the minor allele for a genotype to be considered heterozygous. If two alleles are found but the percentage of minor allele reads is below this cutoff the genotype will be called as a homozygote for the major allele. Setting this argument to 0.51 will produce only homozygous genotypic calls. Between 0 and 1. [0.20]", type=float, default = .2)
parser.add_argument("-S", "--Support", help = 'The minimum number of supporting reads needed for a genotype to be called at an SSR locus. If the total number of reads is less than this threshold, the genotype will not be called and will be reported as "0,-4". [3]', type = int, default = 3)
parser.add_argument("-R", "--RefUnitsMin", help = "The minimum SSR repeat number used to identify repeats using MISA. [4]", type=int, default = 4)
parser.add_argument("-P", "--PopUnitsMin", help = "The minimum SSR repeat number allowed within the population. [3]", type=int, default = 3)
parser.add_argument("-B", "--BorderSeq", help = "The number of bordering (flanking) nucleotides on each side of the SSR motif that must match the reference for a read to be used to support a genotypic call. [20]", type=int, default= 20)
parser.add_argument("-s", "--spuriousAlleleRemoval", help = "Diploid species should only have a maximum of two allele possible. SSR loci that have more than the expected two (major/minor) alleles are marked as ambiguous (missing) if the additional allele(s) is supported by more than this threshold percentage of reads. Otherwise the allele(s) is considered to be spurious and excluded. [.1]", type=float, default = .1)
parser.add_argument("-m", "--mismatch", help = "The number of mismatches (substitutions and indels) allowed in the border sequence (--BorderSeq) region between the reads and the reference. [0]", type = int, default = 0)
parser.add_argument("-A", "--AlignmentShow", help = 'Provides a text display of the read alignments for a specific individual (SAM file) and a specific SSR locus. The user specifies a specific SSR locus name and a specific SAM file name separated by "," (e.g. SSR1,samFile.markdup.Q45.sam). This is useful for spot checking alignments and specific genotypic calls.', type=str, default = "")
parser.add_argument("-W", "--WindowOffset", help = "Window search offset. We do not recommend changing the default offset. [1]", type=int, default = 1)
#Data filtering parameters
parser.add_argument("-F", "--FilterDataLoci", help = "The maximum missing data threshold for reporting an SSR locus. Between 0 and 1. [.30]", type=float, default = .3)
parser.add_argument("-f", "--filterDataSam", help = "The maximum missing data threshold for reporting an individual (SAM file). Between 0 and 1. [.30]", type=float, default = .3)
parser.add_argument("-Q", "--QualityFilter", help = "Only reads with equal to or greater than the specified mapping quality (MAPQ) threshold are utilized in the genotype calling. [45]", type=int, default=45)
parser.add_argument("-N", "--NameSize", help = "This option will limit the number of characters printed in the output table for each SAM file. When using this option make sure that new names will still be unique as SAM files with the same name will result in inaccurate results. [100]", type= int, default = 100)
#Output file types
parser.add_argument("-G", "--Genepop", help = "Ouputs a genepop formated file.", action='store_true')
parser.add_argument("-L", "--LinkageMapFile", help = 'Outputs an "A,B,H" genotype file for downstream linkage map construction of biparental populations. The first two SAM files in the SamFiles (positional argument) should correspond to two parents of the biparental population and are necessary for correctly phasing the genotypes. If the parental genotypes are monomorphic (same genotype) or if one of the parents is missing a genotypic call, the SSR locus is excluded. Similarly, if one or both of the parents have a heterozygous genotype, phase cannot be determined, and the marker is also be excluded. SSRgenotyper can impute the genotype of a missing parent (the other parent must have a genotype) based on the progeny by providing the -L argument with a with a specific numeric threshold value (e.g., -L 0.30). If a threshold is provided and two alleles (major and minor) are found in the progeny with the minor allele frequency above the provided threshold and where one allele agrees with the genotyped parent, SSRgenotyper will internally assign the second allele as the genotype of the missing parent, however the imputed genotype will still be reported in the .map file as missing - thus allowing the user to identify which markers had an imputed parental genotype. [.30]', nargs='?', type=float, const=.3)

args = parser.parse_args()


fastaRef = args.SsrReferenceFile
#mapping done with BWA (no options selected)
#fasta file that made sam (second file) file MUST BE MAPPED to the reference file (first file)
#there are no optical duplicates
#sam files must be filtered for quality and headers removed (samtools view -q 45 fileName)
#then only grab first 10 columns (cut -f1-10 fileName)
#ls *.f1 > files.txt

samsDoc = args.SamFiles
outFile = args.OutputFile
samFiles = []

with open(samsDoc) as sd:
    input = sd.readlines()
    for i in input:
        samFiles.append(i)

majorMinorRatio = args.MinorAlleleHet
filterDataSam = args.filterDataSam
flankOffset = args.WindowOffset
minRefFreq = args.RefUnitsMin
minSSRfreq = args.PopUnitsMin 
minNumReads = args.Support 
numFlankNucs = args.BorderSeq
nameSize = args.NameSize
refFilter = args.FilterDataLoci
qualityFilter = args.QualityFilter
debugName = args.AlignmentShow

ambiguousSlavageThreshold = args.spuriousAlleleRemoval
mismatch = args.mismatch

refDict = SeqIO.to_dict(SeqIO.parse(fastaRef, "fasta"))
#print(refDict)

def prepSam(samFile, includeNames = False):
    #samFile is string
    samData = {}
    with open(samFile, 'r') as f:
        for line in f:
            if line.startswith("@") == False:
                splitLine = line.split('\t')
                if len(splitLine) > 9:
                    refName = splitLine[2]
                    matchRead = splitLine[9]
                    quality = int(splitLine[4])
                    readID = splitLine[0]
                    if quality >= qualityFilter:
                        if refName not in samData:
                            samData[refName] = []
                        if includeNames:
                            samData[refName].append([matchRead, readID])
                        else:
                            samData[refName].append(matchRead)
    return samData

def genRepeats(repeatSize):
    returnable= []
    for x in itertools.product('ATGC', repeat=repeatSize):
        returnable.append(''.join(x))
    return(list(returnable))

def allCharactersSame(s) : 
    n = len(s) 
    for i in range(1, n) : 
        if s[i] != s[0] : 
            return False
    return True

def getMax(array):
    myMax = 0
    returnable = []
    for subArray in array:
        for v in subArray:
            if (len(v) > 0 and len(v[0])> myMax and allCharactersSame(v[1]) == False):
                myMax = len(v[0])
                returnable = v
    return returnable

    

def findRefRepeat(sequence, repeatSize):
    generatedRepeats = genRepeats(repeatSize) 
    result = []
    for s in generatedRepeats:
        reg = "".join(["((", s, ")+)"])
        found = re.findall(reg, str(sequence))
        result.append(found)
    theMax = getMax(result)
    if (len(theMax) <= 1):
        return(None, None, None, None)
    pattern = theMax[1]
    numRepeats = int(len(theMax[0])/repeatSize)
    dotStr = "."*numFlankNucs
    regPart2 = "".join(["(",dotStr,")((", pattern, "){", str(numRepeats), "})(",dotStr,")"])
    foundWflanks = re.findall(regPart2, str(sequence))
    if(len(foundWflanks) == 0):
        return(None, None, None, None)
    flankL = foundWflanks[0][0]
    flankR = foundWflanks[0][3]
    return(pattern, numRepeats, flankL, flankR)

def getMaxLen(array):
    myMax = 0
    for i in array:
        if (len(i[0])> myMax):
            myMax = len(i[0])
    return myMax
            
def findSpecificRepeat(read, repeat, flankL, flankR):
    reg = "".join([flankL,"((", repeat, ")+)", flankR])
    if mismatch > 0:
        mismatchStr = str(mismatch)
        reg = "".join([flankL,"{e<=",mismatchStr,"}((", repeat, ")+)", flankR, "{e<=",mismatchStr,"}"])
    # read="GATTTAAAAGTCGCGAGCCGCTGGTTGCTTAGAGAGAGAGATTTTGTGTGTTTGGTTTTGTCTGACGCTC"
    # print(read)
    # print(reg)
    # exit()
    # found = regex.findall(reg, str(read))
    found = ''
    try:
        found = regex.findall(reg, str(read))
    except Exception: 
        pass
    theMaxLen = getMaxLen(found)
    # print(found)
    # print(theMaxLen)
    # exit()
    ##filter repeat here
    if theMaxLen/len(repeat) < minSSRfreq:
        return None
    return theMaxLen/len(repeat)

def debugFindSpecificRepeat(read, repeat, flankL, flankR):
    reg = "".join([flankL,"((", repeat, ")+)", flankR])
    if mismatch > 0:
        mismatchStr = str(mismatch)
        reg = "".join([flankL,"{e<=",mismatchStr,"}((", repeat, ")+)", flankR, "{e<=",mismatchStr,"}"])
    found = regex.findall(reg, str(read))
    theMaxLen = getMaxLen(found)
    ##filter repeat here
    numRepeats = theMaxLen/len(repeat)
    if numRepeats < minSSRfreq:
        return None, None
    else:
        targetString = repeat*int(numRepeats)
        loc = re.search(targetString, read).span(0)
        return loc

def getRefSeqPattern(nameOfRead, lengthOfRepeat):
    refSeq = refDict[nameOfRead].seq
    refSeq = str(refSeq)
    refSeqSub = refSeq[flankOffset : -flankOffset]
    refPattern, refnumRepeats, flankL, flankR = findRefRepeat(refSeqSub, lengthOfRepeat)
    return (refPattern, refnumRepeats, flankL, flankR)


def veiwRefRead(refName):
    print(refDict[refName].seq)

def process2alleles(alleleData):
    allele1Support = alleleData[0][1]
    allele2Support = alleleData[1][1]
    ratio = allele2Support/(allele1Support + allele2Support)
    if ratio >= majorMinorRatio:
        sortedAlleles = sorted([alleleData[0][0], alleleData[1][0]])
        #smallest first
        return(str(sortedAlleles[0]) + "," + str(sortedAlleles[1]))
    else:
        #reported as homo in table and in stats
        return(str(alleleData[0][0]) + "," + str(alleleData[0][0]))
    
def printResults(resultArray):
    # resultArray is like 7,7,7,7,6,6,6,6
    if (len(resultArray) < minNumReads) or (len(resultArray) <= 0):
        #also not enough SSR freq
        return "0,-4"
        # not enough reads with SSRs were mapped
    uniqueValues = {}
    for i in resultArray:
        if int(i) not in uniqueValues:
            uniqueValues[int(i)] = 1 
        else:
            uniqueValues[int(i)] += 1
    alleleData = sorted(uniqueValues.items(), key=lambda x: x[1], reverse = True)
    # major allele is first
    if len(alleleData) == 0:
        return "ERROR"
    
    elif len(alleleData) == 1:
        return (str(alleleData[0][0]) +","+ str(alleleData[0][0]))
    
    elif len(alleleData) ==2:
        return(process2alleles(alleleData))
    
    elif len(alleleData) > 2:
        # allele data is sorted, [x][0] element SSR unit, [x][1] is reads supporting it
        # grab 3rd allele (alleleData[3]) and see how large it is compared to first 2
        sumFirst2 = alleleData[0][1] + alleleData[1][1]
        third = alleleData[2][1]
        if (third/sumFirst2) >= ambiguousSlavageThreshold:
            return "0,-3"
        else:
            #procced as if 2 alleles
            return(process2alleles(alleleData))

    return "ERROR"

def getStats(df):
    results = {'e1':0, 'e2':0, 'e3':0,'e4':0, 'het':0, 'homo':0}
    
    for c in df.columns[3:]:
        for i in df[c]:
            #first, second = i[0], i[1]
            first, second = i.split(",")
            if second == '-1':
                results['e1']+=1
            elif second == '-2':
                results['e2']+=1
            elif second == '-3':
                results['e3']+=1
            elif second == '-4':
                results['e4']+=1
            elif first == second:
                results['homo']+=1
            elif first != second:
                results['het']+=1
    return results
    
def writeStats(df, runtime, refProcessTime, totalSeqs, foundSeqs):
    stats = getStats(df)
    
    statOut = open(outFile + ".ssrstat", "w")
    statOut.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '\n\n')
    statOut.write('--Run Parameters--\n')
    statOut.write('SSR Reference: ' + fastaRef + '\n')
    statOut.write('Sam Files: ' + samsDoc + '\n')
    statOut.write('Output file names: ' + outFile + '\n')
    statOut.write('MinorAlleleHet: ' + str(majorMinorRatio) + '\n')
    statOut.write('Support: ' + str(minNumReads) + '\n')
    statOut.write('FlankSize: ' + str(numFlankNucs) + '\n')
    statOut.write('filterDataLoci: ' + str(refFilter) + '\n')
    statOut.write('filterDataSam: '+ str(filterDataSam) + '\n')
    statOut.write('QualityFilter: ' + str(qualityFilter) + '\n')
    statOut.write('spuriousAlleleRemoval: ' + str(ambiguousSlavageThreshold) + '\n')
    statOut.write('mismatch: ' + str(mismatch) + '\n')
    
    statOut.write('\n--Run Statistics--\n')
    statOut.write("Total fasta sequences in the modified Reference fasta: " + str(totalSeqs) + "\n")
    statOut.write("Total SSRs identified in the modified Reference " + str(foundSeqs) + '(' + str(round((foundSeqs/totalSeqs)*100, 2)) + "%)\n") # find sperately when going through mod ref
    numSam = len(df.columns[3:])
    totSam = len(samFiles)
    statOut.write("Total loci reported: " + str(df.shape[0]) + "\n")

    statOut.write("Total SAM files reported: " + str(numSam) + " of " + str(totSam) + " (" + str(round((numSam/totSam) *100, 2)) + "%)\n")
    statOut.write("Total number of genotypes called: " + str(stats['homo']+stats['het']) + "\n") # give percentages as well
    statOut.write("\tTotal Homozygous calls: " + str(stats['homo']) + "\n")
    statOut.write("\tTotal Heterozygous calls: " + str(stats['het']) + "\n")
    
    statOut.write("\n--Error codes--\n")
    statOut.write("(-1) No SSR found in reference (counted for each SAM file): " + str(stats['e1']) + "\n")
    statOut.write("(-2) No reads mapped to marker: " + str(stats['e2']) + " #These are missing genotypes due to the lack any mapped reads\n")
    statOut.write("(-3) Ambiguous (more than 2 alleles found): " + str(stats['e3']) + " #We expect 2 alleles in a true diploid, these are genotypes that were deemed ambiguous (i.e., the 3rd allele was greater than the spurious threshold)\n")
    statOut.write("(-4) Not enough coverage to call: " + str(stats['e4']) + " #These are missing genotypes due to insufficient read coverage (per the -S argument) – reads mapped but they didn’t reach the support threshold\n")
    
    statOut.write("RunTime: " + str(runtime) + " minutes" + "\n")
    if args.LinkageMapFile:
        statOut.write(mapStatString)
    statOut.close()

def findSamReads(subSam, refInput):
    # print(subSam)
    # print(refInput)
    # exit()
    refPattern = refInput[0]
    #refName = refInput[1]
    flankL =refInput[2]
    flankR = refInput[3]
    samRepeatCounts = []
    for r in subSam:
        appendable = findSpecificRepeat(r, refPattern, flankL, flankR)
        # print(r)
        # exit()
        if appendable != None:
            samRepeatCounts.append(appendable)
    returnable = printResults(samRepeatCounts)
    return returnable

def debugProcessSamString(samString, refInput):
    refPattern = refInput[0]
    flankL =refInput[2]
    flankR = refInput[3]
    result = debugFindSpecificRepeat(samString, refPattern, flankL, flankR)
    if result == None:
        return None, None
    else:
        return result
    
    #return L location and R location. Return None for a location if None found

def processSams(refData, outputDict, inSamFiles):
    #inSamFiles is list
    #split inSamFiles accross nodes - do in future
    # make list of sam files formed from N and then compare, print warning
    for samFile in inSamFiles:
        samFile = samFile.rstrip("\n")
        samData = prepSam(samFile)
        samName = samFile[0:nameSize]
        if samName in outputDict.keys():
            print("WARNING, 2+ file have name:", samName, " This may be caused by short -N arugment")
        colToAppend = []
        for refName in  refData.keys():
            if refData[refName] == 0:
                appendable= "0,-1"
            elif refName not in samData:
                appendable = "0,-2"
            else:
                subSam = samData[refName]
                #refData[refName] is a list
                appendable = findSamReads(subSam, refData[refName])
            colToAppend.append(appendable)
        outputDict[samName] = colToAppend
        print("processed SAM file:", samFile)

def searchRef(refDict, outputDict):
    print("processing SsrReference")
    refData = {}
    for name in refDict:
        refName = name.rstrip()
        refSeq = refDict[refName].seq
        refSeq = str(refSeq)
        # refSeqSub = refSeq[flankOffset : -flankOffset]
        # print(refName)
        refPattern=refName[refName.find('(')+1:refName.find(')')]
        refNumRepeats=int(refName[refName.find(')')+1:refName.find(':')])
        refRepeats=refNumRepeats*refPattern
        flankL=refSeq[:refSeq.find(refRepeats)]
        flankR=refSeq[refSeq.rfind(refRepeats)+len(refRepeats):]
        # print(refPattern)
        # print(refNumRepeats)
        # print(flankL)
        # print(flankR)
        # print(refSeq)
        # exit()
        # refPattern2, refNumRepeats2, flankL2, flankR2 = getRefSeqPattern(refName, 2)
        # refPattern3, refNumRepeats3, flankL3, flankR3 = getRefSeqPattern(refName, 3)
        # refPattern4, refNumRepeats4, flankL4, flankR4 = getRefSeqPattern(refName, 4)
        # print(refName)
        # print(refPattern3)
        # print(refNumRepeats3)
        # print(flankL3)
        # print(flankR3)
        # exit()
        # if (refNumRepeats2 == None):
            # refNumRepeats2 = 0
        # if (refNumRepeats3 == None):
            # refNumRepeats3 = 0
        # if (refNumRepeats4 == None):
            # refNumRepeats4 = 0
        # maxFreqArray = [refNumRepeats2, refNumRepeats3, refNumRepeats4]   
        # maxFreq = max(maxFreqArray)
        
        # if (maxFreq < minRefFreq):
            # refData[refName] = 0
        # elif(refNumRepeats2 == maxFreq):
            # refData[refName] = [refPattern2, refNumRepeats2, flankL2, flankR2]
        # elif(refNumRepeats3 == maxFreq):
            # refData[refName] = [refPattern3, refNumRepeats3, flankL3, flankR3]
        # elif(refNumRepeats4 == maxFreq):
            # refData[refName] = [refPattern4, refNumRepeats4, flankL4, flankR4]
        # else:
            # refData[refName] = 0
        if (refNumRepeats > 0):
            refData[refName] = [refPattern, refNumRepeats, flankL, flankR]
        else:
            refData[refName] = 0
        
        
        
        
    #create first 2 columns in outputDict
    outputDict["RefName"] = []
    outputDict["SSRPattern"] = []
    outputDict["RefGenotype"] = []
    for i in refData:
        outputDict["RefName"].append(i)
        if refData[i] != 0:
            outputDict["RefGenotype"].append(refData[i][1])
            outputDict["SSRPattern"].append(refData[i][0])
        else:
            outputDict["RefGenotype"].append(0)
            outputDict["SSRPattern"].append("---")
    return refData

def filterTable(outputDf):
    indexToRemove = []
    for index, row in outputDf.iterrows():
        toBeScored = row[3:]
        score = 0
        for i in toBeScored:
            if i.startswith("0",0,1):
                score +=1
        if score/len(toBeScored) >= refFilter:
            indexToRemove.append(index)
    newTable = outputDf.drop(outputDf.index[indexToRemove])
    return newTable

def filterTableSam(outputDf):
    for c in outputDf.columns[3:]:
        score = 0
        for i in c:
            if i.startswith('0'):
                score +=1
        if score/len(c) >= filterDataSam:
            outputDf = outputDf.drop(c,1)
    return outputDf

def debug2(debugName):
    output="ERROR"
    pattern = ""
    split = debugName.split(",")
    markerName = split[0]
    samFileName = split[1]
    outputDict = {}
    refData = searchRef(refDict, outputDict)
    if refData[markerName] != 0:
        pattern = refData[markerName][0]
    samFile = samFileName.rstrip("\n")
    samData = prepSam(samFile, True)
    if markerName not in refData:
        output = "marker not in SsrReference"
    elif markerName not in samData:
        output = "no reads mapped to this marker"
    else:
        output = "Marker: " + markerName + "\n" + "SAM file: " + samFileName + "\n" + "Pattern: " + pattern + "\n"
        refSeq = str(refDict[markerName].seq)
        flankRlocationRef = re.search(refData[markerName][3], refSeq)
        flankLlocationRef = re.search(refData[markerName][2], refSeq)
        refSeq2 = refSeq[:flankLlocationRef.start() + numFlankNucs] + "   " + refSeq[flankLlocationRef.start() + numFlankNucs:flankRlocationRef.start()] + "   " + refSeq[flankRlocationRef.start():]
        output += "\n SsrReference Sequence: " + refSeq2 + "\n\n" 
        subSam = samData[markerName]
        goodReads = []
        badReads = []
        for sub in subSam:
            s = sub[0]
            subName = sub[1]
            flankLlocation, flankRlocation = debugProcessSamString(s, refData[markerName])
#            flankRlocation = re.search(refData[markerName][3], s)
#            flankLlocation = re.search(refData[markerName][2], s)
            if flankLlocation == None or flankRlocation == None:
                badReads.append(s + "  ---" + subName + "---")
            else:
                offset = " " * (flankLlocationRef.start() - flankLlocation + 44) #change this 20 to something more dynamic
                newS = offset + s[:flankLlocation] + "   " + s[flankLlocation:flankRlocation] + "  "+ s[flankRlocation:]
                goodReads.append(newS + "  ---" + subName + "---")
        for g in goodReads:
            g2 = g.rstrip("\n")
            output += (g2 +"\n")
        output += "\n"
        for b in badReads:
            b2 = b.rstrip("\n")
            output += (b2 + "\n")
    with open(markerName + '-' + samFileName +".txt", "w" ) as w:
        w.write(output)     
        
def debug(debugName):
    output="ERROR"
    pattern = ""
    split = debugName.split(",")
    markerName = split[0]
    samFileName = split[1]
    outputDict = {}
    refData = searchRef(refDict, outputDict)
    if refData[markerName] != 0:
        pattern = refData[markerName][0]
    samFile = samFileName.rstrip("\n")
    samData = prepSam(samFile, True)
    if markerName not in refData:
        output = "marker not in SsrReference"
    elif markerName not in samData:
        output = "no reads mapped to this marker"
    else:
        output = "Marker: " + markerName + "\n" + "SAM file: " + samFileName + "\n" + "Pattern: " + pattern + "\n"
        refSeq = str(refDict[markerName].seq)
        flankRlocationRef = re.search(refData[markerName][3], refSeq)
        flankLlocationRef = re.search(refData[markerName][2], refSeq)
        refSeq2 = refSeq[:flankLlocationRef.start() + numFlankNucs] + "   " + refSeq[flankLlocationRef.start() + numFlankNucs:flankRlocationRef.start()] + "   " + refSeq[flankRlocationRef.start():]
        output += "\n SsrReference Sequence: " + refSeq2 + "\n\n" 
        subSam = samData[markerName]
        goodReads = []
        badReads = []
        for sub in subSam:
            s = sub[0]
            subName = sub[1]
            flankRlocation = re.search(refData[markerName][3], s)
            flankLlocation = re.search(refData[markerName][2], s)
            if flankLlocation == None or flankRlocation == None:
                badReads.append(s + "  ---" + subName + "---")
            else:
                offset = " " * (flankLlocationRef.start() - flankLlocation.start() + 20) 
                newS = offset + s[:flankLlocation.start() + numFlankNucs] + "   " + s[flankLlocation.start() + numFlankNucs:flankRlocation.start()] + "  "+ s[flankRlocation.start():]
                goodReads.append(newS + "  ---" + subName + "---")
        for g in goodReads:
            g2 = g.rstrip("\n")
            output += (g2 +"\n")
        output += "\n"
        for b in badReads:
            b2 = b.rstrip("\n")
            output += (b2 + "\n")
    with open(markerName + '-' + samFileName +".txt", "w" ) as w:
        w.write(output)

parentLociGuess = 0

def parentguess(known, r):
    global parentLociGuess
    allele = {}
    total = (len(r)-3)*2
    for e in r[4:]:
        if e[0] != '0':
            if e[0] not in allele:
                allele[e[0]] = 1
            else:
                allele[e[0]] += 1
            if e[1] not in allele:
                allele[e[1]] = 1
            else:
                allele[e[1]] += 1
    alleleSorted = sorted(allele.items(), key=lambda x: x[1], reverse = True)
    
    if len(alleleSorted) == 0:
        return None
    if alleleSorted[0][0] != known:
        if alleleSorted[0][1]/ total >= args.LinkageMapFile:
            parentLociGuess +=1
            return alleleSorted[0][0]
    else:
        if len(alleleSorted) > 1:
            if alleleSorted[1][1]/ total >= args.LinkageMapFile:
                parentLociGuess +=1
                return alleleSorted[1][0]

def checkHet(li):
    if li[0] == '0':
        return False
    if li[0] != li[1]:
        return True
    else:
        return False

mapStatString =''
      
def makeMap(outputDf):
    if outputDf.shape[1] < 5:
        print("ERROR: provide atleast 2 SAM files (2 parents)")
        return
    
    linkMap = []
    listTable = []
    print("Creating Map")
    
    #convert table elements to list of rows
    for index, row in outputDf.iterrows():
        newRow = [row[0]]
        for element in row[3:]:
            newRow.append(element.split(','))
        listTable.append(newRow)
    
    for r in listTable:
        linkMapRow =[r[0]]
        p1 = r[1][0]
        p2 = r[2][0]
        #both missing
        if r[1][0] == '0' and r[2][0] == '0':
            continue
        #check if het, returns true if het
        elif checkHet(r[1]) or checkHet(r[2]):
            continue
        #check if A and B are same (only compare first num b/c won't be het)
        elif r[1][0] == r[2][0]:
            continue
        elif r[1][0] == '0':
            p1 = parentguess(r[2][0],r)
            if p1 == None:
                continue
        elif r[2][0] == '0':
            p2 = parentguess(r[1][0],r)
            if p2 == None:
                continue
        #procced normally with stuff
        for e in r[1:]:
            if e[0] == p1 and e[1] == p1:
                linkMapRow.append('A')
            elif e[0] == p2 and e[1] == p2:
                linkMapRow.append('B')
            elif (e[0] == p1 and e[1] == p2) or (e[0] == p2 and e[1] == p1):
                linkMapRow.append('H')
            else:
                linkMapRow.append('-')
        linkMap.append(linkMapRow)
             
    #transform newTableAsList to newTable
    newDf = pd.DataFrame(linkMap)
        #get headers from old table
    headers = outputDf.columns.values.tolist()
    del headers[1:3]
    newDf.columns = headers
    
    newDf.to_csv(outFile + ".map", sep= "\t", index=False)
    
    #append to stats, newDf is link map
    numA =0
    numB = 0
    numH = 0
    numDash = 0
    #if only 3 columns, no children so don't bother with stats
    if newDf.shape[0] <= 3:
        return
    
    for c in newDf.columns[3:]:
        for i in newDf[c]:
            if i == 'A':
                numA +=1
            if i == 'B':
                numB +=1
            if i == 'H':
                numH +=1
            if i == '-':
                numDash +=1
                
    total = numA + numB + numH
    global parentLociGuess
    global mapStatString
    mapStatString = '\n--Map Stats--\n' + 'Total loci reported: ' + str(newDf.shape[0]) + '\n' + 'note: percent calulated by (count / (A + B + H)), ignores first 2 SAM files (parents)\n'+'Count A: ' + str(numA) + ' (' + str(round(numA/total*100, 2))+ '%)\n'+'Count B: '+ str(numB) + ' (' + str(round(numB/total*100, 2))+ '%)\n'+'Count H: ' + str(numH) + ' (' + str(round(numH/total*100, 2))+ '%)\n'+'Count -: ' + str(numDash) + ' #Missing genotypes\n'+'Number of parental genotypes imputed: ' + str(parentLociGuess) + '#genotypes that were imputed for one of the parents based on the -L argument\n'

def isNotMono(row):
    row = row[3:]
    known = []
    for i in row:
        if i.startswith('0') == False:
            known.append(i)
    if len(set(known)) == 1:
        return False        
    return True

def removeMonomorph(df):
    return df[df.apply(isNotMono,1)]

def createGenePop(outputDf):
    print("creating genePopFile")
    #first line is title
    #second line is marker
    #third line is pop
    #data
    
    outputDf = removeMonomorph(outputDf)
    title = "SSR markers for "+outFile # first line
    # print(outputDf)
    # exit()
    locusList = outputDf.iloc[:,0].tolist()       
    
    with open(outFile + '.pop.txt', 'w') as popWriter:
        popWriter.write(title + '\n')
        for locus in locusList:
            popWriter.write(locus + '\n')
        popWriter.write('POP' + '\n')
        for columnName in outputDf.columns[3:]:
            popWriter.write(columnName + ',')
            col = outputDf[columnName].tolist()
            for i in col:
                a,b = i.split(',')
                if int(a) > 99 or int(b) > 99:
                    print('Warning, allele number is greater than 99, genepop format may not work')
                if int(a) == 0:
                    a ='0'
                    b = '0'
                a = a.zfill(3)
                b = b.zfill(3)
                popWriter.write('\t'+a+b)
            popWriter.write('\n')
                


def main():
    if debugName != "":
        debug2(debugName)
        return
    
    startTime = time.time()      
    
    outputDict = {}
    refData = searchRef(refDict, outputDict)
    # print(refData)
    # exit()
    totalSeqs = len(refData)
    foundSeqs = totalSeqs - sum(x == 0 for x in refData.values())
    refProcessTime = str(round((time.time() - startTime)/60, 2))
    print("processed SsrReference in:", refProcessTime, "minutes")
    #process Sams
    processSams(refData, outputDict, samFiles)
    outputDf = pd.DataFrame(outputDict)
    if refFilter != 1:
        outputDf = filterTable(outputDf)
    if filterDataSam != 1:
        outputDf = filterTableSam(outputDf)
    outputDf.to_csv(outFile + ".ssr", sep= "\t", index=False)
    if args.Genepop:
        a = copy.deepcopy(outputDf)
        createGenePop(a)
    if args.LinkageMapFile:
        b = copy.deepcopy(outputDf)
        makeMap(b)
    
    endTime = time.time()
    runtime = endTime-startTime
    runtime = str(round(runtime/60, 2))
    print("run time:", runtime, "minutes")
    writeStats(outputDf, runtime, refProcessTime, totalSeqs, foundSeqs)

        
main()
