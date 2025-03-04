import argparse
import os
import PIL.Image
import platform
import re
import requests
import shutil
import sys
import time
import yaml
import zipfile
from datetime import datetime
from modules.logs import MyLogger
from modules.notifications import discord, generate_summary

logger = MyLogger()

##define banner
def print_banner(version):
    """Print the Asset Assistant banner and version."""
    logger.separator()
    logger.info_center(r"     _                 _      _            _     _              _    ") 
    logger.info_center(r"    / \   ___ ___  ___| |_   / \   ___ ___(_)___| |_ __ _ _ __ | |_  ")
    logger.info_center(r"   / _ \ / __/ __|/ _ \ __| / _ \ / __/ __| / __| __/ _` | '_ \| __| ")
    logger.info_center(r" / ___ \\__ \__ \  __/ |_ / ___ \\__ \__ \ \__ \ || (_| | | | | |_  ")
    logger.info_center(r" /_/   \_\___/___/\___|\__/_/   \_\___/___/_|___/\__\__,_|_| |_|\__| ")
    logger.info("")
    logger.info("")
    logger.info(f" Version: v{version}")


## start ##
parser = argparse.ArgumentParser(description='Asset Assistant')
parser.add_argument('--version', action='store_true', help='Print version and exit')
args = parser.parse_args()

start_time = time.time()
with open("VERSION", "r") as f:
    version = f.read().strip()

if args.version:
    print_banner(version)
    sys.exit(0)

print_banner(version)
platform_info = platform.platform()
logger.info(f" Platform: {platform.platform()}")
logger.separator(text="Asset Assistant Starting", debug=False)

## load config from file system##  
config_paths = [
    os.path.join('config', 'config.yml'),  # /config/config.yml
    'config.yml'  # ./config.yml
]

config = None
for config_path in config_paths:
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            logger.info(f" Configuration loaded from {config_path}")
            break
    except FileNotFoundError:
        continue

## load config from ENV VARS ##
def load_config_from_env():
    """Load configuration from environment variables with defaults."""
    return {
        'process': os.getenv('PROCESSDIR', '/config/process'),
        'shows': os.getenv('SHOWSDIR', '/config/shows'),
        'movies': os.getenv('MOVIESDIR', '/config/movies'),
        'collections': os.getenv('COLLECTIONSDIR', '/config/collections'),
        'failed': os.getenv('FAILEDDIR', '/config/failed'),
        'backup': os.getenv('BACKUPDIR', '/config/backup'),
        'logs': os.getenv('LOGSDIR', '/config/logs'),
        'enable_backup': os.getenv('ENABLE_BACKUP', 'false').lower() == 'true',
        'service': os.getenv('SERVICE', ''),
        'plex_specials': None if os.getenv('PLEX_SPECIALS', '') == '' else os.getenv('PLEX_SPECIALS', '').lower() == 'true',
        'discord_webhook': os.getenv('DISCORD_WEBHOOK', ''),
        'discord_enabled': os.getenv('DISCORD_ENABLED', 'false').lower() == 'true',
        'debug': os.getenv('DEBUG', 'false').lower() == 'true'
    }


if config is None:
    logger.warning(f" Config file not found. Tried: {', '.join(config_paths)}")
    logger.info(" Falling back to environment variables...")
    config = load_config_from_env()
    logger.info(" Configuration loaded from environment variables")

if config is None:
    logger.error(" No configuration found in files or environment")
    logger.error(f" Current directory: {os.getcwd()}")
    sys.exit(1)

## paths ##
process_dir = config['process']
movies_dir = config['movies']
shows_dir = config['shows']
collections_dir = config['collections']
script_dir = os.path.dirname(os.path.abspath(__file__))
failed_dir = config['failed']
backup_dir = config['backup']
backup_enabled = config.get('enable_backup', False)
service = config.get('service', None)
plex_specials = config.get('plex_specials', None)

## path check ##
unique_paths = {process_dir, movies_dir, shows_dir, collections_dir}
if len(unique_paths) != 4:
    logger.error(" Directory paths must be unique. Terminating script.")
    sys.exit(1)
    
