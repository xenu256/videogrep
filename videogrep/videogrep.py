from os import listdir, remove
from os.path import abspath, dirname, isfile, splitext #basename
from re import MULTILINE, sub, findall, search
from random import shuffle
import gc
from subprocess import PIPE, PIPE, Popen
from collections import OrderedDict

import pattern
from . import searcher
from audiogrep import convert_to_wav, transcribe, search as audiogrepsearch

from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.concatenate import concatenate

from .timecode import Timecode

usable_extensions = ['mp4', 'avi', 'mov', 'mkv', 'm4v']
BATCH_SIZE = 20


def get_fps(filename):
    process = Popen(['ffmpeg', '-i', filename], stdout=PIPE, stderr=STDOUT)
    returncode = process.wait()
    output = process.stdout.read()
    fps = findall(r'\d+ fps', output, flags=MULTILINE)
    try:
        return int(fps[0].split(' ')[0])
    except:
        return 25


def make_edl_segment(n, time_in, time_out, rec_in, rec_out, full_name, filename, fps=25):
    reel = full_name
    if len(full_name) > 7:
        reel = full_name[0:7]

    template = '{} {} AA/V  C {} {} {} {}\n* FROM CLIP NAME:  {}\n* COMMENT: \n FINAL CUT PRO REEL: {} REPLACED BY: {}\n\n'

    # print time_in, time_out, rec_in, rec_out
    # print Timecode(fps, start_seconds=time_in), Timecode(fps,
    # start_seconds=time_out), Timecode(fps, start_seconds=rec_in),
    # Timecode(fps, start_seconds=rec_out)
    #
    # print ''
    out = template.format(
        n,
        full_name,
        Timecode(fps, start_seconds=time_in),
        Timecode(fps, start_seconds=time_out),
        Timecode(fps, start_seconds=rec_in),
        Timecode(fps, start_seconds=rec_out),
        filename,
        full_name,
        reel
    )

    return out


def make_edl(timestamps, name):
    '''Converts an array of ordered timestamps into an EDL string'''

    fpses = {}

    out = "TITLE: {}\nFCM: NON-DROP FRAME\n\n".format(name)

    rec_in = 0

    for index, time_stamp in enumerate(timestamps):
        if time_stamp['file'] not in fpses:
            fpses[time_stamp['file']] = get_fps(timestamp['file'])

        fps = fpses[time_stamp['file']]

        n = str(index + 1).zfill(4)

        time_in = time_stamp['start']
        time_out = time_stamp['end']
        duration = time_out - time_in

        rec_out = rec_in + duration #timestamp['duration']

        full_name = 'reel_{}'.format(n)
        # full_name = basename(timestamp['file'])

        filename = time_stamp['file']

        out += make_edl_segment(n=n, time_in=time_in, time_out=time_out, rec_in=rec_in, rec_out=rec_out, full_name=full_name, filename=filename, fps=fps)

        rec_in = rec_out

    with open(name, 'w') as outfile:
        outfile.write(out)


def create_timestamps(inputfiles):
    files = convert_to_wav(inputfiles)
    transcribe(files)


def convert_timespan(timespan):
    """Convert an srt timespan into a start and end timestamp."""
    start, end = timespan.split('-->')
    start = convert_timestamp(start)
    end = convert_timestamp(end)
    return start, end


def convert_timestamp(timestamp):
    """Convert an srt timestamp into seconds."""
    timestamp = timestamp.strip()
    chunk, millis = timestamp.split(',')
    hours, minutes, seconds = chunk.split(':')
    hours = int(hours)
    minutes = int(minutes)
    seconds = int(seconds)
    seconds = seconds + hours * 60 * 60 + minutes * 60 + float(millis) / 1000
    return seconds


def clean_srt(srt):
    """Remove damaging line breaks and numbers from srt files and return a
    dictionary.
    """
    with open(srt, 'r') as f:
        text = f.read()
    text = sub(r'^\d+[\n\r]', '', text, flags=MULTILINE)
    lines = text.splitlines()
    output = OrderedDict()
    key = ''

    for line in lines:
        line = line.strip()
        if line.find('-->') > -1:
            key = line
            output[key] = ''
        else:
            if key != '':
                output[key] += line + ' '

    return output


def cleanup_log_files(outputfile):
    """Search for and remove temp log files found in the output directory."""
    d = dirname(abspath(outputfile))
    logfiles = [f for f in listdir(d) if f.endswith('ogg.log')]
    for f in logfiles:
        remove(f)


def demo_supercut(composition, padding):
    """Print out timespans to be cut followed by the line number in the srt."""
    for i, c in enumerate(composition):
        line = c['line']
        start = c['start']
        end = c['end']
        if i > 0 and composition[i - 1]['file'] == c['file'] and start < composition[i - 1]['end']:
            start = start + padding
        print("{1} to {2}:\t{0}".format(line, start, end))


