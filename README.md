# Embroidery Stitch File HTML Viewer


### Viewer Screenshot
![](https://raw.githubusercontent.com/KurtSanders/Embroidery/refs/heads/main/images/Viewer%20Screenshot.jpg)

## Example Embroidery Directory Structure

### Embroidery Directory Root Directory 
  1. Must contain folder descriptive names that will form the 'Catalog' structure.

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
  
### Subfolders 
  1. Contains folders and subfolders of '\*.VP3' stitch files. These will be used to make '*.png' image files.  The application will attempt to remove hoop size suffixes to reduce the number of image files.
  2. If the subfolder contains '\*.vip' files, this application will search for '\*.jpg' files to view in the HTML file.  

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

### Configuration

The Python file has a section to define the following constants

```
# Start of User Defined Constants
MAX_FILES                   = 100   # Limit converted VP3 stitch files to PNG images
TABLE_COLS                  = 6     # Columns in HTML file
DEBUG                       = False # Trouble Shooting
faviconURI                  = "https://raw.githubusercontent.com/KurtSanders/Embroidery/f4e6494c4c0d63105bc81259bb854d22aaa46ef9/images/K+N_favicon.svg"
root_embroidery_directory   = os.path.join(Path.home(), 'Documents/Embroidery Thumbnails')
catalog_directory           = os.path.join(root_embroidery_directory, 'Catalog')
html_filename               = os.path.join(catalog_directory, 'Embroidery_image_table.html')
images_folder               = os.path.join(catalog_directory, 'images')
favicon_filename            = os.path.join(images_folder, "K+N_favicon.svg")
downloads_folder            = Path.home() / 'Downloads'
excluded_folders            = ['Alphabets & Monograms']
# End of User Defined Constants```
