#!/usr/bin/env python3
import traits.trait_types
from colorama import Fore, Back, Style, init
from osxmetadata import *
from pathlib import Path
from send2trash import send2trash
from tqdm import tqdm
import fnmatch
# import json
import os
import os.path
import pyembroidery
import requests
import send2trash
import shutil
import webbrowser
import re
import logging
# import concurrent.futures

# import sys
# import threading
# import time

# Start of User Defined Constants
MAX_FILES = 200  # Limit converted VP3 stitch files to PNG images
TABLE_COLS = 6  # Columns in HTML file
DEBUG = False  # Trouble Shooting
faviconURI = "https://raw.githubusercontent.com/KurtSanders/Embroidery/f4e6494c4c0d63105bc81259bb854d22aaa46ef9/images/K+N_favicon.svg"
root_embroidery_directory = os.path.join(Path.home(), 'Documents/Embroidery Thumbnails')
catalog_directory = os.path.join(root_embroidery_directory, 'Catalog')
html_filename = os.path.join(catalog_directory, 'Embroidery_image_table.html')
images_folder = os.path.join(catalog_directory, 'images')
favicon_filename = os.path.join(images_folder, "K+N_favicon.svg")
downloads_folder = Path.home() / 'Downloads'
excluded_folders = ['Alphabets & Monograms']
# End of User Defined Constants

# Add application folders to exclude list
excluded_folders.extend(['images', 'Catalog'])
# Dictionery of defined folders
embroideryFoldersDict = {
    "embroidery_thumbnails_directory": {
        "location": root_embroidery_directory
    },
    "catalog_directory": {
        "location": catalog_directory
    },
    "html_filename": {
        "location": html_filename
    }, "images_folder": {
        "location": images_folder
    },
    "downloads_folder": {
        "location": downloads_folder
    },
    "favicon_filename": {
        "location": favicon_filename
    }
}

VXX_dictionary          = {}
fPattern_VXX            = "*.v[ip][3p]"
fPattern_VP3            = "*.vp3"
fPattern_VIP            = "*.vip"
fPattern_JPG            = "*.jpg"
pPattern_PNG            = "*.png"
catalogFoldersList      = []
VP3_filesToConvertList  = []
total_VXX_Keys          = 0

# Define the LoggerAdapter subclass
class DynamicContextFilter(logging.Filter):
    def __init__(self, prefix=f"{Fore.RESET}", suffix=f"{Back.BLACK}{Fore.RESET}"):
        super().__init__()
        self.prefix = prefix
        self.suffix = suffix

    def filter(self, record):
        # This modifies the LogRecord instance in place
        # The standard formatter can now access these attributes
        record.prefix_data = getattr(record, 'prefix_data', self.prefix)
        record.suffix_data = getattr(record, 'suffix_data', self.suffix)
        return True

logger = logging.getLogger("FilteredLogger")
logger.setLevel(logging.INFO)

# Create and add the filter to the logger/handler
dynamic_filter = DynamicContextFilter()

handler = logging.StreamHandler()
handler.addFilter(dynamic_filter)  # Attach filter to the handler

# Set a standard format string that references the new attributes
formatter = logging.Formatter('%(prefix_data)s%(levelname)s: %(message)s%(suffix_data)s')
handler.setFormatter(formatter)

logger.addHandler(handler)

####################################################################################################################
#  Main
####################################################################################################################

