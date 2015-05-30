# OctoDisplay

When using OctoPrint to print with me 3D printer I used [OctoPiPanel](https://github.com/jonaslorander/OctoPiPanel) to watch my prints. OctoPiPanel works great but it uses a lot of CPU power of my little Raspberry Pi. So I developed thes interface that uses Python and urwid to display a graphical user interface.

## Install

````
git clone git@github.com:plaetzchen/OctoDisplay.git
cd OctoDisplay
pip install -r requirements.txt
python octodisplay.py <addressofoctoprint> <API-Key>
````
