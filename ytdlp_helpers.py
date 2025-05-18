import re
import subprocess

# These are functions that I was using at one point but didn't need. They may be useful again later

def get_format_info_raw(url):
    try:
        process = subprocess.Popen(['yt-dlp', '--allow-u', '-F', url], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            print(f"Error: {stderr}")
            return None
        print(stdout)
        return stdout

    except Exception as err:
        print(f"An error occurred: {err}")
        return None

def parse_ytdlp_formats(format_info):
    formats = []
    lines = format_info.strip().split('\n')
    for line in lines:
        if line.startswith('ID'):
            continue
        match = re.match(
            r'([a-zA-z0-9\-]+|\d+)\s+(\w+)\s+(\d+x\d+|\w+ *\w*)?\s*(\d+)?\s*\|\s*~?\s*?([\d.]+(GiB|MiB))?\s*(\d+k)?\s*(\w+)?\s*\|\s*((?:\w+ \w*)|(?:\w+\.\w*))\s*(\d+k)?\s*(\w+ *\w*)?\s*(.*)',
            line)
        if match:
            format_dict = {
                'ID': match.group(1),
                'Extension': match.group(2),
                'Resolution': match.group(3),
                'FPS': match.group(4),
                'FileSize': match.group(5),
                'TBR': match.group(7),
                'Protocol': match.group(8),
                'VideoCodec': match.group(9),
                'VBR': match.group(10),
                'AudioCodec': match.group(11),
                'MoreInfo': match.group(12)
            }
            formats.append(format_dict)
    return formats


def get_format_info(url):
    format_info = get_format_info_raw(url)
    if format_info:
        parsed_formats = parse_ytdlp_formats(format_info)
        return parsed_formats
    return None


def get_best_audio_format(url):
    """
    Gets the first audio format returned from `yt-dlp -F url`
    TODO: make sure this is always the best
    """
    parsed_formats = get_format_info(url)
    print(parsed_formats)
    for fmt in parsed_formats:
        # return the first option
        if fmt['Resolution'] == 'audio only':
            return fmt['ID'], fmt['Extension']

    return None, None