# Dispense+
This is a simple python script that downloads videos from D1zknee+
I created and tested this in December 2024 to download a themed football game rebroadcast for my dad. I do not remember the extent to which it works. 

When I created this, I remember certain video types didn't work, but I don't remember which or why; I do remember that it would not have been difficult to update this to work for all of them. I just figured that 99% of the content on there could be easily obtained elsewhere in higher quality (this uses an L3 CDM which D+ limits to 720p).

This project started out as a modification of a D+ downloader which I don't know the original repo for (there are dozens of reposts of it on github). I ended up removing almost everything I didn't need. The downloader I used as a base for the auth no longer works because they use encodedFamilyId which used to be in the URL. Now deeplinkId is in the URL. I explain in the codes comments how to obtain encodedFamilyId now. At this point I suspect it may be easy to update the old script using the information in the comments.

The videos are so hard to download because of some custom HLS manifest specification. I'm not sure, but I think it is foreign language credits dub cards that break usual media tools. I get around this by manually traversing the manifest.m3u8. 

## PATH Requirements
1. [python 3.9](https://www.python.org/downloads/release/python-390/)
2. [ffmpeg](https://ffmpeg.org/download.html)
3. [mp4decrypt](https://www.bento4.com/downloads/)
4. [aria2](https://github.com/aria2/aria2)
5. [yt-dlp](https://github.com/yt-dlp/yt-dlp)

## How to use this
1. Acquire a CDM file.wvd file (see below for guide to obtain CDM using an Android Studio emulator)
2. Place the file.wvd file in the same directory as the script.
3. Find the deeplinkId for the content you want
   1. The code after /browse/entity- is the deeplinkId.
   2. For example /browse/entity-0e8ba0c3-47da-44d4-bab5-1c6f5d6e61a0
4. Use the script like this:
    ```    
    dp = DispensePlus(email="", password="")
    print(dp.lookup_video("0e8ba0c3-47da-44d4-bab5-1c6f5d6e61a0"))
    dp.download("0e8ba0c3-47da-44d4-bab5-1c6f5d6e61a0")```

The video I made the script for is a normal video without custom HLS specs. In this case, it may be better to use

```    
dp.download("0e8ba0c3-47da-44d4-bab5-1c6f5d6e61a0", interstitial=False)
```
Almost every video I tested used custom HLS specs that break aria2c/ffmpeg, so I enabled this by default. 


## How to get a CDM file
### Creating a wvd (widevine device file) by extracting keys from an android device.
Here I extract it from android studio emulator using this guide
https://forum.videohelp.com/threads/408031-Dumping-Your-own-L3-CDM-with-Android-Studio/

#### Prerequisites
1. First make sure to check if your PC supports Intel HAXM. If not you may need to use an android phone
2. Enable VT-x and VT-d in BIOS
3. Disable hypervisor on windows

#### Setup the emulator
1. Install android studio
2. Install intel HAXM when android studio asks
3. Create a device 
4. Pixel 6
5. Pie 28 / android 9.0
6. Run the new android device

#### Install python dependencies for everything
```
pip install frida
pip install frida-tools
pip install protobuf
pip install pycryptodome
pip install requests
pip install httpx
pip install pywidevine
```


#### Starting frida server on the emulator
##### Preparation
1. Download frida-server-x.x.x-android-x86.xz https://github.com/frida/frida/releases
2. Make sure it is the same version as the one you installed from pip
3. Extract it (I used peazip) and rename the file to "frida"
4. Move the file you renamed to frida to `C:\Users\yourname\AppData\Local\Android\Sdk\platform-tools`

##### Commands
1. Open CMD and navigate to the same directory
```cd C:\Users\yourname\AppData\Local\Android\Sdk\platform-tools```
2. Check if the android VM is running by running
```adb devices```
3. Now execute these commands to start the frida server on the android device
```
adb push frida /sdcard/
adb shell
su
cp /sdcard/frida /data/local/tmp
chmod +x /data/local/tmp/frida
/data/local/tmp/frida
```

#### Run wvdumper
https://github.com/wvdumper/dumper

```python dump_keys.py```

#### Dump the key files
1. Open Chrome on the android VM and go to any DRM protected video

Your CDM key files will be generated in the key_dumps folder:

`client_id.bin` and `private_key.pem`

The guide recommends renaming them to
`device_client_id_blob` and `device_private_key`


#### Create the device.wvd from the key files:
1. Make a new folder
2. Inside it add the device_client_id_blob and device_private_key files
3. And create a new folder called output
4. Then run this command to create the wvd file in the output folder
```
pywidevine create-device -k device_private_key -c device_client_id_blob -t "ANDROID" -l 3 -o output
```

Rename the file in the output folder to file.wvd and move it to the same folder as dispenseplus.py
Or rename to whatever you like and change the file name in the DispensePlus constructor



