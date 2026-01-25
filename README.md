antennas.py
----------------------------------

Generating the [Numerical Electromagnetics Code](https://www.nec2.org) (NEC) file can be very a time consuming and error prone process. For this reason the latest rewritten [necpp MOM simulator](https://github.com/tmolteno/necpp) includes Python and Ruby API to enable the geometric structures to be generated from code. For other NEC2 based simulators there are other python helper scripts that can be used to generate the .nec text file, allowing the modeller to use python to generate the .nec file. One limitation of all of the helper scripts that I have found so far is that they do not support patch cards (SP / SC) and some only support voltage and do not support current excitation (EX).  They also have limited support for reflection and translation cards (GX, GM).

To begin to address this limitation I have started my own antennas.py pre-processor helper script for Linux.  Please feel free to provide feedback via the [Discussions pages](https://github.com/peteasa/nec_quickly/discussions).

The Objective
----------------------------------

The objective is to create a generic pre-processor that gathers the geometry information into a set of classes that can then be played back to other applications.  For example:

* the geometry can be passed to [nec2utils.py](https://github.com/ckuethe/nec2-toys) to create NEC2 cards,
* or drive the [necpp](https://github.com/tmolteno/necpp) python API
* or populate a [FreeCAD](https://freecad.github.io/) design using the FreeCAD python macro API

The geometry information is captured in matrices that are in part inspired by gmsh input code.

When using with NEC output useful warning messages are output when a selected segment size violates the NEC2 segment size rules.

Progress so far
----------------------------------

I have proven antennas.py with the current excitation example provided by L.B. Cebik, W4RNL [Antenna Modelling Notes ](https://q82.uk/cebikmodelling) (Volume 2 Section 41 Multiple-Feedpoint Loop Modelling) and the Trevor Marshall's [WiFi Coffee Can Feed design for 2.437MHz](https://www.extremetech.com/archive/56984-building-a-wifi-antenna-out-of-a-tin-can) comparing with the original .nec file from [here](https://www.nec2.org/coffee.txt). The output .nec files have been simulated using Eric Wheeler (KJ7LNW) [nec2 with GUI xnec2c](https://github.com/KJ7LNW/xnec2c).