def create_supercut(composition, outputfile, padding):
    """Concatenate video clips together and output finished video file to the
    output directory.
    """
    print ("[+] Creating clips.")
    demo_supercut(composition, padding)

    # add padding when necessary
    for (clip, nextclip) in zip(composition, composition[1:]):
        if ((nextclip['file'] == clip['file']) and (nextclip['start'] < clip['end'])):
            nextclip['start'] += padding

    # put all clips together:
    all_filenames = set([c['file'] for c in composition])
    videofileclips = dict([(f, VideoFileClip(f)) for f in all_filenames])
    cut_clips = [videofileclips[c['file']].subclip(c['start'], c['end']) for c in composition]

    print("[+] Concatenating clips.")
    final_clip = concatenate(cut_clips)

    print("[+] Writing ouput file.")
    final_clip.to_videofile(outputfile, codec="libx264", temp_audiofile='temp-audio.m4a', remove_temp=True, audio_codec='aac')



def create_supercut_in_batches(composition, outputfile, padding):
    """Create & concatenate video clips in groups of size BATCH_SIZE and output
    finished video file to output directory.
    """
    total_clips = len(composition)
    start_index = 0
    end_index = BATCH_SIZE
    batch_comp = []
    while start_index < total_clips:
        filename = outputfile + '.tmp' + str(start_index) + '.mp4'
        try:
            create_supercut(composition[start_index:end_index], filename, padding)
            batch_comp.append(filename)
            gc.collect()
            start_index += BATCH_SIZE
            end_index += BATCH_SIZE
        except:
            start_index += BATCH_SIZE
            end_index += BATCH_SIZE
            next

    clips = [VideoFileClip(filename) for filename in batch_comp]
    video = concatenate(clips)
    video.to_videofile(outputfile, codec="libx264", temp_audiofile='temp-audio.m4a', remove_temp=True, audio_codec='aac')


    # remove partial video files
    for filename in batch_comp:
        remove(filename)

    cleanup_log_files(outputfile)


def search_line(line, search_term, searchtype):
    """Return True if search term is found in given line, False otherwise."""
    if searchtype == 're':
        return search(search_term, line)  #, re.IGNORECASE)
    elif searchtype == 'pos':
        return searcher.search_out(line, search_term)
    elif searchtype == 'hyper':
        return searcher.hypernym_search(line, search_term)


def get_subtitle_files(inputfile):
    """Return a list of subtitle files."""
    srts = []

    for f in inputfile:
        filename = f.split('.')
        filename[-1] = 'srt'
        srt = '.'.join(filename)
        if isfile(srt):
            srts.append(srt)

    if len(srts) == 0:
        print("[!] No subtitle files were found.")

    return srts


def compose_from_srts(srts, search_term, searchtype, padding=0, sync=0):
    """Takes a list of subtitle (srt) filenames, search term and search type
    and, returns a list of timestamps for composing a supercut.
    """
    composition = []
    foundSearchTerm = False

    # Iterate over each subtitles file.
    assert isinstance(srts, list)
    for srt in srts:

        print(srt)
        lines = clean_srt(srt)

        videofile = ""
        foundVideoFile = False

        print("[+] Searching for video file corresponding to '" + srt + "'.")
        for ext in usable_extensions:
            tempVideoFile = srt.replace('.srt', '.' + ext)
            if isfile(tempVideoFile):
                videofile = tempVideoFile
                foundVideoFile = True
                print("[+] Found '" + tempVideoFile + "'.")

        # If a correspndong video file was found for this subtitles file...
        if foundVideoFile:

            # Check that the subtitles file contains subtitles.
            if lines:

                # Iterate over each line in the current subtitles file.
                for timespan in list(lines.keys()):
                    line = lines[timespan].strip()

                    # If this line contains the search term
                    if search_line(line, search_term, searchtype):

                        foundSearchTerm = True

                        # Extract the timespan for this subtitle.
                        start, end = convert_timespan(timespan)

                        # Record this occurance of the search term.
                        composition.append({'file': videofile, 'time': timespan, 'start': start, 'end': end, 'line': line})

                # If the search was unsuccessful.
                if foundSearchTerm is False:
                    print("[!] Search term '" + search_term + "'" + " was not found is subtitle file '" + srt + "'.")

            # If no subtitles were found in the current file.
            else:
                print("[!] Subtitle file '" + srt + "' is empty.")

        # If no video file was found...
        else:
            print("[!] No video file was found which corresponds to subtitle file '" + srt + "'.")
            print("[!] The following video formats are currently supported:")
            extList = ""
            for ext in usable_extensions:
                extList += ext + ", "
            print(extList)

    return composition


