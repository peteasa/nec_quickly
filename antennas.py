#!/usr/bin/env python3

xnec2c = True
freecad = True
try:
    from nec2utils import *
except:
    xnec2c = False

try:
    import FreeCAD
    import FreeCADGui
    import Part
except:
    freecad = False

import numpy as np

c_0 = 299792457.98003 # m/s
cond_cu = 5.8001e7 # Siemens/m
cond_al = 3.7665e7 # Siemens/m

# see L. B. Cebik (W4RNL) - Basic Antenna Modelling - A Hands On Tutorial
cond_water = 0.001 # Siemens/m water
epsilon_water = 80
cond_rocky = 0.002 # Siemens/m rocky
epsilon_rocky = 14
cond_gnd = 0.005 # Siemens/m average soil
epsilon_gnd = 13
cond_marsh = 0.0075 # Siemens/m marshy densely wooded
epsilon_marsh = 12
cond_saltw = 5.0 # Siemens/m salt water
epsilon_saltw = 81

NOPOINT = -999

class Material(object):
    def __init__(self, name='Copper', symbol='cu', cond=cond_cu):
        self._name = name
        self._symbol = symbol
        self._cond = cond

    @property
    def name(self):
        '''required for comment strings
        '''
        return self._name

    @property
    def symbol(self):
        '''used in file names
        '''
        return self._symbol

    @property
    def conductivity(self):
        '''conductivity of the material in Siemens/m
        '''
        return self._cond

class GeoElement(object):
    class Oper(Enum):
        SINGLE = 1
        MULTI  = 2
        APPEND = 3

    def __init__(self, material = None, materials = None,
                 n_points = 0, n_lines = 0,
                 n_patches = 0, n_linesperpatch = 0,
                 transformfn = None, transformdict = None):
        self._material = material
        if self._material is None and not materials is None:
            # specify either material or a list of materials
            self._materials = materials
        else:
            self._materials = []

        # Note zero is an invalid line number for a surface.
        # orientation of line is reversed if index is negative
        # line indexes are 1 based rather than zero based to allow negation
        self._surface = np.zeros((n_linesperpatch, n_patches), dtype = int)
        self._patchdict = {}
        self._transformfn = transformfn
        self._transformdict = {} if transformdict is None else transformdict
        self._points = (NOPOINT-1) * np.ones((3, n_points), dtype = float)
        self._lines = (NOPOINT-1) * np.ones((2, n_lines), dtype = int)
        self._distances = (NOPOINT-1) * np.ones((n_lines), dtype = float)

    @property
    def material(self):
        return self._material

    @property
    def materials(self):
        return self._materials

    @property
    def points(self):
        '''required point coordinates (m, m, m) for the shape
        '''
        return self._points

    @property
    def lines(self):
        '''required point pairs (from; too): these define the lines in the shape
        '''
        # TODO how to handle curves?
        return self._lines

    @property
    def distances(self):
        '''required distance in m: between the two ends of each line
        '''
        return self._distances

    @property
    def surface(self):
        return self._surface

    @property
    def patchdict(self):
        return self._patchdict

    def patchinfo(self, patch):
        if patch in self.patchdict.keys():
            patchinfo = self.patchdict[patch]
        else:
            patchinfo = self.Oper.APPEND
        return patchinfo

    @property
    def transformfn(self):
        return self._transformfn

    @transformfn.setter
    def transformfn(self, value):
        self._transformfn = value

    @property
    def transformdict(self):
        return self._transformdict

class Shape(object):
    def __init__(self, material = None, materials = None, n_points = 5, n_lines = 5, n_intercon = 0):
        self._geo = GeoElement(material = material, materials = materials, n_points = n_points, n_lines = n_lines)
        self._centre = (NOPOINT-1) * np.ones((3), dtype = float)
        self._feed = (NOPOINT-1) * np.ones((3), dtype = float)
        self._feedline = (NOPOINT-1)
        self._surfaces = []
        self._intercon_points = (NOPOINT-1) * np.ones((n_intercon), dtype = int)

    @property
    def material(self):
        return self._geo.material

    @property
    def materials(self):
        return self._geo.materials

    @property
    def centre(self):
        '''optional centre position: not required for shape geometry
        could be inferred from other points
        '''
        return self._centre

    @property
    def feed(self):
        '''optional feed coordinates (m, m, m):
        if specified then feedline is required
        '''
        return self._feed

    @property
    def feedline(self):
        '''optional feed line index:
        if specified then feed is required
        '''
        return self._feedline

    @feedline.setter
    def feedline(self, value):
        self._feedline = int(value)

    @property
    def points(self):
        '''required point coordinates (m, m, m) for the shape
        '''
        return self._geo.points

    @property
    def lines(self):
        '''required point pairs (from; too): these define the lines in the shape
        '''
        return self._geo.lines

    @property
    def distances(self):
        '''required distance in m: between the two ends of each line
        '''
        return self._geo.distances

    @property
    def surfaces(self):
        return self._surfaces

    @property
    def intercon_points(self):
        '''optional interconnection points
        if specified contains the indices of the connection points
        '''
        return self._intercon_points

class Rotator(object):
    ''' rotate about one axis
    '''
    def __init__(self, angle = 0, x_radius = 0., y_radius = 0., z_radius = 0.):
        self._angle = angle
        if 0 < y_radius:
            # rotate about x in the yz plane
            self._radius = y_radius
            s1_size = y_radius ; s2_size = y_radius
            self._c1 = 1; self._c2 = 2; self._ct = 0
            self._angles = (angle, .0, .0)
        if 0 < z_radius:
            # rotate about y in the zx plane
            self._radius = z_radius
            s1_size = z_radius ; s2_size = z_radius
            self._c1 = 2; self._c2 = 0; self._ct = 1
            self._angles = (.0, angle, .0)
        if 0 < x_radius:
            # rotate about z in the xy plane
            self._radius = x_radius
            s1_size = x_radius ; s2_size = x_radius
            self._c1 = 0; self._c2 = 1; self._ct = 2
            self._angles = (.0, .0, angle)

    @property
    def radius(self):
        return self._radius

    @property
    def x_radius(self):
        ''' if none rotate about z in the xy plane
        '''
        return self._radius if 2 == self.ct else 0.

    @property
    def y_radius(self):
        ''' if none rotate about x in the yz plane
        '''
        return self._radius if 0 == self.ct else 0.

    @property
    def z_radius(self):
        ''' if none rotate about y in the zx plane
        '''
        return self._radius if 1 == self.ct else 0.

    @property
    def c1(self):
        ''' first of 3 possible indexes: 3rd index is axis of rotation
        '''
        return self._c1

    @property
    def c2(self):
        ''' second of 3 possible indexes: 3rd index is axis of rotation
        '''
        return self._c2

    @property
    def ct(self):
        ''' index for the axis of rotation
        rotate yz plane about x: ct == 0; c1 == y index 1; c2 == z index 2
        rotate zx plane about y: ct == 1; c1 == z index 2; c2 == x index 0
        rotate xy plane about z: ct == 2; c1 == x index 0; c2 == y index 1
        '''
        return self._ct

    @property
    def angle(self):
        return self._angle

    @property
    def angles(self):
        return self._angles

def setPoint(point):
    '''setter for nec2utils Point()
    '''
    return Point(point[0], point[1], point[2])

def distance(a, b):
    x = a[0] - b[0]
    y = a[1] - b[1]
    z = a[2] - b[2]
    return np.sqrt(x*x + y*y + z*z)

def line_length(points, line):
    return distance(points[:, line[0]], points[:, line[1]])

def freecadVector(point):
    return FreeCAD.Vector(point[0], point[1], point[2])

def freecadEdge(vectors, start, end):
    line = Part.LineSegment(vectors[start], vectors[end])

    return Part.Edge(line)