## check process directory ##
if not os.path.exists(process_dir):
    logger.error(f" Process directory '{process_dir}' not found. Terminating script.")
    sys.exit(1)

## check media directories ##
optional_dirs = {
    'movies': movies_dir,
    'shows': shows_dir,
    'collections': collections_dir
}

for dir_name, dir_path in optional_dirs.items():
    if dir_path and not os.path.exists(dir_path):
        optional_dirs[dir_name] = None
        
logger.debug(" Process directory:")
logger.debug(f" - {process_dir}")
logger.debug(f" Movies directory:")
if movies_dir:
    logger.debug(f" - {movies_dir}")
else:
    logger.warning(f" - Directory not found. Skipping movies.")
logger.debug(f" Shows directory:")
if shows_dir:
    logger.debug(f" - {shows_dir}")
else:
    logger.warning(f" - Directory not found, skipping shows")
logger.debug(f" Collections directory:")
if collections_dir:
    logger.debug(f" - {collections_dir}")
else:
    logger.warning(f" - Directory not found, skipping collections")
logger.debug("")

## service check ##
if service == None:
    logger.warning(" Naming convention: Not set") 
    logger.debug("   Skipping:") 
    logger.debug("   - Season posters")
    logger.debug("   - Episode cards")
    logger.debug("   - Collection assets")
    logger.debug("")
else:
    if service == "kodi" or service == "kometa":
        logger.debug(f" Naming convention: {service.capitalize()}")
        logger.debug("   Enabling:")
        logger.debug("   - Season posters")
        logger.debug("   - Episode cards")
        logger.debug("   - Collection assets")
        logger.debug("")
    else:
        logger.debug(f" Naming convention: {service.capitalize()}")
        logger.debug("   Enabling:")
        logger.debug("   - Season posters")
        logger.debug("   - Episode cards")
        logger.debug("   Skipping:")
        logger.debug("   - Collection assets")
        logger.debug("")

## failed directory ##
if not os.path.exists(failed_dir):
    os.makedirs(failed_dir)
    logger.debug(" Failed directory not found...")
    logger.debug(" Successfully created failed directory")
    logger.debug(f" - {failed_dir}")
    logger.debug("")
else:
    logger.debug(f" Failed Directory:")
    logger.debug(f" - {failed_dir}")
    logger.debug("")

## backup directory ##
if backup_enabled:
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        logger.debug(f" Backup Enabled: {backup_enabled}")
        logger.debug(" Backup directory not found...")
        logger.debug(" Successfully created backup directory")
        logger.debug(f" - {backup_dir}")
    else:
        logger.debug(f" Backup Enabled: {backup_enabled}")
        logger.debug(f" Backup Directory:")
        logger.debug(f" - {backup_dir}")
else:
    logger.debug(f" Backup Enabled: {backup_enabled}")
    
logger.separator(text="Processing Images", debug=False, border=True)

## extract zip files ##
def unzip_files(process_dir):
    for item in os.listdir(process_dir):
        if item.lower().endswith('.zip'):
            file_path = os.path.join(process_dir, item)
            try:
                logger.info(f" Processing zip file '{item}'")
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(process_dir)
                os.remove(file_path)
                logger.info(" - Successfully extracted")
                logger.info("")
            except zipfile.BadZipFile:
                logger.error(f" - '{item}' is not a valid zip file")
                move_to_failed(item, process_dir, failed_dir)
                logger.info(" - Moved to failed directory")
                logger.info("")
            except Exception as e:
                logger.error(f" - Error extracting '{item}': {str(e)}")
                move_to_failed(item, process_dir, failed_dir)
                logger.info(" - Moved to failed directory")
                logger.info("")

## process subdirectories ##
def process_directories(process_dir):
    for item in os.listdir(process_dir):
        item_path = os.path.join(process_dir, item)
        if os.path.isdir(item_path):
            for root, _, files in os.walk(item_path):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                        src = os.path.join(root, file)
                        dest = os.path.join(process_dir, file)
                        shutil.move(src, dest)
            shutil.rmtree(item_path)
            logger.info(f" Processimg folder '{item}'")
            logger.info("")

