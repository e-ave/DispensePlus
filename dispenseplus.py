import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid

import m3u8
import requests
from m3u8 import M3U8
from pywidevine import PSSH, Device, Cdm
from mpegdash.parser import MPEGDASHParser as mpd


# TODO support playready
# TODO: Support downloading entire series
# TODO: support dub cards
# TODO: support bumpers
# TODO: language support
# TODO: Load password from config file
# If you want to add more features you'll need to use their many APIs using the encodedFamilyId/encodedSeriesId/seasonId, which is no longer in the URL or anywhere in the webpage.
# Content is now identified in the url and webpage by deeplinkId. /browse/entity-deeplinkId
# In order to use the api that returns the encodedFamilyId/encodedSeriesId/seasonId you dont need the regular contentId, you need the dmcContentId
# to get dmcContentId from deeplink contentId you need to use the deeplinks api like this
# deeplink_api = f"https://disney.api.edge.bamgrid.com/explore/v1.7/deeplink?action=playback&refId=%s&refIdType=deeplinkId" % deeplink_content_id

# to get encoded family id from dmcContentId: https://disney.content.edge.bamgrid.com/svc/content/DmcVideo/version/5.1/region/US/audience/k-false,l-true/maturity/1850/language/en/contentId/cda6f42b-564d-4f50-879d-90ec513eef75
# https://disney.content.edge.bamgrid.com/svc/content/DmcProgramBundle/version/5.1/region/US/audience/k-false,l-true/maturity/1830/language/en/encodedFamilyId/5iC8Hb3jcEoo
# movies use DmcVideoBundle
# https://disney.content.edge.bamgrid.com/svc/content/DmcVideoBundle/version/5.1/region/US/audience/false/maturity/1830/language/en/encodedFamilyId/5iC8Hb3jcEoo
# other stuff uses DmcSeriesBundle
# https://disney.content.edge.bamgrid.com/svc/content/DmcSeriesBundle/version/5.1/region/US/audience/false/maturity/1830/language/en/encodedSeriesId/1xy9TAOQ0M3r
# https://disney.content.edge.bamgrid.com/svc/content/DmcEpisodes/version/5.1/region/US/audience/false/maturity/1850/language/en/seasonId/ad55a8e6-db54-45a5-aadd-0aa5db9dd9c1/pageSize/30/page/1