def createFreeCAD(name, wireRadius, shapes, freqMHz, angle = NOPOINT-1):
    print('Running macro to create FreeCAD shape')

    doc = FreeCAD.activeDocument()
    if doc is None:
        doc = FreeCAD.newDocument()

    freq = '{:04.0f}'.format(freqMHz)
    anglestr = ''
    if NOPOINT < angle:
        anglestr ='_{:03.0f}'.format(angle)
    objLabel = '{}_{}{}'.format(name, freq, anglestr)

    freecadObj = doc.getObjectsByLabel(objLabel)
    currentDir = os.path.dirname(doc.FileName)
    print(f"Working dir: {currentDir}")

    vectors = []
    edges = []

    n_shapes = len(shapes)
    for o in range(n_shapes):
        shapestartv = len(vectors)
        shapestarte = len(edges)
        for p in range(shapes[o].points.shape[1]):
            vectors.append(freecadVector(shapes[o].points[:,p]))

        interconnectpoints = []
        interconnectpositions = []
        for p in shapes[o].intercon_points:
            interconnectpoints.append(shapestartv + p)

        for l in range(shapes[o].lines.shape[1]):
            edges.append(freecadEdge(vectors, shapestartv + shapes[o].lines[0,l], shapestartv + shapes[o].lines[1,l]))

        if o:
            for idx, p in enumerate(interconnectpoints):
                # add interconnection between shapes
                edges.append(freecadEdge(vectors, interconnectpoints_previous[idx], p))

        if 0 < len(interconnectpoints):
            interconnectpoints_previous = interconnectpoints

    print(len(vectors), len(edges))
    W = Part.Wire(edges)
    O1 = doc.addObject("Part::Feature", objLabel)
    O1.Shape = W
    doc.recompute()

    fileName = 'dipole.nec'
    comments = 'CM\n'
    comments += 'CE'
    stepcount = 100
    stepsize = freqMHz * 0.2 / stepcount

    print('macro done!')

def n_segments(segmentsize, distance):
    n_seg = 2 * int(np.floor_divide(distance, (2 * segmentsize))) + 1
    return n_seg

def constructSinglePatch(model, geo, patch):
    patchinfo = geo.patchinfo('{}info'.format(patch))
    if 'cpcentre' in patchinfo.keys():
        cpcentre = patchinfo['cpcentre']
    else:
        cpcentre = centrePatch(geo, patch)
    if 'cparea' in patchinfo.keys():
        cparea = patchinfo['cparea']
    else:
        base = line_length(geo.points, geo.lines[:, abs(geo.surface[0, patch]) - 1])
        height = line_length(geo.points, geo.lines[:, abs(geo.surface[1, patch]) - 1])
        cparea = base * height

    txt = model.sp(0, cpcentre[0], cpcentre[1], cpcentre[2], patchinfo['norm'], patchinfo['azim'], cparea)

    return txt

def handleSurfaces(model, n_surf, shape, wavelength):
    p1 = (NOPOINT-1) * np.ones((3), dtype = float)
    p2 = (NOPOINT-1) * np.ones((3), dtype = float)
    for g in range(len(shape.surfaces)):
        geo = shape.surfaces[g]
        for p in range(geo.surface.shape[1]):
            patchinfo = geo.patchinfo(p)
            if geo.Oper.APPEND == patchinfo:
                # add line 2
                linetoprocess = 2
            else:
                # add line 0 then continue for line 2
                linetoprocess = 0

            for l in range(0, geo.surface.shape[0], 2):
                if not linetoprocess == l:
                    continue

                idx = abs(geo.surface[l,p]) - 1
                line = geo.lines[:, idx]

                setcoord(p1, geo.points[:, line[0]])
                setcoord(p2, geo.points[:, line[1]])
                seglen = distance(p1, p2) / wavelength
                if 0.1 < seglen or seglen < 0.001:
                    print('WARNING {}:{} patch {} length: {:0.4f}'.format(n_surf, g, p, seglen))

                if geo.Oper.MULTI == patchinfo:
                    if 0 < geo.surface[0,p]:
                        model.geoelems += model.sp(3, p1[0], p1[1], p1[2], p2[0], p2[1], p2[2])
                    else:
                        model.geoelems += model.sp(3, p2[0], p2[1], p2[2], p1[0], p1[1], p1[2])

                    patchinfo = geo.Oper.APPEND
                    linetoprocess = 2
                    continue

                if geo.Oper.SINGLE == patchinfo:
                    model.geoelems += constructSinglePatch(model, geo, p)
                    break

                if 0 < geo.surface[l,p-1]:
                    model.geoelems += model.sc(3, p1[0], p1[1], p1[2], p2[0], p2[1], p2[2])
                else:
                    model.geoelems += model.sc(3, p2[0], p2[1], p2[2], p1[0], p1[1], p1[2])

        if not geo.transformfn is None:
            # allow a transformation after each surface
            model.geoelems += geo.transformfn(model, geo)

def createNEC2Cards(name, comments, wavelength, wireRadius, segmentsize, shapes, plotFreqMHz, plotStart = 1., plotRange = 0.2, plotStepCount = 100, angle = NOPOINT-1, i1 = 0, f1 = 1.0, f6 = 0.0, iperf = NOPOINT-1, gnde = NOPOINT-1, gndc = NOPOINT-1):
    # ground plane is always the xy plane with z == 0 so being able to flip to horizontal is a good idea!
    print('creating NEC2 Cards for {}'.format(name))
    segperwavelength = wavelength / segmentsize
    if 11 < segperwavelength or segperwavelength < 9:
        print('INFO: segments per wavelength recommended is between 9 and 11: using: {}'.format(int(segperwavelength)))

    seglen_min = -NOPOINT ; slomin = NOPOINT ; sllmin = NOPOINT; llmin = NOPOINT; n_segmin = NOPOINT
    seglen_max = NOPOINT ; slomax = NOPOINT ; sllmax = NOPOINT; llmax = NOPOINT; n_segmax = NOPOINT

    if not shapes[0].material is None:
        m = Model(wireRadius, zlr = shapes[0].material.conductivity)
    else:
        # either no material specified or each line has a separate
        # material specification
        m = Model(wireRadius)

    n_shapes = len(shapes)
    for o in range(n_shapes):
        if 0 < len(shapes[o].surfaces):
            handleSurfaces(m, o, shapes[o], wavelength)

        points = []
        for p in range(shapes[o].points.shape[1]):
            points.append(setPoint(shapes[o].points[:, p]))

        interconnectpoints = []
        interconnectpositions = []
        for p in shapes[o].intercon_points:
            interconnectpoints.append(points[p])
            interconnectpositions.append(shapes[o].points[:, p])

        if NOPOINT < shapes[o].feedline:
            feedposition = shapes[o].feed

        for l in range(shapes[o].lines.shape[1]):
            llen = line_length(shapes[o].points, shapes[o].lines[:, l])
            n_seg = n_segments(segmentsize, llen)
            seglen = llen / (n_seg * wavelength)
            if 0.1 < seglen or seglen < 0.001:
                print('WARNING {}:{} n_seg: {} segment length: {:0.4f}'.format(o, l, n_seg, seglen))
            if seglen < seglen_min:
                slomin = o; sllmin = l; llmin = llen; seglen_min = seglen; n_segmin = n_seg
            if seglen_max < seglen:
                slomax = o; sllmax = l; llmax = llen; seglen_max = seglen; n_segmax = n_seg

            zlr = None
            if l < len(shapes[o].materials):
                zlr = shapes[o].materials[l].conductivity

            if l in [shapes[o].feedline]:
                fstart = distance(shapes[o].feed, shapes[o].points[:,shapes[o].lines[0, l]])
                fend = distance(shapes[o].feed, shapes[o].points[:,shapes[o].lines[1, l]])
                if 0.2 < fend / llen and fend / llen < 0.8:
                    print('INFO: feed in middle line: {}'.format(l))
                    m.addWire(n_seg,
                              points[shapes[o].lines[0, l]],
                              points[shapes[o].lines[1, l]],
                              zlr = zlr).feedAtMiddle(i1=i1, f1=f1, f6=f6)
                elif fstart / llen < 0.5:
                    print('INFO: feed at start line: {}'.format(l))
                    m.addWire(n_seg,
                              points[shapes[o].lines[0, l]],
                              points[shapes[o].lines[1, l]],
                              zlr = zlr).feedAtStart(i1=i1, f1=f1, f6=f6)
                else:
                    print('INFO: feed at end line: {}'.format(l))
                    m.addWire(n_seg,
                              points[shapes[o].lines[0, l]],
                              points[shapes[o].lines[1, l]],
                              zlr = zlr).feedAtEnd(i1=i1, f1=f1, f6=f6)
            else:
                m.addWire(n_seg,
                          points[shapes[o].lines[0, l]],
                          points[shapes[o].lines[1, l]],
                          zlr = zlr)

        if o:
            for idx, p in enumerate(interconnectpoints):
                # add interconnection between shapes
                llen = distance(interconnectpositions_previous[idx], interconnectpositions[idx])
                n_seg = n_segments(segmentsize, llen)
                m.addWire(n_seg,
                          interconnectpoints_previous[idx],
                          p,
                          zlr = zlr)

        if 0 < len(interconnectpoints):
            interconnectpoints_previous = interconnectpoints
            interconnectpositions_previous = interconnectpositions

    if 0 <= gnde:
        epsilon = epsilon_gnd
        cond = cond_gnd
        gtype = 2
        if 0 < gnde:
            epsilon = gnde
        if 0 < gndc:
            cond = gndc
        if NOPOINT < iperf:
            gtype = iperf
        if 0 < epsilon:
            m.addExtra(m.gn(iperf = gtype, espr = epsilon, sig = cond))

    print('INFO {}:{} line length: {:0.5f} seg min: {:0.4e} n_seg: {} seg per wavelength: {:0.2f}'.format(slomin,sllmin,llmin,seglen_min,n_segmin, 1 / seglen_min))
    print('INFO {}:{} line length: {:0.5f} seg max: {:0.4e} n_seg: {} seg per wavelength: {:0.2f}'.format(slomax,sllmax,llmax,seglen_max,n_segmax, 1 / seglen_max))

    freq = '{:04.0f}'.format(plotFreqMHz)
    anglestr = ''
    if NOPOINT < angle:
        anglestr ='_{:03.0f}'.format(angle)
    fileName = '{}_{}{}.nec'.format(name, freq, anglestr)

    commentstr = ''
    for c in comments:
        commentstr += 'CM ' + c + '\n'

    commentstr += 'CE'
    stepcount = plotStepCount if 0.00001 < plotRange else 1
    stepsize = plotFreqMHz * plotRange / stepcount
    cardStack = m.getText(start = plotFreqMHz * plotStart, stepSize = stepsize, stepCount = stepcount)
    writeCardsToFile(fileName, commentstr, cardStack)

