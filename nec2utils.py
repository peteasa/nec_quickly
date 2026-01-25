'''
Copyright 2012 Will Snook (http://willsnook.com)
Copyright 2015 Chris Kuethe (https://github.com/ckuethe)
Copyright 2026 Peter Saunderson
MIT License

Utility code for generating antenna geometry files in nec2 card stack format
'''

import copy
from enum import Enum
import math

# =======================================================================================================
# Field formatting functions (i.e. "columns" in punchcard-speak)
# =======================================================================================================

def sci(f):
	''' Return formatted string containinga scientific notaion float in a 13 char wide field (xyz coordiates, radius)
	'''
	return '{: > 13.5E}'.format(f)


def dec(i):
	''' Return formatted string containing a decimal integer in a 6 char wide field (tags, segments)
	'''
	return '{: >6d}'.format(math.trunc(i))


# =======================================================================================================
# Unit conversions... The nec2 engine requires its inputs to be in meters and degrees. Note that these
# functions are named to denote the pre-conversion units, because I consider those more suitable for
# the calculations I will be working with.
# =======================================================================================================

def m(m):
	''' Convert meters to meters. Useful for being consistent about always specifying units and for
		making sure not to accidentaly run afoul of Python's integer math (hence the * 1.0)
	'''
	return m * 1.0

def inch(i):
	''' Convert inches to meters
	'''
	return i * 2.54 / 100.0

def deg(degrees):
	''' Make sure degrees are float
	'''
	return degrees * 1.0

def AWG(n):
	'''
	convert awg to wire diameter in m.
	AWG 0000 (4/0) .. 0 (1/0) maps to -3..0
	'''
	if type(n) is not int:
		raise TypeError('AWG must be an integer')
	if n not in range(-3, 41):
		raise ValueError('AWG must be from -3 to 40')
	# https://en.wikipedia.org/wiki/American_wire_gauge
	return math.exp(2.1104 - 0.11594*n) * 1e-3

# =======================================================================================================
# Output conversions from meters back to inches
# =======================================================================================================

def mToIn(meters):
	''' Convert meters back to inches for output in the comment section
	'''
	return meters * 100.0 / 2.54




# =======================================================================================================
# 3D point and rotation classes
# =======================================================================================================

class Point:
	def __init__(self,x,y,z):
		self.x = float(x)
		self.y = float(y)
		self.z = float(z)


class Rotation:
	def __init__(self,rx,ry,rz):
		self.rx = float(rx)
		self.ry = float(ry)
		self.rz = float(rz)


# =======================================================================================================
# Model class
# =======================================================================================================

