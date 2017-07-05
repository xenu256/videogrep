import sys
from os.path import isfile, isdir
from re import sub

from nltk import pos_tag


inputfile = sys.argv[1]
srts = []
text = ''
if isfile(inputfile):
    filename = inputfile.split('.')
    filename[-1] = 'srt'
    srts = ['.'.join(filename)]

elif isdir(inputfile):
    if inputfile.endswith('/') == False:
        inputfile += '/'
    srts = [inputfile + f for f in os.listdir(inputfile) if f.lower().endswith('srt')]
    assert len(srts) > 0

for srt in srts:
    f = open(srt, 'rb')
    for line in f:
        if line.find('-->') == -1:
            text += line
    f.close()

text = sub(r'^\d+[\n\r]', '', text, flags=re.MULTILINE)
tags = pos_tag(text)
pos = [t[1] for t in tags]
ngrams = {}
n = int(sys.argv[2])

for i in range(len(pos) - n + 1):
    gram = tuple(pos[i:i+n])
    if gram in ngrams:
        ngrams[gram] += 1
    else:
        ngrams[gram] = 1

for ngram in sorted(ngrams, key=ngrams.get, reverse=True):
    count = ngrams[ngram]
    if count > 4:
        print(' '.join(ngram) + ": " + str(count))