def guage(guage):
    '''AWG guage to meters
    '''
    return 0.127 * 92**((36 - guage)/39) * 1e-3

def setcoord(points, point):
    '''used to set sequences of values (float or int)
    '''
    for p in range(points.shape[0]):
        points[p] = point[p]

# could split the above into a separate library file for now keep a single file
# to make testing with FreeCAD easier

class Cantenna(object):
    def __init__(self, freqMHz = 0, diameter = 0., length = 0., wire_guage = 8):
        self.verbose = False
        self._freqMHz = freqMHz
        self._length = length
        self._wire_guage = wire_guage

        self._iter = 0
        self._iter_1 = -1
        self._iter_2 = -1
        self._diameter = np.zeros((5), dtype = float)
        self._diameter[self._iter] = diameter
        self._inside_length = np.zeros((5), dtype = float)

    def __str__(self):
        txt = '===============\nCantenna spec\n===============\n'
        txt += 'wavelength waveguide: {:0.4f} free space: {:0.4f}\n'.format(self.wavelength_guide, self.wavelength)
        txt += 'feed length: {:0.4f} pin distance from reflector: {:0.4f}\n'.format(self.feed_length, self.feed_pin_to_reflector)
        txt += 'can inside length: {:0.4f} (distance pin feed to rim: {:0.4f})\n'.format(self.inside_length, self.edge_to_pin_feed)
        txt += 'can diameter: {:0.4f} can radius: {:0.4f}\n'.format(self.diameter, self.diameter/2.)
        txt += 'frequency min: {:0.3f} target: {:0.3f} max: {:0.3f}\n'.format(self.freq_minMHz, self.freqMHz, self.freq_maxMHz)
        txt += 'frequency cutoff TE11: {:0.3f} secondary TM01: {:0.3f}\n'.format(self.freq_cutoffTE11MHz, self.freq_cutoffTM01MHz)
        txt += '==============='
        return txt

    @property
    def freqMHz(self):
        return self._freqMHz

    @property
    def radius(self):
        if not hasattr(self, '_radius'):
            self._radius = self.diameter / 2.
        return self._radius

    @property
    def diameter(self):
        return self._diameter[self._iter]

    @property
    def inside_length(self):
        self._inside_length[self._iter] = 3. * self.wavelength_guide / 4.
        return self._inside_length[self._iter]

    @inside_length.setter
    def inside_length(self, value):
        print('target inside length: {:0.4f}'.format(value))
        self._iter_2 = self._iter_1
        self._iter_1 = self._iter
        self._inside_length[self._iter] = self.inside_length
        self._iter += 1
        self._iter = self._iter % self._inside_length.shape[0]
        self._clear_derived()
        pctchange = self._bound_pct(self.pctchange(value))
        self._diameter[self._iter] = self._diameter[self._iter_1] * (1 + pctchange)
        self._inside_length[self._iter] = self.inside_length

    def _bound_pct(self, pctchange):
        bound = 0.50
        if bound < abs(pctchange):
            _pctchange = pctchange
            if 0 < pctchange:
                pctchange = bound
            else:
                pctchange = -bound
            print('WARNING diverging? pctchange {:0.4f} reduced: {:0.4f}'.format(_pctchange, pctchange))
        elif abs(pctchange) < 0.0000000001:
            pctchange = 0.0000000001
            print('WARNING diverging? pctchange {:0.4f} increased: {:0.4f}'.format(_pctchange, pctchange))

        return pctchange

    def pctchange(self, value):
        if -1 < self._iter_2:
            grad = (self._diameter[self._iter_1] - self._diameter[self._iter_2]) / (self._inside_length[self._iter_1] - self._inside_length[self._iter_2])
        else:
            grad = -0.1 * self._diameter[self._iter_1] / self._inside_length[self._iter_1]

        #print('grad {}'.format(grad))
        diamest = self._diameter[self._iter_1] + (value - self._inside_length[self._iter_1]) * grad
        #print('diamest: {}'.format(diamest))
        pctchange = (diamest - self._diameter[self._iter_1]) / self._diameter[self._iter_1]
        return pctchange

    @property
    def edge_to_pin_feed(self):
        if not hasattr(self, '_edge_to_pin_feed'):
            if self.verbose: print('new _edge_to_pin_feed')
            self._edge_to_pin_feed = self.wavelength_guide / 2.
        return self._edge_to_pin_feed

    @property
    def edge_to_wedge_feed(self):
        if not hasattr(self, '_edge_to_wedge_feed'):
            if self.verbose: print('new _edge_to_wedge_feed')
            self._edge_to_wedge_feed = (3./4. - 0.14) * self.wavelength_guide
        return self._edge_to_wedge_feed

    @property
    def feed_pin_to_reflector(self):
        if not hasattr(self, '_feed_pin_to_reflector'):
            if self.verbose: print('new _feed_pin_to_reflector')
            self._feed_pin_to_reflector = self.wavelength_guide / 4.
        return self._feed_pin_to_reflector

    @property
    def feed_wedge_to_reflector(self):
        if not hasattr(self, '_feed_wedge_to_reflector'):
            if self.verbose: print('new _feed_wedge_to_reflector')
            self._feed_wedge_to_reflector = 0.14 * self.wavelength_guide
        return self._feed_wedge_to_reflector

    @property
    def feed_radius(self):
        if not hasattr(self, '_feed_radius'):
            if self.verbose: print('new _feed_radius')
            self._feed_radius = guage(self._wire_guage) / 2. # 2.74 / 2
        return self._feed_radius

    @property
    def feed_length(self):
        if not hasattr(self, '_feed_length'):
            if self.verbose: print('new _feed_length')
            self._feed_length = self.wavelength / 4.
        return self._feed_length

    @property
    def wedge_width(self):
        if not hasattr(self, '_wedge_width'):
            if self.verbose: print('new _wedge_width')
            self._wedge_width = 0.46 * self.wavelength
        return self._wedge_width

    @property
    def freq_minMHz(self):
        if not hasattr(self, '_freq_minMHz'):
            if self.verbose: print('new _freq_minMHz')
            self._freq_minMHz = c_0 * 1e-6 / self.upper_usable_length
        return self._freq_minMHz

    @property
    def freq_maxMHz(self):
        if not hasattr(self, '_freq_maxMHz'):
            if self.verbose: print('new _freq_maxMHz')
            self._freq_maxMHz = c_0 * 1e-6 / self.lower_usable_length
        return self._freq_maxMHz

    @property
    def freq_cutoffTE11MHz(self):
        if not hasattr(self, '_freq_cutoffTE11MHz'):
            if self.verbose: print('new _freq_cutoffTE11MHz')
            self._freq_cutoffTE11MHz = 1.8412 * c_0 * 1e-6 / (2. * np.pi * self.radius)
        return self._freq_cutoffTE11MHz

    @property
    def freq_cutoffTM01MHz(self):
        if not hasattr(self, '_freq_cutoffTM01MHz'):
            if self.verbose: print('new _freq_cutoffTM01MHz')
            self._freq_cutoffTM01MHz = 1.147 * c_0 * 1e-6 / (2. * np.pi * self.radius)
        return self._freq_cutoffTM01MHz

    @property
    def wavelength(self):
        if not hasattr(self, '_wavelength'):
            if self.verbose: print('new _wavelength')
            self._wavelength = c_0 * 1e-6 / self.freqMHz
        return self._wavelength

    @property
    def wavelength_guide(self):
        # lg
        if not hasattr(self, '_wavelength_guide'):
            if self.verbose: print('new _wavelength_guide')
            lc2 = self.dominant_cutoff_length**2
            wl2 = self.wavelength**2
            if lc2 < wl2:
                wl2 = lc2 - .00000001
                print('WARNING dominant_cutoff_length < wavelength')
            self._wavelength_guide = np.sqrt(lc2 * wl2 / (lc2 - wl2))
        return self._wavelength_guide

    @property
    def lower_usable_length(self):
        # ls
        if not hasattr(self, '_lower_usable_length'):
            if self.verbose: print('new _lower_usable_length')
            self._lower_usable_length = 2.8 * self.diameter / 2.
        return self._lower_usable_length

    @property
    def upper_usable_length(self):
        # lu
        if not hasattr(self, '_upper_usable_length'):
            if self.verbose: print('new _upper_usable_length')
            self._upper_usable_length = 3.2 * self.diameter / 2.
        return self._upper_usable_length

    @property
    def dominant_cutoff_length(self):
        # lc
        if not hasattr(self, '_dominant_cutoff_length'):
            if self.verbose: print('new _dominant_cutoff_length')
            self._dominant_cutoff_length = 3.41 * self.diameter / 2.
        return self._dominant_cutoff_length

    def _clear_derived(self):
        for n in ['_radius', '_lower_usable_length', '_upper_usable_length', '_dominant_cutoff_length',
                  '_wavelength', '_wavelength_guide', '_freq_cutoffTE11MHz', '_freq_cutoffTM01MHz',
                  '_freq_maxMHz', '_freq_minMHz',
                  '_edge_to_pin_feed', '_edge_to_wedge_feed', '_feed_pin_to_reflector', '_feed_wedge_to_reflector',
                  '_feed_length', '_feed_radius', '_wedge_width']:
            # clear the out of date values
            if hasattr(self, n): delattr(self, n)

