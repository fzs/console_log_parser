import logging
import argparse
import json
from os.path import dirname, isabs, splitext, exists, join
from os import makedirs
import sys
from terminal2html import parse as html_parse, HopTarget
from asciinema2html import parse as asciinema_parse, copy_asciinema_files
from twebber import parse as parse_hops

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

LOG = logging.getLogger()


class TodoArgs:
    def __init__(self, args):
        self.infile = args.infile
        self.format = 'terminal'
        self.outfile = args.outfile
        self.palette = args.palette
        self.review_mode = args.review_mode
        self.title = None
        self.chapters = {}
        self.filter = []
        self.hopto = None

class Index:
    HTML_INTRO = """
<!DOCTYPE html>
<html>
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  <meta charset="utf-8"/>
  <title>%(title)s</title>

  <style type="text/css">
    /* *** Text styling *** */

    h1 { color: #D1C3CB; } 
    h2 { color: #e0e0c0; }
    section { color: #e0e0c0; font-family: sans-serif; }

    h2 > a { color: #e0e0c0;  text-decoration: none; }
    h2 > a:hover { color: #FFFFEE; text-decoration: underline; }
    h2 > a:visited { color: #BEBE90;  text-decoration: none; }

    section > a { color: #e0e0c0;  text-decoration: none; }
    section > a:hover { color: #FFFFEE; text-decoration: underline; }
    section > a:visited { color: #BEBE90;  text-decoration: none; }

    .f9 { color: %(cf9)s; }
    .b9 { background-color: %(cb9)s; }
  </style>

  <style type="text/css">
    /* *** Layout *** */
    h1 { text-align: center; }
    h2 { padding-left: 1em; }
    section { padding-left: 4em; }

  </style>
"""

    BODY_INTRO = """
</head>

<body class="f9 b9">

  <h1>%(title)s</h1>
"""

    HTML_OUTRO = """
</body>
</html>
"""

    def __init__(self, title=None, dark_bg=True):
        self.dark_bg = dark_bg
        self.title = title
        self.files = {}

        sdict = {
            'title' : self.title,
            'cf9' : "#f8f8f2",
            'cb9' : "#21222c"
        }


        self.html_intro = (self.HTML_INTRO + self.BODY_INTRO) % sdict
        self.html_body_string = ""
        self.html_outro = self.HTML_OUTRO


    def add_file(self, outfile, title=None):
        if outfile in self.files:
            LOG.error("The file %s already exists in the index, cannot add again.", outfile)
            return

        if not title:
            title = splitext(outfile)

        self.files[outfile] = {'title' : title}

    def add_chapters(self, outfile, chapters):
        if not outfile in self.files:
            self.add_file(outfile)

        self.files[outfile]['chapters'] = chapters

    def build_body(self):
        body_string = self.html_body_string
        for filename in self.files:
            file = self.files[filename]
            body_string += '\n  <h2><a href="' + filename + '">' + file['title'] + '</a></h2>\n'

            if 'chapters' in file:
                chapters = file['chapters']
                for id in chapters:
                    if id:
                        body_string += '    <section><a href="' + filename + '#c' + id + '">' + chapters[id] + '</a></section>\n'
        return body_string


    def get_html_page(self):

        return self.html_intro + self.build_body() + self.html_outro



def parse_to_html(args, logfile, destfile):
    if args.format == 'asciinema':
        asciinema_parse(logfile, destfile, palette=args.palette, title=args.title, chapters=args.chapters, cmd_filter=args.filter, hopto=args.hopto, review=args.review_mode)
        if args.outfile:
            copy_asciinema_files(dirname(args.outfile))

    else:
        html_parse(logfile, destfile, palette=args.palette, title=args.title, chapters=args.chapters, cmd_filter=args.filter, hopto=args.hopto, review=args.review_mode)

def parse_file(args):
    with open(args.infile, 'rb') as logfile:
        LOG.info("Parsing file %s", args.infile)
        if args.outfile:
            if not exists(dirname(args.outfile)):
                makedirs(dirname(args.outfile))
            with open(args.outfile, encoding="utf-8", mode='w') as destfile:
                parse_to_html(args, logfile, destfile)
        else:
            parse_to_html(args, logfile, None)

def parse_file_hops(fromfile, tofile):
    with open(fromfile, 'rb') as leftfile, open(tofile, 'rb') as rightfile:
        LOG.info("Parsing file hops from %s to %s", fromfile, tofile)
        return parse_hops(leftfile, rightfile)

# def join(path, file):
#     """ Redefined join since even under windows we work in a Linux shell """
#     return path + '/' + file

def files_by_id(file_list, dir=''):
    filedict = {}
    for file in file_list:
        if 'id' in file and file['id']:
            if dir:
                filedict[file['id']] = file[dir]
            else:
                filedict[file['id']] = (file['in'], file['out'])

    return filedict


