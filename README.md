# SDVX GST Generator
Script that takes contents path and creates tagged songs or videos in output folder.
Requires ffmpeg to be installed and added to PATH. *You will get an error without ffmpeg!*
```
python gst.py -i -o [-ver] [-d] [-b] [-g] [-yt (noshorts)] [-j] [-vb]
```

## Arguments
**-i: Input folder** (REQUIRED) Path to your contents folder. (Ex. ./KFC/contents)

**-o: Output folder** (REQUIRED) Path to your GST folder. (Ex. ./SDVX_GST/)

**-ver: Version** Game version as an integer (Ex. 6 to generate only the Exceed Gear GST)

**-d: After Date** Only get songs added after this date as YYYYMMDD. (Ex. 20240101 for songs added since 2024)

**-b: Before Date** Only get songs added before this date as YYYYMMDD. (Ex. 20240101 for songs added before 2024)

**-g: Genre folders** Seperates songs into folders depending on their in game genre, if a song has multiple genres, it will put it in both. (Defaults false)

**-yt: Video** Create GST as .mp4 video files instead of audio files. Automatically uses the song jacket as the video. Add "noshorts" to put black bars on the sides of the video, preventing them from uploading as YT shorts. (Defaults false)

**-vb: Verbose** Enables verbose ffmpeg output. (Defaults false)

**-j: Jobs** Number of jobs. Dependent on CPU core count. (Speeds up GST generation, Defaults to 2)

## Example usage:
```
python gst.py -i D:\KFC\contents -o D:\KFC\2024_soundtrack -d 20240101 -b 20241231 -g -yt noshorts
```

Will create the soundtrack from data in D:\KFC\contents in D:\KFC\2024_soundtrack, only including songs added in 2024, and sorted into genre folders. The songs will be saved as 16:9 videos.