class DispensePlus:
    def __init__(self, email, password, proxies=None, wvdfile='./file.wvd'):
        self.wvdfile = wvdfile
        self.email = email
        self.password = password
        self.web_page = 'https://www.disneyplus.com/login'
        self.devices_url = "https://global.edge.bamgrid.com/devices"
        self.login_url = 'https://global.edge.bamgrid.com/idp/login'
        self.token_url = "https://global.edge.bamgrid.com/token"
        self.grant_url = 'https://global.edge.bamgrid.com/accounts/grant'
        self.session = requests.Session()
        if proxies:
            self.session.proxies.update(proxies)

    def _get_client_api_key(self):
        response = self.session.get(self.web_page)

        match = re.search(r'"clientApiKey":"([^"]+)"', response.text)
        json_data = match.group(1)
        print(json_data)
        return json_data

    def _get_assertion(self, client_api_key):
        headers = {"Authorization": f"Bearer {client_api_key}", "Origin": "https://www.disneyplus.com"}
        post_data = {
            "applicationRuntime": "firefox",
            "attributes": {},
            "deviceFamily": "browser",
            "deviceProfile": "macosx"
        }
        response = self.session.post(url=self.devices_url, headers=headers, json=post_data)
        return response.json()["assertion"]

    def _get_access_token(self, client_api_key, assertion):
        headers = {"Authorization": f"Bearer {client_api_key}", "Origin": "https://www.disneyplus.com"}
        post_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "latitude": "0",
            "longitude": "0",
            "platform": "browser",
            "subject_token": assertion,
            "subject_token_type": "urn:bamtech:params:oauth:token-type:device"
        }
        response = self.session.post(url=self.token_url, headers=headers, data=post_data)

        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            self._handle_error(response)

    def _handle_error(self, response):
        try:
            error_message = response.json().get("errors", {}).get('error_description', response.text)
        except json.JSONDecodeError:
            error_message = response.text
        print(f'Error: {error_message}')
        exit()

    def get_license_headers(self, extra_headers=None):
        headers = {
            "accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
            "Sec-Fetch-Mode": "cors",
            "x-bamsdk-platform": "windows",
            "x-bamsdk-version": '31.0',
            "authorization": f'Bearer {self.get_auth_token()[0]}'
        }
        if extra_headers: headers |= extra_headers
        return headers

    def _login(self, access_token):
        headers = self._get_headers(access_token)
        data = {'email': self.email, 'password': self.password}
        response = self.session.post(url=self.login_url, data=json.dumps(data), headers=headers)

        if response.status_code == 200:
            print(response.json())
            return response.json()["id_token"]
        else:
            self._handle_error(response)

    def _get_headers(self, access_token):
        return {
            'Accept': 'application/json; charset=utf-8',
            'Authorization': f"Bearer {access_token}",
            'Content-Type': 'application/json; charset=UTF-8',
            'Origin': 'https://www.disneyplus.com',
            'Referer': 'https://www.disneyplus.com/login/password',
            'Sec-Fetch-Mode': 'cors',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.132 Safari/537.36',
            'X-Bamsdk-Platform': 'windows',
            'X-Bamsdk-Version': '31.0',
        }

    def _grant(self, id_token, access_token):
        headers = self._get_headers(access_token)
        data = {'id_token': id_token}
        response = self.session.post(url=self.grant_url, data=json.dumps(data), headers=headers)
        return response.json()["assertion"]

    def _get_final_token(self, subject_token, client_api_key):
        headers = {"Authorization": f"Bearer {client_api_key}", "Origin": "https://www.disneyplus.com"}
        post_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "latitude": "0",
            "longitude": "0",
            "platform": "browser",
            "subject_token": subject_token,
            "subject_token_type": "urn:bamtech:params:oauth:token-type:account"
        }
        response = self.session.post(url=self.token_url, headers=headers, data=post_data)

        if response.status_code == 200:
            token_data = response.json()
            return token_data["access_token"], token_data["expires_in"]
        else:
            self._handle_error(response)

    def get_auth_token(self):
        client_api_key = self._get_client_api_key()
        assertion = self._get_assertion(client_api_key)
        access_token = self._get_access_token(client_api_key, assertion)
        id_token = self._login(access_token)
        user_assertion = self._grant(id_token, access_token)
        final_token, expires_in = self._get_final_token(user_assertion, client_api_key)
        return final_token, expires_in

    def get_playback_headers(self):
        playback_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Accept': 'application/vnd.media-service+json',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.disneyplus.com/',
            'authorization': self.get_auth_token()[0],
            'content-type': 'application/json',
            'x-dss-feature-filtering': 'true',
            'x-application-version': '1.1.2',
            'x-bamsdk-client-id': 'disney-svod-3d9324fc',
            'x-bamsdk-platform': 'javascript/macosx/firefox',
            'x-bamsdk-version': '31.0',
            'x-dss-edge-accept': 'vnd.dss.edge+json; version=2',
            'Origin': 'https://www.disneyplus.com',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        }
        return playback_headers

    def lookup_video(self, content_id):
        playback_id = self.get_playback_id(content_id)
        json_data = {
            'playback': {
                'attributes': {
                    'resolution': {'max': ['1280x720']},  # max res supported seems to be 720 without L1
                    'protocol': 'HTTPS',
                    # 'assetInsertionStrategy': 'SGAI',
                    'assetInsertionStrategies': {
                        'point': 'SGAI',
                        'range': 'SGAI'
                    },
                    'playbackInitiationContext': 'ONLINE',
                    'frameRates': [30],
                    # 'slugDuration': 'SLUG_500_MS',
                },
                'adTracking': {
                    'limitAdTrackingEnabled': 'YES',
                    'deviceAdId': '00000000-0000-0000-0000-000000000000',
                },
                'tracking': {
                    'playbackSessionId': str(uuid.uuid4()),
                },
            },
            'playbackId': playback_id,
        }

        r = requests.post(url="https://disney.playback.edge.bamgrid.com/v7/playback/ctr-regular",
                          json=json_data, headers=self.get_playback_headers())
        if r.status_code == 200:
            data = r.json()
            print(data)
            sources = data["stream"]["sources"]
            print(sources)
            return sources
        else:
            print("Error " + str(r.status_code) + " loading playback request")
            return None

    def get_playback_id(self, content_id):
        for action in self.get_disney_playback_info(content_id):
            if "resourceId" in action:
                return action["resourceId"]
        return None

    def get_playback_title(self, content_id):
        for action in self.get_disney_playback_info(content_id):
            if "internalTitle" in action:
                int_title = action["internalTitle"].split(" - ")
                return int_title[0] + "." + int_title[1]
        return "Unknown"


    def get_disney_playback_info(self, content_id):
        # Some videos: Deeplink -> resourceId(playbackID)
        # other videos: Deeplink -> pageId -> page request -> resourceId(playbackID)
        # or actually does action=playback make it have the resourceId?

        deeplink_api = f"https://disney.api.edge.bamgrid.com/explore/v1.7/deeplink?action=playback&refId=%s&refIdType=deeplinkId" % content_id
        r = requests.get(deeplink_api, headers=self.get_playback_headers())
        if r.status_code == 200:
            data = r.json()
            print(data)
            actions = data["data"]["deeplink"]["actions"]
            print(actions)
            return actions
        else:
            print("Error " + str(r.status_code) + " loading playback request")
            return None

    def request_decryption_keys(self, ipssh):
        pssh = PSSH(ipssh)
        device = Device.load(self.wvdfile)
        cdm = Cdm.from_device(device)
        session_id = cdm.open()
        challenge = cdm.get_license_challenge(session_id, pssh)
        licence = requests.post("https://disney.playback.edge.bamgrid.com/widevine/v1/obtain-license",
                                data=challenge, headers=self.get_license_headers())
        licence.raise_for_status()
        cdm.parse_license(session_id, licence.content)
        fkeys = ""
        for key in cdm.get_keys(session_id):
            if key.type != 'SIGNING':
                fkeys += key.kid.hex + ":" + key.key.hex() + "\n"
        print("Keys:")
        print(fkeys)
        cdm.close(session_id)
        return fkeys

    def download(self, content_id, interstitial=True, subtitles=True):
        sources = self.lookup_video(content_id)
        title = self.get_playback_title(content_id)
        for source in sources:
            if source["priority"] == 1:
                # m3u8_link_sliding = source["slide"]["url"]
                m3u8_link = source["complete"]["url"]

                pssh = parse_widevine_pssh(m3u8_link)
                decr_key = self.request_decryption_keys(pssh)

                temp_dir = tempfile.TemporaryDirectory()
                working_dir = temp_dir.name

                if interstitial:
                    self.download_interstitial_video(m3u8_link, working_dir)

                    start_process(["mp4decrypt", "--key", decr_key, "file.mp4", "decrypted_video.mp4"], working_dir)
                    decrypted_output = title + (".temp.mp4" if subtitles else ".mp4")
                    start_process(["ffmpeg", "-y", "-i", "decrypted_video.mp4", "-i", "file.m4a", "-c", "copy", decrypted_output], working_dir)

                    if subtitles:
                        self.download_subs(m3u8_link, title + ".temp.mp4", working_dir)

                else:
                    download_video_normal(url=m3u8_link, key=decr_key, filename=title + ".mp4", working_dir=working_dir)

                temp_dir.cleanup()

    def download_subs(self, url, video_file, working_dir):
        # download all subtitle files
        start_process(
            ["yt-dlp", "--all-subs", "--convert-subs", "srt", "--skip-download", "-o", "subtitles.%(ext)s", url],
            working_dir)

        # get a dictionary of subtitle language code to language name from the m3u8
        sub_names = find_subtitle_names(url)

        subtitle_files = [f for f in os.listdir(working_dir) if f.startswith("subtitles")]

        # create an ffmpeg command to add all of the subtitles into the video
        command = ['ffmpeg', '-i', video_file]
        for subtitle_file in subtitle_files:
            command.extend(['-i', subtitle_file])

        command.extend(['-c:v', 'copy', '-c:a', 'copy'])
        # add metadata so the subtitles have names
        for i, subtitle_file in enumerate(subtitle_files):
            lang_code = subtitle_file.split('.')[1]
            command.extend(['-map', '0', '-map', str(i + 1), '-c:s', 'mov_text'])
            meta = '-metadata:s:s:' + str(i)
            name = sub_names[lang_code]
            command.extend([meta, 'language=' + lang_code, meta, 'handler_name=' + name, meta, 'title=' + name])
        # add the output file name
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_file = script_dir + "/" + video_file.replace(".temp", "")
        command.append(output_file)

        start_process(command, working_dir)

        # cleanup temp files
        # for sub_file in subtitle_files:
        #     os.remove('f%s/%s' % (working_dir, sub_file))
        # os.remove('f%s/%s' % (working_dir, video_file))

    def download_interstitial_video(self, manifest_url, working_dir):
        """
        Downloads videos that use interstitials with EXT-X-DISCONTINUITY and EXT-X-DATETIME, which
         are a custom implementation of apple or disney HLS and not supported by ffmpeg or aria2c.
         I think the interstitials are used for dub cards for videos with foreign languages.

        :param manifest_url:
        :param working_dir:
        :return:
        """
        baseurl = manifest_url.rsplit('/', 1)[0] + '/'
        manifest = requests.get(manifest_url).text
        index = M3U8(manifest)
        max_bandwidth_playlist = max(index.playlists, key=lambda p: p.stream_info.bandwidth)
        video_link = baseurl + max_bandwidth_playlist.uri

        audio_link = baseurl + best_audio(index, 'en').uri
        print(max_bandwidth_playlist)
        self.download_segments(baseurl, video_link, working_dir)
        self.download_segments(baseurl, audio_link, working_dir, audio=True)
        print()

    def download_segments(self, baseurl, media_link, working_dir, audio=False):
        ext = "m4a" if audio else "mp4"
        playlist = requests.get(media_link).text

        print(playlist)
        dict_m3u8 = M3U8(playlist)
        media_segment = dict_m3u8.segments
        segments = []
        frags_path = []
        for seg_map in dict_m3u8.segment_map:
            if 'MAIN' in seg_map.uri:
                segments.append(baseurl + 'r/' + seg_map.uri)
        for seg in media_segment:
            if 'MAIN' in seg.uri:
                segments.append(baseurl + 'r/' + seg.uri)
        segments = list(dict.fromkeys(segments))  # Remove duplicates
        txturls = f'%s/links.txt' % working_dir
        print(txturls)
        txt = open(txturls, "w+")
        for i, s in enumerate(segments):
            name = "0" + str(i) + '.' + ext
            frags_path.append(working_dir + "/" + name)
            txt.write(s + f"\n out={name}\n")
        txt.close()
        aria2c_command = [
            "aria2c",
            f'--input-file=links.txt',
            '-x16',
            '-j16',
            '-s16',
            '--summary-interval=0',
            '--retry-wait=3',
            '--max-tries=10',
            '--enable-color=false',
            '--download-result=hide',
            '--console-log-level=error'
        ]
        subprocess.run(aria2c_command, cwd=working_dir)
        openfile = open(f"%s/file.%s" % (working_dir, ext), "wb")
        for run_num, fragment in enumerate(frags_path):
            if os.path.isfile(fragment):
                shutil.copyfileobj(open(fragment, "rb"), openfile)
            #os.remove(fragment)
        openfile.close()
        #os.remove(txturls)

        print('Download and concatenation complete!')