class Model:
	class Pos(Enum):
		START = 1
		MID = 2
		END = 3

	def __init__(self, wireRadius, ldtyp=5, ldtagf=0, ldtagt=0, zlr=None, zli=None, zlc=None,
				 wavelength=None, frequency=None, velocityfactor=1.0):
		''' Prepare the model with the given wire radius
			if zlr, zli or zlc are specified then all wires have the same conductivity
			else loading for each wire must be specified separately
		'''
		self.geoelems   = ""
		self.wires	= ""
		self.transforms = ""
		self.wireRadius = wireRadius
		self.tag	= 0
		# for feed
		self.EX_segment = -1
		# for load
		self._extras = []
		self.zlr = zlr
		self.zli = zli
		self.zlc = zlc
		self.loadall = not self.isLoadNone(self.zlr, self.zli, self.zlc)
		if self.loadall:
			self.addExtra(self.ld(ldtyp, 0, ldtagf, ldtagt, zlr, zli, zlc))
		# for ground card
		self.hasGrnd = False

		self.velocityfactor = velocityfactor
		if (wavelength and frequency):
			self.wavelength = wavelength
			self.frequency = frequency
		elif wavelength:
			self.wavelength = wavelength
			self.frequency = self.velocityfactor * 3e8 / self.wavelength
		elif frequency:
			self.frequency = frequency
			self.wavelength = self.velocityfactor * 3e8 / self.frequency
		else:
			self.wavelength = self.frequency = None

		self.transformBuffer = ''

	# ---------------------------------------------------------------------------------------------------
	# Low-level functions to generate nec2 cards
	# See documentation at http://www.nec2.org/part_3/cards/
	# Tag & segments have no units. Dimensions are in meters. Angles are in degrees.
	# ---------------------------------------------------------------------------------------------------

	def isLoadNone(self, zlr=None, zli=None, zlc=None):
		''' Test to see if a load has been specified
		'''
		return (zlr is None) and (zli is None) and (zlc is None)

	def flushTransformBuffer(self):
		''' Used in some song and dance to avoid the edge case that can occur with an arc as the last element
		    My double GM card trick causes a problem if the second GM tries to refer to a tag that doesn't exist
		'''
		self.transforms += self.transformBuffer
		self.transformBuffer  = ""


	def gw(self, tag, segments, x1, y1, z1, x2, y2, z2, radius):
		''' Return the line for a GW card, a wire.
		'''
		gw = "GW" + dec(tag) + dec(segments)
		gw += sci(x1) + sci(y1) + sci(z1)
		gw += sci(x2) + sci(y2) + sci(z2)
		gw += sci(radius) + "\n"
		return gw

	def gh(self, tag, segments, pitch,height, xzr1,yzr1, xzr2,yzr2, wireRadius):
		'''
		NEC2 calls it "Turns Spacing" and "Helix Length"; I
		prefer to say "Pitch" and "Height", respectively.

		Height is how tall the structure is if you stand it up on a
		table. It has nothing to do with wire length. Zero height
		generates a flat spiral, non-zero height generates a spring.
		Negative height generates a left hand turn.

		Pitch is how far apart the wires are per turn; in spirals
		that's like cylinder number on a disk, for springs, that's
		height per turn. Thus, n_turns = height / spacing

		xzrN == yzRN ? circular : ellipsoid

		r1 == r2 ? cylindrical : tapered

		'''
		gh = "GH" + dec(tag) + dec(segments)
		gh += sci(pitch) + sci(height)
		gh += sci(xzr1) + sci(yzr1) + sci(xzr2) + sci(yzr2)
		gh += sci(wireRadius) + "\n"
		return gh

	def sp(self, typ, x1, y1, z1, f4, f5, f6):
		''' Return the line for a SP card for a surface patch.
		patch size should match the segment size of wires.
		NEC2: a patch is not directly excited unless a wire segment connects to the patch centre
		patches constructed by the reflection card are not electrically connected but rather
		NEC4: is slightly better. This difference can cause a model for NEC4 to fail in NEC2
		'''
		sp = "SP" + dec(0) + dec(typ)
		sp += sci(x1) + sci(y1) + sci(z1)
		sp += sci(f4) + sci(f5) + sci(f6)
		sp += "\n"
		return sp

	def sc(self, typ, xnp1, ynp1, znp1, xnp2=0., ynp2=0., znp2=0.):
		''' Return the line for a SC card for a surface patch connected to the preceeding SP patch
		'''
		sc = "SC" + dec(0) + dec(typ)
		sc += sci(xnp1) + sci(ynp1) + sci(znp1)
		sc += sci(xnp2) + sci(ynp2) + sci(znp2)
		sc += "\n"
		return sc

	def ld(self, typ, tag=0, tagf=0, tagt=0, zlr=None, zli=None, zlc=None):
		''' Return the line for a LD card, a wire. Apply after any reflection
		'''
		ld = ""
		if not self.isLoadNone(zlr, zli, zlc):
			ld = "LD" + dec(typ)
			ld += dec(tag) + dec(tagf) + dec(tagt)
			if zlr is None:
				# either enter zlr or zero
				ld += sci(0)
			else: ld += sci(zlr)
			if not zlc is None and zli is None:
				ld += sci(0)
			elif not zli is None:
				# either enter zli or leave blank
				ld += sci(zli)
			if not zlc is None:
				ld += sci(zlc)
			ld += "\n"

		return ld

	def ga(self, tag, segments, arcRadius, startAngle, endAngle, wireRadius):
		''' Return the line for a GA card, an arc in the X-Z plane with its center at the origin
		'''
		notUsed = 0.0
		ga = "GA" + dec(tag) + dec(segments)
		ga += sci(arcRadius) + sci(startAngle) + sci(endAngle)
		ga += sci(wireRadius)
		ga += sci(notUsed) # Note: xnec2c fills this in with its "Segs % lambda" field, but that may be a bug
		ga += sci(notUsed) + sci(notUsed) + "\n"
		return ga

	def gm(self, tagIncrement=0, newStructures=0, rotX=0, rotY=0, rotZ=0, trX=0, trY=0, trZ=0, firstTag=0):
		''' Return the line for a GM card, move (rotate and translate).
			rotX, rotY, and rotZ: angle to rotate around each axis
			trX, trY, and trZ: distance to translate along each axis
			firstTag: first tag# to apply transform to (subseqent tag#'s get it too... like it or not)
		'''
		gm = "GM" + dec(tagIncrement) + dec(newStructures)
		gm += sci(rotX) + sci(rotY) + sci(rotZ)
		gm += sci(trX) + sci(trY) + sci(trZ)
		gm += sci(firstTag*1.0) + "\n"
		return gm

	def gx(self, tagIncrement=0, reflectX=0, reflectY=0, reflectZ=0):
		''' Return the line for a GX card, reflect
		'''
		gx = "GX" + dec(tagIncrement) + dec(100*(reflectX%2) + 10*(reflectY%2) + (reflectZ%2))
		gx += "\n"
		return gx

	def ge(self):
		''' Card to "terminate reading of geometry data cards"
		'''
		GPFLAG = 0  # Ground plane flag. 0 means no ground plane present.
		ge = "GE"
		ge += dec(GPFLAG) + dec(0) + sci(0) + sci(0) + sci(0) + sci(0) + sci(0) + sci(0) + sci(0) + "\n"
		return ge

	def fr(self, start, stepSize, stepCount):
		''' Define the frequency range to be modeled
		'''
		IFRQ = 0           # Step type, 0 is linear (additive), 1 = multiplicative
		NFRQ = stepCount   # Number of frequency steps
		I3   = 0           # blank
		I4   = 0           # blank
		FMHZ   = start     # Starting frequency in MHz
		DELFRQ = stepSize  # Frequency stepping increment (IFRQ=0), or multiplication factor (IFRQ=1)
		fr = "FR"
		fr += dec(IFRQ) + dec(NFRQ) + dec(I3) + dec(I4)
		fr += sci(FMHZ) + sci(DELFRQ) + "\n"
		return fr

	def ex(self, i1=0, i2=0, i3=0, i4=0, f1=0.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0, f7=0.0):
		''' Define excitation parameters.
		'''
		# for a voltage source
		# i1 Excitation type. 0 means an "applied-E-field" voltage source
		# i2 Tag number of the wire element to which the source will be applied
		# i3 Segment within the previously specified wire element to which the source will be applied
		# i4 0 means use defaults for admittance matrix asymmetry and printing input impedance voltage
		# f1 Real part of voltage
		# f2 Imaginary part of voltage
		# see nec2 specifications for other source parameters
		ex = "EX"
		ex += dec(i1) + dec(i2) + dec(i3) + dec(i4)
		ex += sci(f1) + sci(f2) + sci(f3) + sci(f4) + sci(f5) + sci(f6) + sci(f7) + "\n"
		return ex

	def gn(self, iperf=1, nradl=0, espr=0.0, sig=0.0, rads=0.0, radw=0.0):
		''' Return the line for a GN card, ground parameters
		'''
		# iperf Ground-type flag
		# nradl Number of radial wires in the ground screen
		# espr  Relative dielectric constant of the second medium
		# sig   Conductivity in mhos/meter of the second medium.
		# rads  radius of the screen in meters
		# radw  Radius of the wires used in the screen
		self.hasGrnd = True
		ze = 0
		gn = "GN" + dec(iperf) + dec(nradl) + dec(ze) + dec(ze)
		gn += sci(espr) + sci(sig) + sci(rads) + sci(radw) + "\n"
		return gn

	def gd(self, espr=0.0, sig=0.0, clt=0, cht=0):
		''' Return the line for a GD card, additional ground parameters
		'''
		# espr  Relative dielectric constant of the second medium
		# sig   Conductivity in mhos/meter of the second medium.
		# clt   Distance in meters from the origin to the join between medium 1 and 2
		# cht   Distance in meters by which the surface of medium 2 is below medium 1
		ze = 0
		gd = "GD" + dec(ze)+ dec(ze)+ dec(ze)+ dec(ze)
		gd += sci(espr) + sci(sig) + sci(clt) + sci(cht) + "\n"
		return gd

	def rp(self, mode=0, nth=37, nph=37, dth=10.0, dph=10.0):
		''' Card to initiate calculation and output of radiation pattern.
		'''
		# 0 is normal mode: defaults to free-space unless a previous GN card specified a ground plane
		n_th = nth ; theta = dth
		if self.hasGrnd and 90 < nth * dth:
			n_th = 9 ; theta = 10

		# Number of values of theta (angle away from positive Z axis)
		# Number of values of phi (angle away from X axis in the XY plane)
		I4  = 0	  # Use defaults for some misc output printing options
		THETS = 0.0  # Theta start value in degrees
		PHIS  = 0.0  # Phi start value in degrees
		# Delta-theta in degrees
		# Delta-phi in degrees
		rp = "RP"
		rp += dec(mode) + dec(n_th) + dec(nph) + dec(I4)
		rp += sci(THETS) + sci(PHIS) + sci(theta) + sci(dph) + "\n"
		return rp

	def en(self):
		''' Card to mark end of input
		'''
		return "EN\n"

	# ---------------------------------------------------------------------------------------------------
	# High-level geometry functions
	# ---------------------------------------------------------------------------------------------------

	def addLD(self, ldtyp, ldtagf=0, ldtagt=0, zlr=None, zli=None, zlc=None):
		''' Append an additional LD card using relative segment numbers ldtagf, ldtagt to the current wire tag.
			These cards are added from an extra card list after the geometry specification is complete.
			addWire() can be used to add an LD card without calling this API
		'''
		if ldtyp == -1:
			# short all previous loads
			self.loadall = False
			self.addExtra("LD"+dec(ldtyp)+"\n")
		else:
			if self.loadall and not self.isLoadNone(zlr, zli, zlc):
				print('WARNING: using global wire load; per wire load ignored')
			elif not self.isLoadNone(zlr, zli, zlc):
				# typ 5: wire conductivity ldtagf (start seg), ldtagt (last seg) 0: all segments the same
				self.addExtra(self.ld(ldtyp, self.tag, ldtagf, ldtagt, zlr, zli, zlc))

	def addWire(self, segments, pt1, pt2, ldtyp=5, ldtagf=0, ldtagt=0, zlr=None, zli=None, zlc=None):
		''' Append a wire, increment the tag number, and return this object to facilitate a chained attachToEX() call
		Optionally also add an LD card specific to this wire (when not using the global wire LD card)
		'''
		self.tag += 1
		self.wires += self.gw(self.tag, segments, pt1.x, pt1.y, pt1.z, pt2.x, pt2.y, pt2.z, self.wireRadius)
		self.flushTransformBuffer()
		self.midseg = math.trunc(segments/2) + 1
		self.pt1 = copy.copy(pt1)
		self.pt2 = copy.copy(pt2)

		# calculate mid point, alpha and beta for current source
		self.midpoint = ((pt1.x + pt2.x)/2, (pt1.y + pt2.y)/2, (pt1.z + pt2.z)/2)
		xdiff = pt2.x - pt1.x
		xdiffsign = -1. if pt2.x < pt1.x else 1.
		xdiff = xdiff if 0.0000001 < abs(xdiff) else xdiffsign * 0.0000001
		ydiff = pt2.y - pt1.y
		if abs(ydiff) < 0.0000001:
			self.beta = 0.0
		else:
			self.beta = 180. * math.atan2(ydiff, xdiff) / math.pi

		xydiff = math.sqrt((xdiff)**2 + (ydiff)**2)
		zdiffsign = -1. if pt2.z < pt1.z else 1.
		self.alpha = 180. * math.atan2(pt2.z - pt1.z, xydiff) / math.pi if 0.0000001 < abs(xydiff) else zdiffsign * 90.

		# print('alpha: {} beta: {} midpoint: {}'.format(self.alpha, self.beta, self.midpoint))

		self.segend = segments
		self.addLD(ldtyp, ldtagf, ldtagt, zlr, zli, zlc)

		return self

	def addArc(self, segments, radius, start, end, rotate, translate,
			   ldtyp=5, ldtagf=0, ldtagt=0, zlr=None, zli=None, zlc=None):
		''' Append an arc using a combination of a GA card (radius, start angle, end angle), a GM card to rotate
			and translate the arc from the origin into it's correct location, and a second GM card to restore the
			transformation matrix for cards that come after the arc.
		'''
		# Place the arc in the XZ plane with its center on the origin
		self.tag += 1
		self.wires += self.ga(self.tag, segments, radius, start, end, self.wireRadius)
		self.flushTransformBuffer()
		self.midseg = math.trunc(segments/2) + 1
		self.midpoint = None
		self.alpha = None
		self.beta = None
		self.segend = segments
		# Move the arc to where it's supposed to be (note the tag #)
		r = rotate
		t = translate
		self.transforms += self.gm(rotX=r.rx, rotY=r.ry, rotZ=r.rz, trX=t.x, trY=t.y, trZ=t.z, firstTag=self.tag)
		# Queue up the transforms to roll back the translation and rotation, using multiple gm cards to ensure
		# that it really works (see GM card documentation about order of operations). This will restore the normal
		# coordinate system if any elements are appended to the model after this arc, but the use of tag = n+1
		# means it could break the nec2 parser if it's included without a GW or GA that actually uses tag n+1. The
		# point of this buffering nonsense is to avoid triggering that parsing problem.
		self.transformBuffer += self.gm(trX=-t.x, trY=-t.y, trZ=-t.z, firstTag=self.tag+1)
		self.transformBuffer += self.gm(rotZ=-r.rz, firstTag=self.tag+1)
		self.transformBuffer += self.gm(rotY=-r.ry, firstTag=self.tag+1)
		self.transformBuffer += self.gm(rotX=-r.rx, firstTag=self.tag+1)

		self.addLD(ldtyp, ldtagf, ldtagt, zlr, zli, zlc)

		return self

	def addHelix(self, segments, pt1, properties, rotate=None, translate=None):
		''' Append a helix...
		Also does housekeeping such as incrementing the tag number,
		translating or rotate it, and return this object to facilitate chaining
		'''
		self.tag += 1
		hr = properties['length'] / math.pi / 2
		height = properties['height']
		pitch = properties['height']
		self.wires += self.gh(self.tag, segments, pitch, height, hr, hr, hr, hr, self.wireRadius)
		self.flushTransformBuffer()
		# Move the helix to where it's supposed to be (note the tag #)
		r = rotate
		t = translate
		self.transforms += self.gm(rotX=r.rx, rotY=r.ry, rotZ=r.rz, trX=t.x, trY=t.y, trZ=t.z, firstTag=self.tag)
		# Queue up the transforms to roll back the translation and rotation, using multiple gm cards to ensure
		# that it really works (see GM card documentation about order of operations). This will restore the normal
		# coordinate system if any elements are appended to the model after this arc, but the use of tag = n+1
		# means it could break the nec2 parser if it's included without a GW or GA that actually uses tag n+1. The
		# point of this buffering nonsense is to avoid triggering that parsing problem.
		self.transformBuffer += self.gm(trX=-t.x, trY=-t.y, trZ=-t.z, firstTag=self.tag+1)
		self.transformBuffer += self.gm(rotZ=-r.rz, firstTag=self.tag+1)
		self.transformBuffer += self.gm(rotY=-r.ry, firstTag=self.tag+1)
		self.transformBuffer += self.gm(rotX=-r.rx, firstTag=self.tag+1)
		self.midseg = math.trunc(segments/2) + 1
		self.midpoint = None
		self.alpha = None
		self.beta = None
		self.segend = segments
		return self

	def addFeed(self, i1=0, i2=None, i3=None, i4=0,
				 f1=1.0, f2=0.0, f3=0.0, f4=None, f5=None, f6=0.0, f7=0.0):
		''' i2, i3, f4 and f5 can be generated internally or externally
			overridden by the user
		'''
		# provide generic overrides
		oi2 = 0 if i2 is None else i2
		oi3 = 0 if i3 is None else i3
		of4 = 0. if f4 is None else f4
		of5 = 0. if f5 is None else f5
		if 0 == i1 or 5 == i1:
			tag = self.tag if i2 is None else i2
			if i3 is None:
				segment = self.segend if self.EX_segment == self.Pos.END else self.midseg
				segment = 1 if self.EX_segment == self.Pos.START else segment
				# print('DEBUG: addFeed feed is {} / {}'.format(segment, self.segend))
			else:
				segment = i3
			self.addExtra(
				self.ex(i1 = i1, i2 = tag, i3 = segment, i4 = i4,
						f1 = f1, f2 = f2, f3 = f3,
						f4 = of4, f5 = of5, f6 = f6, f7 = f7))
		if 1 == i1 or 2 == i1 or 3 == i1:
			self.addExtra(
				self.ex(i2 = oi2, i3 = oi3, i1 = i1, i4 = i4,
						f1 = f1, f2 = f2, f3 = f3,
						f4 = of4, f5 = of5, f6 = f6, f7 = f7))
		if 4 == i1:
			alpha = self.alpha if f4 is None else f4
			beta = self.beta if f5 is None else f5

			# user overrides by providing f1, f2, f3, f4 and f5
			x = f1; y = f2 ; z = f3
			if not self.alpha is None and (f4 is None or f5 is None):
				if self.Pos.START == self.EX_segment:
					x = self.pt1.x; y = self.pt1.y; z = self.pt1.z
					#print('addFeed start x,y,z', x,y,z)
				if self.Pos.MID == self.EX_segment:
					x = self.midpoint[0]; y = self.midpoint[1]; z = self.midpoint[2]
					#print('addFeed mid x,y,z', x,y,z)
				if self.Pos.END == self.EX_segment:
					x = self.pt2.x; y = self.pt2.y; z = self.pt2.z
					#print('addFeed end x,y,z', x,y,z)
			if alpha is None or beta is None:
				print('WARNING ignoring feed alpha: {} beta: {} feed point: {}'.format(
					f4, f5, (f1,f2,f3)))
			else:
				self.addExtra(
					self.ex(i1 = i1, i2 = oi2, i3 = oi3, i4 = i4,
							f1 = x, f2 = y, f3 = z, f4 = alpha, f5 = beta, f6 = f6, f7 = f7))
			self.alpha = None
			self.beta = None
			self.EX_segment = -1

	def feedAtMiddle(self, i1=0, i2=None, i3=None, i4=0, f1=1.0, f2=0.0, f3=0.0, f4=None, f5=None, f6=0.0, f7=0.0):
		''' Attach the EX card feedpoint to the middle segment of the element that was most recently created
		'''
		self.EX_segment = self.Pos.MID
		self.addFeed(i1, i2, i3, i4, f1, f2, f3, f4, f5, f6, f7)

	def feedAtStart(self, i1=0, i2=None, i3=None, i4=0, f1=1.0, f2=0.0, f3=0.0, f4=None, f5=None, f6=0.0, f7=0.0):
		''' Attach the EX card feedpoint to the start of the element that was most recently created
		'''
		self.EX_segment = self.Pos.START
		self.addFeed(i1, i2, i3, i4, f1, f2, f3, f4, f5, f6, f7)

	def feedAtEnd(self, i1=0, i2=None, i3=None, i4=0, f1=1.0, f2=0.0, f3=0.0, f4=None, f5=None, f6=0.0, f7=0.0):
		''' Attach the EX card feedpoint to the end of the element that was most recently created
		'''
		self.EX_segment = self.Pos.END
		self.addFeed(i1, i2, i3, i4, f1, f2, f3, f4, f5, f6, f7)

	def addExtra(self, extra):
		if 0 < len(extra):
			self._extras.append(extra)

	def getText(self, start, stepSize, stepCount):
		footer = self.ge()
		for e in self._extras:
			footer += e

		footer += self.fr(start, stepSize, stepCount)
		footer += self.rp()
		footer += self.en()
		return self.geoelems + self.wires + self.transforms + footer

# =======================================================================================================
# File I/O
# =======================================================================================================

def writeCardsToFile(fileName, comments, cardStack):
	''' Write a NEC2 formatted card stack to the output file
	'''
	nec2File = open(fileName,'w')
	nec2File.write(comments.strip() + "\n")
	nec2File.write(cardStack.strip() + "\n")
	nec2File.close()

def copyCardFileToConsole(fileName):
	''' Dump the card stack back to the console for a quick sanity check
	'''
	nec2File = open(fileName,'r')
	print(nec2File.read())
	nec2File.close()