## define categories ##
def categories(filename, movies_dir, shows_dir):
    # Update the season pattern to handle hyphenated format like "Show (Year) - Season X"
    season_pattern = re.compile(r'(?:^|\s|-)\s*Season\s+(\d+)', re.IGNORECASE)
    episode_pattern = re.compile(r'S(\d+)[\s\.]?E(\d+)', re.IGNORECASE)
    specials_pattern = re.compile(r'Specials', re.IGNORECASE)
    show_pattern = re.compile(r'(.+)\s\((\d{4})\)', re.IGNORECASE)

    season_match = season_pattern.search(filename)
    episode_match = episode_pattern.search(filename)
    specials_match = specials_pattern.search(filename)
    show_match = show_pattern.search(filename)
    
    category = None
    season_number = None 
    episode_number = None
    show_name = None
    
    if show_match:
        show_name = show_match.group(1).strip()
        show_year = show_match.group(2).strip()
        logger.debug(f" Extracted show name: '{show_name}', year: '{show_year}'")
    
    if season_match:
        if service:
            category = 'season'
            season_number = season_match.group(1)
            if show_name:
                expected_dir = f"{show_name} ({show_year})"
                logger.debug(f" Looking for show directory: {expected_dir}")
                if not os.path.exists(os.path.join(shows_dir, expected_dir)):
                    logger.debug(f" Show directory not found for: {expected_dir}")
                    category = None
        else:
            category = 'skip'
    
    elif specials_match:
        if service:
            category = 'season'
            season_number = None  # Explicitly set to None for specials
            if show_name:
                # Just check if the show directory exists, not the specials directory
                expected_dir = f"{show_name} ({show_year})"
                logger.debug(f" Looking for show directory for specials: {expected_dir}")
                if not os.path.exists(os.path.join(shows_dir, expected_dir)):
                    logger.debug(f" Show directory not found for specials: {expected_dir}")
                    category = None
        else:
            category = 'skip'
    
    elif episode_match:
        if service:
            category = 'episode'
            season_number = episode_match.group(1)
            episode_number = episode_match.group(2)
            
            # Log exact episode details for debugging
            logger.debug(f" Found episode S{season_number}E{episode_number}")
            
            if show_name:
                # Try multiple matching strategies with country preference
                exact_match = f"{show_name} ({show_year})"
                matching_dirs = []
                
                # Step 1: Collect all possible matches with year
                for dir_name in os.listdir(shows_dir):
                    dir_show_match = re.match(r'(.+)\s\((\d{4})\)', dir_name, re.IGNORECASE)
                    if dir_show_match:
                        dir_show_name = dir_show_match.group(1).strip().lower()
                        dir_show_year = dir_show_match.group(2)
                        
                        # Check if show names match
                        if dir_show_name.startswith(show_name.lower()):
                            matching_dirs.append(dir_name)
                
                best_match = None
                
                # Step 2: If multiple matches, prioritize exact match first, then US version
                if len(matching_dirs) > 1:
                    # First look for exact match with year
                    for match_dir in matching_dirs:
                        if match_dir.lower() == exact_match.lower():
                            best_match = match_dir
                            logger.debug(f" Using exact match: '{match_dir}'")
                            break
                    
                    # If no exact match found, look for US version
                    if not best_match:
                        for match_dir in matching_dirs:
                            if "(US)" in match_dir or "(USA)" in match_dir:
                                best_match = match_dir
                                logger.debug(f" Prioritizing US version: '{match_dir}'")
                                break
                
                # Step 3: If still no match, prioritize closest year match
                if not best_match:
                    closest_year_diff = 9999
                    for match_dir in matching_dirs:
                        dir_year_match = re.search(r'\((\d{4})\)', match_dir)
                        if dir_year_match:
                            dir_year = int(dir_year_match.group(1))
                            year_diff = abs(int(show_year) - dir_year)
                            if year_diff < closest_year_diff:
                                closest_year_diff = year_diff
                                best_match = match_dir
                
                # Step 4: If only one match, use it
                elif len(matching_dirs) == 1:
                    best_match = matching_dirs[0]
                
                # Step 5: If no matches found by year, try partial match as last resort
                if not best_match:
                    for dir_name in os.listdir(shows_dir):
                        if show_name.lower() in dir_name.lower():
                            if "(AU)" in dir_name or "(UK)" in dir_name or "(CA)" in dir_name:
                                # Skip non-US versions in partial matching unless it's the only option
                                continue
                            best_match = dir_name
                            logger.debug(f" Using partial match: '{show_name}' -> '{dir_name}'")
                            break
                    
                    # If still nothing, accept any partial match including non-US versions
                    if not best_match:
                        for dir_name in os.listdir(shows_dir):
                            if show_name.lower() in dir_name.lower():
                                best_match = dir_name
                                logger.warning(f" Using non-US partial match: '{show_name}' -> '{dir_name}'")
                                break
                
                # Check if we found any match at all
                found = best_match is not None
                
                if not found:
                    logger.debug(f" Could not find directory for '{show_name} ({show_year})'")
                    category = None
    
    else:
        for dir_name in os.listdir(collections_dir):
            if filename.split('.')[0].lower().replace("collection", "").strip() == dir_name.lower().replace("collection", "").strip():
                if (service in ["kometa", "kodi"]):
                    category = 'collection'
                    break
                elif service not in ["kometa", "kodi"]:
                    category = 'not_supported'
                break
        else:
            for dir_name in os.listdir(movies_dir):
                if filename.split('.')[0].lower() in dir_name.lower():
                    category = 'movie'
                    break
            else:
                for dir_name in os.listdir(shows_dir):
                    if filename.split('.')[0].lower() in dir_name.lower():
                        category = 'show'
                        break

    if category not in ['movie', 'show', 'season', 'episode', 'collection']:
        move_to_failed(filename, process_dir, failed_dir)
        logger.info(f" {filename}:")
        if category == 'skip':
            logger.info(" - Asset skipped due to 'service' not being specified")
        elif category == 'not_supported':
            logger.info(f" - Asset skipped due to {service.capitalize()} not supporting collection assets")
        else:
            logger.info(" - Match not found, please double check file/directory naming")
        logger.info(" - Moved to failed directory")
        logger.info("")

    return category, season_number, episode_number
    
