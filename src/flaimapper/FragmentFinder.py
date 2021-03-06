#!/usr/bin/env python

"""FlaiMapper: computational annotation of small ncRNA derived fragments using RNA-seq high throughput data

 Here we present Fragment Location Annotation Identification mapper
 (FlaiMapper), a method that extracts and annotates the locations of
 sncRNA-derived RNAs (sncdRNAs). These sncdRNAs are often detected in
 sequencing data and observed as fragments of their  precursor sncRNA.
 Using small RNA-seq read alignments, FlaiMapper is able to annotate
 fragments primarily by peak-detection on the start and  end position
 densities followed by filtering and a reconstruction processes.
 Copyright (C) 2011-2014:
 - Youri Hoogstrate
 - Elena S. Martens-Uzunova
 - Guido Jenster
 
 
 [License: GPL3]
 
 This file is part of flaimapper.
 
 flaimapper is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.
 
 flaimapper is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program. If not, see <http://www.gnu.org/licenses/>.

 Documentation as defined by:
 <http://epydoc.sourceforge.net/manual-fields.html#fields-synonyms>
"""


import os,re,random,operator,argparse,sys

from flaimapper.ncRNAfragment import ncRNAfragment


class FragmentFinder:
	"""Class Flaimapper Finds fragments in alignment files.
	
	@todo merge masked_region
	"""
	def __init__(self,masked_region,readcount,autorun=True):
		"""
		----
		@param: name
		@param: seq
		@param: readcount
		@param: autorun
		"""
		
		self.masked_region = masked_region
		self.name = masked_region[0]
		
		if(autorun):
			self.positions = {}
			self.positions['startPositions'] = readcount.start_positions
			self.positions['stopPositions'] = readcount.stop_positions
			self.positions['startAvgLengths'] = readcount.start_avg_lengths
			self.positions['stopAvgLengths'] = readcount.stop_avg_lengths
			
			self.peaksStart = False
			self.peaksStop = False
			
			self.correctedPeaksStart = False
			self.correctedPeaksStop = False
			
			self.run()
		
	def findPeaks(self,plist,drop_cutoff=0.1):
		"""
		----
		@return: 
		@rtype: dictionary
		"""
		
		# Define variables:
		peaks = {}
		
		previous = 0
		highest = 0
		highestPos = -1
		
		# Walk over list of [start/stop]-position counts:
		for pos in range(len(plist)):
			current = plist[pos]
			if((current > previous) ):# and (current > (noise_type_alpha_cutoff/100.0*max(plist)))):  
				if current > highest:
					highest = current
					highestPos = pos
			elif (current < previous):
				#if (current < (drop_cutoff*highest)) and (highestPos != -1):
				#if (current < (100.0*drop_cutoff*highest)) and (highestPos != -1):   #
				#if (current < (10.0*highest)) and (highestPos != -1):   # 
				if (drop_cutoff * current < highest) and (highestPos != -1):
					peaks[highestPos] = highest
					
					#highestPos = -1
					highest = 0
			
			previous = current
		return peaks
	
	def correctNeighbourPeaks(self,plist):
		"""
		Smooth filtering
		----
		@return:
		@rtype:
		"""
		
		psorted = sorted(plist.iteritems(),key=operator.itemgetter(1))[::-1]
		pmatrix = {
		-15 :0.00003726653,
		-14 :0.0001866447,
		-13 :0.008364835,
		-12 :0.0354626,
		-11 :0.1203860,
		-10 :0.3865920,
		 -9 :1.110900,
		 -8 :2.856550,
		 -7 :6.572853,
		 -6 :13.53353,
		 -5 :24.93522,
		 -4 :100,
		 -3 :100,
		 -2 :100,
		 -1 :100,
		
		  1 :100,
		  2 :100,
		  3 :100,
		  4 :100,
		  5 :24.93522,
		  6 :13.53353,
		  7 :6.572853,
		  8 :2.856550,
		  9 :1.110900,
		 10 :0.3865920,
		 11 :0.1203860,
		 12 :0.0354626,
		 13 :0.008364835,
		 14 :0.0001866447,
		 15 :0.00003726653 }
		
		# There is a small mistake in the algorithm,
		# it should search not for ALL peaks
		# but only for ALL peaks except itself; position i can not be a noise product of i itself
		
		for i in range(len(psorted)):
			if(psorted[i] != False):
				item = psorted[i]
				for j in range(len(psorted)):							# Can be limited to size and -size of pmatrix
					if((psorted[j] != False) and (j != i)):
						item2 = psorted[j]
						diff = item2[0]-item[0]
						if(pmatrix.has_key(diff)):
							perc = pmatrix[diff]/100.0
							if((perc*item[1]) > item2[1]):
								psorted[j] = False
		
		pnew = {}
		
		for item in psorted:
			if(item != False):
				pnew[item[0]] = item[1]
		
		return pnew
	
	def find_fragments(self,pstart,pstop,pexpectedStart,pexpectedStop,prime_5_ext = 3,prime_3_ext=5,genomic_offset_masked_region=0):
		"""Traceback:
		
		genomic_offset_masked_region - imagine your pre-miRNA is starts at position 400.000 in the genome; then your position should be 400.000 + start
		
		----
		@return:
		@rtype:
		"""
		fragments = []
		if(len(pstart) >= len(pstop)):									# More start than stop positions
			pstopSorted = sorted(pstop.iteritems(),key=operator.itemgetter(1))[::-1]
			for itema in pstopSorted:
				pos = itema[0]
				diff = pexpectedStop[pos]
				predictedPos = pos+diff+1								# 149 - 50 = 99; 149- 50 + 1 = 100 (example of read aligned to 100,149 (size=50)
				fragment = False
				
				highest = 0
				items = [s for s in pstart if ((s >= predictedPos-15) and (s <= predictedPos+15))]
				for item in items:
					distance = abs(predictedPos - item)
					penalty = 1.0 - (distance * 0.09)
					score = pstart[item]*penalty 
					if(score >= highest):
						highest = pstart[item]
						
						fragment = ncRNAfragment(item,pos,None,self.masked_region,genomic_offset_masked_region)
						fragment.supporting_reads_start = pstart[fragment.start]
						fragment.supporting_reads_stop = pstop[fragment.stop]
				
				if(fragment != False):
					fragments.append(fragment)
					del(pstart[fragment.start])
					items = []
		else:															# More stop than start positions
			pstartSorted = sorted(pstart.iteritems(),key=operator.itemgetter(1))[::-1]
			for itema in pstartSorted:
				pos = itema[0]
				diff = pexpectedStart[pos]
				
				#@todo figure out if this requires << + 1
				predictedPos = pos+diff
				fragment = False
				
				highest = 0
				items = [s for s in pstop if ((s >= predictedPos-15) and (s <= predictedPos+15))]
				
				for item in items:
					distance = abs(predictedPos - item)
					penalty = 1.0 - (distance * 0.09)
					score = pstop[item]*penalty 
					if(score >= highest):
						highest = pstop[item]
						
						#fragment = {'start':pos,'stop':item,'sequence':None}
						#fragment['start_supporting_reads'] = pstart[fragment['start']]
						#fragment['stop_supporting_reads']  = pstop[fragment['stop']]
						
						fragment = ncRNAfragment(pos,item,None,self.masked_region,genomic_offset_masked_region)
						fragment.supporting_reads_start = pstart[fragment.start]
						fragment.supporting_reads_stop = pstop[fragment.stop]
				
				if(fragment != False):
					fragments.append(fragment)
					del(pstop[fragment.stop])
					items = []
		#(counter >= fragment['start']) and (counter < fragment['stop'])
		
		for fragment in fragments:
			#fragment['sequence'] = self.seq[fragment['start']:fragment['stop']]
			
			cut5 = prime_5_ext
			cut3 = prime_3_ext
			
			"""
			@todo fix this:
			diff = fragment['start']-prime_5_ext
			cut5 = prime_5_ext
			if(diff < 0):
				cut5 = prime_5_ext+diff
			
			diff = len(self.seq)-(fragment['stop']+prime_3_ext)
			cut3 = prime_3_ext
			if(diff < 0):
				cut3 = prime_3_ext + diff
			"""
			
			#fragment['extended'] = {'5_prime_cut':cut5,'3_prime_cut':cut3,'5_prime_pos':fragment['start']-cut5,'3_prime_pos':fragment['stop']+cut3,'sequence':self.seq[(fragment['start']-cut5):(fragment['stop']+cut3)]}
			fragment.extended = {
				'5_prime_cut':cut5,
				'3_prime_cut':cut3,
				
				'5_prime_pos':fragment['start']-cut5,
				'3_prime_pos':fragment.stop+cut3
				}
		
		return fragments
	
	def run(self):
		"""
		----
		@return:
		@rtype:
		"""
		
		# Finds peaks
		self.peaksStart = self.findPeaks(self.positions['startPositions']+[0])
		self.peaksStop = self.findPeaks(self.positions['stopPositions']+[0])
		
		# Correct / filter noisy peaks
		self.correctedPeaksStart = self.correctNeighbourPeaks(self.peaksStart)
		self.correctedPeaksStop = self.correctNeighbourPeaks(self.peaksStop)
		
		# Trace start and stop positions together and obtain actual peaks
		self.results = self.find_fragments(self.correctedPeaksStart,self.correctedPeaksStop,self.positions['startAvgLengths'],self.positions['stopAvgLengths'])
		
		return True
	
	def getResults(self):
		"""
		---
		@return:
		@rtype:
		"""
		return self.results