def midPoint(p0, p1):
    return ((p0[0] + p1[0]) / 2., (p0[1] + p1[1]) / 2., (p0[2] + p1[2] / 2.))

def centreSquare(points, l1, l3):
    av = []
    for i in range(3):
        val = 0
        for v in l1:
            val += points[i, v]

        for v in l3:
            val += points[i, v]

        av.append(val / 4)

    return (av[0], av[1], av[2])

def centreNew(ct, source, val):
    if 0 == ct:
        # yz plane
        point = (val, source[1], source[2])
    elif 1 == ct:
        # zx plane
        point = (source[0], val, source[2])
    elif 2 == ct:
        # xy plane
        point = (source[0], source[1], val)

    return point

def pointInc(c1, c2, ct, source, s1val, s2val):
    if 0 == ct:
        # yz plane
        point = (source[ct], source[c1] + s1val, source[c2] + s2val)
    elif 1 == ct:
        # zx plane
        point = (source[c2] + s2val, source[ct], source[c1] + s1val)
    elif 2 == ct:
        # xy plane
        point = (source[c1] + s1val, source[c2] + s2val, source[ct])

    return point

def pointNew(c1, c2, ct, source, s1val, s2val):
    if 0 == ct:
        # yz plane
        point = (source[ct], s1val, s2val)
    elif 1 == ct:
        # zx plane
        point = (s2val, source[ct], s1val)
    elif 2 == ct:
        # xy plane
        point = (s1val, s2val, source[ct])

    return point

def centrePatch(surface, patch):
    return centreSquare(
        surface.points,
        surface.lines[:, abs(surface.surface[0, patch]) - 1], # line 1
        surface.lines[:, abs(surface.surface[2, patch]) - 1]) # line 3

def isOnLine(p0, p1, p):
    '''is point p on the line p0 - p1
    '''
    dist0 = distance(p0, p1)
    dist1 = distance(p1, p)
    dist2 = distance(p0, p)
    distsum = dist1 + dist2
    distdiff = dist0 - distsum

    return abs(distdiff) < 0.0000001

def addFeed(shape, feed, feedline, line):
    '''if feed is specified then:
    for straight line find matching feedline if present
    if feedline is specified then:
    override feed with mid point
    '''
    if 3 == len(feed) and isOnLine(
            shape.points[:, shape.lines[0, line]],
            shape.points[:, shape.lines[1, line]], feed):
        setcoord(shape.feed, feed)
        shape.feedline = line
    if 0 == len(feed) and line in [feedline]:
        setcoord(shape.feed, midPoint(
            shape.points[:, shape.lines[0, line]],
            shape.points[:, shape.lines[1, line]]))
        shape.feedline = line

def createTriDipole(centre, length, feedlinelength, angle, material = None, materials = None):
    ''' small centre wire with two larger dipole wires attached
    '''
    n_points = 3 ; n_lines = 2
    if 0 < feedlinelength:
        n_points += 1+1 ; n_lines += 1

    # centre has no point associated with it so can't be part of a wire
    # leave default n_intercon = 0: disable interconnect from the middle of a wire
    dipole = Shape(material = material, n_points = n_points, n_lines = n_lines)
    if material is None and len(materials) == n_lines:
        for mat in materials:
            dipole.materials.append(mat)

    setcoord(dipole.centre, centre)
    p = 0 ; l = 0
    if 0 < feedlinelength:
        setcoord(dipole.points[:, p],
                 (dipole.centre[0] - feedlinelength / 2,
                  dipole.centre[1],
                  dipole.centre[2])) ; p += 1
        setcoord(dipole.points[:, p],
                 (dipole.centre[0] + feedlinelength / 2,
                  dipole.centre[1],
                  dipole.centre[2])) ; p += 1
        dipole.feedline = l
        setcoord(dipole.lines[:, l], (p-2, p-1)) ; l += 1
        setcoord(dipole.feed, dipole.centre)

    halflength = float(length) / 2
    halfangle = (180 - float(angle))/2
    x_min = dipole.centre[0] - halflength * np.cos(np.pi * halfangle / 180) - feedlinelength / 2
    x_max = dipole.centre[0] + halflength * np.cos(np.pi * halfangle / 180) + feedlinelength / 2
    y_max = dipole.centre[1] + halflength * np.sin(np.pi * halfangle / 180)
    setcoord(dipole.points[:, p], (x_min, y_max, dipole.centre[2])) ; p += 1
    setcoord(dipole.lines[:,l], (p-1, p-3)) ; l += 1

    setcoord(dipole.points[:, p], (x_max, y_max, dipole.centre[2])) ; p += 1
    setcoord(dipole.lines[:,l], (p-3, p-1)) ; l += 1

    return dipole