# copy and rename #
def copy_and_rename(filename, category, season_number, episode_number, movies_dir, shows_dir, collections_dir, process_dir, failed_dir, service):
    # Define the source path at the beginning of the function
    src = os.path.join(process_dir, filename)
    
    if category == 'movie' or category == 'show':
        directory = movies_dir if category == 'movie' else shows_dir
        
        # Extract movie/show name and year if available
        name_year_match = re.match(r'(.+)\s\((\d{4})\)', filename, re.IGNORECASE)
        
        if name_year_match:
            # Use strict matching with name and year
            file_name = name_year_match.group(1).strip().lower()
            file_year = name_year_match.group(2)
            
            best_match = None
            
            for dir_name in os.listdir(directory):
                # Check for exact match with year first
                dir_match = re.match(r'(.+)\s\((\d{4})\)', dir_name, re.IGNORECASE)
                if dir_match:
                    dir_title = dir_match.group(1).strip().lower()
                    dir_year = dir_match.group(2)
                    
                    # First try exact match with year
                    if file_name == dir_title and file_year == dir_year:
                        best_match = dir_name
                        break
            
            # If no exact match found, fall back to less strict matching
            if not best_match:
                for dir_name in os.listdir(directory):
                    if file_name in dir_name.lower():
                        best_match = dir_name
                        logger.warning(f" - Using partial match: '{file_name}' -> '{dir_name}'")
                        break
        else:
            # Fall back to simple matching for files without year
            best_match = None
            file_name_simple = filename.split('.')[0].lower()
            
            for dir_name in os.listdir(directory):
                if file_name_simple == dir_name.lower().split('(')[0].strip():
                    best_match = dir_name
                    break
            
            # Last resort - partial match
            if not best_match:
                for dir_name in os.listdir(directory):
                    if file_name_simple in dir_name.lower():
                        best_match = dir_name
                        logger.warning(f" - Using partial match: '{file_name_simple}' -> '{dir_name}'")
                        break
        
        # Process the matched directory
        if best_match:
            dest = os.path.join(directory, best_match, filename)
            shutil.copy(src, dest)
            logger.info(f" {filename}:")
            logger.info(f" - Category: {category.capitalize()}")
            logger.info(f" - Copied to {best_match}")
            
            # Continue with the rest of the function as before...
    elif category == 'collection':
        directory = collections_dir
        for dir_name in os.listdir(directory):
            if filename.split('.')[0].lower().replace("collection", "").strip() in dir_name.lower():
                dest = os.path.join(directory, dir_name, filename)
                shutil.copy(src, dest)
                logger.info(f" {filename}:")
                logger.info(f" - Category: {category.capitalize()}")
                logger.info(f" - Copied to {dir_name}")
                with PIL.Image.open(dest) as img:
                    width, height = img.size
                    new_name = "poster" + os.path.splitext(filename)[1] if height > width else "background" + os.path.splitext(filename)[1]
                    new_dest = os.path.join(directory, dir_name, new_name)
                    os.rename(dest, new_dest)
                    logger.info(f" - Renamed {new_name}")
                    return category
                    
    # Service-specific handling
    elif service == 'kometa':
        if category == 'season':
            directory = shows_dir
            for dir_name in os.listdir(directory):
                if filename.split(')')[0].strip().lower() in dir_name.split(')')[0].strip().lower():
                    dest = os.path.join(directory, dir_name, filename)
                    shutil.copy(src, dest)
                    logger.info(f" {filename}:")
                    logger.info(f" - Category: {category.capitalize()}")
                    logger.info(f" - Copied to {dir_name}")
                    if season_number:
                        new_name = f"Season{season_number.zfill(2)}" + os.path.splitext(filename)[1]
                    else:
                        new_name = "Season00" + os.path.splitext(filename)[1]
                    new_dest = os.path.join(directory, dir_name, new_name)
                    os.rename(dest, new_dest)
                    logger.info(f" - Renamed {new_name}")
                    return category

        elif category == 'episode':
            directory = shows_dir
            # For Kometa, we need to find the show directory by name
            # but prioritize US versions over other country variants
            
            # Extract show name for better matching
            show_match = re.match(r'(.+?)\s*(?:\(|S\d+|$)', filename, re.IGNORECASE)
            if not show_match:
                move_to_failed(filename, process_dir, failed_dir)
                logger.info(f" {filename}:")
                logger.info(" - Category: Episode")
                logger.error(" - Failed to extract show name")
                logger.info(" - Moved to failed directory")
                logger.info("")
                return 'failed'
                
            file_show_name = show_match.group(1).strip().lower()
            matching_dirs = []
            
            # First, collect all potential matching directories
            for dir_name in os.listdir(directory):
                dir_show_name = dir_name.split('(')[0].strip().lower()
                if file_show_name in dir_show_name or dir_show_name in file_show_name:
                    matching_dirs.append(dir_name)
            
            # If no matches found, move to failed
            if not matching_dirs:
                move_to_failed(filename, process_dir, failed_dir)
                logger.info(f" {filename}:")
                logger.info(" - Category: Episode")
                logger.error(" - No matching show directory found")
                logger.info(" - Moved to failed directory")
                logger.info("")
                return 'failed'
            
            # If multiple matches found, prioritize US versions
            best_match = None
            if len(matching_dirs) > 1:
                # Look for US version first
                for match_dir in matching_dirs:
                    if "(US)" in match_dir or "(USA)" in match_dir:
                        best_match = match_dir
                        logger.debug(f" Prioritizing US version for Kometa: '{match_dir}'")
                        break
                        
                # If no US version found, use first match
                if not best_match:
                    best_match = matching_dirs[0]
            else:
                # Only one match found, use it
                best_match = matching_dirs[0]
            
            # Process the best match
            dest = os.path.join(directory, best_match, filename)
            shutil.copy(src, dest)
            logger.info(f" {filename}:")
            logger.info(f" - Category: {category.capitalize()}")
            logger.info(f" - Copied to {best_match}")
            new_name = f"S{season_number.zfill(2)}E{episode_number.zfill(2)}" + os.path.splitext(filename)[1]
            new_dest = os.path.join(directory, best_match, new_name)
            os.rename(dest, new_dest)
            logger.info(f" - Renamed {new_name}")
            return category
                    
    elif service == 'plex':
        if category == 'season':
            directory = shows_dir
            show_dir = None
            matching_dir_name = None
            
            # Find matching show directory first
            for dir_name in os.listdir(directory):
                if filename.split(')')[0].strip().lower() in dir_name.split(')')[0].strip().lower():
                    show_dir = os.path.join(directory, dir_name)
                    matching_dir_name = dir_name
                    break  # Exit loop once match is found
                    
            # Only proceed if a matching directory was found
            if show_dir:
                # Determine season directory name
                if season_number:
                    season_dir_name = f'Season {season_number.zfill(2)}'
                else:
                    if 'Specials' in filename:
                        if plex_specials is None:
                            logger.error(" 'plex_specials' is not set in the config, please set it to True or False and try again")
                            sys.exit(1)
                        elif plex_specials:
                            season_dir_name = 'Specials'
                        else:
                            season_dir_name = 'Season 00'
                
                # Create the season directory if it doesn't exist
                season_dir = os.path.join(show_dir, season_dir_name)
                if not os.path.exists(season_dir):
                    os.makedirs(season_dir)
                    
                # Copy the file
                dest = os.path.join(season_dir, filename)
                shutil.copy(src, dest)
                logger.info(f" {filename}:")
                logger.info(f" - Category: {category.capitalize()}")
                logger.info(f" - Copied to {matching_dir_name}/{season_dir_name}")
                
                # Rename the file
                if season_number:
                    new_name = f"Season{season_number.zfill(2)}" + os.path.splitext(filename)[1]
                else:
                    new_name = "season-specials-poster" + os.path.splitext(filename)[1] 
                new_dest = os.path.join(season_dir, new_name)
                os.rename(dest, new_dest)
                logger.info(f" - Renamed {new_name}")
                return category
            else:
                # No matching directory found, move to failed
                move_to_failed(filename, process_dir, failed_dir)
                logger.info(f" {filename}:")
                logger.info(" - Category: Season")
                logger.error(" - No matching show directory found")
                logger.info(" - Moved to failed directory")
                logger.info("")
                return 'failed'
                
        elif category == 'episode':
            directory = shows_dir
            show_dir = None
            matching_dir_name = None
            
            # First, extract show name from filename
            show_match = re.match(r'(.+?)\s*(?:-|S\d+)', filename, re.IGNORECASE)
            if show_match:
                file_show_name = show_match.group(1).strip()
                logger.debug(f" Looking for show directory matching: '{file_show_name}'")
            else:
                file_show_name = filename.split('.')[0]
                logger.debug(f" Could not parse show name, using: '{file_show_name}'")
            
            # Find matching show directory with improved logic
            best_match = None
            exact_matches = []
            partial_matches = []
            
            # Collect potential matches
            for dir_name in os.listdir(directory):
                # Check for exact title match
                if file_show_name.lower() == dir_name.lower().split('(')[0].strip():
                    exact_matches.append(dir_name)
                # Check for partial match
                elif file_show_name.lower() in dir_name.lower():
                    partial_matches.append(dir_name)
            
            # Prioritize exact matches
            if exact_matches:
                # First try to find US version among exact matches
                for match in exact_matches:
                    if "(US)" in match or "(USA)" in match:
                        best_match = match
                        logger.debug(f" Found US version exact match: '{match}'")
                        break
                        
                # If no US version, use first exact match
                if not best_match and exact_matches:
                    best_match = exact_matches[0]
                    logger.debug(f" Using best exact match: '{best_match}'")
            
            # Fall back to partial matches if needed
            elif partial_matches:
                # Try to find US version among partial matches
                for match in partial_matches:
                    if "(US)" in match or "(USA)" in match:
                        best_match = match
                        logger.debug(f" Found US version partial match: '{match}'")
                        break
                        
                # If no US version, use first partial match
                if not best_match and partial_matches:
                    best_match = partial_matches[0]
                    logger.debug(f" Using best partial match: '{best_match}'")
            
            # Use the best match if found
            if best_match:
                show_dir = os.path.join(directory, best_match)
                matching_dir_name = best_match
                logger.debug(f" Selected show directory: '{matching_dir_name}'")
            else:
                move_to_failed(filename, process_dir, failed_dir)
                logger.info(f" {filename}:")
                logger.info(" - Category: Episode")
                logger.error(" - No matching show directory found")
                logger.info(" - Moved to failed directory")
                logger.info("")
                return 'failed'
            
            # Rest of the existing episode handling logic...
            # Only proceed if a matching directory was found
            if show_dir:
                episode_match = re.match(r'.*S(\d+)[\s\.]?E(\d+)', filename, re.IGNORECASE)
                if episode_match:
                    season_number = episode_match.group(1)
                    episode_number = episode_match.group(2)
                else:
                    move_to_failed(filename, process_dir, failed_dir)
                    logger.info(f" {filename}:")
                    logger.info(" - Category: Episode")
                    logger.error(" - Failed to extract season and episode numbers")
                    logger.info(" - Moved to failed directory")
                    logger.info("")
                    return 'failed'
                    
                season_number = season_number.zfill(2)
                episode_number = episode_number.zfill(2)
                
                if season_number == '00':
                    if plex_specials is None:
                        logger.error(" 'plex_specials' is not set in the config, please set it to True or False and try again")
                        sys.exit(1)
                    elif plex_specials:
                        season_dir_name = 'Specials'
                    else:
                        season_dir_name = 'Season 00'
                else:
                    season_dir_name = f'Season {season_number.zfill(2)}'
                
                season_dir = os.path.join(show_dir, season_dir_name)
                if not os.path.exists(season_dir):
                    move_to_failed(filename, process_dir, failed_dir)                       
                    logger.info(f" {filename}:")
                    logger.info(" - Category: Episode")
                    logger.error(f" - {season_dir_name} does not exist in {matching_dir_name}")
                    logger.info(" - Moved to failed directory")
                    logger.info("")
                    return 'failed'
                
                episode_video_name = None
                for video_file in os.listdir(season_dir):
                    if video_file.endswith(('.mkv', '.mp4', '.avi')):
                        video_match = re.match(r'.*S(\d+)[\s\.]?E(\d+)', video_file, re.IGNORECASE)
                        if video_match:
                            video_season_number = video_match.group(1)
                            video_episode_number = video_match.group(2)
                            if season_number == video_season_number and episode_number == video_episode_number:
                                episode_video_name = os.path.splitext(video_file)[0] + os.path.splitext(filename)[1]
                                break
                
                if episode_video_name:
                    new_name = episode_video_name
                    new_dest = os.path.join(season_dir, new_name)
                    dest = os.path.join(season_dir, filename)
                    shutil.copy(src, dest)
                    os.rename(dest, new_dest)
                    logger.info(f" {filename}:")
                    logger.info(" - Category: Episode")
                    logger.info(f" - Copied to {matching_dir_name}/{season_dir_name}")
                    logger.info(f" - Renamed {new_name}")
                    return category
                else:
                    move_to_failed(filename, process_dir, failed_dir)
                    logger.info(f" {filename}:")
                    logger.info(" - Category: Episode")
                    logger.error(f" - Corresponding video file not found in {matching_dir_name}/{season_dir_name}")
                    logger.info(" - Moved to failed directory")
                    logger.info("")
                    return 'failed'
            else:
                # No matching directory found, move to failed
                move_to_failed(filename, process_dir, failed_dir)
                logger.info(f" {filename}:")
                logger.info(" - Category: Episode")
                logger.error(" - No matching show directory found")
                logger.info(" - Moved to failed directory")
                logger.info("")
                return 'failed'
    else:
        move_to_failed(filename, process_dir, failed_dir)
    
    return category

