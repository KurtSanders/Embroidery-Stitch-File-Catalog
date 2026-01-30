# Embroidery Stitch File Catalog


### Viewer Screenshot
![](https://raw.githubusercontent.com/KurtSanders/Embroidery/refs/heads/main/images/Viewer%20Screenshot.jpg)

## Operating Environment
 - This Python application was designed and tested on Macos Tahoe 26.2.  

## Example Embroidery Directory Structure

### Embroidery Directory Root Directory 
  1. The Embroidery root folder must contain folder descriptive names that will form the 'Catalog' structure as shown below.  Each folder will contain sub-folders of Husqvarna embroidery stitch files in the format of:
    - \*.vp3 
    - \*.vip with associated \*.jpg image files
    - other files (e.g., \*.pdf, *.txt, etc) will be ignored

```
	Embroidery Thumbnails/
	├── _My Designs
	├── 4th of July
	├── Baby
	├── Banners
	├── Birthdays
	├── Breezy Lane
	├── Cartoon Characters
	├── Catalog
	├── Christmas
	├── Classic Collection
	├── Dinos
	├── Easter
	├── Elephants
	├── Fairies
	├── Fall
	├── Felties
	├── Flowers
	├── Gnomes
	├── Halloween
	etc

```  
  
### Sub-folders 
  1. Sub-folders will contain the stitch files and associated jpg files. These stitch files will be used to create '*.png' image files in the 'images' folder.  The application will attempt to remove the file suffixes for the hoop size to reduce the number of image files.
  2. If the subfolder contains '\*.vip' files, this application will search for '\*.jpg' files in the same folder to view them in the HTML file.  

```
	Embroidery Thumbnails/
	├── _My Designs
	│   └── Embrilliance
	├── 4th of July
	│   ├── 3StarsApplique+-+EB
	│   │   ├── 3 Stars Applique 4x4.vp3
	│   │   ├── 3 Stars Applique 5x5.vp3
	│   │   ├── 3 Stars Applique 5x7.vp3
	│   │   ├── 3 Stars Applique 6x10.vp3
	│   │   └── 3 Stars Applique 9x9.vp3
	│   ├── CA 2988 Heart Star Stripes
	│   │   ├── CA Heart Star Stripes 4x4.vp3
	│   │   ├── CA Heart Star Stripes 5x7.vp3
	│   │   ├── CA Heart Star Stripes 6x10.vp3
	│   │   └── CA Heart Star Stripes 8X8.vp3
	├── Baby
	│   ├── 4x4Big-Lil-Brother-Sister
	│   │   ├── BigBrother-4x4.vp3
	│   │   ├── BigSister-4x4.vp3
	│   │   ├── LilBrother-4x4.vp3
	│   │   └── LilSister-4x4.vp3
	│   ├── ANGEL CUTIE
	│   │   └── VP3
	│   │       ├── ANGEL CUTIE 4X4.vp3
	│   │       ├── ANGEL CUTIE 5X7.vp3
	│   │       ├── ANGEL CUTIE 6X10.vp3
	│   │       └── ANGEL CUTIE 9x9.vp3
	├── Birthdays
	│   ├── BalloonCluster
	│   │   ├── BalloonCluster-4x4.vip
	│   │   ├── BalloonCluster-4x4.vp3
	│   │   ├── BalloonCluster-5x7.vip
	│   │   ├── BalloonCluster-5x7.jpg
	│   │   ├── BalloonCluster-5x7.vp3
	│   │   ├── BalloonCluster-6x10.vip
	│   │   ├── BalloonCluster-6x10.vp3
	│   ├── birthdayballoonsapplique
	│   │   ├── birthdayballoons4x4.vip
	│   │   ├── birthdayballoons5x7.vip
	│   │   └── birthdayballoons6x10.vip
	etc

```

### Application Configuration

The Python file has a beginning section for the users to define the following required constants:

```
# Start of User Defined Constants
MAX_FILES                   = 100   # Limit the number of stitch files to process
TABLE_COLS                  = 6     # Columns in HTML file
DEBUG                       = False # Verbose Output Troubleshooting
faviconURI                  = "https://raw.githubusercontent.com/KurtSanders/Embroidery/f4e6494c4c0d63105bc81259bb854d22aaa46ef9/images/K+N_favicon.svg"
root_embroidery_directory   = os.path.join(Path.home(), 'Documents/Embroidery Thumbnails')
catalog_directory           = os.path.join(root_embroidery_directory, 'Catalog')
html_filename               = os.path.join(catalog_directory, 'Embroidery_image_table.html')
images_folder               = os.path.join(catalog_directory, 'images')
favicon_filename            = os.path.join(images_folder, "K+N_favicon.svg")
downloads_folder            = Path.home() / 'Downloads'
excluded_folders            = ['Alphabets & Monograms']
# End of User Defined Constants

```
### Installation

## Requirements

Requirements.txt