def main():
    init(autoreset=True)
    cdToHomeFolder()
    width = 55
    global total_VXX_Keys

    # Display Constants
    for key, value in embroideryFoldersDict.items():
        location = embroideryFoldersDict[key]['location']
        if os.path.exists(location):
            validLocation = f"{Style.BRIGHT}{Back.GREEN}{Fore.BLACK}[Exists]"
        else:
            validLocation = f"{Style.BRIGHT}{Back.RED}{Fore.BLACK}[Created]"
            if os.path.isdir(location):
                os.makedirs(location, exist_ok=True)
            else:
                download_image_to_folder(faviconURI, images_folder, favicon_filename)
        logger.info(
            f"{Fore.RED}{key:<{width}} : {Fore.YELLOW}{str(embroideryFoldersDict[key]['location']):<80} : {validLocation}")
    logger.info(f"{Fore.YELLOW}Excluded Folders: {', '.join(excluded_folders)}")
    logger.info(
        f"{Fore.RED}Starting {Fore.YELLOW}{MAX_FILES:,}{Fore.RED} loops images from {Fore.YELLOW}{count_files_pathlib():,}{Fore.RED} VXX files")

    index = 0
    for dirpath, dirnames, filenames in os.walk(root_embroidery_directory, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in excluded_folders]
        filenames[:] = [f for f in filenames if f != '.DS_Store']
        dirnames.sort()
        filenames.sort()

        if not filenames: continue
        logger.debug(f"{'Dirpath':<{width}}: {dirpath}")
        logger.debug(f"{'Dirnames':<{width}}: {dirnames}")
        logger.debug(f"{'Filenames':<{width}}: {filenames}")

        matching_files = fnmatch.filter(filenames, fPattern_VP3)
        if matching_files:
            logger.debug(f"{'VP3 Filenames: '} {matching_files}")
        else:
            matching_files = fnmatch.filter(filenames, fPattern_VIP)
            if matching_files:
                # Check for JPG files in the same directpry
                matching_JPG_Images = fnmatch.filter(filenames, fPattern_JPG)
                if matching_JPG_Images:
                    logger.info(f"{'VIP Filenames: '} {matching_files}")
                    logger.info(f"{'JPG Filenames: '} {matching_JPG_Images}")
                else:
                    logger.warning(f"{Fore.RED}{'VIP Directory: '} {dirpath} has no JPG images")
                    continue
            else:
                continue

        # Update Folder & File Counter
        index += 1

        # Get Catalog Folder Name
        CatalogName = getCatalogFolderName(dirpath)

        # Remove hoop sizes in filename in the format of -numberxnumber
        lastMetaName = ''
        for index2, filename in enumerate(matching_files):
            metaName = os.path.splitext(re.sub(r'-?\d?[xX]?\d+[xX]?', '', filename))[0]
            metaName = camel_to_spaces(re.sub('[._-]', ' ', metaName)).strip()
            if metaName == lastMetaName:
                logger.debug(f"{Fore.RED}Skipping {metaName} for {filename}")
                continue
            logger.debug(f"{Fore.GREEN}Processing {metaName} for {dirpath}/{filename}")

            p = Path(filename)
            VXX_Filename = os.path.join(dirpath, filename)
            if fnmatch.fnmatch(VXX_Filename, fPattern_VP3):
                # Add .png file suffix which will be created by makePic function
                Image_Filename = f"{os.path.join(images_folder, CatalogName, p.stem)}.png"
            else:
                #  This is a .VIP file, which cannot be handled by makePic, so grab a 'jpg' file
                matching_JPG_files = fnmatch.filter(filenames, fPattern_JPG)
                if matching_JPG_files:
                    logger.debug(f"VXX_Filename {index2}: {VXX_Filename}")
                    logger.debug(f"JPG Images {index2}: {matching_JPG_files}")
#                    Image_Filename = f"{os.path.join(images_folder, CatalogName, matching_JPG_files[0])}"
                    Image_Filename = f"{os.path.join(dirpath, matching_JPG_files[0])}"
                    logger.debug(f"JPG Image Filename {index2}: {Image_Filename}")
                    Image_infile = f"{os.path.join(dirpath, matching_JPG_files[0])}"
                    logger.debug(f"JPG Image infile {index2}: {Image_infile}")
#                    copy_file(Image_infile, Image_Filename)
                else:
                    logger.debug(f"Skipping: No JPG Images found: {dirpath}")
                    break

            logger.debug(f"Catalog Name {index2}: {CatalogName}")
            logger.debug(f"metaName {index2}: {metaName}")
            logger.debug(f"VXX filename {index2}: {filename}")
            logger.debug(f"Image_filename {index2}: {Image_Filename}")

            # Build Catalog Dictionary of VXX Files and Paths
            VXX_dictionary.setdefault(CatalogName, {})
            VXX_dictionary[CatalogName].setdefault(metaName, {})
            # Add sub-keys and values
            VXX_dictionary[CatalogName][metaName] = {
                "VXX_filename": VXX_Filename,
                'Image_filename': Image_Filename
            }
            lastMetaName = metaName

        if index >= MAX_FILES: break