## move failed assets ##
def move_to_failed(filename, process_dir, failed_dir):
    src = os.path.join(process_dir, filename)
    dest = os.path.join(failed_dir, filename)
    moved_counts['failed'] += 1
    
    try:
        shutil.move(src, dest)
    except FileNotFoundError:
        logger.error(" - File not found during move to failed directory")
    except PermissionError:
        logger.error(" - Permission denied when movingto failed directory")
    except Exception as e:
        logger.error(f" - Failed to move to failed directory: {e}")

## backup assets ##
def backup(filename, process_dir, backup_dir):
    src = os.path.join(process_dir, filename)
    dest = os.path.join(backup_dir, filename)
    
    try:
        shutil.move(src, dest)
        logger.info(f" - Moved '{filename}' to backup directory")
    except FileNotFoundError:
        logger.error(f" - File '{filename}' not found during backup")
    except PermissionError:
        logger.error(f" - Permission denied when backing up '{filename}'")
    except Exception as e:
        logger.error(f" - Failed to backup '{filename}' to backup directory: {e}")

## track assets ##
copied_files = []

moved_counts = {'movie':0, 'show': 0, 'season': 0, 'episode': 0, 'collection': 0, 'failed': 0} 

## processing loop ##           
unzip_files(process_dir)

process_directories(process_dir)