def createOblong(centre, feed = (), feedline = NOPOINT-1, x_size = 0, y_size = 0, z_size = 0, material = None, materials = None):
    ''' Create an oblong shape about a centre position.
        optionally add a feed position.
    '''
    n_points = 4 ; n_lines = 4
    oblong = Shape(material = material, n_points = n_points, n_lines = n_lines)
    if material is None and len(materials) == n_lines:
        for mat in materials:
            oblong.materials.append(mat)

    # 2d shape with one of the sizes marked as zero to allow multiple shapes to be
    # duplicated along that axis.  The size that is zero defines the two axes used
    # to create the 2d shape
    if 0 == x_size:
        # yz plane
        s1_size = y_size ; s2_size = z_size
        c1 = 1; c2 = 2; ct = 0
    if 0 == y_size:
        # zx plane
        s1_size = z_size ; s2_size = x_size
        c1 = 2; c2 = 0; ct = 1
    if 0 == z_size:
        # xy plane
        s1_size = x_size ; s2_size = y_size
        c1 = 0; c2 = 1; ct = 2

    # setcoord(oblong.centre, centre)
    s1halfwidth = s1_size / 2
    s2halfwidth = s2_size / 2

    # start with negative and work round anticlockwise (right hand rule)
    point = pointInc(c1, c2, ct, centre, -s1halfwidth, -s2halfwidth)

    s1m = 1 ; s2m = 1
    s1n = 0 ; s2n = 0
    for p in range(oblong.points.shape[1]):
        setcoord(oblong.points[:, p], point)
        if p%2:
            s1n = 0 ; s2n = s2m ; s2m = -s2m

        elif (p+1)%2:
            s1n = s1m; s1m = -s1m; s2n = 0

        point = pointInc(c1, c2, ct, point, s1n * s1_size, s2n * s2_size)

    for l in range(4):
        loidx = l ; hiidx = (l+1)%4
        if not oblong.points[:, loidx].min() < NOPOINT and not oblong.points[:, hiidx].min() < NOPOINT:
            setcoord(oblong.lines[:, loidx], (l, hiidx))
            oblong.distances[l] = line_length(oblong.points, oblong.lines[:,l])
            addFeed(oblong, feed, feedline, l)

    return oblong

def createGridCircle(centre, n_radii, n_rings, feed = (), feedline = NOPOINT-1, n_interconnect = 0, radius_inner = 0., x_radius = 0., y_radius = 0., z_radius = 0., material = None):
    n_inner_points = 1 if 0. == radius_inner else n_radii
    n_inner_lines = 0 if 0. == radius_inner else n_radii
    n_points = n_radii * n_rings + n_inner_points; n_lines = 2 * n_radii * n_rings + n_inner_lines
    grid = Shape(material, n_points = n_points, n_lines = n_lines, n_intercon = n_interconnect)

    # 2d shape with only one non-zero radius allow multiple shapes to be
    # duplicated along the remaining axis. 3 planes considered: xy yz, zx
    # The remaining axis allows the shape to be duplicated along that axis
    # to create a 3d object
    if 0 < y_radius:
        # yz plane
        radius_outer = y_radius - radius_inner
        s1_size = y_radius ; s2_size = y_radius
        c1 = 1; c2 = 2; ct = 0
    if 0 < z_radius:
        # zx plane
        radius_outer = z_radius - radius_inner
        s1_size = z_radius ; s2_size = z_radius
        c1 = 2; c2 = 0; ct = 1
    if 0 < x_radius:
        # xy plane
        radius_outer = x_radius - radius_inner
        s1_size = x_radius ; s2_size = x_radius
        c1 = 0; c2 = 1; ct = 2

    inner_points = (NOPOINT-1) * np.ones((n_inner_points), dtype = int)
    angle = 2 * np.pi / n_radii
    point = 0
    line = 0
    for a in range(n_radii):
        # inner ring
        c1inner = (centre[c1] + radius_inner) * np.cos(a * angle)
        c2inner = (centre[c2] + radius_inner) * np.sin(a * angle)
        inner_points[a] = point
        if a < grid.intercon_points.shape[0]:
            grid.intercon_points[a] = point

        if 0. == radius_inner and 0 == a:
            setcoord(grid.points[:, point], pointNew(c1, c2, ct, centre, c1inner, c2inner)) ; point += 1
            for a in range(n_radii - 1):
                inner_points[a+1] = 0
            break
        else:
            setcoord(grid.points[:, point], pointNew(c1, c2, ct, centre, c1inner, c2inner)) ; point += 1

        if a:
            setcoord(grid.lines[:, line], (point_previous_inner, point - 1)) ; line += 1
            grid.distances[line-1] = line_length(grid.points, grid.lines[:,line-1])
            addFeed(grid, feed, feedline, line-1)
        else:
            first_inner_point = point - 1

        point_previous_inner = point - 1

    if 0 < radius_inner:
        setcoord(grid.lines[:, line], (point_previous_inner, first_inner_point)) ; line += 1
        grid.distances[line-1] = line_length(grid.points, grid.lines[:,line-1])
        addFeed(grid, feed, feedline, line-1)

    for r in range(n_rings):
        for a in range(n_radii):
            c1outer = (centre[c1] + (r+1) * (radius_outer) / n_rings + radius_inner) * np.cos(a * angle)
            c2outer = (centre[c2] + (r+1) * (radius_outer) / n_rings + radius_inner) * np.sin(a * angle)
            inner_point = inner_points[a]
            inner_points[a] = point
            setcoord(grid.points[:, point], pointNew(c1, c2, ct, centre, c1outer, c2outer)) ; point += 1
            setcoord(grid.lines[:, line], (inner_point, point - 1)) ; line += 1
            grid.distances[line-1] = line_length(grid.points, grid.lines[:,line-1])
            addFeed(grid, feed, feedline, line-1)
            if a:
                setcoord(grid.lines[:, line], (point_previous, point - 1)) ; line += 1
                grid.distances[line-1] = line_length(grid.points, grid.lines[:,line-1])
                addFeed(grid, feed, feedline, line-1)
            else:
                first_point = point - 1

            point_previous = point - 1

        setcoord(grid.lines[:, line], (point_previous, first_point)) ; line += 1
        grid.distances[line-1] = line_length(grid.points, grid.lines[:,line-1])
        addFeed(grid, feed, feedline, line-1)

    return grid

def prepCylinder(centre, rot, start, p1, p2, l, n_points, n_lines, n_lperp, n_patches):
    c1 = rot.c1
    c2 = rot.c2
    ct = rot.ct

    pl1 = p1[0] ; ph1 = p1[1]
    pl2 = p2[0] ; ph2 = p2[1]

    loc = start
    cntr = centreNew(ct, centre, loc)
    point = 0
    line = 0

    cyl = GeoElement(n_points = n_points, n_lines = n_lines,
                     n_patches = n_patches, n_linesperpatch = n_lperp)

    # setup a multi patch surface
    if 1 < n_patches:
        cyl.patchdict[0] = cyl.Oper.MULTI
    else:
        cyl.patchdict[0] = cyl.Oper.SINGLE

    surface = cyl.surface
    for i in range(surface.shape[1] + 1):
        if i:
            setcoord(cyl.points[:, point], pointNew(c1, c2, ct, cntr, pl2, ph2)) ; point += 1
            setcoord(cyl.points[:, point], pointNew(c1, c2, ct, cntr, pl1, ph1)) ; point += 1
            if line < 2:
                setcoord(cyl.lines[:, line], (cyl.lines[1, line - 1], point - 2)) ; line += 1 # 1:1->2
            else:
                setcoord(cyl.lines[:, line], (cyl.lines[0, line - 2], point - 2)) ; line += 1 # 4:2->4
            setcoord(cyl.lines[:, line], (point - 2, point - 1)) ; line += 1 # 2:2->3; 5:4->5
            setcoord(cyl.lines[:, line], (point - 1, cyl.lines[0, line - 3])) ; line += 1 # 3:3->0
            if line < 5:
                # line indexes are 1 based rather than zero based to allow negation
                setcoord(surface[:, i - 1], (line - 3, line - 2, line - 1, line)) #lines: 1,2,3,4
            else:
                # line 2 is 2->3; square patch 1 requires 3->2->4->5->3 so line 2 is reversed (-ve)
                setcoord(surface[:, i - 1], (4 - line, line - 2, line - 1, line)) #lines: -3,4,5,6

            loc += l
        else:
            # rotate around the patch in a right handed way
            # normal to the patch towards the centre if l is negative
            # normal to the patch outwards from centre if l is positive
            setcoord(cyl.points[:, point], pointNew(c1, c2, ct, cntr, pl1, ph1)) ; point += 1
            setcoord(cyl.points[:, point], pointNew(c1, c2, ct, cntr, pl2, ph2)) ; point += 1
            setcoord(cyl.lines[:, line], (point - 2, point - 1)) ; line += 1 # 0:0->1

            loc += l

        cntr = centreNew(ct, centre, loc)

    return cyl

