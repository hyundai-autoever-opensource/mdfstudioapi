<p align=center>

mdfstudioAPI is an API for reading asam mdf file and converting data to csv file format, including LGPL 3.0 open source library (asammdf-6.1.2)


</p>

# Goals
The main goals for this library are:

* to easily convert mdf files to csv files
* to implement specific requirements from users

# Features

* read mdf files (*.dat, *.mdf, *.mf4)
* calculate sampling rates and resample from these sampling rate list
* offer several export functions - group by, statistics, with index, etc.

# Open Source Library Notice
<p> A part of this library based on asammdf-6.1.2 and conveyed under the terms of this LGPL-3.0 license.<br>
You can find modification commments(author, date, contents) in source codes</p>

<p>Open source library information : </p>

* Name: asammdf
* Version: 6.1.2
* Summary: ASAM MDF measurement data file parser
* Home-page: https://github.com/danielhrisca/asammdf
* Author: Daniel Hrisca
* Author-email: daniel.hrisca@gmail.com
* License: LGPLv3+ 

# Dependencies
mdfstudioAPI uses the following libraries:
  - cChardet : to detect non-standard unicode encodings
  - hdf5storage : for Matlab v7.3 .mat export
  - lxml : for canmatrix arxml support
  - lz4 : to speed up the disk IO peformance
  - matplotlib : as fallback for Signal plotting
  - natsort : for fast channel sorting
  - numexpr : for algebraic and rational channel conversions
  - numpy : the heart that makes all tick
  - pandas : for DataFrame export
  - PyQt5 : for GUI tool
  - pyqtgraph : for GUI tool and Signal plotting (preferably the latest develop branch code)
  - scipy : for Matlab v4 and v5 .mat export
  - wheel : for installation in virtual environments
  - future : for fast .csv export