#    print(json.dumps(VXX_dictionary, indent=4))

    #   Iterate over the VXX Master Dictionery
    total_VXX_Keys = count_nested_key(VXX_dictionary, 'VXX_filename')
    pbar = tqdm(total=total_VXX_Keys, unit=" files")
    for CatalogName, inner_dict in VXX_dictionary.items():
        CatalogFolder = os.path.join(images_folder, CatalogName)

        # The folders in the embroidery root are used as Catalog Indexes
        if CatalogName not in catalogFoldersList:
            catalogFoldersList.append(CatalogName)
            pbar.set_description(f"Processing {CatalogName}")
            if not os.path.exists(CatalogFolder):
                logger.error(f"{Fore.YELLOW}Error: '{CatalogFolder}' does not exist. Creating...")
                os.makedirs(CatalogFolder, exist_ok=True)
        for metaName, value in inner_dict.items():
            metaName = camel_to_spaces(metaName).strip()
            VXX_Filename    = VXX_dictionary[CatalogName][metaName]['VXX_filename']
            Image_Filename  = VXX_dictionary[CatalogName][metaName]['Image_filename']
            ImageExists     = os.path.exists(Image_Filename)
            logger.debug(f'{Fore.CYAN}MetaName', metaName)
            logger.debug('  VXX_Filename: ', VXX_Filename)
            ImageExistsStatus = f"{Style.BRIGHT}{Back.GREEN}{Fore.BLACK}[Exists]" if ImageExists else f"{Style.BRIGHT}{Back.RED}{Fore.BLACK}[Not Found.. {Back.GREEN}Created]"
            logger.debug(f" Image: {Image_Filename} {ImageExistsStatus}")
            if not ImageExists:
                if fnmatch.fnmatch(VXX_Filename, fPattern_VP3):
                    makePic(VXX_Filename, Image_Filename)
            pbar.update()

    pbar.close()

    create_image_table_html()

    logger.info(f"{Fore.RED}Image catalog generation complete.{Style.RESET_ALL}")