def parse_widevine_pssh(url):
    """
    Parses the Widevine PSSH from an mpd or m3u8 manifest

    :param url: The url of your index.mpd/index.m3u8
    :return: An extracted Widevine PSSH
    """
    widevine_pssh = None
    if ".m3u8" in url:
        manifest = m3u8.load(url)
        print()
        for key in manifest.session_keys:
            if key is not None and key.keyformat == "urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed":
                widevine_pssh = key.uri
        if widevine_pssh is not None:
            widevine_pssh = widevine_pssh.partition('base64,')[2]
    else:  # .mpd
        manifest = mpd.parse(url)
        for period in manifest.periods:
            for adaptation_set in period.adaptation_sets:
                for prot in adaptation_set.content_protections:
                    if prot.scheme_id_uri == "urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed":
                        widevine_pssh = prot.pssh
                        if len(prot.pssh) >= 1:  # TODO multiple keys
                            widevine_pssh = prot.pssh[0].pssh
    return widevine_pssh


def start_process(command, directory):
    print(directory, " ".join(command))
    process = subprocess.Popen(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.communicate()

    if process.returncode != 0:
        print(f"Failure to decrypt: {command[0]} exited with non-zero return code ({process.returncode})")
        stderr = process.stderr.read().decode()
        print(stderr)
        exit(1)
    else:
        print("Process completed successfully.")


def download_video_normal(url, key, filename, working_dir, verify=False, subtitles=True):
    """
    I do not know when this can be used, but i suspect it is either when a video lacks foreign language dubs,
    or it is a video replay.
    This was my original code used to download a replay of a sports game that was only in english
    :param url:
    :param key:
    :param filename:
    :param verify:
    :return:
    """

    print("Downloading Encrypted Audio/Video Files")

    # It fails to download audio if we try to download both at once because the audio extension is mp4 instead of m4a.
    # Downloading separately is easier than messing with the filename template...
    # Even then, in my test it downloaded 64k instead of 128k audio.
    external_downloader = "aria2c"  # "ffmpeg"
    start_process(["yt-dlp", "-o", "file.m4a", "--allow-u", "--external-downloader", external_downloader, "-f",
                   "ba[language=en]", url], working_dir)
    if subtitles: # TODO find video to test this on
        start_process(
            ["yt-dlp", "--all-subs", "-o", "file.mp4", "--allow-u", "--external-downloader", external_downloader, "-f",
             "bv", url], working_dir)
    else:
        start_process(["yt-dlp", "-o", "file.mp4", "--allow-u", "--external-downloader", external_downloader, "-f",
                   "bv", url], working_dir)

    # print("Decrypting Audio")
    # start_process(["mp4decrypt", "--key", key, "file.m4a", "decrypted_audio.m4a"], working_dir)

    # if verify:
    #     print("Verifying Audio")
    #     start_process(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of",
    #                    "default=noprint_wrappers=1:nokey=1", "decrypted_audio.m4a"], working_dir)

    print("Decrypting Video")
    start_process(["mp4decrypt", "--key", key, "file.mp4", "decrypted_video.mp4"], working_dir)

    if verify:
        print("Verifying Video")
        start_process(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of",
                       "default=noprint_wrappers=1:nokey=1", "decrypted_video.mp4"], working_dir)

    print("Combining Decrypted Video & Audio")
    start_process(
        ["ffmpeg", "-y", "-i", "decrypted_video.mp4", "-i", "file.m4a", "-c", "copy", filename],
        working_dir)

    print(url)