def compose_from_transcript(files, search_term, searchtype):
    """Takes transcripts created by audiogrep/pocketsphinx, a search and search type
    and returns a list of timestamps for creating a supercut"""

    final_segments = []

    if searchtype in ['re', 'word', 'franken', 'fragment']:
        if searchtype == 're':
            searchtype = 'sentence'

        segments = audiogrepsearch(search_term, files, mode=searchtype, regex=True)
        for seg in segments:
            seg['file'] = seg['file'].replace('.transcription.txt', '')
            seg['line'] = seg['words']
            final_segments.append(seg)

    elif searchtype in ['hyper', 'pos']:
        for s in audiogrep.convert_timestamps(files):
            for w in s['words']:
                if search_line(w[0], search, searchtype):
                    seg = {
                        'file': s['file'].replace('.transcription.txt',''),
                        'line': w[0],
                        'start': float(w[1]),
                        'end': float(w[2])
                    }
                    final_segments.append(seg)

    return final_segments


def videogrep(inputfile, outputfile, search_term, searchtype, maxclips=0, padding=0, test=False, randomize=False, sync=0, use_transcript=False):
    """Search through and find all instances of the search term in an srt or transcript,
    create a supercut around that instance, and output a new video file
    comprised of those supercuts.
    """

    padding = padding / 1000.0
    sync = sync / 1000.0
    composition = []
    foundSearchTerm = False

    if use_transcript:
        composition = compose_from_transcript(files=inputfile, search_term=search_term, searchtype=searchtype)
    else:
        srts = get_subtitle_files(inputfile)
        composition = compose_from_srts(srts=srts, search_term=search_term, searchtype=searchtype, padding=padding, sync=sync)


    # If the search term was not found in any subtitle file...
    if len(composition) == 0:
        print("[!] Search term '" + search_term + "'" + " was not found in any file.")
        exit(1)

    else:
        print("[+] Search term '" + search_term + "'" + " was found in " + str(len(composition)) + " places.")

        # apply padding and sync
        for c in composition:
            c['start'] = c['start'] + sync - padding
            c['end'] = c['end'] + sync + padding

        if maxclips > 0:
            composition = composition[:maxclips]

        if randomize is True:
            shuffle(composition)

        if test is True:
            demo_supercut(composition=composition, padding=padding)
        else:
            if splitext(outputfile)[1].lower() == '.edl':
                make_edl(timestamps=composition, name=outputfile)
            else:
                if len(composition) > BATCH_SIZE:
                    print("[+} Starting batch job.")
                    create_supercut_in_batches(composition=composition, outputfile=outputfile, padding=padding)
                else:
                    create_supercut(composition=composition, outputfile=outputfile, padding=padding)


def main():
    from argparse import ArgumentParser

    parser = ArgumentParser(description='Generate a "supercut" of one or more video files by searching through subtitle tracks.')
    parser.add_argument('--inputfile', '-i', dest='inputfile', nargs='*', required=True, help='video or subtitle file, or folder')
    parser.add_argument('--search_term', '-s', dest='search_term', help='search term')
    parser.add_argument('--search-type', '-st', dest='searchtype', default='re', choices=['re', 'pos', 'hyper', 'fragment', 'franken', 'word'], help='type of search')
    parser.add_argument('--use-transcript', '-t', action='store_true', dest='use_transcript', help='Use a transcript generated by pocketsphinx instead of srt files')
    parser.add_argument('--max-clips', '-m', dest='maxclips', type=int, default=0, help='maximum number of clips to use for the supercut')
    parser.add_argument('--output', '-o', dest='outputfile', default='supercut.mp4', help='name of output file')
    parser.add_argument('--demo', '-d', action='store_true', help='show results without making the supercut')
    parser.add_argument('--randomize', '-r', action='store_true', help='randomize the clips')
    parser.add_argument('--youtube', '-yt', help='grab clips from youtube based on your search')
    parser.add_argument('--padding', '-p', dest='padding', default=0, type=int, help='padding in milliseconds to add to the start and end of each clip')
    parser.add_argument('--resyncsubs', '-rs', dest='sync', default=0, type=int, help='Subtitle re-synch delay +/- in milliseconds')
    parser.add_argument('--transcribe', '-tr', dest='transcribe', action='store_true', help='Transcribe the video using audiogrep. Requires pocketsphinx')

    args = parser.parse_args()

    if args.search_term is None:
        parser.error('Argument --search_term/-s is required')

    if args.transcribe:
        create_timestamps(args.inputfile)
    else:
        videogrep(args.inputfile, args.outputfile, args.search_term, args.searchtype, args.maxclips, args.padding, args.demo, args.randomize, args.sync, args.use_transcript)


if __name__ == '__main__':
    main()