def create_image_table_html():
    logger.info(f"Creating HTML Images File from {Fore.YELLOW}{total_VXX_Keys} {Fore.RED}images")
    lastParentFolder = ''

    #   Begin building of the HTML webpage
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Kurt's Embroidery Image Finder</title>
        <link rel='icon' type='image/svg' href='images/K+N_favicon.svg'</link>
        <style>
            html {{ scroll-behavior: smooth; }}
            table {{ border-collapse: collapse; }}
            td {{ border: 1px solid powderblue; padding: 3px; text-align: center; }}
            img {{ width: 100px; height: auto; display: block; margin: auto; }}
            th {{ background-color:powderblue; font-family: Verdana; text-align: center; }}
            a {{text-decoration: none; font-family: Verdana; }}
            .highlight {{ background-color: yellow; font-weight: bold; }}
            .display-box {{
              display: none; /* Hide the boxes by default */
              padding: 15px;
              border: 1px solid #ccc;
              background-color: #f9f9f9;
              margin-top: 10px;
              width: 200px;
            }}

            #imageSearchInput {{
              width: 100%; 
              padding: 12px 20px 12px 40px; /* Add padding for a potential search icon */
              border: 1px solid #ddd; 
              margin-bottom: 12px; 
              box-sizing: border-box; /* Ensures padding doesn't affect width */
            }}

            #imageTable {{
              border-collapse: collapse; 
              width: 100%; 
              border: 1px solid #ddd; 
            }}

            #imageTable th, #imageTable td {{
              text-align: left; 
              padding: 12px; 
            }}

            #imageTable tr {{
              border-bottom: 1px solid #ddd;
            }}

            #imageTable tr:hover {{
              background-color: #f1f1f1;
            }}

            .image-cell {{
              /* Optional: Define a specific size or make the cell responsive */
              width: 200px; 
              height: 150px;
              /* Optional: Remove default cell padding if desired */
              padding: 0; 
            }}

            .image-cell img {{
              /* This ensures the image will not exceed the dimensions of the cell */
              max-width: 100%; 
              max-height: 100%;
              /* This prevents the image from stretching if the cell aspect ratio differs */
              height: auto; 
              width: auto;
              /* To control how the image fills the space while preserving aspect ratio */
              object-fit: contain; /* or 'cover' if you want it to fill the cell and crop any excess */
            }}

            #scrollToTopBtn {{
                display: none; /* Hidden by default */
                position: fixed; /* Fixed/sticky position */
                bottom: 20px; /* Place the button at the bottom of the page */
                right: 30px; /* Place the button 30px from the right */
                z-index: 99; /* Make sure it does not overlap */
                border: none;
                outline: none;
                background-color: red;
                color: white;
                cursor: pointer;
                padding: 15px;
                border-radius: 10px;
                font-size: 18px;
            }}

            #scrollToTopBtn:hover {{
                background-color: #555; /* Add a hover effect */
            }}

        </style>
        <script>           
            function filterTable() {{
                  // Declare variables
                  var input, filter, table, tr, td, img, i, j, txtValue, isFound;
                  input = document.getElementById("imageSearchInput");
                  filter = input.value.toUpperCase();
                  table = document.getElementById("imageTable");
                  tr = table.getElementsByTagName("tr");

                  // Loop through all table rows, starting from index 1 to skip the header row
                  for (i = 1; i < tr.length; i++) {{
                    isFound = false;
                    // Get all cells in the current row
                    td = tr[i].getElementsByTagName("td");

                    // Loop through all cells in the current row
                    for (j = 0; j < td.length; j++) {{
                      // Check for an image in the cell
                      img = td[j].querySelector('img');
                      if (img) {{
                        // Use the 'alt' attribute for filtering
                        txtValue = img.alt;
                      }} else {{
                        // Fallback to text content if no image is found in the cell
                        txtValue = td[j].textContent || td[j].innerText;
                      }}

                      // Check if the filter text is in the cell's text or image's alt text
                      if (txtValue.toUpperCase().indexOf(filter) > -1) {{
                        isFound = true;
                        break; // Stop searching cells in this row if a match is found
                      }}
                    }}

                    // Show or hide the row based on whether a match was found
                    if (isFound) {{
                      tr[i].style.display = "";
                    }} else {{
                      tr[i].style.display = "none";
                    }}
                  }}
                }}                
        </script>
    </head>
    <body>
        <button id="scrollToTopBtn" title="Go to top">Top</button>
        <input type="text" id="imageSearchInput" onkeyup="filterTable()" placeholder="Search by image description...">
        <table id="imageTable">
        <tbody>
    """
    #   Create Table of Folder Links
    html_content += f"""
        <tr>
            <th colspan={TABLE_COLS}; style="text-align: center;">
                Embroidery Catagory Folder Name Links
            </th>
        </tr>
    """
    i = 0
    for catalogName in sorted(VXX_dictionary.keys()):
        i += 1
        if i % TABLE_COLS == 0:
            html_content += "<tr>"
        html_content += f"""
        <td style="text-align: center;">
            <a href="#{catalogName}">{catalogName}</a>
        </td>
        """
        if (i + 1) % TABLE_COLS == 0 or i == len(VXX_dictionary):
            # Close the table row
            html_content += "</tr>"

    # Iterate the Master Dictionery
    loopIndex = 0
    boxIndex = 0
    boxHtml = ''
    for CatalogName, inner_dict in VXX_dictionary.items():
        groupTotal = len(inner_dict)
        logger.debug(f"Processing {CatalogName}")
        for metaName, value in inner_dict.items():
            VXX_Filename = VXX_dictionary[CatalogName][metaName]['VXX_filename']
            Image_Filename = VXX_dictionary[CatalogName][metaName]['Image_filename']
            logger.debug(f". metaName   : {metaName}")
            logger.debug(f". VXX_Filename: {VXX_Filename}")
            logger.debug(f". Image_Filename: {Image_Filename}")
            # Iterate through images and create table rows and cells
            if loopIndex % TABLE_COLS == 0:
                # Start a new table row
                html_content += "<tr>"

            if lastParentFolder != CatalogName:
                lastParentFolder = CatalogName
                if loopIndex % TABLE_COLS != 0:
                    html_content += f"</tr>"
                loopIndex = 0
                html_content += f"""
                <tr>
                    <th colspan={TABLE_COLS}>
                        <div style="text-align: center;" id='{CatalogName}'>{CatalogName}</div>
                    </th>                    
                </tr>"
                """

            # Add the table cell with a clickable image
            # The <a> tag links to the full image, and the <img> tag displays a thumbnail (same source for simplicity)
            html_content += f"""
            <td class="image-cell"; style="text-align: center;">
                <a href="{Image_Filename}">
                    <img style='display:block;' src="{Image_Filename}" alt="{metaName}">
                </a>
                <p>
                    <a href="{VXX_Filename}">{metaName} </a>
                    <a href="#" onclick="toggleDisplayBox(event, 'box{boxIndex}')"> &#128194</a>
                    <div id="box{boxIndex}" class="display-box">
                      <h4>Embroidery Thumbnail Folder</h4>
                      <p>{VXX_Filename.replace(f"{root_embroidery_directory}/",'')}</p>
                    </div>
                </p>
            </td>
            """
            boxIndex += 1

            if (loopIndex + 1) % TABLE_COLS == 0 or loopIndex == groupTotal:
                # Close the table row
                html_content += "</tr>"

            loopIndex += 1

    html_content += f"""
                    </tbody>
                </table>
                <script>                
                     // Function to toggle the visibility of a specific display box
                    function toggleDisplayBox(event, boxId) {{
                      event.preventDefault(); // Prevent the default link behavior (e.g., jumping to the top of the page)
                      
                      const box = document.getElementById(boxId);
                      const unicodeValue = 0x1F4C1;
                      const symbol = String.fromCodePoint(unicodeValue);
                    
                      if (box.style.display === 'block') {{
                        box.style.display = 'none';
                        event.target.textContent = symbol; // Update link text
                      }} else {{
                        box.style.display = 'block';
                        event.target.textContent = 'Hide Box'; // Update link text
                      }}
                    }}
                
                    // Get the button element
                    const scrollToTopBtn = document.getElementById("scrollToTopBtn");

                    // Function to scroll to the top of the page smoothly
                    const scrollToTop = () => {{
                        window.scrollTo({{
                            top: 0,
                            behavior: "smooth"
                        }});
                    }};

                    // Function to toggle button visibility based on scroll position
                    const toggleVisibility = () => {{
                        if (window.pageYOffset > 300) {{ // Show button after scrolling 300px
                            scrollToTopBtn.style.display = "block";
                        }} else {{
                            scrollToTopBtn.style.display = "none";
                        }}
                    }};

                    // Add event listeners
                    window.addEventListener("scroll", toggleVisibility);
                    scrollToTopBtn.addEventListener("click", scrollToTop);
                </script>
            </body>
        </html>
    """

    with open(html_filename, "w") as f:
        f.write(html_content)

    logger.info(f"HTML table saved to {Fore.YELLOW}{html_filename}")

    # Create a file URL (important for local files)
    file_url = f"file://{os.path.abspath(html_filename)}"
    # Open the URL in a new browser tab (optional, can also use webbrowser.open)
    webbrowser.open_new_tab(file_url)


###############################################
# Functions
###############################################


def count_files_pathlib():
    # Convert the input string path to a Path object
    p = Path(root_embroidery_directory)
    # Use rglob('*') to find all entries recursively
    # Filter for items that are files and count them
    count = len([file for file in p.rglob('*.vp3') if file.is_file()])
    count += len([file for file in p.rglob('*.vip') if file.is_file()])
    return count


def download_image_to_folder(image_url, folder_name, image_filename):
    """Downloads an image from a URL to a specified folder."""

    # Create the folder if it doesn't exist
    if not os.path.exists(folder_name):
        logger.critical(f"Error: Folder '{folder_name}' does not exist for the favicon image.")
        exit(100)

    # Define the full path for saving the file
    save_path = os.path.join(folder_name, image_filename)

    try:
        # Get the image content
        response = requests.get(image_url)
        response.raise_for_status()  # Raise an exception for bad status codes

        # Write the content to a file in binary mode
        with open(save_path, 'wb') as f:
            f.write(response.content)
        logger.debug(f"Image saved successfully to '{save_path}'.")

    except requests.exceptions.RequestException as e:
        logger.error(f"An error occurred during download: {e}")


def remove_file(infile):
    if not os.path.exists(infile):
        logger.error(f"{Fore.RED}Error: File '{infile}' does not exist.")
        return

    if ask_yes_no(f"{Fore.RED}Are you sure you want to delete '{infile}'?"):
        try:
            send2trash(infile)
            logger.info(f"{Fore.YELLOW}File '{infile}' moved to trash successfully.")
        except send2trash.TrashPermissionError:
            logger.error(f"{Fore.RED}Could not move '{infile}' to trash due to a permission error.")
        except Exception as e:
            logger.error(f"{Fore.RED}An unexpected error occurred: {e}")
    else:
        logger.warning("{Fore.RED}File Deletion cancelled.")


def ask_yes_no(question):
    """
    Continues prompting user until they enter a valid 'yes' or 'no' response.
    Returns True for 'yes', False for 'no'.
    """
    while True:
        # Ask the question and convert input to lowercase
        reply = input(f"{Fore.RED}{question} (y/n): ").lower().strip()  # .strip() removes leading/trailing whitespace

        if reply in ("yes", "y"):
            return True
        elif reply in ("no", "n"):
            return False
        else:
            logger.error(f"{Fore.YELLOW}Sorry, invalid input. Please try again.")


def copy_file(source_file, destination_file):
    """
    Copy Source to Destination
    Args:
        source_file: The source file to be copied.
        destination_file (str): The full path name of the target file.
    """

    # Define the source and destination paths
    # Use absolute paths for clarity or to avoid potential issues
    logger.debug(f"Copying file '{source_file}' to '{destination_file}'")
    # Ensure the destination directory exists (shutil.copy2 will raise an error otherwise if destination is a directory)
    destination_dir = os.path.dirname(destination_file)
    if not os.path.exists(destination_dir):
        os.makedirs(destination_dir)

    try:
        shutil.copy2(source_file, destination_file)
        logger.info(f"File successfully copied from '{source_file}' to '{destination_file}'")
    except shutil.SameFileError:
        logger.error("Error: Source and destination represent the same file.")
    except FileNotFoundError:
        logger.warning(f"Error: Source file '{source_file}' not found.")
    except PermissionError:
        logger.warning("Error: Permission denied. Check file permissions.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}")


def count_nested_key(d, key_name):
    """
    Recursively counts the occurrences of a specific key name in a nested dictionary.
    Args:
        d (dict): The dictionary to search.
        key_name (str): The name of the key to count.
    Returns:
        int: The total count of the key name.
    """
    count = int(key_name in d)  # Check if the key is in the current dictionary
    for value in d.values():
        if isinstance(value, dict):
            # If the value is a dictionary, recurse and add to the count
            count += count_nested_key(value, key_name)
        elif isinstance(value, list):
            # Also handle lists that might contain dictionaries
            for item in value:
                if isinstance(item, dict):
                    count += count_nested_key(item, key_name)
    return count


def getCatalogFolderName(dirpath):
    # Get the Catalog Folder Index Name for the embroidery file
    p = Path(dirpath)
    try:
        where = p.parts.index('Embroidery Thumbnails')
        # Get all parts after the specific folder, then join them
        parentFolderName = p.parts[where + 1]
        logger.debug(f"Catalog Folder: {parentFolderName}")
    except ValueError:
        logger.critical(f"'Error: 'Embroidery Thumbnails' not found in the '{dirpath}'")
        exit(99)
    return parentFolderName


def cdToHomeFolder():
    # Change the current working directory
    try:
        os.chdir(downloads_folder)
    except FileNotFoundError:
        logger.critical(f"Error: The directory {downloads_folder} was not found.")
        exit(99)
    except Exception as e:
        logger.critical(f"An error occurred changing directory to {downloads_folder}: {e}")
        exit(99)


def makePic(infile, outfile):
    # Read the design
    logger.debug(f"Reading : {infile}")
    rc = False
    if infile.endswith(".vp3") and outfile.endswith(".png"):
        try:
            pattern = pyembroidery.read(infile)
        except (TypeError, AttributeError) as e:
            logger.error(f"An error occurred reading {infile}")
            logger.error(f"Error: {e}")
            remove_file(infile)
            return rc

        # Write the image (visual representation)
        logger.debug(f"Writing Image file to: {outfile}")
        rc = pyembroidery.write_png(pattern, outfile)

        set_finder_comment(outfile, infile.replace(root_embroidery_directory, ""))
    return rc

def set_finder_comment(file_path, comment_text):
    # Ensure the path is an absolute path for best compatibility
    abs_path = os.path.abspath(file_path)

    try:
        md = OSXMetaData(abs_path)
        md.kMDItemFinderComment = comment_text
        logger.debug(f"Comment set for {file_path}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")


def camel_to_spaces(camel_str):
    """
    Converts a camelCase string to a space-separated string.
    """
    # Inserts a space before any capital letter that is followed by a lowercase letter,
    # or a capital letter that follows a lowercase letter/digit.
    # This handles cases like "ABCWord" -> "ABC Word" and "myVariableName" -> "my Variable Name"
    s1 = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', camel_str)
    # Inserts a space before any sequence of two or more capital letters
    # if they are followed by a lowercase letter, to handle acronyms.
    s2 = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', s1)
    return s2

if __name__ == "__main__":

    main()