def process_file_list(args, file_list_file):
    with open(file_list_file, 'r', encoding="utf-8") as file_list:
        data = json.load(file_list)

        base_dir_in = dirname(file_list_file)
        if 'base_dir_in' in data and data['base_dir_in']:
            dir = data['base_dir_in']
            if isabs(dir):
                base_dir_in = dir
            else:
                base_dir_in = join(base_dir_in, dir)

        base_dir_out = dirname(file_list_file)
        if 'base_dir_out' in data and data['base_dir_out']:
            dir = data['base_dir_out']
            if isabs(dir):
                base_dir_out = dir
            else:
                base_dir_out = join(base_dir_out, dir)


        if 'title' in data and data['title']:
            index_title = data['title']
        else:
            index_title = "Git Training"

        index = Index(index_title)

        if data['files']:
            files = files_by_id(data['files'])
            for file in data['files']:
                in_file = join(base_dir_in, file['in'])
                if 'out' in file and file['out']:
                    out_file_name = file['out']
                else:
                    base, ext = splitext(file['in'])
                    out_file_name = base + '.html'
                out_file = join(base_dir_out, out_file_name)

                if 'format' in file and file['format']:
                    log_format = file['format']
                    if log_format != 'terminal' and log_format != 'asciinema':
                        print("Unsupported input file format '%s' for file '%s'. Exiting.".format(log_format, file['in']), file=sys.stderr)
                        return
                else:
                    log_format = 'terminal'

                if 'title' in file and file['title']:
                    index.add_file(out_file_name, file['title'])
                else:
                    index.add_file(out_file_name)


                my_args = TodoArgs(args)
                my_args.infile = in_file
                my_args.outfile = out_file
                my_args.format = log_format
                if 'palette' in file and file['palette']:
                    my_args.palette = file['palette']
                if 'title' in file and file['title']:
                    my_args.title = file['title']
                if 'review' in file:
                    my_args.review_mode = file['review']

                if 'id' in file and file['id']:
                    chapters = file['id'] + '-chapters'
                    if chapters in data:
                        index.add_chapters(out_file_name, data[chapters])
                        my_args.chapters = data[chapters]

                    filter = file['id'] + '-suppress'
                    if filter in data:
                        my_args.filter = data[filter]

                    hopto = file['id'] + '-hopto'
                    if hopto in data:
                        my_args.hopto = data[hopto]
                        ofid = data[hopto]['id']
                        tfilterid = ofid + '-suppress'
                        if tfilterid in data:
                            tfilter = data[tfilterid]
                        else:
                            tfilter = tuple()
                        my_args.hopto['target'] = HopTarget(ofid, files[ofid][1], tfilter)
                        print(len(tfilter))

                    if my_args.review_mode and 'ahopto' in file and file['ahopto']:
                        to_file = join(base_dir_in, files[file['ahopto']][0])
                        ahops = parse_file_hops(in_file, to_file)
                        if not my_args.hopto:
                            my_args.hopto = {}
                        my_args.hopto['rev_hops'] = ahops.hops_from_left


                print("Process")
                print(f"    {my_args.infile}")
                print(f" -> {my_args.outfile}")
                print(f" as {my_args.title}")
                print(f" in {my_args.palette}")
                sys.stdout.flush()

                parse_file(my_args)


    print("Generating index file")
    generate_index(base_dir_out, index)


def generate_index(base_dir_out, index : Index):
    index_file = join(base_dir_out, "index.html")
    if not exists(dirname(index_file)):
        makedirs(dirname(index_file))
    with open(index_file, encoding="utf-8", mode='w') as indexfile:
        indexfile.write(index.get_html_page())


def main():
    """
    main.py [<options>] <infile> [<outfile>]
      <infile> logfile to convert
      <outfile> HTML file to write to. Default is standard out.
    """
    argparser = argparse.ArgumentParser(description="Convert a terminal log file into processed output, e.g. HTML")
    argparser.add_argument('infile', help="terminal log input file")
    argparser.add_argument('outfile', nargs='?', help="HTML file to write to. Default is stdout")
    argparser.add_argument('--MyDracula', '--MyDarcula', '--local', dest='palette', action='store_const', const='MyDracula',
                           help="Use color palette MyDracula (default)")
    argparser.add_argument('--Dracula', '--Darcula', '--remote', dest='palette', action='store_const', const='Dracula',
                           help="Use color palette Dracula")
    argparser.add_argument('--TangoDark', dest='palette', action='store_const', const='TangoDark',
                           help="Use color palette Tango Dark")
    argparser.add_argument('--list', '-l', action='store_true', dest='filelist',
                           help="The input file is a JSON todo list with files to convert and their options")
    argparser.add_argument('--review', '-w', action='store_true', dest='review_mode',
                           help="In review mode some hidden elements are shown in the HTML")
    args = argparser.parse_args()

    if args.filelist:
        process_file_list(args, args.infile)
    else:
        args.title = ''
        parse_file(TodoArgs(args))


if __name__ == '__main__':
    LOG_FORMAT = "%(levelname)s :%(module)s - %(message)s"
    logging.basicConfig(filename="parser.log",
                        level=logging.INFO,
                        format=LOG_FORMAT,
                        filemode='w')
    main()