# Add a list of supported image extensions
supported_extensions = ('.jpg', '.jpeg', '.png')

# Get a stable snapshot of files before processing begins
files_to_process = []
for filename in os.listdir(process_dir):
    file_path = os.path.join(process_dir, filename)
    # Only include files (not directories) with supported extensions
    if os.path.isfile(file_path) and filename.lower().endswith(supported_extensions):
        files_to_process.append(filename)
    elif os.path.isfile(file_path):  # Handle non-image files
        logger.info(f" Skipping non-image file: {filename}")
        move_to_failed(filename, process_dir, failed_dir)

logger.info(f" Found {len(files_to_process)} images to process")

# Now process all files in the stable snapshot
for filename in files_to_process:
    if not os.path.exists(os.path.join(process_dir, filename)):
        logger.warning(f" File disappeared during processing: {filename}")
        continue
        
    category, season_number, episode_number = categories(filename, movies_dir, shows_dir)
    if category in ['movie', 'show', 'season', 'episode', 'collection']:
        updated_category = copy_and_rename(filename, category, season_number, episode_number, movies_dir, shows_dir, collections_dir, process_dir, failed_dir, service)
        if updated_category != 'failed':
            if backup_enabled:
                backup(filename, process_dir, backup_dir)
            else:
                try:
                    os.remove(os.path.join(process_dir, filename))
                    logger.info(" - Deleted from process directory")
                except FileNotFoundError:
                    logger.error(" - File not found during deletion")
                except PermissionError:
                    logger.error(" - Permission denied when deleting")
                except Exception as e:
                    logger.error(f" - Failed to delete: {e}")
            logger.info("")
            moved_counts[updated_category] += 1

## end ##
end_time = time.time()
logger.separator(text="Summary", debug=False, border=True)

total_runtime = end_time - start_time
logger.info(f' Movie Assets: {moved_counts["movie"]}')
logger.info(f' Show Assets: {moved_counts["show"]}')
logger.info(f' Season Posters: {moved_counts["season"]}')
logger.info(f' Episode Cards: {moved_counts["episode"]}')
logger.info(f' Collection Assets: {moved_counts["collection"]}')
logger.info(f' Failures: {moved_counts["failed"]}')

current_date = datetime.now()

## notifications ##
summary = generate_summary(moved_counts, backup_enabled, total_runtime, version)

## discord notification ##
discord_webhook = config.get('discord_webhook')
if discord_webhook:
    discord(summary, discord_webhook, version, total_runtime)

## version ##
version_file = os.path.join(os.path.dirname(__file__), 'VERSION')
with open(version_file, 'r') as f:
    version = f.read().strip()

logger.separator(text=f'Asset Assistant Finished\nTotal runtime {total_runtime:.2f} seconds', debug=False, border=True)