def prepDisc(centre, rot, start, p1, p2, n_patches, frac = 1.0):
    c1 = rot.c1
    c2 = rot.c2
    ct = rot.ct

    pl1 = p1[0] ; ph1 = p1[1]
    pl2 = p2[0] ; ph2 = p2[1]

    n_points = n_patches * 2 + 2
    n_lines = 3 * int((n_points - 2)/2) + 1
    n_lperp = 4

    loc = start
    cntr = centreNew(ct, centre, loc)
    point = 0
    line = 0

    disc = GeoElement(n_points = n_points, n_lines = n_lines,
                      n_patches = n_patches, n_linesperpatch = n_lperp)

    # setup single patch surface
    if 1 < n_patches:
        disc.patchdict[0] = disc.Oper.MULTI
    else:
        disc.patchdict[0] = disc.Oper.SINGLE

    surface = disc.surface

    pldiff = pl1 - pl2
    phdiff = ph2 - ph1
    for p in range(n_patches + 1):
        if p:
            setcoord(disc.points[:, point], pointNew(c1, c2, ct, cntr, pl3, ph3)) ; point += 1
            setcoord(disc.points[:, point], pointNew(c1, c2, ct, cntr, pl4, ph4)) ; point += 1
            if line < 2:
                setcoord(disc.lines[:, line], (disc.lines[1, line - 1], point - 2)) ; line += 1 # 1:1->2
            else:
                setcoord(disc.lines[:, line], (disc.lines[0, line - 2], point - 2)) ; line += 1 # 4:2->4

            setcoord(disc.lines[:, line], (point - 2, point - 1)) ; line += 1 # 2:2->3; 5:4->5
            setcoord(disc.lines[:, line], (point - 1, disc.lines[0, line - 3])) ; line += 1 # 3:3->0
            if line < 5:
                setcoord(surface[:, p - 1], (line - 3, line - 2, line - 1, line)) #lines: 1,2,3,4
            else:
                setcoord(surface[:, p - 1], (4 - line, line - 2, line - 1, line)) #lines: -3,4,5,6
        else:
            setcoord(disc.points[:, point], pointNew(c1, c2, ct, cntr, pl1, ph1)) ; point += 1
            setcoord(disc.points[:, point], pointNew(c1, c2, ct, cntr, pl2, ph2)) ; point += 1
            # line indexes are 1 based rather than zero based to allow negation
            setcoord(disc.lines[:, line], (point - 2, point - 1)) ; line += 1 # 0:0->1

        pl3 = pl2 - phdiff * frac
        ph3 = ph2 - pldiff * frac
        pl4 = pl1 - phdiff * frac
        ph4 = ph1 - pldiff * frac
        pl1 = pl4 ; ph1 = ph4 ; pl2 = pl3 ; ph2 = ph3

    return disc

def rotateTo90(model, surface):
    rot = surface.transformdict['rot']
    mrpt = int(90 / rot.angle) - 1
    txt = model.gm(newStructures=mrpt, rotX=rot.angles[0], rotY=rot.angles[1], rotZ=rot.angles[2])

    return txt

def reflection90To360(model, surface):
    rot = surface.transformdict['rot']
    if 0 == rot.ct:
        rx = 0 ; ry = 1 ; rz = 1
    if 1 == rot.ct:
        rx = 1 ; ry = 0 ; rz = 1
    if 2 == rot.ct:
        rx = 1 ; ry = 1 ; rz = 0

    txt = model.gx(reflectX=rx, reflectY=ry, reflectZ=rz)

    return txt

def completeCanTransform(model, surface):
    txt = rotateTo90(model, surface)

    return txt

def completeDiscTransform(model, disc_surface):
    print(disc_surface.transformdict)
    txt = reflection90To360(model, disc_surface)

    if 'finalspin' in disc_surface.transformdict.keys():
        rot = disc_surface.transformdict['rot']
        spin = disc_surface.transformdict['finalspin']
        txt += model.gm(newStructures=0,
                        rotX=spin*rot.angles[0], rotY=spin*rot.angles[1], rotZ=spin*rot.angles[2])

    return txt

def createCanPatch(centre, rot, can = None, length = 0., first_seg = -1, frac = 1., material = None, materials = None):
    # patch size calculated with half the angle
    a1 = rot.angle * np.pi / 180
    sinah = np.sin(a1/2)
    lh = rot.radius * sinah

    # distance from axis
    cosah = np.cos(a1/2)
    la = rot.radius * cosah

    # length of each square patch
    l = lh * 2 * frac

    if first_seg < 0: first_seg = l

    n_patches = int(length / l)
    n_lperp = 4
    n_points = n_patches * 2 + 2
    n_lines = 3 * int((n_points - 2)/2) + 1

    # xy plane example: point (radius,0,0)
    pl1 = rot.radius
    ph1 = 0
    # point (radius,0,0) rotated about the axis
    pl2 = rot.radius * np.cos(a1) # = radius - l * sinah # cos2a = 1 - 2sin^2a
    ph2 = rot.radius * np.sin(a1) # = l * cosah # sin2a = 2sinacosa

    start = l * n_patches
    cyl_surface = prepCylinder(centre, rot, start, (pl1, ph1), (pl2, ph2), -l,
                               n_points, n_lines, n_lperp, n_patches)

    if can is None:
        # the surface patch is appended to the surfaces of a Shape
        # if a feed wire is required then supply the Shape separately
        can = Shape(material = material, materials = materials)
        setcoord(can.centre, centre)

    n_cyl = len(can.surfaces)
    can.surfaces.append(cyl_surface)

    # now start to construct the first bit of the can base
    # can base is a disc and will have central patch with diagonal < radius
    # and min x < side length

    # The central patch will be created with a single NEC2 card
    lcpcentre = centrePatch(cyl_surface, n_patches - 1)
    print('centre patch', lcpcentre)
    print(pointNew(rot.c1, rot.c2, rot.ct, centre, lcpcentre[rot.c1], lcpcentre[rot.c2]))
    diagonal = distance(pointNew(rot.c1, rot.c2, rot.ct, centre, lcpcentre[rot.c1], lcpcentre[rot.c2]),
                        centre)
    cplength = diagonal / np.sqrt(2.)
    print('length', cplength, diagonal, 2 * cplength * cplength, diagonal * diagonal)

    # calculate the intersection of the patch with the axis to ensure no gaps
    # with the central patch and the surrounding can rim
    # angle: radius / diagonal; is constant
    # each new patch reduces diagonal by 2 * lh
    # compare the axis intersection with the size of the central patch
    # cplength < (diagonal - 2 * lh * n) * pl1 / diagonal
    n_patches = 0
    factor = 2 * lh * pl1 / diagonal
    for n in range(10):
        if cplength < (pl1 - n * factor * frac):
            n_patches = n + 1
        else:
            print('SUCCESS: centre cube covered with {}: {} > {}'.format(
                n_patches, cplength, (pl1 - n * factor)))
            break

    if 0 == rot.ct:
        norm = 0.  # elevation angle relative to the x-y plane of the normal vector
        azim = 0.  # azimuth angle from the x-axis of the normal vector
    if 1 == rot.ct:
        norm = 0.  # elevation angle relative to the x-y plane of the normal vector
        azim = 90. # azimuth angle from the x-axis of the normal vector
    if 2 == rot.ct:
        norm = 90. # elevation angle relative to the x-y plane of the normal vector
        azim = 0.  # azimuth angle from the x-axis of the normal vector

    start = .0

    disc_surface = prepDisc(centre, rot, start, (pl1, ph1), (pl2, ph2), n_patches, frac = frac)

    # override initial patch default to append to cylinder
    disc_surface.patchdict[0] = disc_surface.Oper.APPEND

    # in preparation for the central patch: rotate the cylinder and the disc to 90 degrees
    # this operation is a transformation details could be different for each
    # of FreeCAD and NEC2
    disc_surface.transformdict['rot'] = rot
    disc_surface.transformfn = completeCanTransform

    n_disc = len(can.surfaces)
    can.surfaces.append(disc_surface)

    # Now create the central patch
    start = .0
    n_patches = 1
    cpatch_surface = prepDisc(centre, rot, start, (cplength, 0), (cplength, cplength), n_patches)

    # override initial patch default to demonstrate Oper.SINGLE patch style
    cpatch_surface.patchdict[0] = disc_surface.Oper.SINGLE
    cpatch_surface.patchdict['0info'] = {'norm': norm, 'azim': azim}

    roth = Rotator(-rot.angle/2, rot.x_radius, rot.y_radius, rot.z_radius)

    cpatch_surface.transformdict['rot'] = roth

    # always place the centre of the patch on the axis
    n_rot = int(45. / rot.angle)
    cpatch_surface.transformdict['finalspin'] = rot.angle * n_rot + ((1+n_rot) % 2) * rot.angle/2.
    cpatch_surface.transformfn = completeDiscTransform
    n_cpatch = len(can.surfaces)
    can.surfaces.append(cpatch_surface)

    return can