def combine_vtt_segments(vtt_strings):
    """
    Not needed with ffmpeg
    """
    timestamp_pattern = re.compile(r'\d{2}:\d{2}:\d{2}\.\d{3}')
    combined_vtt = ""

    for i, vtt_string in enumerate(vtt_strings):
        found_timestamp = False
        lines = vtt_string.splitlines()
        for line in lines:
            if i == 0:  # Keep the header on the first vtt file
                combined_vtt += line + "\n"
            else:
                if not found_timestamp and timestamp_pattern.match(line):
                    found_timestamp = True

                if found_timestamp:
                    combined_vtt += line + "\n"

        combined_vtt += "\n"

    return combined_vtt


def find_subtitle_names(playlist_m3u8_url):
    playlist_m3u8 = M3U8(requests.get(playlist_m3u8_url).text)
    subtitles = []
    for media in playlist_m3u8.media:
        if media.type == 'SUBTITLES':
            subtitles.append((media.language, media.name))
    return dict(subtitles)


def search_subtitles(playlist_m3u8, language, captions=False, easyreader=False):
    subtitles = []
    for media in playlist_m3u8.media:
        if media.type == 'SUBTITLES' and media.language == language:
            if not captions and "public.accessibility.describes-music-and-sound" in str(media.characteristics):
                continue
            if not easyreader and "public.easy-to-read" in str(media.characteristics):
                continue
            if "public.accessibility.transcribes-spoken-dialog" in str(media.characteristics):
                subtitles.append(media)
    return subtitles


def best_audio(playlist_m3u8, language):
    preferred_audio = None
    for media in playlist_m3u8.media:
        if media.type == 'AUDIO' and media.language == language:
            if media.group_id == 'eac-3':
                return media
            elif 'aac' in media.group_id:
                bitrate = int(media.group_id.split('-')[1].replace('k', ''))
                if preferred_audio is None or bitrate > int(preferred_audio.group_id.split('-')[1].replace('k', '')):
                    preferred_audio = media
    return preferred_audio


if __name__ == "__main__":
    dp = DispensePlus(email="", password="")
    print(dp.lookup_video("0e8ba0c3-47da-44d4-bab5-1c6f5d6e61a0"))
    dp.download("0e8ba0c3-47da-44d4-bab5-1c6f5d6e61a0")