def dipoleexperiment():
    al = Material('Aluminium', 'al', cond_al)
    targetMHz = 137.5 # 300 # 1420 # MHz

    # dipole calculator http://www.csgnetwork.com/antennaedcalc.html
    wavelength = 1e-6 * c_0 / targetMHz

    # velocity factor is determined by the relative permittivity of the coax insulation
    # for a dipole in free air the relative permittivity is 1.0 however this is not sufficient:
    # it is also determined by the inductance / capacitance per unit length of a transmission line
    # so in this case the inductance / capacitance per unit length of the wire comes into play!
    vf = 1.0 # ideal velocity factor! the actual dipole length could be shorter
    length_ideal = vf * wavelength / 2 # 10.973
    length = 0.52 * 2 # 1.3 # 1.426 # 0.475 # 1.426
    angle = 60 * 2

    height_above = 10.0 #1.0 # 0.5 #5. # height above the ground
    if 0 < height_above:
        gndepsilon = 0
    else:
        gndepsilon = NOPOINT

    comments = ['v-shape dipole with {} degree using {} wire for {} MHz'.format(angle, al.name, targetMHz)]

    # feed is at centre of small central wire
    segperwave = 100 # 97.258MHz
    detail = 'tripole_{}'.format(al.symbol)

    segmentsize = wavelength / segperwave
    print('segment size: {:0.4f}'.format(1/segperwave))

    # ideal: dipole fed from middle of feedline
    feedlinelength = 0.015 # segmentsize # 97.245 # 3*segmentsize # 92.428
    print('segment size: {:0.4f}'.format(1/segperwave))

    dipole = createTriDipole((0,0, height_above), length, feedlinelength, angle, materials = [al,al,al])
    comments.append('centre fed {:0.4f}m feed wire using {} segments per wavelength'.format(feedlinelength, segperwave))

    wireRadius = guage(9) / 2
    print('target frequency: {:0.1f} MHz vshape angle: {} degrees'.format(targetMHz, angle))
    print('ideal length: {:0.4f} calculator length: {:0.4f}m with {:0.4f}mm wire radius'.format(length_ideal, length, wireRadius*1e3))
    print(dipole.points) ; print(dipole.lines)

    print('distance between end points: {}'.format(feedlinelength + length * np.sin(np.pi * angle / 360)))
    print('distance from points rightangle to centre: {}'.format(length * np.cos(np.pi * angle / 360)/2))

    startMHz = 130; rangeMHz = 20
    if freecad:
        createFreeCAD('dipole_{}'.format(detail), wireRadius, [dipole], targetMHz, angle = angle)
    elif xnec2c:
        comments.append('Drafted using antennas.py and net2utils.py')
        comments.append('Author: Peter Saunderson')
        createNEC2Cards('dipole_{}'.format(detail), comments,
                        wavelength, wireRadius, segmentsize, [dipole],
                        targetMHz, plotStart = startMHz / targetMHz, plotRange = rangeMHz / targetMHz,
                        angle = angle,
                        gnde = gndepsilon)

def quadloopexperiment():
    comments = ['Reference: L.B. Cebik, W4RNL Antenna Modelling Notes']
    comments.append('Volume 2 Section 41 Multiple-Feedpoint Loop Modelling')
    cu = Material('Copper', 'cu', cond_cu)
    al = Material('Aluminium', 'al', cond_al)

    targetMHz = 144.4 # MHz
    wavelength = 1e-6 * c_0 / targetMHz
    length = 0.55565

    print('target frequency: {:0.1f} MHz'.format(targetMHz))
    print('wavelength: {:0.4f} quad side length: {:0.4f} m'.format(wavelength, length))

    n_squares = 1
    startpoint = 0.0
    # separation = endpoint / (n_squares - 1)
    squares = []
    for e in range(n_squares):
        centre = (0, startpoint, 0)
        feed = (-length/2, startpoint, 0)
        squares.append(createOblong(centre, feed = feed, x_size = length, z_size = length, material = cu))
        # startpoint += separation

    n_squares = len(squares)

    wireRadius = guage(18) / 2
    n_seg = 21
    segmentsize = length / n_seg
    if freecad:
        pass # TODO
    elif xnec2c:
        k_al = 1 / (13.948331085278 * 0.998627802325805 * 1.0012812488275 * 0.999999983524304 * 1.00000011044934) # 0.07169980519332197 @ 21seg
        k_cu = 1 / (13.9794619484346 * 0.998618610313404 * 1.00129169865054 * 1.00000228834924 * 1.00000241637224) # 0.07154005550662473 @ 21seg
        k_cu_23 = 0.07154005550662473 / (1.09576812373999 * 0.999983876989408 * 1.00001158140431 * 0.999998898770091) # 0.06528788242538795 @23seg
        k_cu_25 = 0.06528788242538795 / (1.08734816454031 * 0.999984371947918 * 1.00000664485415 ) # 0.06004375696813586 @ 25seg
        k = 0.07154005550662473
        print('INFO k: {}'.format(k))
        extypeI = 4; imoment = 1 * length * k / n_seg
        comments.append('Drafted using antennas.py and net2utils.py')
        createNEC2Cards('quadloop', comments, wavelength, wireRadius, segmentsize, squares,
                        targetMHz, plotStart = 1, plotRange = 0.000001,
                        i1 = extypeI, f6 = imoment )

def canexperiment():
    al = Material('Aluminium', 'al', cond_al)
    targetMHz = 2437.

    lp = 2 * 0.007958
    radius = lp / (2 * np.sin(18 * np.pi / (180 * 2)))
    length = 0.135

    coffeecan =  Cantenna(freqMHz = targetMHz, diameter = radius * 2, wire_guage = 9)
    print(coffeecan)
    print('wedge type element: {:0.4f} wedge width: {:0.4f}'.format(
        coffeecan.feed_wedge_to_reflector, coffeecan.wedge_width))

    wavelength = 1e-6 * c_0 / targetMHz
    vf = wavelength / coffeecan.wavelength_guide
    length_ideal = 3. * wavelength / (4. * vf)

    a = 2 * np.pi / wavelength
    b = 1.8412 / radius
    print('ideal guide wavelength: {:0.4f}'.format(2 * np.pi / np.sqrt(a*a + b*b)))

    print('target frequency: {:0.1f} MHz velocity factor: {:0.4f}'.format(targetMHz, vf))
    print('wavelength: {:0.4f} guide length: {:0.4f} can length: {:0.4f} m'.format(wavelength, coffeecan.wavelength_guide, length))

    print('dim in m radius: {:0.4f} patch size: {:0.6f} can length: {:0.4f}'.format(radius, lp, length))
    print('fraction radius: {:0.4f} patch size: {:0.4f} can length: {:0.4f}'.format(
        radius/coffeecan.wavelength_guide, lp/coffeecan.wavelength_guide, length/coffeecan.wavelength_guide))

    # match original dimensions from https://www.extremetech.com/archive/56984-building-a-wifi-antenna-out-of-a-tin-can
    wegoffset = 0.028
    stublength = distance((0.0354, 0.0354, 0.028), (0.034, 0.034, 0.028)) # 0.001979898987322331
    wegd = distance((.034, .034, .028), (.016, .016, .026))   # 0.025534290669607412
    wegc = distance((.034, .034, .028), (.016, .016, .028))   # 0.025455844122715714
    wegu = distance((.034, .034, .028), (.016, .016, .030))   # 0.025534290669607412
    wegl = distance((.034, .034, .028), (.018, .014, .028))   # 0.0256124969497314
    wegr = distance((.034, .034, .028), (.014, .018, .028))   # 0.0256124969497314
    wdown = distance((.016, .016, .026), (.016, .016, .028))  # 0.002
    wup = distance((.016, .016, .028), (.016, .016, .030))    # 0.002
    wleft = distance((.016, .016, .028), (.018, .014, .028))  # 0.0028284271247461888
    wright = distance((.016, .016, .028), (.014, .018, .028)) # 0.0028284271247461888
    wegvcos = wegc / wegd
    wegwcos = wegc / wegl
    wegvsin = np.sqrt(1 - wegvcos * wegvcos)
    wegwsin = np.sqrt(1 - wegwcos * wegwcos)
    print('stublength: {:0.4f} wedge length: {:0.4f} wedge width cos: {:0.4f} wedge vertical cos: {:0.4f}'.format(stublength, wegc, wegwcos, wegvcos))
    print('check: {:0.8f} {:0.8f} and: {:0.8f} {:0.8f}'.format(wleft, wegl*wegwsin, wup, wegu*wegvsin))

    print('dim in m ideal wedge length: {:0.4f} actual wedge length: {:0.4f}'.format(wavelength / 5, stublength + wegc))
    print('fraction ideal wedge length: {:0.4f} actual wedge length: {:0.4f}'.format(1 / 5, stublength + wegc / wavelength
                                                                                     ))
    print('ideal wedge offset: {:0.4f} actual wedge offset: {:0.4f}'.format(7 * wavelength / 32, wegoffset))
    wwidth = wleft + wright ; wheight = wdown + wup
    print('dim in m width of wedge: {:0.4f} height of wedge: {:0.4f}'.format(wwidth, wheight))
    print('fraction width of wedge: {:0.4f} height of wedge: {:0.4f}'.format(wwidth/wavelength, wheight/wavelength))

    dangle = 90. / 5.

    # modify wegoffset
    # wegoffset = 0.0225
    # wegoffset = 0.0241
    if 18. == dangle:
        #wegoffset = 0.023874
        #wegoffset = 0.022
        #wegoffset = 0.021
        #wegoffset = 0.023
        pass # wegoffset = 0.025
    if 18. / 3. == dangle:
        wegoffset = 0.023961509102665587
        wegoffset = 0.02928628890325795
        wegoffset = 0.028
        #wegoffset = 0.024
    if 18. / 5. == dangle:
        wegoffset = 0.023968518127970767

    centre = (.0,.0,.0)
    rot = Rotator(angle = dangle, x_radius = radius)
    c1 = rot.c1
    c2 = rot.c2
    ct = rot.ct
    cntr = centreNew(ct, centre, wegoffset)
    p1 = pointNew(c1, c2, ct, cntr, radius, 0.) ; p2 = pointNew(c1, c2, ct, cntr,
                                                                radius * np.cos(dangle * np.pi / 180),
                                                                radius * np.sin(dangle * np.pi / 180))
    av = []
    for i in range(3):
        val = 0
        val += p1[i]
        val += p2[i]
        av.append(val / 2)

    patchc = distance(pointNew(c1, c2, ct, cntr, av[c1], av[c2]),
                            cntr)
    print('axis to centre of patch: {}'.format(patchc))

    n_feed_points = 7
    n_feed_lines = 6
    can = Shape(material = al, n_points = n_feed_points, n_lines = n_feed_lines)
    setcoord(can.centre, centre)

    can = createCanPatch(centre, rot, can = can, length = length, frac = 1.)
    if 0:
        for idx, s in enumerate(can.surfaces):
            print('{}: n_points: {} n_lines: {} surface: {}'.format(idx, s.points.shape[1], s.lines.shape[1], s.surface))
    if 1:
        # use the centre of the cylinder patch to select a suitable feed point (wegoffset)
        for idx, l in enumerate(can.surfaces[0].surface[2, :]):
            point = can.surfaces[0].lines[0, abs(l)-1]
            pos = can.surfaces[0].points[rot.ct, point]
            if idx:
                diff = pre - pos
                print('patch centre {}: {}'.format(idx - 1, pos + diff / 2))

            pre = pos

    # now create the feed wedge
    point = 0 ; line = 0
    setcoord(can.points[:, point], (patchc, 0., wegoffset)) ; point += 1

    # create feed point at start of wedge
    can.feedline = line
    setcoord(can.feed, can.points[:, point - 1])

    # now complete the feed line stub
    endofstub = point
    setcoord(can.points[:, point], (patchc - stublength, 0., wegoffset)) ; point += 1
    setcoord(can.lines[:,line], (point-2, endofstub)) ; line += 1

    # wegd
    hv = wegc / wegvcos
    zdelta = hv * wegvsin
    setcoord(can.points[:, point], (patchc - stublength - wegc, 0., wegoffset - zdelta)) ; point += 1
    setcoord(can.lines[:,line], (endofstub, point - 1)) ; line += 1
    setcoord(can.points[:, point], (patchc - stublength - wegc, 0., wegoffset)) ; point += 1
    setcoord(can.lines[:,line], (endofstub, point - 1)) ; line += 1
    setcoord(can.points[:, point], (patchc - stublength - wegc, 0., wegoffset + zdelta)) ; point += 1
    setcoord(can.lines[:,line], (endofstub, point - 1)) ; line += 1
    hw = wegc / wegwcos
    ydelta = hw * wegwsin
    setcoord(can.points[:, point], (patchc - stublength - wegc, 0. - ydelta, wegoffset)) ; point += 1
    setcoord(can.lines[:,line], (endofstub, point - 1)) ; line += 1
    setcoord(can.points[:, point], (patchc - stublength - wegc, 0. + ydelta, wegoffset)) ; point += 1
    setcoord(can.lines[:,line], (endofstub, point - 1)) ; line += 1

    name = 'can'
    segperwave = 100
    segmentsize = wavelength / segperwave
    print('segment size: {:0.4f}'.format(1/segperwave))

    wireRadius = guage(6) / 2

    startMHz = 2400; rangeMHz = 100
    plotStart = startMHz / targetMHz
    plotRange = rangeMHz / targetMHz
    plotFreqMHz = startMHz
    plotStepCount = 100

    comments = ['{} can antenna for {} MHz'.format(al.name, targetMHz)]
    comments.append('Drafted using antenna.py and net2utils.py')
    comments.append('Author: Peter Saunderson')

    createNEC2Cards('can', comments,
                    wavelength, wireRadius, segmentsize, [can],
                    targetMHz, plotStart = startMHz / targetMHz, plotRange = rangeMHz / targetMHz, plotStepCount = plotStepCount)

if __name__ == '__main__':
    canexperiment()
